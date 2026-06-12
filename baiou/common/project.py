from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from baiou.common.io import PROJECT_ROOT, read_json, read_text, resolve_path, write_json, write_jsonl

BAIOU_ROOT = PROJECT_ROOT / "baiou"
PROMPT_ROOT = BAIOU_ROOT / "prompts"


def baiou_output_root() -> Path:
    return resolve_path(os.environ.get("BAIOU_OUTPUT_ROOT", "outputs/baiou"))


def section_output_root(section: str) -> Path:
    return baiou_output_root() / section


def load_config(section: str, name: str) -> dict[str, Any]:
    data = read_json(BAIOU_ROOT / "config" / section / name)
    return data if isinstance(data, dict) else {}


def load_prompt(name: str) -> str:
    return read_text(PROMPT_ROOT / name)


def write_text(path: str | Path, text: str) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = resolve_path(path)
    if not target.exists():
        return []
    rows = []
    for line in target.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def timestamp_id() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


