from __future__ import annotations

import hashlib
import json
import os
import uuid
from csv import DictWriter
from io import StringIO
from pathlib import Path
from typing import Any
from urllib import parse, request as urlrequest

from flask import Flask, Response, jsonify, request
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
    "auth": {"default_user_id": "dev_user", "dev_login_enabled": True, "session_days": 30, "wechat_appid": "", "wechat_secret": ""},
    "admin": {"token": ""},
    "retention": {"upload_days": 30, "run_days": 30},
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
        code = str(payload.get("code", "")).strip()
        if code:
            session, error = wechat_code_to_session(config, code)
            if error:
                return fail(error, "微信登录失败，请稍后重试。", 401)
            openid = str(session.get("openid", "")).strip()
            if not openid:
                return fail("wechat_openid_missing", "微信登录失败，请稍后重试。", 401)
            user_id = wechat_user_id(openid)
            user = store.ensure_user(user_id, openid, str(payload.get("nickname", "")))
        elif config["dev_login_enabled"]:
            user_id = requested_user_id(config, payload)
            user = store.ensure_user(user_id, str(payload.get("openid", "")), str(payload.get("nickname", "")))
        else:
            return fail("login_code_required", "请先完成微信登录。", 401)
        token = store.create_session(user["user_id"], int(config.get("session_days", 30)))
        return ok({"token": token, "user": public_user(user), "limits": usage_payload(store, config, user["user_id"])})

    @app.get("/api/v1/me")
    def me():
        user_id = current_user_id(config, store)
        if not user_id:
            return fail("auth_required", "请先登录。", 401)
        user = store.ensure_user(user_id)
        return ok({"user": public_user(user), "limits": usage_payload(store, config, user_id)})

    @app.get("/api/v1/conversations")
    def conversations_index():
        user_id = current_user_id(config, store)
        if not user_id:
            return fail("auth_required", "请先登录。", 401)
        store.ensure_user(user_id)
        return ok({"conversations": [public_conversation(item) for item in store.list_conversations(user_id)]})

    @app.post("/api/v1/conversations")
    def conversations_create():
        user_id = current_user_id(config, store)
        if not user_id:
            return fail("auth_required", "请先登录。", 401)
        store.ensure_user(user_id)
        if store.active_conversation_count(user_id) >= int(config["max_conversations_per_user"]):
            return fail("conversation_limit_reached", f"最多可创建 {config['max_conversations_per_user']} 个聊天窗口。", 429)
        payload = request.get_json(silent=True) or {}
        item = store.create_conversation(user_id, str(payload.get("title", "") or "新的聊天"), str(payload.get("background", "")))
        return ok({"conversation": public_conversation(item)}, 201)

    @app.patch("/api/v1/conversations/<conversation_id>")
    def conversations_update(conversation_id: str):
        user_id = current_user_id(config, store)
        if not user_id:
            return fail("auth_required", "请先登录。", 401)
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
        user_id = current_user_id(config, store)
        if not user_id:
            return fail("auth_required", "请先登录。", 401)
        if not store.archive_conversation(user_id, conversation_id):
            return fail("conversation_not_found", "聊天窗口不存在。", 404)
        store.ensure_default_conversation(user_id)
        return ok({"deleted": True})

    @app.post("/api/v1/replies")
    def replies_create():
        user_id = current_user_id(config, store)
        if not user_id:
            return fail("auth_required", "请先登录。", 401)
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
        user_id = current_user_id(config, store)
        if not user_id:
            return fail("auth_required", "请先登录。", 401)
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
        user_id = current_user_id(config, store)
        if not user_id:
            return fail("auth_required", "请先登录。", 401)
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

    @app.get("/api/v1/admin/stats")
    def admin_stats():
        auth_error = require_admin(config)
        if auth_error:
            return auth_error
        return ok({"stats": store.admin_stats()})

    @app.get("/api/v1/admin/feedback")
    def admin_feedback():
        auth_error = require_admin(config)
        if auth_error:
            return auth_error
        limit = bounded_int(request.args.get("limit"), 50, 1, 500)
        return ok({"feedback": [public_feedback_detail(item) for item in store.list_feedback_detail(limit)]})

    @app.get("/api/v1/admin/config")
    def admin_config_get():
        auth_error = require_admin(config)
        if auth_error:
            return auth_error
        return ok({"config": public_admin_config(config)})

    @app.post("/api/v1/admin/config")
    def admin_config_save():
        auth_error = require_admin(config)
        if auth_error:
            return auth_error
        payload = request.get_json(silent=True) or {}
        saved = save_admin_config(config, payload)
        apply_admin_config(config, clean_admin_config_payload(payload, config))
        return ok({"config": public_admin_config(config), "saved": saved})

    @app.get("/api/v1/admin/feedback/export.csv")
    def admin_feedback_export():
        auth_error = require_admin(config)
        if auth_error:
            return auth_error
        limit = bounded_int(request.args.get("limit"), 1000, 1, 10000)
        rows = [feedback_export_row(item) for item in store.feedback_export_rows(limit)]
        handle = StringIO()
        fieldnames = [
            "created_at",
            "user_id",
            "conversation_id",
            "run_id",
            "mode",
            "status",
            "rating",
            "notes",
            "question",
            "reply",
            "risk_warning",
            "image_count",
            "reference_count",
        ]
        writer = DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return Response(
            "\ufeff" + handle.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=baiou_feedback.csv"},
        )

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

    @app.get("/admin")
    def admin_page():
        return Response(admin_page_html(), mimetype="text/html; charset=utf-8")

    return app


def load_api_config(path: str | Path | None = None) -> dict[str, Any]:
    raw = json.loads(json.dumps(DEFAULT_CONFIG))
    config_path = resolve_path(path or os.environ.get("BAIOU_MINIPROGRAM_CONFIG") or CONFIG_ROOT / "miniprogram.json")
    if config_path.exists():
        loaded = load_data(config_path)
        if isinstance(loaded, dict):
            deep_update(raw, loaded)
    admin_config_path = resolve_path(os.environ.get("BAIOU_ADMIN_CONFIG") or raw.get("admin", {}).get("config_path", "outputs/baiou/product/admin_config.json"))
    if admin_config_path.exists():
        loaded_admin_config = load_data(admin_config_path)
        if isinstance(loaded_admin_config, dict):
            deep_update(raw, loaded_admin_config)
    server = raw.get("server", {})
    storage = raw.get("storage", {})
    upload = raw.get("upload", {})
    limits = raw.get("limits", {})
    runtime = raw.get("runtime", {})
    auth = raw.get("auth", {})
    admin = raw.get("admin", {}) if isinstance(raw.get("admin"), dict) else {}
    retention = raw.get("retention", {}) if isinstance(raw.get("retention"), dict) else {}
    rag = raw.get("rag", {}) if isinstance(raw.get("rag"), dict) else {}
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
        "session_days": int(os.environ.get("BAIOU_SESSION_DAYS") or auth.get("session_days", 30)),
        "wechat_appid": os.environ.get("BAIOU_WECHAT_APPID") or auth.get("wechat_appid", ""),
        "wechat_secret": os.environ.get("BAIOU_WECHAT_SECRET") or auth.get("wechat_secret", ""),
        "admin_token": os.environ.get("BAIOU_ADMIN_TOKEN") or admin.get("token", ""),
        "admin_config_path": str(admin_config_path),
        "upload_retention_days": int(os.environ.get("BAIOU_UPLOAD_RETENTION_DAYS") or retention.get("upload_days", 30)),
        "run_retention_days": int(os.environ.get("BAIOU_RUN_RETENTION_DAYS") or retention.get("run_days", 30)),
        "vector_store_ids": configured_list(rag.get("vector_store_ids") or os.environ.get("BAIOU_VECTOR_STORE_IDS") or "n7s0ou2dpt"),
        "rag_max_num_results": bounded_int(rag.get("max_num_results") or os.environ.get("BAIOU_RAG_MAX_NUM_RESULTS"), 3, 1, 10),
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


def current_user_id(config: dict[str, Any], store: ProductStore) -> str:
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            user_id = store.user_id_for_session(token)
            if user_id:
                return user_id
            if config.get("dev_login_enabled"):
                return token
    header = request.headers.get("X-Baiou-User-Id", "").strip()
    if header and config.get("dev_login_enabled"):
        return header
    return str(config.get("default_user_id", "dev_user")) if config.get("dev_login_enabled") else ""


def wechat_code_to_session(config: dict[str, Any], code: str) -> tuple[dict[str, Any], str]:
    appid = str(config.get("wechat_appid", "")).strip()
    secret = str(config.get("wechat_secret", "")).strip()
    if not appid or not secret:
        return {}, "wechat_config_missing"
    query = parse.urlencode({"appid": appid, "secret": secret, "js_code": code, "grant_type": "authorization_code"})
    url = f"https://api.weixin.qq.com/sns/jscode2session?{query}"
    try:
        with urlrequest.urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return {}, "wechat_request_failed"
    if int(payload.get("errcode", 0) or 0) != 0:
        return {}, f"wechat_error_{payload.get('errcode')}"
    return payload, ""


def wechat_user_id(openid: str) -> str:
    return "wx_" + hashlib.sha256(openid.encode("utf-8")).hexdigest()[:24]


def require_admin(config: dict[str, Any]):
    token = str(config.get("admin_token", "")).strip()
    if not token:
        return fail("admin_not_configured", "管理员 token 未配置。", 503)
    auth = request.headers.get("Authorization", "").strip()
    provided = auth[7:].strip() if auth.lower().startswith("bearer ") else request.headers.get("X-Baiou-Admin-Token", "").strip()
    if not provided:
        provided = request.args.get("token", "").strip()
    if provided != token:
        return fail("admin_unauthorized", "没有后台访问权限。", 401)
    return None


def public_admin_config(config: dict[str, Any]) -> dict[str, Any]:
    announcement = first_announcement(config)
    return {
        "runtime": {
            "default_mode": config.get("default_mode", MODE_BAILIAN_RAG_FAST),
            "modes": config.get("modes", {}),
        },
        "rag": {
            "vector_store_ids": config.get("vector_store_ids", []),
            "max_num_results": config.get("rag_max_num_results", 3),
        },
        "limits": {
            "daily_reply_quota": config.get("daily_reply_quota", 20),
            "max_conversations_per_user": config.get("max_conversations_per_user", 5),
            "history_turns_for_reply": config.get("history_turns_for_reply", 6),
            "max_images_per_reply": config.get("max_images_per_reply", 3),
            "min_images_per_reply": config.get("min_images_per_reply", 1),
            "max_image_mb": config.get("max_image_mb", 8),
        },
        "retention": {
            "upload_days": config.get("upload_retention_days", 30),
            "run_days": config.get("run_retention_days", 30),
        },
        "announcement": {
            "title": announcement.get("title", ""),
            "content": announcement.get("content", ""),
            "status": announcement.get("status", "active"),
        },
        "secrets": {
            "dashscope_api_key": bool(os.environ.get("DASHSCOPE_API_KEY")),
            "deepseek_api_key": bool(os.environ.get("DEEPSEEK_API_KEY")),
            "wechat_appid": bool(config.get("wechat_appid")),
            "wechat_secret": bool(config.get("wechat_secret")),
            "admin_token": bool(config.get("admin_token")),
        },
        "paths": {
            "admin_config_path": config.get("admin_config_path", ""),
            "sqlite_path": config.get("sqlite_path", ""),
            "upload_root": config.get("upload_root", ""),
        },
        "auth": {
            "dev_login_enabled": bool(config.get("dev_login_enabled")),
            "session_days": config.get("session_days", 30),
        },
    }


def save_admin_config(config: dict[str, Any], payload: dict[str, Any]) -> str:
    cleaned = clean_admin_config_payload(payload, config)
    path = resolve_path(config.get("admin_config_path") or "outputs/baiou/product/admin_config.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def clean_admin_config_payload(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    runtime = payload.get("runtime", {}) if isinstance(payload.get("runtime"), dict) else {}
    rag = payload.get("rag", {}) if isinstance(payload.get("rag"), dict) else {}
    limits = payload.get("limits", {}) if isinstance(payload.get("limits"), dict) else {}
    retention = payload.get("retention", {}) if isinstance(payload.get("retention"), dict) else {}
    announcement = payload.get("announcement", {}) if isinstance(payload.get("announcement"), dict) else {}
    mode = normalize_api_mode(str(runtime.get("default_mode") or config.get("default_mode")), config)
    return {
        "runtime": {"default_mode": mode},
        "rag": {
            "vector_store_ids": configured_list(rag.get("vector_store_ids") or config.get("vector_store_ids", [])),
            "max_num_results": bounded_int(rag.get("max_num_results"), int(config.get("rag_max_num_results", 3)), 1, 10),
        },
        "limits": {
            "daily_reply_quota": bounded_int(limits.get("daily_reply_quota"), int(config.get("daily_reply_quota", 20)), 1, 10000),
            "max_conversations_per_user": bounded_int(limits.get("max_conversations_per_user"), int(config.get("max_conversations_per_user", 5)), 1, 100),
            "history_turns_for_reply": bounded_int(limits.get("history_turns_for_reply"), int(config.get("history_turns_for_reply", 6)), 0, 50),
            "max_images_per_reply": bounded_int(limits.get("max_images_per_reply"), int(config.get("max_images_per_reply", 3)), 1, 10),
            "min_images_per_reply": bounded_int(limits.get("min_images_per_reply"), int(config.get("min_images_per_reply", 1)), 0, 10),
            "max_image_mb": bounded_int(limits.get("max_image_mb"), int(config.get("max_image_mb", 8)), 1, 50),
        },
        "retention": {
            "upload_days": bounded_int(retention.get("upload_days"), int(config.get("upload_retention_days", 30)), 1, 365),
            "run_days": bounded_int(retention.get("run_days"), int(config.get("run_retention_days", 30)), 1, 365),
        },
        "announcements": [
            {
                "announcement_id": "admin_notice",
                "title": str(announcement.get("title", "")).strip()[:80],
                "content": str(announcement.get("content", "")).strip()[:500],
                "status": "active" if str(announcement.get("status", "active")).strip() != "inactive" else "inactive",
            }
        ],
    }


def apply_admin_config(config: dict[str, Any], cleaned: dict[str, Any]) -> None:
    runtime = cleaned.get("runtime", {})
    rag = cleaned.get("rag", {})
    limits = cleaned.get("limits", {})
    retention = cleaned.get("retention", {})
    config["default_mode"] = runtime.get("default_mode", config.get("default_mode", MODE_BAILIAN_RAG_FAST))
    config["vector_store_ids"] = configured_list(rag.get("vector_store_ids") or config.get("vector_store_ids", []))
    config["rag_max_num_results"] = bounded_int(rag.get("max_num_results"), int(config.get("rag_max_num_results", 3)), 1, 10)
    for key in [
        "daily_reply_quota",
        "max_conversations_per_user",
        "history_turns_for_reply",
        "max_images_per_reply",
        "min_images_per_reply",
        "max_image_mb",
    ]:
        if key in limits:
            config[key] = limits[key]
    config["max_image_bytes"] = int(config.get("max_image_mb", 8)) * 1024 * 1024
    config["upload_retention_days"] = retention.get("upload_days", config.get("upload_retention_days", 30))
    config["run_retention_days"] = retention.get("run_days", config.get("run_retention_days", 30))
    if isinstance(cleaned.get("announcements"), list):
        config["announcements"] = cleaned["announcements"]


def first_announcement(config: dict[str, Any]) -> dict[str, Any]:
    items = config.get("announcements", [])
    if isinstance(items, list) and items:
        first = items[0]
        return first if isinstance(first, dict) else {}
    return {}


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


def public_feedback_detail(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "feedback_id": item.get("feedback_id", ""),
        "user_id": item.get("user_id", ""),
        "conversation_id": item.get("conversation_id", ""),
        "run_id": item.get("run_id", ""),
        "mode": item.get("mode", ""),
        "status": item.get("status", ""),
        "rating": item.get("rating", ""),
        "notes": item.get("notes", ""),
        "question": item.get("question", ""),
        "reply": item.get("reply", ""),
        "risk_warning": item.get("risk_warning", ""),
        "image_count": item.get("image_count", 0),
        "reference_count": item.get("reference_count", 0),
        "created_at": item.get("created_at", ""),
    }


def feedback_export_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "created_at": item.get("created_at", ""),
        "user_id": item.get("user_id", ""),
        "conversation_id": item.get("conversation_id", ""),
        "run_id": item.get("run_id", ""),
        "mode": item.get("mode", ""),
        "status": item.get("status", ""),
        "rating": item.get("rating", ""),
        "notes": item.get("notes", ""),
        "question": item.get("question", ""),
        "reply": item.get("reply", ""),
        "risk_warning": item.get("risk_warning", ""),
        "image_count": item.get("image_count", 0),
        "reference_count": item.get("reference_count", 0),
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


def admin_page_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Baiou Admin</title>
  <style>
    :root {
      --bg: #f5f7f8;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #667085;
      --line: #dfe6ef;
      --accent: #176b5d;
      --warn: #9a4b18;
      --soft: #eef6f3;
      --shadow: 0 18px 48px rgba(30, 41, 59, 0.08);
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--ink); }
    main { max-width: 1180px; margin: 0 auto; padding: 28px 18px 48px; }
    header { display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; margin-bottom: 18px; }
    h1 { margin: 0; font-size: 30px; letter-spacing: 0; }
    h2 { margin: 0 0 14px; font-size: 18px; }
    p { margin: 6px 0 0; color: var(--muted); line-height: 1.55; }
    .grid { display: grid; grid-template-columns: 0.95fr 1.35fr; gap: 16px; align-items: start; }
    .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); padding: 18px; }
    .metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
    .metric { border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fbfcfd; }
    .metric b { display: block; font-size: 22px; margin-bottom: 2px; }
    .metric span, label span { color: var(--muted); font-size: 13px; }
    form { display: grid; gap: 14px; }
    .fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    label { display: grid; gap: 6px; font-weight: 700; font-size: 14px; }
    input, select, textarea { width: 100%; border: 1px solid var(--line); border-radius: 7px; padding: 10px 11px; font: inherit; color: var(--ink); background: #fff; }
    textarea { min-height: 86px; resize: vertical; }
    .full { grid-column: 1 / -1; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
    button, a.button { border: 0; border-radius: 7px; padding: 10px 14px; background: var(--accent); color: #fff; font-weight: 800; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; }
    button.secondary, a.secondary { background: #eef1f5; color: var(--ink); }
    .status { min-height: 22px; color: var(--muted); font-size: 13px; }
    .secret-list { display: grid; gap: 8px; margin-top: 10px; }
    .secret { display: flex; justify-content: space-between; border-bottom: 1px solid #edf1f5; padding: 8px 0; }
    .tag { border-radius: 999px; padding: 3px 8px; background: #f1f5f9; color: var(--muted); font-size: 12px; }
    .tag.ok { background: var(--soft); color: var(--accent); }
    .tag.warn { background: #fff7ed; color: var(--warn); }
    .feedback { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; border-bottom: 1px solid #edf1f5; padding: 9px 6px; vertical-align: top; }
    th { color: var(--muted); font-weight: 800; }
    @media (max-width: 860px) {
      header, .grid { display: block; }
      header .actions { margin-top: 14px; }
      .panel { margin-bottom: 14px; }
      .fields, .metrics { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Baiou 运维面板</h1>
        <p>查看运行状态，调整常用产品配置。密钥只显示配置状态，不回显明文。</p>
      </div>
      <div class="actions">
        <input id="token" type="password" placeholder="管理员 token" autocomplete="current-password">
        <button id="load" type="button">进入</button>
      </div>
    </header>
    <section class="grid">
      <div class="panel">
        <h2>运行状态</h2>
        <div id="metrics" class="metrics"></div>
        <div class="secret-list" id="secrets"></div>
        <div class="actions" style="margin-top:14px">
          <a class="button secondary" href="/api/v1/admin/feedback/export.csv" id="export">导出反馈 CSV</a>
        </div>
      </div>
      <div class="panel">
        <h2>产品配置</h2>
        <form id="configForm">
          <div class="fields">
            <label>默认模式
              <select name="default_mode">
                <option value="bailian_rag_fast">百炼快速模式</option>
                <option value="bailian_rag_quality">百炼质量模式</option>
              </select>
            </label>
            <label>百炼知识库 ID
              <input name="vector_store_ids" placeholder="n7s0ou2dpt">
            </label>
            <label>RAG 召回数量
              <input name="rag_max_num_results" type="number" min="1" max="10">
            </label>
            <label>每日额度
              <input name="daily_reply_quota" type="number" min="1">
            </label>
            <label>最大会话数
              <input name="max_conversations_per_user" type="number" min="1">
            </label>
            <label>回复参考历史轮数
              <input name="history_turns_for_reply" type="number" min="0">
            </label>
            <label>每次最大图片数
              <input name="max_images_per_reply" type="number" min="1" max="10">
            </label>
            <label>最少图片数
              <input name="min_images_per_reply" type="number" min="0" max="10">
            </label>
            <label>单图大小 MB
              <input name="max_image_mb" type="number" min="1" max="50">
            </label>
            <label>截图保留天数
              <input name="upload_days" type="number" min="1" max="365">
            </label>
            <label>运行明细保留天数
              <input name="run_days" type="number" min="1" max="365">
            </label>
            <label>公告状态
              <select name="announcement_status">
                <option value="active">显示</option>
                <option value="inactive">隐藏</option>
              </select>
            </label>
            <label class="full">公告标题
              <input name="announcement_title">
            </label>
            <label class="full">公告内容
              <textarea name="announcement_content"></textarea>
            </label>
          </div>
          <div class="actions">
            <button type="submit">保存配置</button>
            <button class="secondary" type="button" id="reload">刷新</button>
            <span class="status" id="status"></span>
          </div>
        </form>
      </div>
    </section>
    <section class="panel feedback">
      <h2>最近反馈</h2>
      <table>
        <thead><tr><th>时间</th><th>评分</th><th>备注</th><th>问题</th><th>回复</th></tr></thead>
        <tbody id="feedback"></tbody>
      </table>
    </section>
  </main>
  <script>
    const tokenInput = document.querySelector("#token");
    const statusEl = document.querySelector("#status");
    const form = document.querySelector("#configForm");
    tokenInput.value = localStorage.getItem("baiou_admin_token") || "";

    function headers() {
      return { "Content-Type": "application/json", "Authorization": "Bearer " + tokenInput.value.trim() };
    }
    async function api(path, options = {}) {
      const res = await fetch(path, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
      const contentType = res.headers.get("content-type") || "";
      const data = contentType.includes("application/json") ? await res.json() : await res.text();
      if (!res.ok || data.ok === false) throw new Error((data.error && data.error.message) || "请求失败");
      return data;
    }
    function setStatus(text) { statusEl.textContent = text; }
    function escapeHtml(value) {
      return String(value || "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
    }
    function fillMetrics(stats) {
      const totals = stats.totals || {};
      const items = [
        ["今日生成", totals.today_reply_runs || 0],
        ["今日上传", totals.today_uploads || 0],
        ["今日反馈", totals.today_feedback || 0],
        ["用户总数", totals.users || 0],
        ["回复总数", totals.reply_runs || 0],
        ["反馈总数", totals.feedback || 0],
      ];
      document.querySelector("#metrics").innerHTML = items.map(([k, v]) => `<div class="metric"><b>${v}</b><span>${k}</span></div>`).join("");
    }
    function fillSecrets(secrets) {
      const labels = { dashscope_api_key: "DashScope Key", deepseek_api_key: "DeepSeek Key", wechat_appid: "微信 AppID", wechat_secret: "微信 AppSecret", admin_token: "后台 Token" };
      document.querySelector("#secrets").innerHTML = Object.entries(labels).map(([key, label]) => {
        const ok = !!secrets[key];
        return `<div class="secret"><span>${label}</span><span class="tag ${ok ? "ok" : "warn"}">${ok ? "已配置" : "未配置"}</span></div>`;
      }).join("");
    }
    async function downloadFeedbackCsv() {
      localStorage.setItem("baiou_admin_token", tokenInput.value.trim());
      setStatus("导出中...");
      const res = await fetch("/api/v1/admin/feedback/export.csv", {
        headers: { "Authorization": "Bearer " + tokenInput.value.trim() },
      });
      if (!res.ok) {
        const contentType = res.headers.get("content-type") || "";
        const data = contentType.includes("application/json") ? await res.json() : await res.text();
        throw new Error((data.error && data.error.message) || data || "导出失败");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "baiou_feedback.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setStatus("已导出");
    }
    function fillConfig(cfg) {
      form.default_mode.value = cfg.runtime.default_mode || "bailian_rag_fast";
      form.vector_store_ids.value = (cfg.rag.vector_store_ids || []).join(",");
      form.rag_max_num_results.value = cfg.rag.max_num_results || 3;
      form.daily_reply_quota.value = cfg.limits.daily_reply_quota || 20;
      form.max_conversations_per_user.value = cfg.limits.max_conversations_per_user || 5;
      form.history_turns_for_reply.value = cfg.limits.history_turns_for_reply || 6;
      form.max_images_per_reply.value = cfg.limits.max_images_per_reply || 3;
      form.min_images_per_reply.value = cfg.limits.min_images_per_reply || 1;
      form.max_image_mb.value = cfg.limits.max_image_mb || 8;
      form.upload_days.value = cfg.retention.upload_days || 30;
      form.run_days.value = cfg.retention.run_days || 30;
      form.announcement_status.value = cfg.announcement.status || "active";
      form.announcement_title.value = cfg.announcement.title || "";
      form.announcement_content.value = cfg.announcement.content || "";
      fillSecrets(cfg.secrets || {});
      const exportLink = document.querySelector("#export");
      exportLink.onclick = async event => {
        event.preventDefault();
        try {
          await downloadFeedbackCsv();
        } catch (error) {
          setStatus(error.message);
        }
      };
    }
    function fillFeedback(rows) {
      document.querySelector("#feedback").innerHTML = (rows || []).map(row => `<tr><td>${escapeHtml(row.created_at)}</td><td>${escapeHtml(row.rating)}</td><td>${escapeHtml(row.notes)}</td><td>${escapeHtml(row.question)}</td><td>${escapeHtml(row.reply)}</td></tr>`).join("");
    }
    async function loadAll() {
      localStorage.setItem("baiou_admin_token", tokenInput.value.trim());
      setStatus("加载中...");
      const [cfg, stats, feedback] = await Promise.all([
        api("/api/v1/admin/config"),
        api("/api/v1/admin/stats"),
        api("/api/v1/admin/feedback?limit=20"),
      ]);
      fillConfig(cfg.config);
      fillMetrics(stats.stats);
      fillFeedback(feedback.feedback);
      setStatus("已加载");
    }
    form.addEventListener("submit", async event => {
      event.preventDefault();
      setStatus("保存中...");
      const payload = {
        runtime: { default_mode: form.default_mode.value },
        rag: { vector_store_ids: form.vector_store_ids.value, max_num_results: form.rag_max_num_results.value },
        limits: {
          daily_reply_quota: form.daily_reply_quota.value,
          max_conversations_per_user: form.max_conversations_per_user.value,
          history_turns_for_reply: form.history_turns_for_reply.value,
          max_images_per_reply: form.max_images_per_reply.value,
          min_images_per_reply: form.min_images_per_reply.value,
          max_image_mb: form.max_image_mb.value,
        },
        retention: { upload_days: form.upload_days.value, run_days: form.run_days.value },
        announcement: { title: form.announcement_title.value, content: form.announcement_content.value, status: form.announcement_status.value },
      };
      const saved = await api("/api/v1/admin/config", { method: "POST", body: JSON.stringify(payload) });
      fillConfig(saved.config);
      setStatus("已保存，当前服务已刷新配置");
    });
    document.querySelector("#load").addEventListener("click", loadAll);
    document.querySelector("#reload").addEventListener("click", loadAll);
  </script>
</body>
</html>"""


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def configured_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]


def normalize_extension(value: Any) -> str:
    suffix = str(value or "").lower().strip()
    return suffix if suffix.startswith(".") else f".{suffix}" if suffix else ""
