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
