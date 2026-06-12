from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path
from typing import Callable

from baiou.common.io import ensure_overwrite_allowed
from baiou.common.io import write_json as write_json_file

from .adapters import prepare_html, prepare_image_folder, prepare_long_image, prepare_pdf
from .config_loader import PREPARED_ROOT, ROOT
from .schema import SourceBlock
from .utils import ensure_dir, stable_source_id


RUNS_ROOT = PREPARED_ROOT
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")


def write_json(path: Path, data: object) -> None:
    write_json_file(path, data)


def choose_adapter(source_type: str) -> Callable:
    adapters = {
        "html": prepare_html,
        "pdf": prepare_pdf,
        "long_image": prepare_long_image,
        "image": prepare_long_image,
        "folder": prepare_image_folder,
        "image_folder": prepare_image_folder,
    }
    if source_type not in adapters:
        raise ValueError(f"Unsupported source_type: {source_type}")
    return adapters[source_type]


def safe_source_id(input_path: Path, run_id: str | None) -> str:
    if not run_id:
        return stable_source_id(input_path)
    if not SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must use English letters, numbers, underscore, or hyphen only.")
    return run_id


def blocks_to_payload(blocks: list[SourceBlock]) -> dict:
    return {
        "schema_version": "source_blocks_v1",
        "blocks": [block.to_dict() for block in blocks],
    }


def prepare(source_type: str, input_path: Path, run_id: str | None = None, overwrite: bool = False) -> Path:
    source_id = safe_source_id(input_path, run_id)
    output_dir = RUNS_ROOT / source_id
    runs_root = RUNS_ROOT.resolve()
    resolved_output = output_dir.resolve()
    if not resolved_output.is_relative_to(runs_root):
        raise ValueError(f"Unsafe output directory: {output_dir}")
    if output_dir.exists():
        ensure_overwrite_allowed(output_dir, overwrite)
        shutil.rmtree(output_dir)
    ensure_dir(output_dir)

    adapter = choose_adapter(source_type)
    manifest, blocks = adapter(input_path, output_dir, ROOT)
    manifest.pipeline_version = "baiou_source_pipeline_v1"
    write_json(output_dir / "source_manifest.json", manifest.to_dict())
    write_json(output_dir / "block_manifest.json", blocks_to_payload(blocks))
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare source files into ordered image blocks.")
    parser.add_argument("source_type", choices=["html", "pdf", "long_image", "image", "folder", "image_folder"])
    parser.add_argument("input_path")
    parser.add_argument("--run-id")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    output_dir = prepare(args.source_type, Path(args.input_path), args.run_id, args.overwrite)
    print(output_dir)


if __name__ == "__main__":
    main()


