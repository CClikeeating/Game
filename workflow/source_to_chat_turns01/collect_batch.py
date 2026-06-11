from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path
from typing import Any

from workflow.common.io import PROJECT_ROOT
from workflow.common.io import ensure_overwrite_allowed
from workflow.common.io import read_json as read_json_file
from workflow.common.io import write_json as write_json_file


OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "source_to_chat_turns01"
PREPARED_ROOT = OUTPUT_ROOT / "_prepared_sources"
CASE_RUNS_ROOT = OUTPUT_ROOT / "_case_runs"
DEFAULT_DEFER_FAILED_GROUPS_GT = 1


def read_json(path: Path) -> Any:
    return read_json_file(path)


def write_json(path: Path, data: Any) -> None:
    write_json_file(path, data)


def rewrite_case_image_paths(payload: Any, target_root: Path) -> Any:
    if isinstance(payload, dict):
        return {key: rewrite_case_image_paths(value, target_root) for key, value in payload.items()}
    if isinstance(payload, list):
        return [rewrite_case_image_paths(item, target_root) for item in payload]
    if isinstance(payload, str) and "prepared_images" in payload:
        return str((target_root / "prepared_images" / Path(payload).name).resolve())
    return payload


def failure_blocks(raw: dict[str, Any]) -> list[dict[str, Any]]:
    failures = []
    for result in raw.get("results", []):
        if result.get("status") != "model_success":
            failures.append(
                {
                    "call_index": result.get("call_index"),
                    "block_ids": result.get("block_ids", []),
                    "status": result.get("status", ""),
                    "error": str(result.get("error", "")),
                }
            )
    return failures


def collect(batch_id: str, case_ids: list[str], defer_failed_groups_gt: int, overwrite: bool = False) -> Path:
    batch_dir = OUTPUT_ROOT / "batches" / batch_id
    if batch_dir.exists():
        ensure_overwrite_allowed(batch_dir, overwrite)
        shutil.rmtree(batch_dir)
    (batch_dir / "cases").mkdir(parents=True, exist_ok=True)
    (batch_dir / "deferred_cases").mkdir(parents=True, exist_ok=True)

    manifest = []
    combined = []
    for case_id in case_ids:
        source_dir = CASE_RUNS_ROOT / case_id / "group"
        quality = read_json(source_dir / "quality_report.json")
        turns = read_json(source_dir / "chat_turns.json")
        raw = read_json(source_dir / "raw_model_results.json")
        failures = failure_blocks(raw)
        deferred = len(failures) > defer_failed_groups_gt
        target_root = batch_dir / ("deferred_cases" if deferred else "cases") / case_id
        target_root.mkdir(parents=True, exist_ok=True)
        for name in ["chat_readable.md", "quality_report.json", "raw_model_results.json"]:
            shutil.copy2(source_dir / name, target_root / name)
        prepared_dir = PREPARED_ROOT / case_id
        if prepared_dir.exists():
            for name in ["prepared_images", "source_images"]:
                src = prepared_dir / name
                dst = target_root / name
                if src.exists() and not dst.exists():
                    shutil.copytree(src, dst)
            for name in ["source_manifest.json", "block_manifest.json"]:
                src = prepared_dir / name
                if src.exists():
                    shutil.copy2(src, target_root / name)
        turns = rewrite_case_image_paths(turns, target_root)
        raw = rewrite_case_image_paths(raw, target_root)
        write_json(target_root / "chat_turns.json", turns)
        write_json(target_root / "raw_model_results.json", raw)

        row = {
            "case_id": case_id,
            "source_output": quality.get("source_output", ""),
            "mode": quality.get("mode", ""),
            "image_count": quality.get("image_count", 0),
            "call_count": quality.get("call_count", 0),
            "success_count": quality.get("success_count", 0),
            "failure_count": quality.get("failure_count", 0),
            "failed_group_count": len(failures),
            "need_review_turns": quality.get("need_review_turns", 0),
            "status": "deferred_safety_blocked" if deferred else (
                "needs_attention" if failures or quality.get("need_review_turns", 0) else "ready"
            ),
            "case_folder": str(target_root.as_posix()),
            "chat_turns_path": str((target_root / "chat_turns.json").as_posix()),
            "quality_report_path": str((target_root / "quality_report.json").as_posix()),
            "failure_blocks": failures,
        }
        manifest.append(row)
        if not deferred:
            combined.append(
                {
                    "case_id": case_id,
                    "summary": turns.get("summary", {}),
                    "blocks": turns.get("blocks", []),
                    "failure_blocks": failures,
                }
            )

    write_json(batch_dir / "batch_manifest.json", {
        "schema_version": "chat_turns_batch_manifest_v1",
        "batch_id": batch_id,
        "defer_failed_groups_gt": defer_failed_groups_gt,
        "cases": manifest,
    })
    write_json(batch_dir / "batch_chat_turns.json", {
        "schema_version": "chat_turns_batch_v1",
        "batch_id": batch_id,
        "cases": combined,
    })
    write_json(batch_dir / "handoff.json", {
        "schema_version": "pipeline_handoff_v1",
        "pipeline": "source_to_chat_turns01",
        "batch_id": batch_id,
        "main_entry": "batch_chat_turns.json",
        "cases_dir": "cases",
        "next_pipeline": "qingsheng_cases02",
        "notes": "Pipeline 2 should read this bundle root, not a copied standalone JSON file.",
    })
    with (batch_dir / "batch_manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "case_id",
            "source_output",
            "mode",
            "image_count",
            "call_count",
            "success_count",
            "failure_count",
            "failed_group_count",
            "need_review_turns",
            "status",
            "case_folder",
            "chat_turns_path",
            "quality_report_path",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in manifest:
            writer.writerow({field: row.get(field, "") for field in fields})
    return batch_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect chat-turn outputs into a second-stage batch folder.")
    parser.add_argument("batch_id")
    parser.add_argument("case_ids", nargs="+")
    parser.add_argument("--defer-failed-groups-gt", type=int, default=DEFAULT_DEFER_FAILED_GROUPS_GT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    print(collect(args.batch_id, args.case_ids, args.defer_failed_groups_gt, args.overwrite))


if __name__ == "__main__":
    main()
