from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workflow.common.io import PROJECT_ROOT, read_json, read_text, resolve_path, write_json, write_jsonl

WORKV_ROOT = PROJECT_ROOT / "workV"
CONFIG_ROOT = WORKV_ROOT / "config"
PROMPT_ROOT = WORKV_ROOT / "prompts"
OUTPUT_ROOT = WORKV_ROOT / "outputs"


def load_config(name: str) -> dict[str, Any]:
    data = read_json(CONFIG_ROOT / name)
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
