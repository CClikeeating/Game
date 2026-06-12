from pathlib import Path
from typing import Any

from baiou.common.io import PROJECT_ROOT as ROOT
from baiou.common.io import load_config as load_config_file
from baiou.common.project import section_output_root

PROJECT_ROOT = ROOT / "baiou" / "source_pipeline"
CONFIG_ROOT = ROOT / "baiou" / "config" / "source_pipeline"
OUTPUT_ROOT = section_output_root("source")
PREPARED_ROOT = OUTPUT_ROOT / "prepared"
CASE_RUNS_ROOT = OUTPUT_ROOT / "case_runs"
BATCHES_ROOT = OUTPUT_ROOT / "batches"


def load_config(name: str) -> dict[str, Any]:
    return load_config_file(CONFIG_ROOT, name)


