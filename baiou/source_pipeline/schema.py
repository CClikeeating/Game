from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SourceBlock:
    block_id: str
    order: int
    kind: str
    prepared_path: str | None = None
    source_ref: str | None = None
    source_url: str | None = None
    page: int | None = None
    crop_box: list[int] | None = None
    source_size: list[int] | None = None
    overlap_top: int = 0
    overlap_bottom: int = 0
    text: str = ""
    status: str = "pending_ocr"
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value not in (None, [], {})}


@dataclass
class SourceManifest:
    source_id: str
    source_type: str
    original_path: str
    output_dir: str
    block_count: int
    adapter: str
    pipeline_version: str = "baiou_source_pipeline_v1"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def relative_to(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


