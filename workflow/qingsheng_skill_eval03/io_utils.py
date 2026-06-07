from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
PROJECT_ROOT = ROOT / "workflow" / "qingsheng_skill_eval03"
CONFIG_ROOT = PROJECT_ROOT / "config"


def resolve_path(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def load_settings() -> dict[str, Any]:
    return read_json(CONFIG_ROOT / "settings.json")


def read_json(path: str | Path) -> Any:
    return json.loads(resolve_path(path).read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, data: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    target.write_text(content + ("\n" if content else ""), encoding="utf-8")
