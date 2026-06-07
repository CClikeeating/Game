from __future__ import annotations

import argparse
import json
from pathlib import Path

from .apply_human_review import read_json, rebuild_batch, refresh_case_quality, write_json, write_manifest_csv
from .build_human_review import build_rows, write_xlsx


def refresh(batch_dir: Path, rebuild_review: bool = True) -> dict[str, object]:
    manifest_path = batch_dir / "batch_manifest.json"
    manifest = read_json(manifest_path)
    review_counts = {}
    review_case_ids = set()
    for case in manifest.get("cases", []):
        case_dir = batch_dir / "cases" / case["case_id"]
        if not case_dir.exists():
            continue
        quality = refresh_case_quality(batch_dir, case)
        case["need_review_turns"] = quality.get("need_review_turns", 0)
        case["speaker_counts"] = quality.get("speaker_counts", {})
        failures = case.get("failure_blocks", [])
        case["failed_group_count"] = len(failures)
        case["failure_count"] = len(failures)
        if len(failures) == 0 and case.get("need_review_turns", 0) == 0:
            case["status"] = "ready"
        elif str(case.get("status", "")).startswith("deferred"):
            pass
        else:
            case["status"] = "needs_attention"

    write_json(manifest_path, manifest)
    write_manifest_csv(batch_dir, manifest)
    rebuild_batch(batch_dir)

    review_rows = []
    if rebuild_review:
        review_rows = build_rows(batch_dir)
        write_xlsx(batch_dir / "batch_001_human_review.xlsx", review_rows)
        for row in review_rows:
            review_type = row.get("review_type", "")
            review_counts[review_type] = review_counts.get(review_type, 0) + 1
            if row.get("case_id"):
                review_case_ids.add(row["case_id"])

    if review_case_ids:
        for case in manifest.get("cases", []):
            if case.get("case_id") in review_case_ids and case.get("status") == "ready":
                case["status"] = "needs_attention"
        write_json(manifest_path, manifest)
        write_manifest_csv(batch_dir, manifest)

    summary = {
        "batch_dir": str(batch_dir),
        "case_count": len(manifest.get("cases", [])),
        "review_row_count": len(review_rows),
        "review_counts": review_counts,
        "ready_count": sum(1 for case in manifest.get("cases", []) if case.get("status") == "ready"),
        "needs_attention_count": sum(
            1 for case in manifest.get("cases", []) if case.get("status") == "needs_attention"
        ),
    }
    write_json(batch_dir / "refresh_summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh batch manifest, quality reports and review workbook.")
    parser.add_argument("batch_dir")
    parser.add_argument("--skip-review", action="store_true")
    args = parser.parse_args()
    print(json.dumps(refresh(Path(args.batch_dir), not args.skip_review), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
