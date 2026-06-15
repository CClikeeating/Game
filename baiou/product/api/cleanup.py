from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from baiou.common.io import resolve_path
from baiou.product.api.app import load_api_config
from baiou.product.common import OUTPUT_ROOT
from baiou.product.storage import ProductStore


def cleanup(apply: bool = False, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_api_config()
    now = datetime.now()
    upload_cutoff = now - timedelta(days=int(config.get("upload_retention_days", 30)))
    run_cutoff = now - timedelta(days=int(config.get("run_retention_days", 30)))
    store = ProductStore(config["sqlite_path"])
    upload_paths = store.delete_upload_rows_before(upload_cutoff.isoformat(timespec="seconds")) if apply else old_upload_paths(config, upload_cutoff)
    run_dirs = old_run_dirs(run_cutoff)

    deleted_uploads = delete_paths(upload_paths, apply)
    deleted_runs = delete_paths(run_dirs, apply)
    prune_empty_dirs(resolve_path(config["upload_root"]), apply)
    return {
        "applied": apply,
        "upload_retention_days": int(config.get("upload_retention_days", 30)),
        "run_retention_days": int(config.get("run_retention_days", 30)),
        "old_upload_files": len(upload_paths),
        "old_run_dirs": len(run_dirs),
        "deleted_upload_files": deleted_uploads,
        "deleted_run_dirs": deleted_runs,
    }


def old_upload_paths(config: dict[str, Any], cutoff: datetime) -> list[Path]:
    root = resolve_path(config["upload_root"])
    if not root.exists():
        return []
    return [path for path in root.rglob("*") if path.is_file() and datetime.fromtimestamp(path.stat().st_mtime) < cutoff]


def old_run_dirs(cutoff: datetime) -> list[Path]:
    runs_root = OUTPUT_ROOT / "runs"
    if not runs_root.exists():
        return []
    dirs = []
    for summary in runs_root.rglob("summary.json"):
        run_dir = summary.parent
        if datetime.fromtimestamp(summary.stat().st_mtime) < cutoff:
            dirs.append(run_dir)
    return sorted(set(dirs), key=lambda path: len(path.parts), reverse=True)


def delete_paths(paths: list[str | Path], apply: bool) -> int:
    count = 0
    for raw in paths:
        path = resolve_path(raw)
        if not path.exists():
            continue
        if apply:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        count += 1
    return count


def prune_empty_dirs(root: Path, apply: bool) -> None:
    if not apply or not root.exists():
        return
    for path in sorted([item for item in root.rglob("*") if item.is_dir()], key=lambda item: len(item.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean expired Baiou product uploads and runtime details.")
    parser.add_argument("--apply", action="store_true", help="Actually delete files. Without this flag only reports counts.")
    args = parser.parse_args()
    report = cleanup(apply=args.apply)
    for key, value in report.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
