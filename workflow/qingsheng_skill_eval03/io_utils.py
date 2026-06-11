from __future__ import annotations

from pathlib import Path
from typing import Any

from workflow.common.io import PROJECT_ROOT as ROOT
from workflow.common.io import read_json as read_json_file
from workflow.common.io import resolve_path as resolve_project_path
from workflow.common.io import write_json as write_json_file
from workflow.common.io import write_jsonl as write_jsonl_file

PROJECT_ROOT = ROOT / "workflow" / "qingsheng_skill_eval03"
CONFIG_ROOT = PROJECT_ROOT / "config"


def resolve_path(path: str | Path) -> Path:
    return resolve_project_path(path)


def load_settings() -> dict[str, Any]:
    return read_json(CONFIG_ROOT / "settings.json")


def read_json(path: str | Path) -> Any:
    return read_json_file(path)


def write_json(path: str | Path, data: Any) -> None:
    write_json_file(path, data)


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    write_jsonl_file(path, rows)
