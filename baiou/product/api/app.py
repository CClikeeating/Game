from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from baiou.common.io import PROJECT_ROOT, load_data, resolve_path
from baiou.product.runtime.reply_engine import MODE_BAILIAN_RAG_FAST, MODE_BAILIAN_RAG_QUALITY, normalize_mode, run_reply
from baiou.product.storage import ProductStore

CONFIG_ROOT = PROJECT_ROOT / "baiou" / "config" / "product"

DEFAULT_CONFIG: dict[str, Any] = {
    "server": {"host": "127.0.0.1", "port": 7871, "debug": False},
    "storage": {"sqlite_path": "outputs/baiou/product/app.db"},
    "upload": {
        "root": "outputs/baiou/product/miniprogram/uploads",
        "allowed_image_extensions": [".png", ".jpg", ".jpeg", ".webp"],
        "max_image_mb": 8,
    },
    "limits": {
        "max_conversations_per_user": 5,
        "history_turns_for_reply": 6,
        "daily_reply_quota": 20,
        "max_images_per_reply": 3,
        "min_images_per_reply": 1,
        "max_image_mb": 8,
    },
    "runtime": {
        "default_mode": MODE_BAILIAN_RAG_FAST,
        "modes": {MODE_BAILIAN_RAG_FAST: "快速模式", MODE_BAILIAN_RAG_QUALITY: "质量模式"},
    },
    "auth": {"default_user_id": "dev_user", "dev_login_enabled": True},
    "announcements": [],
    "billing": {"products": []},
}


def create_app(config: dict[str, Any] | None = None, store: ProductStore | None = None) -> Flask:
    config = config or load_api_config()
    store = store or ProductStore(config["sqlite_path"])
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = int(config["max_images_per_reply"]) * int(config["max_image_bytes"]) + 1024 * 1024

    @app.get("/api/v1/health")
    def health():
        return ok(
            {
                "status": "ok",
                "default_mode": config["default_mode"],
                "modes": config["modes"],
                "limits": public_limits(config),
            }
        )

    @app.post("/api/v1/auth/login")
    def login():
        payload = request.get_json(silent=True) or {}
        user_id = requested_user_id(config, payload)
        user = store.ensure_user(user_id, str(payload.get("openid", "")), str(payload.get("nickname", "")))
        return ok({"token": user["user_id"], "user": public_user(user), "limits": usage_payload(store, config, user["user_id"])})

    @app.get("/api/v1/me")
    def me():
        user_id = current_user_id(config)
        user = store.ensure_user(user_id)
        return ok({"user": public_user(user), "limits": usage_payload(store, config, user_id)})

    @app.get("/api/v1/conversations")
    def conversations_index():
        user_id = current_user_id(config)
        store.ensure_user(user_id)
        return ok({"conversations": [public_conversation(item) for item in store.list_conversations(user_id)]})

    @app.post("/api/v1/conversations")
    def conversations_create():
        user_id = current_user_id(config)
        store.ensure_user(user_id)
        if store.active_conversation_count(user_id) >= int(config["max_conversations_per_user"]):
            return fail("conversation_limit_reached", f"最多可创建 {config['max_conversations_per_user']} 个聊天窗口。", 429)
        payload = request.get_json(silent=True) or {}
        item = store.create_conversation(user_id, str(payload.get("title", "") or "新的聊天"), str(payload.get("background", "")))
        return ok({"conversation": public_conversation(item)}, 201)

    @app.patch("/api/v1/conversations/<conversation_id>")
    def conversations_update(conversation_id: str):
        user_id = current_user_id(config)
        payload = request.get_json(silent=True) or {}
        item = store.update_conversation(
            user_id,
            conversation_id,
            str(payload["title"]) if "title" in payload else None,
            str(payload["background"]) if "background" in payload else None,
        )
        if not item:
            return fail("conversation_not_found", "聊天窗口不存在。", 404)
        return ok({"conversation": public_conversation(item)})

    @app.delete("/api/v1/conversations/<conversation_id>")
    def conversations_delete(conversation_id: str):
        user_id = current_user_id(config)
        if not store.archive_conversation(user_id, conversation_id):
            return fail("conversation_not_found", "聊天窗口不存在。", 404)
        store.ensure_default_conversation(user_id)
        return ok({"deleted": True})

    @app.post("/api/v1/replies")
    def replies_create():
        user_id = current_user_id(config)
        store.ensure_user(user_id)
        form = request.form if request.form else request.get_json(silent=True) or {}
        conversation_id = str(form.get("conversation_id", "")).strip()
        conversation = store.get_conversation(user_id, conversation_id)
        if not conversation or conversation.get("status") != "active":
            return fail("conversation_not_found", "聊天窗口不存在。", 404)
        question = str(form.get("question", "")).strip()
        if not question:
            return fail("question_required", "请输入要回复的内容。", 400)
        dry_run = parse_bool(form.get("dry_run"))
        used = store.usage_today(user_id)
        if not dry_run and used >= int(config["daily_reply_quota"]):
            return fail("daily_quota_exhausted", "今日回复次数已用完。", 429, {"remaining_quota": 0})
        mode = normalize_api_mode(str(form.get("mode", "") or config["default_mode"]), config)
        files = request.files.getlist("images") if request.files else []
        validation_error = validate_images(files, config)
        if validation_error:
            code, message = validation_error
            return fail(code, message, 400)
        upload_ids = parse_upload_ids(form.get("upload_ids", []))
        staged_uploads = store.get_uploads(user_id, upload_ids)
        if len(staged_uploads) != len(upload_ids):
            return fail("upload_not_found", "截图上传记录不存在或已经使用。", 404)
        if len(files) + len(staged_uploads) > int(config["max_images_per_reply"]):
            return fail("too_many_images", f"一次最多上传 {config['max_images_per_reply']} 张截图。", 400)
        if len(files) + len(staged_uploads) < int(config["min_images_per_reply"]):
            return fail("image_required", "请上传聊天截图。", 400)
        user_context = str(form.get("context", "")).strip()
        history = store.recent_reply_runs(user_id, conversation_id, int(config["history_turns_for_reply"]))
        runtime_context = build_runtime_context(conversation, history, user_context)
        image_count = len(files) + len(staged_uploads)
        run_record = store.create_reply_run(user_id, conversation_id, mode, question, user_context, runtime_context, image_count)
        image_paths = [Path(item["path"]) for item in staged_uploads]
        image_paths.extend(save_images(files, resolve_path(config["upload_root"]) / run_record["run_id"], config))
        try:
            result = run_reply(
                question=question,
                context=runtime_context,
                images=[str(path) for path in image_paths],
                batch_id=f"miniprogram_{run_record['run_id']}",
                dry_run=dry_run,
                mode=mode,
            )
            saved = store.update_reply_run(user_id, run_record["run_id"], result) or run_record
            store.mark_uploads_consumed(user_id, upload_ids)
            if not dry_run:
                used = store.increment_usage(user_id)
        except Exception as exc:  # noqa: BLE001
            saved = store.fail_reply_run(user_id, run_record["run_id"], f"{exc.__class__.__name__}: {exc}") or run_record
        return ok({"reply_run": public_reply_run(saved, config), "limits": usage_payload(store, config, user_id)})

    @app.post("/api/v1/uploads")
    def uploads_create():
        user_id = current_user_id(config)
        store.ensure_user(user_id)
        files = request.files.getlist("images") or request.files.getlist("file")
        validation_error = validate_images(files, {**config, "max_images_per_reply": 1})
        if validation_error:
            code, message = validation_error
            return fail(code, message, 400)
        if not files:
            return fail("image_required", "请上传截图。", 400)
        target_dir = resolve_path(config["upload_root"]) / "staged" / uuid.uuid4().hex[:12]
        paths = save_images([files[0]], target_dir, config)
        upload = store.add_upload(user_id, files[0].filename or "image.jpg", paths[0], paths[0].stat().st_size)
        return ok({"upload": public_upload(upload)}, 201)

    @app.post("/api/v1/feedback")
    def feedback_create():
        user_id = current_user_id(config)
        payload = request.get_json(silent=True) or {}
        rating = str(payload.get("rating", "")).strip()
        if rating not in {"good", "ok", "bad", "有用", "一般", "不合适"}:
            return fail("rating_invalid", "反馈只能是 good/ok/bad。", 400)
        item = store.add_feedback(
            user_id,
            str(payload.get("conversation_id", "")),
            str(payload.get("run_id", "")),
            rating,
            str(payload.get("notes", "")),
        )
        if not item:
            return fail("feedback_target_not_found", "反馈对应的回复不存在。", 404)
        return ok({"feedback": public_feedback(item)}, 201)

    @app.get("/api/v1/announcements")
    def announcements_index():
        stored = store.list_announcements()
        configured = [item for item in config.get("announcements", []) if item.get("status", "active") == "active"]
        return ok({"announcements": [public_announcement(item) for item in (stored or configured)]})

    @app.get("/api/v1/billing/products")
    def billing_products():
        return ok({"products": config.get("billing_products", []), "payment_enabled": False})

    @app.post("/api/v1/billing/orders")
    def billing_orders():
        return fail("payment_not_enabled", "第一期暂未接入真实支付。", 501)

    return app


def load_api_config(path: str | Path | None = None) -> dict[str, Any]:
    raw = json.loads(json.dumps(DEFAULT_CONFIG))
    config_path = resolve_path(path or os.environ.get("BAIOU_MINIPROGRAM_CONFIG") or CONFIG_ROOT / "miniprogram.json")
    if config_path.exists():
        loaded = load_data(config_path)
        if isinstance(loaded, dict):
            deep_update(raw, loaded)
    server = raw.get("server", {})
    storage = raw.get("storage", {})
    upload = raw.get("upload", {})
    limits = raw.get("limits", {})
    runtime = raw.get("runtime", {})
    auth = raw.get("auth", {})
    max_image_mb = int(os.environ.get("BAIOU_MINIPROGRAM_MAX_IMAGE_MB") or limits.get("max_image_mb") or upload.get("max_image_mb", 8))
    return {
        "host": os.environ.get("BAIOU_MINIPROGRAM_HOST") or server.get("host", "127.0.0.1"),
        "port": int(os.environ.get("BAIOU_MINIPROGRAM_PORT") or server.get("port", 7871)),
        "debug": parse_bool(os.environ.get("BAIOU_MINIPROGRAM_DEBUG"), bool(server.get("debug", False))),
        "sqlite_path": os.environ.get("BAIOU_MINIPROGRAM_DB") or storage.get("sqlite_path", "outputs/baiou/product/app.db"),
        "upload_root": os.environ.get("BAIOU_MINIPROGRAM_UPLOAD_ROOT") or upload.get("root", "outputs/baiou/product/miniprogram/uploads"),
        "allowed_image_extensions": {normalize_extension(item) for item in upload.get("allowed_image_extensions", [])},
        "max_conversations_per_user": int(limits.get("max_conversations_per_user", 5)),
        "history_turns_for_reply": int(limits.get("history_turns_for_reply", 6)),
        "daily_reply_quota": int(limits.get("daily_reply_quota", 20)),
        "max_images_per_reply": int(limits.get("max_images_per_reply", 3)),
        "min_images_per_reply": int(limits.get("min_images_per_reply", 1)),
        "max_image_mb": max_image_mb,
        "max_image_bytes": max_image_mb * 1024 * 1024,
        "default_mode": os.environ.get("BAIOU_REPLY_MODE") or runtime.get("default_mode", MODE_BAILIAN_RAG_FAST),
        "modes": runtime.get("modes", DEFAULT_CONFIG["runtime"]["modes"]),
        "default_user_id": os.environ.get("BAIOU_MINIPROGRAM_DEFAULT_USER_ID") or auth.get("default_user_id", "dev_user"),
        "dev_login_enabled": parse_bool(os.environ.get("BAIOU_MINIPROGRAM_DEV_LOGIN"), bool(auth.get("dev_login_enabled", True))),
        "announcements": raw.get("announcements", []),
        "billing_products": raw.get("billing", {}).get("products", []) if isinstance(raw.get("billing"), dict) else [],
    }


def deep_update(base: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_update(base[key], value)
        else:
            base[key] = value


def ok(payload: dict[str, Any], status: int = 200):
    body = {"ok": True}
    body.update(payload)
    return jsonify(body), status


def fail(code: str, message: str, status: int, extra: dict[str, Any] | None = None):
    body = {"ok": False, "error": {"code": code, "message": message}}
    if extra:
        body.update(extra)
    return jsonify(body), status


def requested_user_id(config: dict[str, Any], payload: dict[str, Any]) -> str:
    user_id = str(payload.get("user_id") or payload.get("openid") or "").strip()
    if user_id:
        return user_id
    return str(config.get("default_user_id", "dev_user"))


def current_user_id(config: dict[str, Any]) -> str:
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return token
    header = request.headers.get("X-Baiou-User-Id", "").strip()
    return header or str(config.get("default_user_id", "dev_user"))


def normalize_api_mode(value: str, config: dict[str, Any]) -> str:
    mode = normalize_mode(value)
    return mode if mode in config["modes"] else normalize_mode(config["default_mode"])


def build_runtime_context(conversation: dict[str, Any], history: list[dict[str, Any]], user_context: str) -> str:
    parts = []
    background = str(conversation.get("background", "")).strip()
    if background:
        parts.extend(["当前聊天窗口背景：", background])
    if history:
        lines = []
        for item in history:
            answer = item.get("answer", {}) if isinstance(item.get("answer", {}), dict) else {}
            reply = str(answer.get("reply", "")).strip()
            lines.append(f"- 用户：{item.get('question', '')}")
            if reply:
                lines.append(f"  AI建议：{reply}")
        parts.extend(["当前聊天窗口最近历史：", "\n".join(lines)])
    if user_context.strip():
        parts.extend(["本次补充背景：", user_context.strip()])
    return "\n\n".join(parts)


def validate_images(files: list[FileStorage], config: dict[str, Any]) -> tuple[str, str] | None:
    files = [item for item in files if item and item.filename]
    if len(files) > int(config["max_images_per_reply"]):
        return "too_many_images", f"一次最多上传 {config['max_images_per_reply']} 张截图。"
    for file in files:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in config["allowed_image_extensions"]:
            return "image_type_not_allowed", "仅支持 png、jpg、jpeg、webp 图片。"
        pos = file.stream.tell()
        file.stream.seek(0, os.SEEK_END)
        size = file.stream.tell()
        file.stream.seek(pos)
        if size > int(config["max_image_bytes"]):
            return "image_too_large", f"单张图片最大 {config['max_image_mb']}MB。"
    return None


def parse_upload_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, tuple):
        raw = list(value)
    else:
        text = str(value or "").strip()
        if not text:
            return []
        try:
            loaded = json.loads(text)
            raw = loaded if isinstance(loaded, list) else [text]
        except json.JSONDecodeError:
            raw = text.replace(";", ",").split(",")
    return [str(item).strip() for item in raw if str(item).strip()]


def save_images(files: list[FileStorage], upload_dir: Path, config: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for index, file in enumerate(files, start=1):
        if not file or not file.filename:
            continue
        filename = secure_filename(file.filename) or f"image_{index}.jpg"
        target = unique_path(upload_dir / filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        file.save(target)
        paths.append(target)
    return paths


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{path.stem}_{uuid.uuid4().hex[:8]}{path.suffix}")


def usage_payload(store: ProductStore, config: dict[str, Any], user_id: str) -> dict[str, Any]:
    used = store.usage_today(user_id)
    quota = int(config["daily_reply_quota"])
    return {**public_limits(config), "daily_reply_used": used, "daily_reply_remaining": max(0, quota - used)}


def public_limits(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "max_conversations_per_user": config["max_conversations_per_user"],
        "history_turns_for_reply": config["history_turns_for_reply"],
        "daily_reply_quota": config["daily_reply_quota"],
        "max_images_per_reply": config["max_images_per_reply"],
        "min_images_per_reply": config["min_images_per_reply"],
        "max_image_mb": config["max_image_mb"],
    }


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {"user_id": user.get("user_id", ""), "nickname": user.get("nickname", ""), "plan": user.get("plan", "trial")}


def public_conversation(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "conversation_id": item.get("conversation_id", ""),
        "title": item.get("title", ""),
        "background": item.get("background", ""),
        "status": item.get("status", ""),
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
    }


def public_reply_run(item: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    answer = item.get("answer", {}) if isinstance(item.get("answer", {}), dict) else {}
    return {
        "run_id": item.get("run_id", ""),
        "conversation_id": item.get("conversation_id", ""),
        "mode": item.get("mode", ""),
        "display_mode": config["modes"].get(item.get("mode", ""), item.get("mode", "")),
        "status": item.get("status", ""),
        "answer": {
            "reply": answer.get("reply", ""),
            "coach_analysis": answer.get("coach_analysis", ""),
            "risk_warning": answer.get("risk_warning", ""),
            "next_step": answer.get("next_step", ""),
            "labels": answer.get("labels", {}),
            "reference_segments": answer.get("reference_segments", []),
        },
        "image_understanding": item.get("image_understanding", ""),
        "reference_segments": compact_references(item.get("reference_segments", [])),
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
    }


def compact_references(items: Any) -> list[dict[str, Any]]:
    refs = items if isinstance(items, list) else []
    output = []
    for item in refs[:5]:
        if not isinstance(item, dict):
            continue
        output.append(
            {
                "segment_id": item.get("segment_id", ""),
                "filename": item.get("filename", ""),
                "score": item.get("score", ""),
                "text": item.get("text", ""),
                "match_reasons": item.get("match_reasons", []),
                "labels": item.get("labels", {}),
            }
        )
    return output


def public_feedback(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "feedback_id": item.get("feedback_id", ""),
        "conversation_id": item.get("conversation_id", ""),
        "run_id": item.get("run_id", ""),
        "rating": item.get("rating", ""),
        "notes": item.get("notes", ""),
        "created_at": item.get("created_at", ""),
    }


def public_upload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "upload_id": item.get("upload_id", ""),
        "original_name": item.get("original_name", ""),
        "size_bytes": item.get("size_bytes", 0),
        "created_at": item.get("created_at", ""),
    }


def public_announcement(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "announcement_id": item.get("announcement_id", ""),
        "title": item.get("title", ""),
        "content": item.get("content", ""),
        "status": item.get("status", "active"),
    }


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_extension(value: Any) -> str:
    suffix = str(value or "").lower().strip()
    return suffix if suffix.startswith(".") else f".{suffix}" if suffix else ""
