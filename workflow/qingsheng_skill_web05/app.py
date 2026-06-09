from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, render_template, request
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from workflow.qingsheng_skill_runtime04.run_skill import run_skill


ROOT = Path.cwd()
OUTPUT_ROOT = Path("outputs") / "qingsheng_skill_web05"
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 24 * 1024 * 1024

    @app.get("/")
    def index():
        return render_template("index.html", result=None, form=default_form())

    @app.post("/run")
    def run():
        started = time.time()
        run_id = uuid.uuid4().hex[:12]
        form = form_from_request()
        upload_dir = ROOT / OUTPUT_ROOT / "uploads" / run_id
        image_paths = save_images(request.files.getlist("images"), upload_dir)
        result: dict[str, Any]
        error = ""
        try:
            result = run_skill(
                question=form["question"],
                context=form["context"],
                images=[str(path) for path in image_paths],
                batch_id=f"web05_{run_id}",
                mode=form["mode"],
                dry_run=form["dry_run"],
            )
        except Exception as exc:  # noqa: BLE001 - web console should show errors.
            result = {
                "status": "web_error",
                "answer": "",
                "mode": form["mode"],
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
            "dry_run": form["dry_run"],
            "images": [str(path) for path in image_paths],
            "status": result.get("status", ""),
            "answer": result.get("answer", ""),
            "vision_result": result.get("vision_result", {}),
            "model_result": result.get("model_result", {}),
            "prompt_preview": result.get("prompt_preview", ""),
            "result_path": result.get("result_path", ""),
            "error": error,
        }
        summary_path = ROOT / OUTPUT_ROOT / "runs" / run_id / "summary.json"
        write_json(summary_path, summary)
        summary["summary_path"] = str(summary_path)
        return render_template("index.html", result=summary, form=form)

    return app


def default_form() -> dict[str, Any]:
    return {"question": "", "context": "", "mode": "rag", "dry_run": False}


def form_from_request() -> dict[str, Any]:
    return {
        "question": request.form.get("question", "").strip(),
        "context": request.form.get("context", "").strip(),
        "mode": normalize_mode(request.form.get("mode", "rag")),
        "dry_run": request.form.get("dry_run") == "on",
    }


def normalize_mode(value: str) -> str:
    mode = str(value or "rag").lower().strip()
    return mode if mode in {"fast", "rag", "auto"} else "rag"


def save_images(files: list[FileStorage], upload_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for index, file in enumerate(files, start=1):
        if not file or not file.filename:
            continue
        original = secure_filename(file.filename) or f"image_{index}.jpg"
        suffix = Path(original).suffix.lower()
        if suffix not in ALLOWED_IMAGE_EXTENSIONS:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7860, debug=False, use_reloader=False)
