from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
PROJECT_ROOT = ROOT / "workflow" / "source_to_chat_turns01"
CONFIG_ROOT = PROJECT_ROOT / "config"


def load_config(name: str) -> dict[str, Any]:
    path = CONFIG_ROOT / name
    text = path.read_text(encoding="utf-8-sig")
    return json.loads(text)
