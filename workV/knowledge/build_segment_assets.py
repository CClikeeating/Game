from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from workflow.common.io import write_json, write_jsonl
from workV.common import OUTPUT_ROOT, load_config
from workV.knowledge.build_segment_index import case_dirs_for_batch
from workflow.common.io import read_json


DEFAULT_CONFIG = {
    "output": {"root": "segment_assets"},
    "learning_cases": {"directory": "learning_cases", "json_filename": "segment_cases_index.json", "jsonl_filename": "segment_cases_index.jsonl"},
    "experience_pack": {"directory": "experience_pack", "json_filename": "segment_experience_pack.json", "jsonl_filename": "segment_experience_pack.jsonl"},
    "rag_knowledge_base": {
        "directory": "rag_knowledge_base",
        "segments_directory": "segments",
        "index_filename": "segments_index.jsonl",
        "manifest_filename": "upload_manifest.csv",
        "summary_filename": "rag_build_summary.json",
        "max_text_chars": 1200,
    },
}


def build_assets(batch_id: str, output_root: str | None = None, approved_only: bool = True) -> dict[str, Any]:
    config = merged_config()
    batch_root = OUTPUT_ROOT / "segments" / batch_id
    cases_root = batch_root / "cases"
    if not cases_root.exists():
        raise FileNotFoundError(cases_root)

    target_root = Path(output_root) if output_root else OUTPUT_ROOT / str(config["output"].get("root", "segment_assets")) / batch_id
    if not target_root.is_absolute():
        from workflow.common.io import PROJECT_ROOT

        target_root = PROJECT_ROOT / target_root

    rows = load_segment_rows(batch_root, cases_root, approved_only)
    learning_summary = write_learning_cases(target_root, batch_id, rows, config["learning_cases"])
    experience_summary = write_experience_pack(target_root, batch_id, rows, config["experience_pack"])
    rag_summary = write_rag_knowledge_base(target_root, batch_id, rows, config["rag_knowledge_base"])
    summary = {
        "schema_version": "segment_assets_v01",
        "batch_id": batch_id,
        "source_batch_root": str(batch_root),
        "output_root": str(target_root),
        "approved_only": approved_only,
        "segment_count": len(rows),
        "learning_cases": learning_summary,
        "experience_pack": experience_summary,
        "rag_knowledge_base": rag_summary,
    }
    write_json(target_root / "build_summary.json", summary)
    return summary


def merged_config() -> dict[str, Any]:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    loaded = load_config("assets.json")
    deep_update(config, loaded)
    return config


def deep_update(base: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_update(base[key], value)
        else:
            base[key] = value


def load_segment_rows(batch_root: Path, cases_root: Path, approved_only: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_dir in case_dirs_for_batch(batch_root, cases_root):
        segments_path = case_dir / "segments.json"
        outline_path = case_dir / "case_outline.json"
        if not segments_path.exists():
            continue
        outline = read_json(outline_path) if outline_path.exists() else {}
        payload = read_json(segments_path)
        for index, segment in enumerate(payload.get("segments", []), start=1):
            if approved_only and segment.get("quality_status") != "approved":
                continue
            rows.append(segment_asset_row(segment, outline, index))
    return rows


def segment_asset_row(segment: dict[str, Any], outline: dict[str, Any], index: int) -> dict[str, Any]:
    labels = {
        "聊天阶段": segment.get("聊天阶段", ""),
        "女生状态": segment.get("女生状态", ""),
        "男生目标": segment.get("男生目标", ""),
        "推荐策略": segment.get("推荐策略", ""),
        "风险类型": segment.get("风险类型", []),
        "回复强度": segment.get("回复强度", ""),
    }
    secondary_labels = segment.get("次要标签", {}) if isinstance(segment.get("次要标签", {}), dict) else {}
    row = {
        "schema_version": "segment_asset_v01",
        "case_id": segment.get("case_id", ""),
        "segment_id": segment.get("segment_id", ""),
        "segment_index": index,
        "source_turn_ids": segment.get("source_turn_ids", []),
        "labels": labels,
        "secondary_labels": secondary_labels,
        "case_summary": outline.get("case_summary", ""),
        "stage_path": outline.get("stage_path", []),
        "当前上下文": segment.get("当前上下文", ""),
        "女生最后一句": segment.get("女生最后一句", ""),
        "男生原回复": segment.get("男生原回复", ""),
        "原回复评价": segment.get("原回复评价", ""),
        "更优回复": segment.get("更优回复", ""),
        "下一步建议": segment.get("下一步建议", ""),
        "quality_status": segment.get("quality_status", ""),
    }
    row["tags"] = build_tags(row)
    row["search_text"] = build_search_text(row)
    return row


def write_learning_cases(root: Path, batch_id: str, rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    directory = root / str(config.get("directory", "learning_cases"))
    json_path = directory / str(config.get("json_filename", "segment_cases_index.json"))
    jsonl_path = directory / str(config.get("jsonl_filename", "segment_cases_index.jsonl"))
    write_json(json_path, {"schema_version": "segment_cases_index_v01", "batch_id": batch_id, "segments": rows})
    write_jsonl(jsonl_path, rows)
    return {"json": str(json_path), "jsonl": str(jsonl_path), "segment_count": len(rows)}


def write_experience_pack(root: Path, batch_id: str, rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    directory = root / str(config.get("directory", "experience_pack"))
    json_path = directory / str(config.get("json_filename", "segment_experience_pack.json"))
    jsonl_path = directory / str(config.get("jsonl_filename", "segment_experience_pack.jsonl"))
    pack_rows = [experience_row(row) for row in rows]
    write_json(json_path, {"schema_version": "segment_experience_pack_v01", "batch_id": batch_id, "segment_count": len(pack_rows), "segments": pack_rows})
    write_jsonl(jsonl_path, pack_rows)
    return {"json": str(json_path), "jsonl": str(jsonl_path), "segment_count": len(pack_rows)}


def write_rag_knowledge_base(root: Path, batch_id: str, rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    rag_root = root / str(config.get("directory", "rag_knowledge_base"))
    segments_root = rag_root / str(config.get("segments_directory", "segments"))
    index_path = rag_root / str(config.get("index_filename", "segments_index.jsonl"))
    manifest_path = rag_root / str(config.get("manifest_filename", "upload_manifest.csv"))
    summary_path = rag_root / str(config.get("summary_filename", "rag_build_summary.json"))
    max_text_chars = int(config.get("max_text_chars", 1200))

    if segments_root.exists():
        for old_file in segments_root.glob("*.md"):
            old_file.unlink()

    index_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    for row in rows:
        segment_id = str(row.get("segment_id", "")).strip()
        if not segment_id:
            continue
        file_path = segments_root / f"{safe_filename(asset_file_stem(row))}.md"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(render_segment_markdown(row, max_text_chars), encoding="utf-8")
        relative = file_path.relative_to(rag_root).as_posix()
        index_rows.append(
            {
                "case_id": row.get("case_id", ""),
                "segment_id": segment_id,
                "file_path": relative,
                "tags": row.get("tags", []),
                "labels": row.get("labels", {}),
                "search_text": row.get("search_text", ""),
            }
        )
        manifest_rows.append(
            {
                "case_id": row.get("case_id", ""),
                "segment_id": segment_id,
                "file_path": relative,
                "upload_status": "pending",
                "notes": "",
            }
        )
    write_jsonl(index_path, index_rows)
    write_csv(manifest_path, ["case_id", "segment_id", "file_path", "upload_status", "notes"], manifest_rows)
    summary = {
        "schema_version": "segment_rag_knowledge_base_v01",
        "batch_id": batch_id,
        "document_count": len(index_rows),
        "segments_directory": str(segments_root),
        "index_file": str(index_path),
        "manifest_file": str(manifest_path),
    }
    write_json(summary_path, summary)
    return summary

def asset_file_stem(row: dict[str, Any]) -> str:
    case_id = str(row.get("case_id", "")).strip()
    segment_id = str(row.get("segment_id", "")).strip()
    if case_id and segment_id and not segment_id.startswith(f"{case_id}_"):
        return f"{case_id}_{segment_id}"
    return segment_id or case_id or "segment"

def experience_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": row.get("case_id", ""),
        "segment_id": row.get("segment_id", ""),
        "source_turn_ids": row.get("source_turn_ids", []),
        "labels": row.get("labels", {}),
        "secondary_labels": row.get("secondary_labels", {}),
        "scene": row.get("当前上下文", ""),
        "female_last_message": row.get("女生最后一句", ""),
        "original_reply": row.get("男生原回复", ""),
        "original_reply_review": row.get("原回复评价", ""),
        "better_reply": row.get("更优回复", ""),
        "next_step": row.get("下一步建议", ""),
        "transferable_rule": infer_transferable_rule(row),
        "search_text": row.get("search_text", ""),
    }


def render_segment_markdown(row: dict[str, Any], max_text_chars: int) -> str:
    labels = row.get("labels", {}) if isinstance(row.get("labels", {}), dict) else {}
    secondary_labels = row.get("secondary_labels", {}) if isinstance(row.get("secondary_labels", {}), dict) else {}
    lines = [
        f"# 片段：{row.get('segment_id', '')}",
        "",
        f"案例：{row.get('case_id', '')}",
        f"标签：{', '.join(row.get('tags', []))}",
        f"source_turn_ids：{', '.join(row.get('source_turn_ids', []))}",
        "",
        "## 标签",
        json.dumps(labels, ensure_ascii=False, indent=2),
        "",
        "## 次要标签",
        json.dumps(secondary_labels, ensure_ascii=False, indent=2),
        "",
        "## 当前上下文",
        trim(row.get("当前上下文", ""), max_text_chars),
        "",
        "## 女生最后一句",
        trim(row.get("女生最后一句", ""), max_text_chars),
        "",
        "## 男生原回复",
        trim(row.get("男生原回复", ""), max_text_chars),
        "",
        "## 原回复评价",
        trim(row.get("原回复评价", ""), max_text_chars),
        "",
        "## 更优回复",
        trim(row.get("更优回复", ""), max_text_chars),
        "",
        "## 下一步建议",
        trim(row.get("下一步建议", ""), max_text_chars),
        "",
        "## 检索文本",
        trim(row.get("search_text", ""), max_text_chars),
        "",
    ]
    return "\n".join(lines)


def infer_transferable_rule(row: dict[str, Any]) -> str:
    strategy = row.get("labels", {}).get("推荐策略", "") if isinstance(row.get("labels", {}), dict) else ""
    review = str(row.get("原回复评价", "")).strip()
    if strategy and review:
        return f"{strategy}：{review}"
    return strategy or review


def build_tags(row: dict[str, Any]) -> list[str]:
    labels = row.get("labels", {}) if isinstance(row.get("labels", {}), dict) else {}
    tags = []
    for key in ["聊天阶段", "女生状态", "男生目标", "推荐策略", "回复强度"]:
        value = str(labels.get(key, "")).strip()
        if value:
            tags.append(value)
    for risk in labels.get("风险类型", []) if isinstance(labels.get("风险类型", []), list) else []:
        text = str(risk).strip()
        if text:
            tags.append(text)
    secondary_labels = row.get("secondary_labels", {}) if isinstance(row.get("secondary_labels", {}), dict) else {}
    for key in ["聊天阶段", "女生状态", "男生目标", "推荐策略", "回复强度"]:
        value = str(secondary_labels.get(key, "")).strip()
        if value:
            tags.append(f"次要:{value}")
    for risk in secondary_labels.get("风险类型", []) if isinstance(secondary_labels.get("风险类型", []), list) else []:
        text = str(risk).strip()
        if text:
            tags.append(f"次要:{text}")
    return list(dict.fromkeys(tags))[:10]


def build_search_text(row: dict[str, Any]) -> str:
    chunks = [
        row.get("case_id", ""),
        row.get("segment_id", ""),
        " ".join(row.get("tags", [])),
        json.dumps(row.get("secondary_labels", {}), ensure_ascii=False),
        row.get("case_summary", ""),
        row.get("当前上下文", ""),
        row.get("女生最后一句", ""),
        row.get("男生原回复", ""),
        row.get("原回复评价", ""),
        row.get("更优回复", ""),
        row.get("下一步建议", ""),
    ]
    return "\n".join(str(item).strip() for item in chunks if str(item).strip())


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def trim(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= max_chars else text[:max_chars] + "\n...[truncated]"


def safe_filename(value: str) -> str:
    keep = []
    for char in value:
        keep.append(char if char.isalnum() or char in {"-", "_"} else "_")
    return "".join(keep).strip("_") or "segment"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deployable assets from approved workV segments.")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--include-unapproved", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_assets(args.batch_id, args.output_root, not args.include_unapproved), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
