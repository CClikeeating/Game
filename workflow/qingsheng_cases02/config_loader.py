from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
PROJECT_ROOT = ROOT / "workflow" / "qingsheng_cases02"
CONFIG_ROOT = PROJECT_ROOT / "config"
OUTPUTS_ROOT = ROOT / "outputs" / "qingsheng_cases02"


def load_config(name: str) -> dict[str, Any]:
    return json.loads((CONFIG_ROOT / name).read_text(encoding="utf-8-sig"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
