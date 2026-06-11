from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, render_template, request
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from workflow.common.io import PROJECT_ROOT as ROOT
from workflow.common.io import load_data
from workflow.common.io import read_json as read_json_file
from workflow.common.io import write_json as write_json_file
from workflow.qingsheng_skill_runtime04.run_skill import run_skill


CONFIG_ROOT = ROOT / "workflow" / "qingsheng_skill_web05" / "config"
DEFAULT_WEB_CONFIG = {
    "server": {
        "host": "127.0.0.1",
        "port": 7860,
        "debug": False,
    },
    "upload": {
        "max_content_mb": 24,
        "allowed_image_extensions": [".png", ".jpg", ".jpeg", ".webp", ".gif"],
    },
    "output": {
        "root": "outputs/qingsheng_skill_web05",
    },
}


def create_app(config: dict[str, Any] | None = None) -> Flask:
    config = config or load_web_config()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = int(config["max_content_mb"]) * 1024 * 1024

    @app.get("/")
    def index():
        return render_template("index.html", result=None, form=default_form())

    @app.post("/run")
    def run():
        started = time.time()
        run_id = uuid.uuid4().hex[:12]
        form = form_from_request()
        output_root = resolve_path(config["output_root"])
        upload_dir = output_root / "uploads" / run_id
        image_paths = save_images(request.files.getlist("images"), upload_dir, config)
        result: dict[str, Any]
        error = ""
        try:
            result = run_skill(
                question=form["question"],
                context=form["context"],
                images=[str(path) for path in image_paths],
                batch_id=f"web05_{run_id}",
                mode=form["mode"],
                answer_style=form["answer_style"],
                dry_run=form["dry_run"],
            )
        except Exception as exc:  # noqa: BLE001 - web console should show errors.
            result = {
                "status": "web_error",
                "answer": "",
                "mode": form["mode"],
                "answer_style": form["answer_style"],
                "vision_result": {},
                "model_result": {},
                "prompt_preview": "",
                "result_path": "",
            }
            error = f"{exc.__class__.__name__}: {exc}"
        elapsed = round(time.time() - started, 2)
        summary = {
            "run_id": run_id,
            "elapsed_seconds": elapsed,
            "question": form["question"],
            "context": form["context"],
            "mode": form["mode"],
            "answer_style": form["answer_style"],
            "dry_run": form["dry_run"],
            "images": [str(path) for path in image_paths],
            "status": result.get("status", ""),
            "answer": result.get("answer", ""),
            "vision_result": result.get("vision_result", {}),
            "model_result": result.get("model_result", {}),
            "prompt_preview": result.get("prompt_preview", ""),
            "prompt_preview_data": read_json_if_exists(result.get("prompt_preview", "")),
            "result_path": result.get("result_path", ""),
            "error": error,
        }
        summary["model_metrics"] = collect_model_metrics(summary)
        summary["rag_references"] = collect_references(summary)
        summary_path = output_root / "runs" / run_id / "summary.json"
        write_json(summary_path, summary)
        summary["summary_path"] = str(summary_path)
        return render_template("index.html", result=summary, form=form)

    return app


def load_web_config(path: str | Path | None = None) -> dict[str, Any]:
    raw = json.loads(json.dumps(DEFAULT_WEB_CONFIG))
    config_path = resolve_path(path or os.environ.get("QINGSHENG_WEB_CONFIG", CONFIG_ROOT / "web.json"))
    if config_path.exists():
        loaded = load_data(config_path)
        if isinstance(loaded, dict):
            deep_update(raw, loaded)

    server = raw.get("server", {}) if isinstance(raw.get("server"), dict) else {}
    upload = raw.get("upload", {}) if isinstance(raw.get("upload"), dict) else {}
    output = raw.get("output", {}) if isinstance(raw.get("output"), dict) else {}

    host = os.environ.get("QINGSHENG_WEB_HOST", server.get("host", "127.0.0.1"))
    port = int(os.environ.get("QINGSHENG_WEB_PORT", server.get("port", 7860)))
    debug = parse_bool(os.environ.get("QINGSHENG_WEB_DEBUG"), bool(server.get("debug", False)))
    max_content_mb = int(os.environ.get("QINGSHENG_WEB_MAX_CONTENT_MB", upload.get("max_content_mb", 24)))
    output_root = Path(os.environ.get("QINGSHENG_WEB_OUTPUT_ROOT", output.get("root", "outputs/qingsheng_skill_web05")))
    allowed_extensions = {
        normalize_extension(item)
        for item in upload.get("allowed_image_extensions", [])
        if normalize_extension(item)
    }

    return {
        "host": str(host),
        "port": port,
        "debug": debug,
        "max_content_mb": max_content_mb,
        "output_root": output_root,
        "allowed_image_extensions": allowed_extensions,
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
    if not suffix:
        return ""
    return suffix if suffix.startswith(".") else f".{suffix}"


def resolve_path(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def default_form() -> dict[str, Any]:
    return {"question": "", "context": "", "mode": "rag", "answer_style": "coach", "dry_run": False}


def form_from_request() -> dict[str, Any]:
    return {
        "question": request.form.get("question", "").strip(),
        "context": request.form.get("context", "").strip(),
        "mode": normalize_mode(request.form.get("mode", "rag")),
        "answer_style": normalize_answer_style(request.form.get("answer_style", "coach")),
        "dry_run": request.form.get("dry_run") == "on",
    }


def normalize_mode(value: str) -> str:
    mode = str(value or "rag").lower().strip()
    return mode if mode in {"fast", "rag", "auto"} else "rag"


def normalize_answer_style(value: str) -> str:
    style = str(value or "coach").lower().strip()
    return style if style in {"simple", "coach", "analysis", "autopilot"} else "coach"


def read_json_if_exists(path_value: Any) -> dict[str, Any]:
    if not path_value:
        return {}
    path = Path(str(path_value))
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return {}
    try:
        data = read_json_file(path)
    except Exception:  # noqa: BLE001 - diagnostic panel should be best-effort.
        return {}
    return data if isinstance(data, dict) else {}


def collect_model_metrics(summary: dict[str, Any]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for label, key in [("视觉模型", "vision_result"), ("回复模型", "model_result")]:
        item = summary.get(key, {})
        if not isinstance(item, dict) or not item:
            continue
        usage = item.get("usage", {}) if isinstance(item.get("usage"), dict) else {}
        metrics.append(
            {
                "label": label,
                "client": item.get("client", ""),
                "model": item.get("model", ""),
                "status": item.get("status", ""),
                "elapsed_seconds": item.get("elapsed_seconds", ""),
                "user_id": item.get("user_id", ""),
                "tokens": format_usage(usage),
                "usage": usage,
            }
        )
    return metrics


def format_usage(usage: dict[str, Any]) -> str:
    if not usage:
        return "无 token 数据"
    total = usage.get("total_tokens") or usage.get("total_token") or usage.get("total")
    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
    pieces = []
    if total is not None:
        pieces.append(f"total={total}")
    if input_tokens is not None:
        pieces.append(f"input={input_tokens}")
    if output_tokens is not None:
        pieces.append(f"output={output_tokens}")
    return " / ".join(pieces) if pieces else json.dumps(usage, ensure_ascii=False)


def collect_references(summary: dict[str, Any]) -> list[dict[str, Any]]:
    model_result = summary.get("model_result", {})
    if not isinstance(model_result, dict):
        return []
    references = model_result.get("references", [])
    return references if isinstance(references, list) else []


def allowed_image(filename: str, config: dict[str, Any]) -> bool:
    return Path(filename).suffix.lower() in config["allowed_image_extensions"]


def save_images(files: list[FileStorage], upload_dir: Path, config: dict[str, Any] | None = None) -> list[Path]:
    config = config or load_web_config()
    paths: list[Path] = []
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
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"cannot allocate upload filename for {path}")


def write_json(path: Path, data: dict[str, Any]) -> None:
    write_json_file(path, data)


app = create_app()


if __name__ == "__main__":
    web_config = load_web_config()
    app.run(host=web_config["host"], port=web_config["port"], debug=web_config["debug"], use_reloader=False)
