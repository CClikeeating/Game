from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from baiou.common.io import read_json, write_jsonl, write_json
from baiou.case_pipeline.common import OUTPUT_ROOT


def build_index(batch_id: str, output_path: str | None = None, approved_only: bool = True) -> dict[str, Any]:
    batch_root = OUTPUT_ROOT / "segments" / batch_id
    cases_root = batch_root / "cases"
    rows: list[dict[str, Any]] = []
    if not cases_root.exists():
        raise FileNotFoundError(cases_root)
    for case_dir in case_dirs_for_batch(batch_root, cases_root):
        segments_path = case_dir / "segments.json"
        outline_path = case_dir / "case_outline.json"
        if not segments_path.exists():
            continue
        outline = read_json(outline_path) if outline_path.exists() else {}
        payload = read_json(segments_path)
        for segment in payload.get("segments", []):
            if approved_only and segment.get("quality_status") != "approved":
                continue
            rows.append(index_row(segment, outline))
    target = Path(output_path) if output_path else OUTPUT_ROOT / "indexes" / "segments_index.jsonl"
    if not target.is_absolute():
        from baiou.common.io import PROJECT_ROOT

        target = PROJECT_ROOT / target
    write_jsonl(target, rows)
    summary = {"batch_id": batch_id, "index_path": str(target), "segment_count": len(rows), "approved_only": approved_only}
    write_json(target.with_suffix(".summary.json"), summary)
    return summary


def case_dirs_for_batch(batch_root: Path, cases_root: Path) -> list[Path]:
    manifest_path = batch_root / "segments_manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        dirs: list[Path] = []
        for row in manifest.get("cases", []):
            case_dir_text = str(row.get("case_dir", "")).strip()
            case_id = str(row.get("case_id", "")).strip()
            case_dir = Path(case_dir_text) if case_dir_text else cases_root / case_id
            if not case_dir.is_absolute():
                case_dir = batch_root / case_dir
            if case_dir.exists():
                dirs.append(case_dir)
        return dirs
    return sorted(path for path in cases_root.iterdir() if path.is_dir())


def index_row(segment: dict[str, Any], outline: dict[str, Any]) -> dict[str, Any]:
    labels = {
        "聊天阶段": segment.get("聊天阶段", ""),
        "接触状态": segment.get("接触状态", "未知"),
        "关系推进目标": segment.get("关系推进目标", "无"),
        "女生状态": segment.get("女生状态", ""),
        "男生目标": segment.get("男生目标", ""),
        "推荐策略": segment.get("推荐策略", ""),
        "风险类型": segment.get("风险类型", []),
        "回复强度": segment.get("回复强度", ""),
    }
    heat_signal = str(segment.get("高热度信号", "无") or "无")
    secondary_labels = segment.get("次要标签", {}) if isinstance(segment.get("次要标签", {}), dict) else {}
    chunks = [
        segment.get("case_id", ""),
        segment.get("segment_id", ""),
        outline.get("case_summary", ""),
        " ".join(str(value) for value in labels.values()),
        heat_signal,
        json.dumps(secondary_labels, ensure_ascii=False),
        segment.get("当前上下文", ""),
        segment.get("女生最后一句", ""),
        segment.get("男生原回复", ""),
        segment.get("原回复评价", ""),
        segment.get("更优回复", ""),
        segment.get("迁移学习价值", ""),
    ]
    return {
        "case_id": segment.get("case_id", ""),
        "segment_id": segment.get("segment_id", ""),
        "source_turn_ids": segment.get("source_turn_ids", []),
        "labels": labels,
        "高热度信号": heat_signal,
        "secondary_labels": secondary_labels,
        "当前上下文": segment.get("当前上下文", ""),
        "女生最后一句": segment.get("女生最后一句", ""),
        "男生原回复": segment.get("男生原回复", ""),
        "原回复评价": segment.get("原回复评价", ""),
        "更优回复": segment.get("更优回复", ""),
        "迁移学习价值": segment.get("迁移学习价值", ""),
        "case_summary": outline.get("case_summary", ""),
        "quality_status": segment.get("quality_status", ""),
        "search_text": "\n".join(str(chunk) for chunk in chunks if chunk),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local Baiou segment index.")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--output-path")
    parser.add_argument("--include-unapproved", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_index(args.batch_id, args.output_path, not args.include_unapproved), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
