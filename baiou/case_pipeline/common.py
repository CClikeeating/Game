from __future__ import annotations

from pathlib import Path
from typing import Any

from baiou.common.project import load_config as load_section_config
from baiou.common.project import load_prompt, read_jsonl, section_output_root, timestamp_id, write_text

OUTPUT_ROOT = section_output_root("cases")


def load_config(name: str) -> dict[str, Any]:
    return load_section_config("case_pipeline", name)


