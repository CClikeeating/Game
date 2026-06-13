from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from baiou.common.io import PROJECT_ROOT, read_json, write_json, write_jsonl
from baiou.common.project import read_jsonl, timestamp_id
from baiou.case_pipeline.common import OUTPUT_ROOT, load_config
from baiou.case_pipeline.knowledge.build_segment_index import case_dirs_for_batch


DEFAULT_CONFIG = {
    "output": {
        "root": "knowledge",
        "current_directory": "current",
        "imports_directory": "imports",
        "segments_filename": "segments.jsonl",
        "summary_filename": "build_summary.json",
    },
    "local_index": {"directory": "local_index", "index_filename": "segments_index.jsonl"},
    "rag_knowledge_base": {
        "directory": "rag_knowledge_base",
        "segments_directory": "segments",
        "import_folder_template": "{batch_id}_{timestamp}",
        "index_filename": "segments_index.jsonl",
        "manifest_filename": "upload_manifest.csv",
        "summary_filename": "rag_build_summary.json",
        "max_text_chars": 1200,
    },
    "experience_pack": {
        "enabled": False,
        "directory": "experience_pack",
        "json_filename": "segment_experience_pack.json",
        "jsonl_filename": "segment_experience_pack.jsonl",
    },
}


def build_assets(batch_id: str, output_root: str | None = None, approved_only: bool = True) -> dict[str, Any]:
    config = merged_config()
    batch_root = OUTPUT_ROOT / "segments" / batch_id
    cases_root = batch_root / "cases"
    if not cases_root.exists():
        raise FileNotFoundError(cases_root)

    knowledge_root = resolve_knowledge_root(config, output_root)
    current_root = knowledge_root / str(config["output"].get("current_directory", "current"))
    import_root = knowledge_root / str(config["output"].get("imports_directory", "imports")) / batch_id
    current_segments_path = current_root / str(config["output"].get("segments_filename", "segments.jsonl"))

    import_rows, skipped_rows = load_import_rows(batch_root, cases_root, approved_only)
    existing_rows = read_jsonl(current_segments_path) if current_segments_path.exists() else []
    rag_config = config["rag_knowledge_base"]
    import_folder = rag_import_folder_name(batch_id, rag_config)
    import_rows = [with_rag_file_path(row, import_folder, str(rag_config.get("segments_directory", "segments"))) for row in import_rows]
    merged_rows, created_count, updated_count = merge_rows(existing_rows, import_rows)

    write_jsonl(current_segments_path, merged_rows)
    local_index_summary = write_local_index(current_root, merged_rows, config["local_index"])
    rag_summary = write_rag_knowledge_base(current_root, batch_id, merged_rows, import_rows, import_folder, config["rag_knowledge_base"])
    experience_summary = {}
    if bool(config.get("experience_pack", {}).get("enabled", False)):
        experience_summary = write_experience_pack(current_root, batch_id, merged_rows, config["experience_pack"])

    imported_records = [import_record(row, "created" if row.get("segment_id") not in existing_segment_ids(existing_rows) else "updated") for row in import_rows]
    write_jsonl(import_root / "imported_segments.jsonl", imported_records)
    write_jsonl(import_root / "skipped_segments.jsonl", skipped_rows)
    import_summary = {
        "schema_version": "segment_knowledge_import_v01",
        "batch_id": batch_id,
        "source_batch_root": str(batch_root),
        "import_root": str(import_root),
        "approved_only": approved_only,
        "imported_count": len(import_rows),
        "skipped_count": len(skipped_rows),
        "created_count": created_count,
        "updated_count": updated_count,
        "current_segment_count": len(merged_rows),
    }
    write_json(import_root / "import_summary.json", import_summary)

    summary = {
        "schema_version": "segment_knowledge_current_v01",
        "last_import_batch_id": batch_id,
        "output_root": str(current_root),
        "segments_file": str(current_segments_path),
        "segment_count": len(merged_rows),
        "local_index": local_index_summary,
        "rag_knowledge_base": rag_summary,
        "experience_pack": experience_summary,
        "last_import": import_summary,
    }
    write_json(current_root / str(config["output"].get("summary_filename", "build_summary.json")), summary)
    return summary


def resolve_knowledge_root(config: dict[str, Any], output_root: str | None) -> Path:
    root = Path(output_root) if output_root else OUTPUT_ROOT / str(config["output"].get("root", "knowledge"))
    return root if root.is_absolute() else PROJECT_ROOT / root


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


def load_import_rows(batch_root: Path, cases_root: Path, approved_only: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    import_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    for case_dir in case_dirs_for_batch(batch_root, cases_root):
        segments_path = case_dir / "segments.json"
        outline_path = case_dir / "case_outline.json"
        if not segments_path.exists():
            continue
        outline = read_json(outline_path) if outline_path.exists() else {}
        payload = read_json(segments_path)
        for index, segment in enumerate(payload.get("segments", []) if isinstance(payload.get("segments"), list) else [], start=1):
            row = segment_asset_row(segment, outline, index)
            if approved_only and segment.get("quality_status") != "approved":
                skipped_rows.append(skipped_row(row, "not_approved"))
                continue
            import_rows.append(row)
    return import_rows, skipped_rows


def merge_rows(existing_rows: list[dict[str, Any]], import_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    existing_by_id = {str(row.get("segment_id", "")): row for row in existing_rows if str(row.get("segment_id", "")).strip()}
    order = [str(row.get("segment_id", "")) for row in existing_rows if str(row.get("segment_id", "")).strip()]
    created_count = 0
    updated_count = 0
    for row in import_rows:
        segment_id = str(row.get("segment_id", "")).strip()
        if not segment_id:
            continue
        if segment_id in existing_by_id:
            updated_count += 1
        else:
            created_count += 1
            order.append(segment_id)
        existing_by_id[segment_id] = row
    return [existing_by_id[segment_id] for segment_id in order if segment_id in existing_by_id], created_count, updated_count


def existing_segment_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("segment_id", "")).strip() for row in rows if str(row.get("segment_id", "")).strip()}


def import_record(row: dict[str, Any], action: str) -> dict[str, Any]:
    return {
        "case_id": row.get("case_id", ""),
        "segment_id": row.get("segment_id", ""),
        "quality_status": row.get("quality_status", ""),
        "rag_file_path": row.get("rag_file_path", ""),
        "action": action,
    }


def skipped_row(row: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "case_id": row.get("case_id", ""),
        "segment_id": row.get("segment_id", ""),
        "quality_status": row.get("quality_status", ""),
        "skip_reason": reason,
        "当前上下文": row.get("当前上下文", ""),
        "女生最后一句": row.get("女生最后一句", ""),
        "男生原回复": row.get("男生原回复", ""),
    }


def segment_asset_row(segment: dict[str, Any], outline: dict[str, Any], index: int) -> dict[str, Any]:
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
    secondary_labels = segment.get("次要标签", {}) if isinstance(segment.get("次要标签", {}), dict) else {}
    heat_signal = str(segment.get("高热度信号", "无") or "无")
    row = {
        "schema_version": "segment_asset_v01",
        "case_id": segment.get("case_id", ""),
        "segment_id": segment.get("segment_id", ""),
        "segment_index": index,
        "source_turn_ids": segment.get("source_turn_ids", []),
        "labels": labels,
        "高热度信号": heat_signal,
        "secondary_labels": secondary_labels,
        "case_summary": outline.get("case_summary", ""),
        "stage_path": outline.get("stage_path", []),
        "当前上下文": segment.get("当前上下文", ""),
        "女生最后一句": segment.get("女生最后一句", ""),
        "男生原回复": segment.get("男生原回复", ""),
        "原回复评价": segment.get("原回复评价", ""),
        "更优回复": segment.get("更优回复", ""),
        "迁移学习价值": segment.get("迁移学习价值", ""),
        "quality_status": segment.get("quality_status", ""),
    }
    row["tags"] = build_tags(row)
    row["search_text"] = build_search_text(row)
    return row


def write_local_index(root: Path, rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    directory = root / str(config.get("directory", "local_index"))
    index_path = directory / str(config.get("index_filename", "segments_index.jsonl"))
    write_jsonl(index_path, rows)
    return {"index_file": str(index_path), "segment_count": len(rows)}


def write_experience_pack(root: Path, batch_id: str, rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    directory = root / str(config.get("directory", "experience_pack"))
    json_path = directory / str(config.get("json_filename", "segment_experience_pack.json"))
    jsonl_path = directory / str(config.get("jsonl_filename", "segment_experience_pack.jsonl"))
    pack_rows = [experience_row(row) for row in rows]
    write_json(json_path, {"schema_version": "segment_experience_pack_v01", "last_import_batch_id": batch_id, "segment_count": len(pack_rows), "segments": pack_rows})
    write_jsonl(jsonl_path, pack_rows)
    return {"json": str(json_path), "jsonl": str(jsonl_path), "segment_count": len(pack_rows)}


def write_rag_knowledge_base(
    root: Path,
    batch_id: str,
    rows: list[dict[str, Any]],
    import_rows: list[dict[str, Any]],
    import_folder: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    rag_root = root / str(config.get("directory", "rag_knowledge_base"))
    segments_root = rag_root / str(config.get("segments_directory", "segments"))
    import_segments_root = segments_root / import_folder
    index_path = rag_root / str(config.get("index_filename", "segments_index.jsonl"))
    manifest_path = rag_root / str(config.get("manifest_filename", "upload_manifest.csv"))
    summary_path = rag_root / str(config.get("summary_filename", "rag_build_summary.json"))
    max_text_chars = int(config.get("max_text_chars", 1200))

    clear_root_markdown_files(segments_root)
    import_segments_root.mkdir(parents=True, exist_ok=True)
    for old_file in import_segments_root.glob("*.md"):
        old_file.unlink()
    for row in import_rows:
        relative = str(row.get("rag_file_path", "")).strip()
        if not relative:
            continue
        file_path = rag_root / relative
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(render_segment_markdown(row, max_text_chars), encoding="utf-8")

    index_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    for row in rows:
        segment_id = str(row.get("segment_id", "")).strip()
        if not segment_id:
            continue
        relative = str(row.get("rag_file_path", "")).strip() or f"{str(config.get('segments_directory', 'segments'))}/{safe_filename(asset_file_stem(row))}.md"
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
        manifest_rows.append({"case_id": row.get("case_id", ""), "segment_id": segment_id, "file_path": relative, "upload_status": "pending", "notes": ""})
    write_jsonl(index_path, index_rows)
    write_csv(manifest_path, ["case_id", "segment_id", "file_path", "upload_status", "notes"], manifest_rows)
    write_csv(import_segments_root / "upload_manifest.csv", ["case_id", "segment_id", "file_path", "upload_status", "notes"], [row for row in manifest_rows if str(row.get("file_path", "")).startswith(f"{str(config.get('segments_directory', 'segments'))}/{import_folder}/")])
    summary = {
        "schema_version": "segment_rag_knowledge_base_v01",
        "last_import_batch_id": batch_id,
        "document_count": len(index_rows),
        "latest_import_document_count": len(import_rows),
        "segments_directory": str(segments_root),
        "latest_import_segments_directory": str(import_segments_root),
        "index_file": str(index_path),
        "manifest_file": str(manifest_path),
    }
    write_json(summary_path, summary)
    return summary


def rag_import_folder_name(batch_id: str, config: dict[str, Any]) -> str:
    template = str(config.get("import_folder_template", "{batch_id}_{timestamp}"))
    return safe_filename(template.format(batch_id=batch_id, timestamp=timestamp_id()))


def with_rag_file_path(row: dict[str, Any], import_folder: str, segments_directory: str) -> dict[str, Any]:
    updated = dict(row)
    updated["rag_file_path"] = f"{safe_filename(segments_directory)}/{import_folder}/{safe_filename(asset_file_stem(row))}.md"
    updated["rag_import_folder"] = import_folder
    return updated


def clear_root_markdown_files(path: Path) -> None:
    if path.exists():
        for old_file in path.glob("*.md"):
            old_file.unlink()
    path.mkdir(parents=True, exist_ok=True)


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
        "transfer_value": row.get("迁移学习价值", ""),
        "heat_signal": row.get("高热度信号", "无"),
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
        "## 高热度信号",
        trim(row.get("高热度信号", "无"), max_text_chars),
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
        "## 迁移学习价值",
        trim(row.get("迁移学习价值", ""), max_text_chars),
        "",
        "## 检索文本",
        trim(row.get("search_text", ""), max_text_chars),
        "",
    ]
    return "\n".join(lines)


def infer_transferable_rule(row: dict[str, Any]) -> str:
    transfer_value = str(row.get("迁移学习价值", "")).strip()
    if transfer_value:
        return transfer_value
    strategy = row.get("labels", {}).get("推荐策略", "") if isinstance(row.get("labels", {}), dict) else ""
    review = str(row.get("原回复评价", "")).strip()
    if strategy and review:
        return f"{strategy}：{review}"
    return strategy or review


def build_tags(row: dict[str, Any]) -> list[str]:
    labels = row.get("labels", {}) if isinstance(row.get("labels", {}), dict) else {}
    tags = []
    for key in ["聊天阶段", "接触状态", "关系推进目标", "女生状态", "男生目标", "推荐策略", "回复强度"]:
        value = str(labels.get(key, "")).strip()
        if value:
            tags.append(value)
    for risk in labels.get("风险类型", []) if isinstance(labels.get("风险类型", []), list) else []:
        text = str(risk).strip()
        if text:
            tags.append(text)
    heat_signal = str(row.get("高热度信号", "")).strip()
    if heat_signal and heat_signal != "无":
        tags.append(heat_signal)
    secondary_labels = row.get("secondary_labels", {}) if isinstance(row.get("secondary_labels", {}), dict) else {}
    for key in ["聊天阶段", "接触状态", "关系推进目标", "女生状态", "男生目标", "推荐策略", "回复强度"]:
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
        row.get("高热度信号", ""),
        json.dumps(row.get("secondary_labels", {}), ensure_ascii=False),
        row.get("case_summary", ""),
        row.get("当前上下文", ""),
        row.get("女生最后一句", ""),
        row.get("男生原回复", ""),
        row.get("原回复评价", ""),
        row.get("更优回复", ""),
        row.get("迁移学习价值", ""),
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
    parser = argparse.ArgumentParser(description="Build current Baiou knowledge assets from approved segments.")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--include-unapproved", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_assets(args.batch_id, args.output_root, not args.include_unapproved), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
