from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config_loader import OUTPUTS_ROOT, load_config, read_json
from .pipeline import build_eval_cards, normalize_primary_judgment, resolve_input_bundle, write_case_outputs


def refresh_batch(output_batch_id: str, case_ids: set[str] | None = None, input_bundle: str | None = None) -> dict[str, Any]:
    output_dir = OUTPUTS_ROOT / output_batch_id
    manifest = read_json(output_dir / "batch_case_manifest.json")
    batch_id = manifest.get("batch_id", output_batch_id)
    input_bundle_dir = resolve_input_bundle(batch_id, input_bundle)
    input_batch = read_json(input_bundle_dir / "batch_chat_turns.json")
    cases_by_id = {case.get("case_id", ""): case for case in input_batch.get("cases", [])}
    eval_templates = load_config("eval_templates.yaml")

    refreshed = []
    for row in manifest.get("cases", []):
        case_id = row.get("case_id", "")
        if case_ids and case_id not in case_ids:
            continue
        case_dir = Path(row.get("case_folder") or output_dir / "cases" / case_id)
        case_card_path = case_dir / "case_card.json"
        if not case_card_path.exists() or case_id not in cases_by_id:
            continue
        case_card = read_json(case_card_path)
        primary = normalize_primary_judgment(case_card.get("model_judgments", {}).get("primary", {}))
        case_card["model_judgments"]["primary"] = primary
        case_card["gold_reference"] = primary.get("gold_reference", {})
        case_card["eval_cards"] = build_eval_cards(cases_by_id[case_id], primary, eval_templates)
        write_case_outputs(case_dir, case_card)
        refreshed.append(
            {
                "case_id": case_id,
                "reference_type": case_card["gold_reference"].get("reference_type", ""),
                "next_reply": case_card["gold_reference"].get("next_reply", ""),
            }
        )
    return {"output_batch_id": output_batch_id, "refreshed": refreshed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh gold_reference without calling models.")
    parser.add_argument("--output-batch-id", required=True)
    parser.add_argument("--input-bundle")
    parser.add_argument("--case-id", action="append", default=[])
    args = parser.parse_args()
    result = refresh_batch(args.output_batch_id, set(args.case_id) if args.case_id else None, args.input_bundle)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
