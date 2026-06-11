from pathlib import Path
from typing import Any

from workflow.common.io import PROJECT_ROOT as ROOT
from workflow.common.io import load_config as load_config_file

PROJECT_ROOT = ROOT / "workflow" / "source_to_chat_turns01"
CONFIG_ROOT = PROJECT_ROOT / "config"


def load_config(name: str) -> dict[str, Any]:
    return load_config_file(CONFIG_ROOT, name)
