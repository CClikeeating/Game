from __future__ import annotations

import argparse
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .collect_batch import collect
from .config_loader import load_config
from .run_pipeline import run


MAX_WORKERS_CAP = 50


@dataclass(frozen=True)
class CaseJob:
    index: int
    case_id: str
    source_output: str
    mode: str
    limit: int | None
    user_id: str


def load_plan(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [
            {str(key).strip(): str(value).strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]
    required = {"case_id", "source_output"}
    missing = [field for field in required if not rows or field not in rows[0]]
    if missing:
        raise ValueError(f"Plan missing columns: {', '.join(missing)}")
    return [row for row in rows if row.get("case_id") and row.get("source_output")]


def parse_limit(value: str, default: Any) -> int | None:
    text = str(value or "").strip()
    if text:
        return int(text)
    if default in ("", None):
        return None
    return int(default)


def build_jobs(plan_rows: list[dict[str, str]], options: dict[str, Any]) -> list[CaseJob]:
    max_workers = max(1, min(MAX_WORKERS_CAP, int(options.get("max_workers", 1))))
    user_id_start = int(options.get("user_id_start", 1))
    prefix = str(options.get("user_id_prefix", ""))
    default_mode = str(options.get("mode", "group"))
    default_limit = options.get("limit")
    jobs = []
    for index, row in enumerate(plan_rows, start=1):
        worker_slot = (index - 1) % max_workers
        user_id = row.get("user_id") or f"{prefix}{user_id_start + worker_slot}"
        jobs.append(
            CaseJob(
                index=index,
                case_id=row["case_id"],
                source_output=row["source_output"],
                mode=row.get("mode") or default_mode,
                limit=parse_limit(row.get("limit", ""), default_limit),
                user_id=str(user_id),
            )
        )
    return jobs


def process_job(job: CaseJob) -> dict[str, Any]:
    started = time.time()
    result = run(job.case_id, job.source_output, job.mode, job.limit, job.user_id)
    return {
        "case_id": job.case_id,
        "source_output": job.source_output,
        "mode": job.mode,
        "user_id": job.user_id,
        "status": "ok",
        "elapsed_seconds": round(time.time() - started, 2),
        "result": result,
    }


def run_case_plan(
    plan_path: str,
    batch_id: str,
    max_workers: int | None = None,
    defer_failed_groups_gt: int | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    options = load_config("run_options.yaml").get("case_plan", {})
    if max_workers is not None:
        options["max_workers"] = max_workers
    options["max_workers"] = max(1, min(MAX_WORKERS_CAP, int(options.get("max_workers", 1))))
    if defer_failed_groups_gt is not None:
        options["defer_failed_groups_gt"] = defer_failed_groups_gt
    if overwrite:
        options["overwrite"] = True

    jobs = build_jobs(load_plan(Path(plan_path)), options)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=options["max_workers"]) as executor:
        futures = [executor.submit(process_job, job) for job in jobs]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - keep the batch moving and report failures.
                errors.append({"status": "failed", "error": f"{exc.__class__.__name__}: {exc}"})
                if options.get("fail_fast", False):
                    raise
                continue
            results.append(result)
            print(
                json.dumps(
                    {
                        "case_id": result["case_id"],
                        "user_id": result["user_id"],
                        "elapsed_seconds": result["elapsed_seconds"],
                        "failure_count": result["result"].get("failure_count", 0),
                        "need_review_turns": result["result"].get("need_review_turns", 0),
                    },
                    ensure_ascii=False,
                )
            )

    case_ids = [result["case_id"] for result in sorted(results, key=lambda item: item["case_id"])]
    batch_dir = collect(
        batch_id,
        case_ids,
        int(options.get("defer_failed_groups_gt", 1)),
        bool(options.get("overwrite", False)),
    ) if case_ids else None
    run_log = {
        "schema_version": "source_to_chat_turns_case_plan_run_v1",
        "batch_id": batch_id,
        "plan_path": str(Path(plan_path)),
        "max_workers": options["max_workers"],
        "case_count": len(case_ids),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }
    if batch_dir:
        from .run_pipeline import write_json

        write_json(batch_dir / "case_plan_run_log.json", run_log)
    return {
        "batch_id": batch_id,
        "batch_dir": str(batch_dir) if batch_dir else "",
        "case_count": len(case_ids),
        "error_count": len(errors),
        "max_workers": options["max_workers"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run source-to-chat-turns cases from a concurrent case plan.")
    parser.add_argument("--plan", required=True, help="CSV with case_id,source_output columns.")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--max-workers", type=int)
    parser.add_argument("--defer-failed-groups-gt", type=int)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    result = run_case_plan(args.plan, args.batch_id, args.max_workers, args.defer_failed_groups_gt, args.overwrite)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
