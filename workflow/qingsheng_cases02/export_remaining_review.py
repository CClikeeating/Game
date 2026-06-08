from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config_loader import OUTPUTS_ROOT, load_config, read_json, write_json
from .pipeline import collect_review_rows, write_human_review


def export_remaining(batch_id: str) -> dict[str, Any]:
    output_dir = OUTPUTS_ROOT / batch_id
    review_rules = load_config("review_rules.yaml")
    rows: list[dict[str, Any]] = []
    for case_dir in sorted((output_dir / "cases").iterdir()):
        if not case_dir.is_dir():
            continue
        case_card_path = case_dir / "case_card.json"
        if not case_card_path.exists():
            continue
        case_card = read_json(case_card_path)
        rows.extend(collect_review_rows(case_card, review_rules, len(rows) + 1))

    must_rows = [row for row in rows if row.get("review_priority") == "must_review"]
    remaining_path = output_dir / "human_review_remaining.xlsx"
    must_path = output_dir / "human_review_remaining_must_review.xlsx"
    write_human_review(remaining_path, rows, review_rules)
    write_human_review(must_path, must_rows, review_rules)

    summary = {
        "batch_id": batch_id,
        "remaining_total_rows": len(rows),
        "remaining_must_review_rows": len(must_rows),
        "remaining_optional_rows": len(rows) - len(must_rows),
        "remaining_review": str(Path("outputs/qingsheng_cases02") / batch_id / remaining_path.name),
        "remaining_must_review": str(Path("outputs/qingsheng_cases02") / batch_id / must_path.name),
    }
    write_json(output_dir / "human_review_remaining_summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Export unresolved human review rows.")
    parser.add_argument("--batch-id", default="batch_001_data1html_5_cases")
    args = parser.parse_args()
    print(json.dumps(export_remaining(args.batch_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
