from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from baiou.common.io import PROJECT_ROOT, load_data, read_json, write_json
from baiou.product.runtime.reply_engine import run_reply

CONFIG_ROOT = PROJECT_ROOT / "baiou" / "config" / "product"
DEFAULT_CONFIG = {
    "server": {"host": "127.0.0.1", "port": 7870, "debug": False},
    "upload": {"max_content_mb": 24, "allowed_image_extensions": [".png", ".jpg", ".jpeg", ".webp", ".gif"]},
    "output": {"root": "outputs/baiou/product", "feedback_log": "feedback.jsonl"},
    "runtime": {
        "default_mode": "quality_local",
        "modes": {
            "quality_local": "质量模式：本地标签检索",
            "bailian_rag_fast": "百炼 RAG 快速模式",
            "bailian_rag_quality": "百炼 RAG 质量模式：轻量局势标签 + 知识库",
        },
    },
}


def create_app(config: dict[str, Any] | None = None) -> Flask:
    config = config or load_web_config()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = int(config["max_content_mb"]) * 1024 * 1024

    @app.get("/")
    def index():
        return render_template("index.html", result=None, form=default_form(config))

    @app.post("/run")
    def run():
        run_id = uuid.uuid4().hex[:12]
        form = form_from_request(config)
        output_root = resolve_path(config["output_root"])
        upload_dir = output_root / "uploads" / run_id
        image_paths = save_images(request.files.getlist("images"), upload_dir, config)
        error = ""
        try:
            result = run_reply(
                question=form["question"],
                context=form["context"],
                images=[str(path) for path in image_paths],
                index_path=form["index_path"] or None,
                batch_id=f"web_{run_id}",
                dry_run=form["dry_run"],
                mode=form["mode"],
            )
        except Exception as exc:  # noqa: BLE001
            result = {"status": "web_error", "answer": {}, "labels": {}, "reference_segments": [], "output_dir": ""}
            error = f"{exc.__class__.__name__}: {exc}"
        summary = normalize_summary(run_id, form, image_paths, result, error)
        summary_path = output_root / "runs" / run_id / "summary.json"
        write_json(summary_path, summary)
        summary["summary_path"] = str(summary_path)
        return render_template("index.html", result=summary, form=form)

    @app.post("/feedback")
    def feedback():
        payload = request.get_json(silent=True) or {}
        summary_path = Path(str(payload.get("summary_path", "")))
        if not summary_path.is_absolute():
            summary_path = PROJECT_ROOT / summary_path
        if not summary_path.exists():
            return jsonify({"ok": False, "error": "summary_not_found"}), 404
        summary = read_json(summary_path)
        summary["feedback"] = {
            "rating": payload.get("rating", ""),
            "notes": payload.get("notes", ""),
        }
        write_json(summary_path, summary)
        append_feedback(config["feedback_log"], summary_path, summary)
        return jsonify({"ok": True})

    return app


def normalize_summary(run_id: str, form: dict[str, Any], image_paths: list[Path], result: dict[str, Any], error: str) -> dict[str, Any]:
    answer = result.get("answer", {}) if isinstance(result.get("answer", {}), dict) else {}
    return {
        "run_id": run_id,
        "question": form["question"],
        "context": form["context"],
        "index_path": form["index_path"],
        "dry_run": form["dry_run"],
        "mode": form["mode"],
        "images": [str(path) for path in image_paths],
        "status": result.get("status", ""),
        "error": error or result.get("error", ""),
        "image_understanding": result.get("image_understanding", ""),
        "answer": answer,
        "labels": result.get("labels", answer.get("labels", {})),
        "reference_segments": result.get("reference_segments", []),
        "output_dir": result.get("output_dir", ""),
        "raw_result": result,
        "model_metrics": collect_model_metrics(result),
        "labels_json": json.dumps(result.get("labels", answer.get("labels", {})), ensure_ascii=False, indent=2),
        "raw_result_json": json.dumps(result, ensure_ascii=False, indent=2),
    }

def collect_model_metrics(result: dict[str, Any]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    vision = result.get("vision_result", {}) if isinstance(result.get("vision_result", {}), dict) else {}
    if result.get("image_understanding") or vision:
        metrics.append(
            {
                "label": "截图理解",
                "status": vision.get("status", "done"),
                "model": vision.get("model", vision.get("client", "vision_model")),
                "elapsed_seconds": vision.get("elapsed_seconds", ""),
                "tokens": format_usage(vision.get("usage", {}) if isinstance(vision.get("usage", {}), dict) else {}),
            }
        )
    reply_label = "百炼 RAG 回复" if str(result.get("mode", "")).startswith("bailian_rag_") else "回复生成"
    for label, key in [("标签判断", "label_result"), (reply_label, "reply_result")]:
        item = result.get(key, {}) if isinstance(result.get(key, {}), dict) else {}
        if not item:
            continue
        metrics.append(
            {
                "label": label,
                "status": item.get("status", ""),
                "model": item.get("model", item.get("client", "")),
                "elapsed_seconds": item.get("elapsed_seconds", ""),
                "tokens": format_usage(item.get("usage", {}) if isinstance(item.get("usage", {}), dict) else {}),
            }
        )
    return metrics


def format_usage(usage: dict[str, Any]) -> str:
    if not usage:
        return "无 token 数据"
    total = usage.get("total_tokens") or usage.get("total_token") or usage.get("total")
    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
    parts = []
    if total is not None:
        parts.append(f"total={total}")
    if input_tokens is not None:
        parts.append(f"input={input_tokens}")
    if output_tokens is not None:
        parts.append(f"output={output_tokens}")
    return " / ".join(parts) if parts else json.dumps(usage, ensure_ascii=False)

def load_web_config(path: str | Path | None = None) -> dict[str, Any]:
    raw = json.loads(json.dumps(DEFAULT_CONFIG))
    config_path = resolve_path(path or os.environ.get("BAIOU_WEB_CONFIG") or CONFIG_ROOT / "web.json")
    if config_path.exists():
        loaded = load_data(config_path)
        if isinstance(loaded, dict):
            deep_update(raw, loaded)
    server = raw.get("server", {})
    upload = raw.get("upload", {})
    output = raw.get("output", {})
    runtime = raw.get("runtime", {})
    output_root = Path(os.environ.get("BAIOU_WEB_OUTPUT_ROOT") or output.get("root", "outputs/baiou/product"))
    return {
        "host": os.environ.get("BAIOU_WEB_HOST") or server.get("host", "127.0.0.1"),
        "port": int(os.environ.get("BAIOU_WEB_PORT") or server.get("port", 7870)),
        "debug": parse_bool(os.environ.get("BAIOU_WEB_DEBUG"), bool(server.get("debug", False))),
        "max_content_mb": int(os.environ.get("BAIOU_WEB_MAX_CONTENT_MB") or upload.get("max_content_mb", 24)),
        "allowed_image_extensions": {normalize_extension(item) for item in upload.get("allowed_image_extensions", [])},
        "output_root": output_root,
        "feedback_log": output_root / str(output.get("feedback_log", "feedback.jsonl")),
        "default_mode": os.environ.get("BAIOU_REPLY_MODE") or runtime.get("default_mode", "quality_local"),
        "modes": runtime.get("modes", DEFAULT_CONFIG["runtime"]["modes"]),
    }


def deep_update(base: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_update(base[key], value)
        else:
            base[key] = value


def parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_extension(value: Any) -> str:
    suffix = str(value or "").lower().strip()
    return suffix if suffix.startswith(".") else f".{suffix}" if suffix else ""


def resolve_path(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else PROJECT_ROOT / value


def default_form(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "question": "我该怎么回",
        "context": "",
        "index_path": "",
        "dry_run": False,
        "mode": config["default_mode"],
        "modes": config["modes"],
    }


def form_from_request(config: dict[str, Any]) -> dict[str, Any]:
    mode = request.form.get("mode", config["default_mode"]).strip()
    if mode not in config["modes"]:
        mode = config["default_mode"]
    return {
        "question": request.form.get("question", "").strip(),
        "context": request.form.get("context", "").strip(),
        "index_path": request.form.get("index_path", "").strip(),
        "dry_run": request.form.get("dry_run") == "on",
        "mode": mode,
        "modes": config["modes"],
    }


def append_feedback(path: Path, summary_path: Path, summary: dict[str, Any]) -> None:
    feedback = summary.get("feedback", {}) if isinstance(summary.get("feedback", {}), dict) else {}
    answer = summary.get("answer", {}) if isinstance(summary.get("answer", {}), dict) else {}
    record = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "summary_path": str(summary_path),
        "run_id": summary.get("run_id", ""),
        "mode": summary.get("mode", ""),
        "rating": feedback.get("rating", ""),
        "notes": feedback.get("notes", ""),
        "question": summary.get("question", ""),
        "context": summary.get("context", ""),
        "reply": answer.get("reply", ""),
        "status": summary.get("status", ""),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def allowed_image(filename: str, config: dict[str, Any]) -> bool:
    return Path(filename).suffix.lower() in config["allowed_image_extensions"]


def save_images(files: list[FileStorage], upload_dir: Path, config: dict[str, Any]) -> list[Path]:
    paths = []
    for index, file in enumerate(files, start=1):
        if not file or not file.filename:
            continue
        original = secure_filename(file.filename) or f"image_{index}.jpg"
        if not allowed_image(original, config):
            continue
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = unique_path(upload_dir / original)
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
    raise RuntimeError(f"cannot allocate upload filename for {path}")


app = create_app()


if __name__ == "__main__":
    cfg = load_web_config()
    app.run(host=cfg["host"], port=cfg["port"], debug=cfg["debug"], use_reloader=False)



