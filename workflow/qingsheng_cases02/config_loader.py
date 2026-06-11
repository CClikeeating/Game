from __future__ import annotations

from pathlib import Path
from typing import Any

from workflow.common.io import PROJECT_ROOT as ROOT
from workflow.common.io import load_config as load_config_file
from workflow.common.io import read_json as read_json_file
from workflow.common.io import write_json as write_json_file

PROJECT_ROOT = ROOT / "workflow" / "qingsheng_cases02"
CONFIG_ROOT = PROJECT_ROOT / "config"
OUTPUTS_ROOT = ROOT / "outputs" / "qingsheng_cases02"


def load_config(name: str) -> dict[str, Any]:
    return load_config_file(CONFIG_ROOT, name)


def read_json(path: Path) -> Any:
    return read_json_file(path)


def write_json(path: Path, data: Any) -> None:
    write_json_file(path, data)
