from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from baiou.common.io import PROJECT_ROOT, read_json
from baiou.common.project import baiou_output_root


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip())


def git_value(args: list[str], default: str = "") -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return default
    return result.stdout.strip()


def git_info() -> dict[str, Any]:
    status = git_value(["status", "--short", "--branch"])
    return {
        "branch": git_value(["branch", "--show-current"]),
        "commit": git_value(["rev-parse", "--short", "HEAD"]),
        "status": status,
        "dirty": any(line and not line.startswith("## ") for line in status.splitlines()),
    }


def vector_store_ids() -> list[str]:
    models_path = PROJECT_ROOT / "baiou" / "config" / "product" / "models.json"
    if not models_path.exists():
        return []
    models = read_json(models_path)
    rag_model = models.get("reply_rag_model", {}) if isinstance(models, dict) else {}
    file_search = rag_model.get("file_search", {}) if isinstance(rag_model.get("file_search", {}), dict) else {}
    ids = file_search.get("vector_store_ids", [])
    if isinstance(ids, str):
        return [item.strip() for item in ids.replace(";", ",").split(",") if item.strip()]
    return [str(item).strip() for item in ids if str(item).strip()] if isinstance(ids, list) else []


def latest_summary(root: Path) -> dict[str, Any]:
    product_runs = root / "product" / "runs"
    if not product_runs.exists():
        return {}
    summaries = sorted(product_runs.rglob("summary.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not summaries:
        return {}
    path = summaries[0]
    try:
        payload = read_json(path)
    except Exception as exc:  # noqa: BLE001 - health check should report, not crash.
        return {"path": str(path), "error": f"{exc.__class__.__name__}: {exc}"}
    return {
        "path": str(path),
        "status": payload.get("status", ""),
        "mode": payload.get("mode", ""),
        "run_id": payload.get("run_id", ""),
        "output_dir": payload.get("output_dir", ""),
    }


def collect_health() -> dict[str, Any]:
    output_root = baiou_output_root()
    knowledge_root = output_root / "cases" / "knowledge" / "current"
    segments_path = knowledge_root / "segments.jsonl"
    index_path = knowledge_root / "local_index" / "segments_index.jsonl"
    rag_segments = knowledge_root / "rag_knowledge_base" / "segments"
    rag_md_count = len(list(rag_segments.rglob("*.md"))) if rag_segments.exists() else 0
    segment_count = line_count(segments_path)
    index_count = line_count(index_path)
    return {
        "project_root": str(PROJECT_ROOT),
        "git": git_info(),
        "knowledge": {
            "segments_file": str(segments_path),
            "segment_count": segment_count,
            "local_index_file": str(index_path),
            "local_index_count": index_count,
            "rag_markdown_count": rag_md_count,
            "counts_match": segment_count == index_count == rag_md_count,
        },
        "product": {
            "vector_store_ids": vector_store_ids(),
            "latest_run": latest_summary(output_root),
        },
    }


def format_text(report: dict[str, Any]) -> str:
    git = report["git"]
    knowledge = report["knowledge"]
    product = report["product"]
    latest = product.get("latest_run", {})
    return "\n".join(
        [
            "Baiou health check",
            f"- project_root: {report['project_root']}",
            f"- git: {git.get('branch', '')} {git.get('commit', '')} dirty={git.get('dirty', False)}",
            f"- segments: {knowledge['segment_count']}",
            f"- local_index: {knowledge['local_index_count']}",
            f"- rag_markdown: {knowledge['rag_markdown_count']}",
            f"- counts_match: {knowledge['counts_match']}",
            f"- vector_store_ids: {', '.join(product.get('vector_store_ids', [])) or '(none)'}",
            f"- latest_product_run: {latest.get('status', '(none)')} mode={latest.get('mode', '')} path={latest.get('path', '')}",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Baiou project health check.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()
    report = collect_health()
    output = json.dumps(report, ensure_ascii=False, indent=2) if args.json else format_text(report)
    try:
        print(output)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(output.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
