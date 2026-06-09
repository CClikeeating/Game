from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from .io_utils import load_settings, read_json, resolve_path, write_json, write_jsonl


def build_assets(batch_id: str | None = None, input_bundle: str | None = None) -> dict[str, Any]:
    settings = load_settings()
    batch_id = batch_id or settings["input"]["default_batch_id"]
    input_bundle_root = resolve_path(input_bundle) if input_bundle else resolve_path(settings["input"]["case_outputs_root"]) / batch_id
    cases_root = input_bundle_root / "cases"
    output_root = resolve_path(settings["output"]["root"]) / batch_id
    eval_pack = collect_eval_pack(cases_root, settings)
    library_rows = build_reference_library(cases_root, settings)
    experience_rows = build_experience_pack(library_rows)
    rag_summary = build_rag_knowledge_base(output_root, batch_id, library_rows, settings.get("rag_knowledge_base", {}))

    evals_path = output_root / "test_questions" / "generated_qingsheng_evals.json"
    eval_manifest_path = output_root / "test_questions" / "eval_manifest.csv"
    library_index_path = output_root / "learning_cases" / "cases_index.json"
    library_jsonl_path = output_root / "learning_cases" / "cases_index.jsonl"
    library_manifest_path = output_root / "learning_cases" / "learning_manifest.csv"
    experience_path = output_root / "experience_pack" / "qingsheng_experience_pack.json"
    experience_jsonl_path = output_root / "experience_pack" / "qingsheng_experience_pack.jsonl"
    experience_manifest_path = output_root / "experience_pack" / "experience_manifest.json"

    write_json(evals_path, {"evals": eval_pack})
    write_eval_manifest(eval_manifest_path, eval_pack)
    write_json(library_index_path, {"batch_id": batch_id, "cases": library_rows})
    write_jsonl(library_jsonl_path, library_rows)
    write_reference_manifest(library_manifest_path, library_rows)
    write_json(
        experience_path,
        {
            "schema_version": "qingsheng_experience_pack_v1",
            "batch_id": batch_id,
            "case_count": len(experience_rows),
            "cases": experience_rows,
        },
    )
    write_jsonl(experience_jsonl_path, experience_rows)
    write_json(
        experience_manifest_path,
        {
            "schema_version": "experience_manifest_v1",
            "batch_id": batch_id,
            "case_count": len(experience_rows),
            "files": ["qingsheng_experience_pack.json", "qingsheng_experience_pack.jsonl"],
            "notes": "Deployable clean asset pack for future qingsheng skill retrieval; excludes model logs, review workbooks, and raw images.",
        },
    )
    write_json(
        output_root / "handoff.json",
        {
            "schema_version": "pipeline_handoff_v1",
            "pipeline": "qingsheng_skill_eval03",
            "batch_id": batch_id,
            "source_bundle": str(input_bundle_root),
            "main_entry": "build_summary.json",
            "asset_dirs": {
                "learning_cases": "learning_cases",
                "test_questions": "test_questions",
                "experience_pack": "experience_pack",
                "rag_knowledge_base": settings.get("rag_knowledge_base", {}).get("directory", "rag_knowledge_base"),
            },
        },
    )

    summary = {
        "batch_id": batch_id,
        "case_count": len(library_rows),
        "eval_count": len(eval_pack),
        "experience_count": len(experience_rows),
        "evals_path": str(evals_path),
        "reference_index_path": str(library_index_path),
        "reference_jsonl_path": str(library_jsonl_path),
        "experience_pack_path": str(experience_path),
        "rag_knowledge_base": rag_summary,
    }
    write_json(output_root / "build_summary.json", summary)
    return summary


def build_experience_pack(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        gold = row.get("gold_reference", {}) if isinstance(row.get("gold_reference"), dict) else {}
        output.append(
            {
                "case_id": row.get("case_id", ""),
                "stage_number": row.get("stage_number", ""),
                "stage_label": row.get("stage_label", ""),
                "stage_confidence": row.get("stage_confidence", ""),
                "stage_structure": row.get("stage_structure", {}),
                "outcome": row.get("outcome", ""),
                "relationship_arc": row.get("relationship_arc", ""),
                "female_state": row.get("female_state", ""),
                "male_goal": row.get("male_goal", ""),
                "signals": row.get("signals", []),
                "good_replies": row.get("good_replies", []),
                "bad_replies": row.get("bad_replies", []),
                "observed_good_reply": gold.get("observed_good_reply", {}),
                "next_reply": gold.get("next_reply", ""),
                "transferable_rules": [
                    item.get("transferable_rule", "")
                    for item in row.get("good_replies", [])
                    if item.get("transferable_rule", "")
                ],
                "search_text": row.get("search_text", ""),
            }
        )
    return output


def build_rag_knowledge_base(
    output_root: Path,
    batch_id: str,
    rows: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or {}
    directory = settings.get("directory", "rag_knowledge_base")
    cases_directory = settings.get("cases_directory", "cases")
    index_filename = settings.get("index_filename", "qingsheng_cases_index.jsonl")
    manifest_filename = settings.get("manifest_filename", "upload_manifest.csv")
    summary_filename = settings.get("summary_filename", "rag_build_summary.json")
    max_list_items = int(settings.get("max_list_items", 8))

    root = output_root / directory
    cases_root = root / cases_directory
    index_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []

    for row in rows:
        case_id = str(row.get("case_id", "")).strip()
        if not case_id:
            continue
        file_path = cases_root / f"{safe_filename(case_id)}.md"
        content = render_rag_case_markdown(row, max_list_items)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        relative_path = file_path.relative_to(root).as_posix()
        index_rows.append(
            {
                "case_id": case_id,
                "file_path": relative_path,
                "stage_number": row.get("stage_number", ""),
                "stage_label": row.get("stage_label", ""),
                "outcome": row.get("outcome", ""),
                "tags": build_rag_tags(row),
                "search_text": row.get("search_text", ""),
            }
        )
        manifest_rows.append(
            {
                "case_id": case_id,
                "file_path": relative_path,
                "stage_label": row.get("stage_label", ""),
                "outcome": row.get("outcome", ""),
                "upload_status": "pending",
                "notes": "",
            }
        )

    write_jsonl(root / index_filename, index_rows)
    write_csv(
        root / manifest_filename,
        ["case_id", "file_path", "stage_label", "outcome", "upload_status", "notes"],
        manifest_rows,
    )
    summary = {
        "schema_version": "rag_knowledge_base_v1",
        "batch_id": batch_id,
        "document_count": len(index_rows),
        "directory": directory,
        "cases_directory": f"{directory}/{cases_directory}",
        "index_file": f"{directory}/{index_filename}",
        "manifest_file": f"{directory}/{manifest_filename}",
        "notes": "Markdown knowledge-base export derived from case_card assets; keeps experience_pack JSON/JSONL as the structured asset.",
    }
    write_json(root / summary_filename, summary)
    return summary


def render_rag_case_markdown(row: dict[str, Any], max_list_items: int = 8) -> str:
    case_id = str(row.get("case_id", "")).strip()
    stage = format_stage(row.get("stage_number", ""), row.get("stage_label", ""))
    scene = first_meaningful(row.get("outcome", ""), row.get("relationship_arc", ""), default="未总结")
    gold = row.get("gold_reference", {}) if isinstance(row.get("gold_reference"), dict) else {}
    good_replies = row.get("good_replies", []) if isinstance(row.get("good_replies"), list) else []
    bad_replies = row.get("bad_replies", []) if isinstance(row.get("bad_replies"), list) else []
    signals = row.get("signals", []) if isinstance(row.get("signals"), list) else []
    stage_structure = row.get("stage_structure", {}) if isinstance(row.get("stage_structure"), dict) else {}

    sections = [
        f"# 案例：{case_id}",
        "",
        f"标签：{', '.join(build_rag_tags(row)) or '未标注'}",
        f"关系阶段：{stage or '未判断'}",
        f"适用场景：{scene}",
        "",
        "## 阶段路径",
        render_stage_path(stage_structure),
        "",
        "## 关键阶段节点",
        render_key_stage_nodes(stage_structure, max_list_items),
        "",
        "## 用户常见问法",
        f"- 这段聊天现在应该怎么回？",
        f"- 女生这些反应代表什么？",
        f"- 这段关系处在什么阶段，男生下一步怎么推进？",
        "",
        "## 女方关键信号",
        render_item_list(signals, ["quote", "interpretation", "type"], max_list_items),
        "",
        "## 男方好回复",
        render_item_list(good_replies, ["quote", "why_good", "transferable_rule"], max_list_items),
        "",
        "## 为什么有效",
        render_gold_reason(gold, good_replies),
        "",
        "## 男方坏回复",
        render_item_list(bad_replies, ["quote", "why_bad", "better_reply"], max_list_items),
        "",
        "## 不要这样回",
        render_do_not_reply(bad_replies, max_list_items),
        "",
        "## 可迁移规则",
        render_transferable_rules(good_replies, gold, max_list_items),
        "",
        "## 检索关键词",
        render_search_keywords(row, max_list_items),
        "",
    ]
    return "\n".join(sections)


def build_rag_tags(row: dict[str, Any]) -> list[str]:
    tags = []
    for value in [row.get("stage_label", ""), row.get("outcome", ""), row.get("female_state", ""), row.get("male_goal", "")]:
        text = str(value).strip()
        if text:
            tags.append(text)
    return tags[:6]


def build_stage_structure(mapping: dict[str, Any]) -> dict[str, Any]:
    judgment = mapping.get("stage_judgment", {}) if isinstance(mapping.get("stage_judgment"), dict) else {}
    primary_number = coerce_stage_number(judgment.get("primary_stage") or mapping.get("stage_number", ""))
    strategy_number = coerce_stage_number(judgment.get("strategy_stage") or mapping.get("stage_number", ""))
    evidence = mapping.get("stage_evidence", []) if isinstance(mapping.get("stage_evidence", []), list) else []
    cross_signals = mapping.get("cross_stage_signals", []) if isinstance(mapping.get("cross_stage_signals", []), list) else []

    stages: dict[int, dict[str, Any]] = {}
    for number in expand_stage_range(judgment.get("stage_range", [])):
        stages[number] = stage_path_item(number)
    for item in evidence:
        number = stage_number_from_text(item.get("why", "")) or primary_number or strategy_number
        add_stage_turn(stages, number, item.get("turn_id", ""))
    for item in cross_signals:
        number = coerce_stage_number(item.get("to_stage"))
        add_stage_turn(stages, number, item.get("turn_id", ""), is_cross_stage=True)

    key_nodes = []
    for item in evidence:
        number = stage_number_from_text(item.get("why", "")) or primary_number or strategy_number
        key_nodes.append(stage_node(item, number, is_cross_stage=False))
    for item in cross_signals:
        key_nodes.append(stage_node(item, coerce_stage_number(item.get("to_stage")), is_cross_stage=True))

    return {
        "primary_stage": {
            "stage_number": primary_number,
            "stage_label": judgment.get("primary_label") or stage_label_for(primary_number),
            "confidence": judgment.get("confidence", mapping.get("stage_confidence", "")),
        },
        "strategy_stage": {
            "stage_number": strategy_number,
            "stage_label": judgment.get("strategy_label") or stage_label_for(strategy_number),
            "why": judgment.get("why_strategy_stage", ""),
        },
        "stage_range": judgment.get("stage_range", []),
        "stage_path": [stages[number] for number in sorted(stages)],
        "key_stage_nodes": key_nodes,
    }


def add_stage_turn(stages: dict[int, dict[str, Any]], number: int, turn_id: Any, is_cross_stage: bool = False) -> None:
    number = coerce_stage_number(number)
    if not number:
        return
    item = stages.setdefault(number, stage_path_item(number))
    item["is_cross_stage"] = bool(item.get("is_cross_stage")) or is_cross_stage
    turn = str(turn_id).strip()
    if turn and turn not in item["evidence_turn_ids"]:
        item["evidence_turn_ids"].append(turn)


def stage_path_item(number: int) -> dict[str, Any]:
    return {
        "stage_number": number,
        "stage_label": stage_label_for(number),
        "evidence_turn_ids": [],
        "is_cross_stage": False,
    }


def stage_node(item: dict[str, Any], number: int, is_cross_stage: bool) -> dict[str, Any]:
    return {
        "turn_id": item.get("turn_id", ""),
        "stage_number": coerce_stage_number(number),
        "stage_label": stage_label_for(coerce_stage_number(number)),
        "quote": item.get("quote", ""),
        "why": item.get("why", ""),
        "impact_on_strategy": item.get("impact_on_strategy", ""),
        "is_cross_stage": is_cross_stage,
    }


def render_stage_path(stage_structure: dict[str, Any]) -> str:
    path = stage_structure.get("stage_path", []) if isinstance(stage_structure.get("stage_path", []), list) else []
    if not path:
        primary = stage_structure.get("primary_stage", {}) if isinstance(stage_structure.get("primary_stage"), dict) else {}
        label = primary.get("stage_label", "")
        return f"- {label}" if label else "- 暂无明确记录"
    lines = []
    for item in path:
        label = item.get("stage_label") or stage_label_for(coerce_stage_number(item.get("stage_number")))
        turns = ", ".join(item.get("evidence_turn_ids", []) or [])
        suffix = "（穿插信号）" if item.get("is_cross_stage") else ""
        lines.append(f"- {label}{suffix}" + (f"：{turns}" if turns else ""))
    return "\n".join(lines)


def render_key_stage_nodes(stage_structure: dict[str, Any], limit: int) -> str:
    nodes = stage_structure.get("key_stage_nodes", []) if isinstance(stage_structure.get("key_stage_nodes", []), list) else []
    lines = []
    for item in nodes[:limit]:
        label = item.get("stage_label") or stage_label_for(coerce_stage_number(item.get("stage_number")))
        marker = "穿插信号" if item.get("is_cross_stage") else "阶段证据"
        pieces = [
            str(item.get("turn_id", "")).strip(),
            label,
            marker,
            str(item.get("quote", "")).strip(),
            str(item.get("why", "")).strip(),
            str(item.get("impact_on_strategy", "")).strip(),
        ]
        pieces = [piece for piece in pieces if piece]
        if pieces:
            lines.append(f"- {'；'.join(pieces)}")
    return "\n".join(lines) if lines else "- 暂无明确记录"


def render_search_keywords(row: dict[str, Any], limit: int) -> str:
    chunks = [
        row.get("case_id", ""),
        row.get("stage_label", ""),
        row.get("outcome", ""),
        row.get("female_state", ""),
        row.get("male_goal", ""),
    ]
    for item in (row.get("signals", []) or [])[:limit]:
        chunks.extend([item.get("type", ""), item.get("quote", ""), item.get("interpretation", "")])
    for item in (row.get("good_replies", []) or [])[:limit]:
        chunks.extend([item.get("quote", ""), item.get("why_good", ""), item.get("transferable_rule", "")])
    for item in (row.get("bad_replies", []) or [])[:limit]:
        chunks.extend([item.get("quote", ""), item.get("why_bad", ""), item.get("better_reply", "")])
    lines = []
    for chunk in chunks:
        text = str(chunk).strip()
        if text and text.lower() not in {"unknown", "none", "null", "n/a"} and text not in lines:
            lines.append(f"- {text}")
    return "\n".join(lines) if lines else "- 暂无明确记录"


def render_item_list(items: list[dict[str, Any]], fields: list[str], limit: int) -> str:
    lines = []
    for item in items[:limit]:
        parts = []
        for field in fields:
            value = str(item.get(field, "")).strip()
            if value:
                parts.append(value)
        if parts:
            lines.append(f"- {'；'.join(parts)}")
    return "\n".join(lines) if lines else "- 暂无明确记录"


def render_gold_reason(gold: dict[str, Any], good_replies: list[dict[str, Any]]) -> str:
    lines = []
    next_reply = str(gold.get("next_reply", "")).strip()
    why = str(gold.get("why", "")).strip()
    if next_reply:
        lines.append(f"- 推荐/参考回复：{next_reply}")
    if why:
        lines.append(f"- 理由：{why}")
    for item in good_replies[:3]:
        why_good = str(item.get("why_good", "")).strip()
        if why_good:
            lines.append(f"- {why_good}")
    return "\n".join(lines) if lines else "- 暂无明确记录"


def render_do_not_reply(items: list[dict[str, Any]], limit: int) -> str:
    lines = []
    for item in items[:limit]:
        quote = str(item.get("quote", "")).strip()
        why_bad = str(item.get("why_bad", "")).strip()
        if quote and why_bad:
            lines.append(f"- 不要回“{quote}”：{why_bad}")
        elif quote:
            lines.append(f"- 不要回“{quote}”")
        elif why_bad:
            lines.append(f"- {why_bad}")
    return "\n".join(lines) if lines else "- 暂无明确记录"


def render_transferable_rules(items: list[dict[str, Any]], gold: dict[str, Any], limit: int) -> str:
    rules = []
    for item in items[:limit]:
        rule = str(item.get("transferable_rule", "")).strip()
        if rule and rule not in rules:
            rules.append(rule)
    why = str(gold.get("why", "")).strip()
    if why and why not in rules:
        rules.append(why)
    return "\n".join(f"- {rule}" for rule in rules) if rules else "- 暂无明确记录"


def join_non_empty(values: list[Any], separator: str) -> str:
    return separator.join(str(value).strip() for value in values if str(value).strip())


def format_stage(stage_number: Any, stage_label: Any) -> str:
    number = str(stage_number).strip()
    label = str(stage_label).strip()
    if number and label.startswith(f"阶段{number}"):
        return label
    return join_non_empty([number, label], " ")


def first_meaningful(*values: Any, default: str = "") -> str:
    for value in values:
        text = str(value).strip()
        if text and text.lower() not in {"unknown", "none", "null", "n/a"}:
            return text
    return default


def expand_stage_range(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    numbers = [coerce_stage_number(item) for item in value]
    numbers = [number for number in numbers if number]
    if not numbers:
        return []
    return list(range(min(numbers), max(numbers) + 1))


def coerce_stage_number(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if 1 <= number <= 7 else 0


def stage_label_for(number: int) -> str:
    return {
        1: "阶段1 开场破冰",
        2: "阶段2 建立好感",
        3: "阶段3 关系升温",
        4: "阶段4 邀约见面",
        5: "阶段5 约会实战",
        6: "阶段6 亲密升级",
        7: "阶段7 确立关系",
    }.get(number, "")


def stage_number_from_text(text: Any) -> int:
    value = str(text)
    for number in range(1, 8):
        if f"阶段{number}" in value:
            return number
    return 0


def safe_filename(value: str) -> str:
    keep = []
    for char in value:
        keep.append(char if char.isalnum() or char in {"-", "_"} else "_")
    return "".join(keep).strip("_") or "case"


def collect_eval_pack(cases_root: Path, settings: dict[str, Any]) -> list[dict[str, Any]]:
    evals: list[dict[str, Any]] = []
    modes = settings["eval_pack"]["include_modes"]
    file_by_mode = settings["eval_pack"]["file_by_mode"]
    for case_dir in sorted(path for path in cases_root.iterdir() if path.is_dir()):
        for mode in modes:
            eval_path = case_dir / file_by_mode[mode]
            if not eval_path.exists():
                continue
            item = read_json(eval_path)
            item["case_id"] = case_dir.name
            item["mode"] = mode
            evals.append(item)
    return evals


def build_reference_library(cases_root: Path, settings: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    signal_limit = int(settings["reference_library"]["summary_signal_limit"])
    reply_limit = int(settings["reference_library"]["summary_reply_limit"])
    for case_dir in sorted(path for path in cases_root.iterdir() if path.is_dir()):
        case_card_path = case_dir / "case_card.json"
        if not case_card_path.exists():
            continue
        card = read_json(case_card_path)
        mapping = card.get("qingsheng_mapping", {})
        facts = card.get("case_facts", {})
        moments = card.get("key_moments", {})
        gold = card.get("gold_reference", {})
        row = {
            "case_id": card.get("case_meta", {}).get("case_id", case_dir.name),
            "batch_id": card.get("case_meta", {}).get("batch_id", ""),
            "source_output": card.get("case_meta", {}).get("source_output", ""),
            "stage_number": mapping.get("stage_number", ""),
            "stage_label": mapping.get("stage_label", ""),
            "stage_confidence": mapping.get("stage_confidence", ""),
            "stage_structure": build_stage_structure(mapping),
            "outcome": facts.get("outcome", ""),
            "relationship_arc": facts.get("relationship_arc", ""),
            "female_state": facts.get("female_state", ""),
            "male_goal": facts.get("male_goal", ""),
            "signals": summarize_items(mapping.get("signals", []), signal_limit),
            "good_replies": summarize_items(moments.get("good_replies", []), reply_limit),
            "bad_replies": summarize_items(moments.get("bad_replies", []), reply_limit),
            "gold_reference": {
                "reference_type": gold.get("reference_type", ""),
                "observed_good_reply": gold.get("observed_good_reply", {}),
                "model_suggested_reply": gold.get("model_suggested_reply", ""),
                "next_reply": gold.get("next_reply", ""),
                "why": gold.get("why", ""),
            },
            "quality": card.get("quality", {}),
            "paths": {
                "case_card": str(case_card_path),
                "readable_case": str(case_dir / "readable_case.md"),
                "eval_advisory": str(case_dir / "eval_advisory.json"),
                "eval_autopilot": str(case_dir / "eval_autopilot.json"),
            },
        }
        row["search_text"] = build_search_text(row, settings["reference_library"]["search_text_fields"])
        rows.append(row)
    return rows


def summarize_items(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    output = []
    for item in (items or [])[:limit]:
        output.append({key: item.get(key, "") for key in item.keys() if key in {
            "type",
            "turn_id",
            "quote",
            "interpretation",
            "strength",
            "why_good",
            "why_bad",
            "transferable_rule",
            "better_reply",
        }})
    return output


def build_search_text(row: dict[str, Any], fields: list[str]) -> str:
    chunks = []
    for field in fields:
        value = row.get(field, "")
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        if value:
            chunks.append(str(value))
    return "\n".join(chunks)


def write_eval_manifest(path: Path, evals: list[dict[str, Any]]) -> None:
    fields = ["id", "name", "case_id", "mode"]
    write_csv(path, fields, evals)


def write_reference_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "case_id",
        "stage_number",
        "stage_label",
        "stage_confidence",
        "outcome",
        "reference_type",
        "next_reply",
        "case_card",
    ]
    flat_rows = []
    for row in rows:
        gold = row.get("gold_reference", {})
        paths = row.get("paths", {})
        flat_rows.append(
            {
                **row,
                "reference_type": gold.get("reference_type", ""),
                "next_reply": gold.get("next_reply", ""),
                "case_card": paths.get("case_card", ""),
            }
        )
    write_csv(path, fields, flat_rows)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main() -> None:
    parser = argparse.ArgumentParser(description="Build qingsheng eval pack and reference library.")
    parser.add_argument("--batch-id")
    parser.add_argument("--input-bundle")
    args = parser.parse_args()
    print(json.dumps(build_assets(args.batch_id, args.input_bundle), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
