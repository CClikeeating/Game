from __future__ import annotations

import argparse
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config_loader import OUTPUTS_ROOT, load_config, read_json, write_json
from .model_client import ChatModelClient
from .pipeline import (
    REVIEW_SYSTEM_PROMPT,
    PRIMARY_SYSTEM_PROMPT,
    build_case_card,
    collect_review_rows,
    compact_model_log,
    count_turns,
    fallback_primary_judgment,
    resolve_input_bundle,
    review_prompt,
    primary_prompt,
    write_case_outputs,
    write_handoff,
    write_human_review,
    write_manifest,
)


ROOT = Path.cwd()
MAX_WORKERS_CAP = 50


@dataclass(frozen=True)
class CaseJob:
    index: int
    batch_id: str
    input_bundle: str
    case_id: str
    user_id: str


def load_plan(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [
            {str(key).strip(): str(value).strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]
    required = {"batch_id", "input_bundle", "case_id"}
    missing = [field for field in required if not rows or field not in rows[0]]
    if missing:
        raise ValueError(f"Plan missing columns: {', '.join(missing)}")
    return [row for row in rows if row.get("batch_id") and row.get("case_id")]


def build_jobs(plan_rows: list[dict[str, str]], options: dict[str, Any]) -> list[CaseJob]:
    user_id_start = int(options.get("user_id_start", 1))
    prefix = str(options.get("user_id_prefix", ""))
    max_workers = max(1, min(MAX_WORKERS_CAP, int(options.get("max_workers", 1))))
    jobs = []
    for index, row in enumerate(plan_rows, start=1):
        worker_slot = (index - 1) % max_workers
        user_id = row.get("user_id") or f"{prefix}{user_id_start + worker_slot}"
        jobs.append(
            CaseJob(
                index=index,
                batch_id=row["batch_id"],
                input_bundle=row.get("input_bundle", ""),
                case_id=row["case_id"],
                user_id=str(user_id),
            )
        )
    return jobs


def find_case(job: CaseJob) -> tuple[Path, dict[str, Any]]:
    bundle = resolve_input_bundle(job.batch_id, job.input_bundle or None)
    batch = read_json(bundle / "batch_chat_turns.json")
    for case in batch.get("cases", []):
        if case.get("case_id") == job.case_id:
            return bundle, case
    raise ValueError(f"case_id not found: {job.case_id} in {bundle}")


def process_job(
    job: CaseJob,
    output_dir: Path,
    configs: dict[str, Any],
) -> dict[str, Any]:
    started = time.time()
    bundle, case = find_case(job)
    case_id = job.case_id
    case_dir = output_dir / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    models_config = configs["models"]
    primary_client = ChatModelClient("deepseek_primary", models_config["primary"], job.user_id)
    review_client = ChatModelClient("qwen_review", models_config["review"], job.user_id)

    primary_result = primary_client.chat_json(
        PRIMARY_SYSTEM_PROMPT,
        primary_prompt(case, configs["mapping"], configs.get("annotation_memory")),
    )
    primary_judgment = primary_result.get("parsed", {})
    review_result = review_client.chat_json(
        REVIEW_SYSTEM_PROMPT,
        review_prompt(
            case,
            primary_judgment or fallback_primary_judgment(primary_result),
            configs["mapping"],
            configs.get("annotation_memory"),
        ),
    )

    case_card = build_case_card(
        batch_id=job.batch_id,
        source_bundle=bundle,
        case=case,
        schema_config=configs["schema"],
        primary_result=primary_result,
        review_result=review_result,
        eval_templates=configs["eval_templates"],
    )
    write_case_outputs(case_dir, case_card)
    review_rows = collect_review_rows(
        case_card=case_card,
        review_rules=configs["review_rules"],
        review_start=1,
    )

    return {
        "ok": True,
        "job": job,
        "case_card": case_card,
        "review_rows": review_rows,
        "manifest_row": {
            "case_id": case_id,
            "source_batch_id": job.batch_id,
            "source_bundle": str(bundle),
            "source_output": case.get("summary", {}).get("source_output", case_id),
            "turn_count": count_turns(case),
            "worker_user_id": job.user_id,
            "primary_model": primary_result.get("model", ""),
            "primary_status": primary_result.get("status", ""),
            "review_model": review_result.get("model", ""),
            "review_status": review_result.get("status", ""),
            "review_item_count": len(review_rows),
            "status": "needs_human_review" if review_rows else "ready",
            "case_folder": str(case_dir),
            "case_card_path": str(case_dir / "case_card.json"),
            "elapsed_seconds": round(time.time() - started, 2),
        },
        "model_log": [
            compact_model_log(case_id, "primary", primary_result),
            compact_model_log(case_id, "review", review_result),
        ],
    }


def renumber_review_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index, row in enumerate(rows, start=1):
        row["review_id"] = f"review_{index:04d}"
    return rows


def run_case_plan(
    plan_path: str,
    output_batch_id: str,
    max_workers: int | None = None,
) -> dict[str, Any]:
    options = load_config("run_options.yaml").get("case_plan", {})
    if max_workers is not None:
        options["max_workers"] = max_workers
    options["max_workers"] = max(1, min(MAX_WORKERS_CAP, int(options.get("max_workers", 1))))

    models_config = load_config("models.yaml")
    configs = {
        "models": models_config,
        "mapping": load_config("qingsheng_mapping.yaml"),
        "annotation_memory": load_config("annotation_memory.yaml"),
        "eval_templates": load_config("eval_templates.yaml"),
        "review_rules": load_config("review_rules.yaml"),
        "schema": load_config("case_schema.yaml"),
    }

    jobs = build_jobs(load_plan(Path(plan_path)), options)
    output_dir = OUTPUTS_ROOT / output_batch_id
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    model_log: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=options["max_workers"]) as executor:
        futures = [executor.submit(process_job, job, output_dir, configs) for job in jobs]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - batch should continue and report all failed jobs.
                errors.append({"status": "failed", "error": f"{exc.__class__.__name__}: {exc}"})
                if options.get("fail_fast", False):
                    raise
                continue
            manifest_rows.append(result["manifest_row"])
            review_rows.extend(result["review_rows"])
            model_log.extend(result["model_log"])
            print(
                json.dumps(
                    {
                        "case_id": result["manifest_row"]["case_id"],
                        "user_id": result["manifest_row"]["worker_user_id"],
                        "review_items": result["manifest_row"]["review_item_count"],
                        "elapsed_seconds": result["manifest_row"]["elapsed_seconds"],
                    },
                    ensure_ascii=False,
                )
            )

    manifest_rows.sort(key=lambda row: row.get("case_id", ""))
    review_rows = renumber_review_rows(review_rows)
    write_manifest(output_dir, output_batch_id, manifest_rows)
    write_human_review(output_dir / "human_review.xlsx", review_rows, configs["review_rules"])
    write_json(
        output_dir / "model_call_log.json",
        {
            "output_batch_id": output_batch_id,
            "plan_path": str(Path(plan_path)),
            "max_workers": options["max_workers"],
            "user_id_strategy": options.get("user_id_strategy", ""),
            "calls": model_log,
            "errors": errors,
        },
    )
    write_json(
        output_dir / "handoff.json",
        {
            "schema_version": "pipeline_handoff_v1",
            "pipeline": "qingsheng_cases02",
            "batch_id": output_batch_id,
            "source_plan": str(Path(plan_path)),
            "main_entry": "batch_case_manifest.json",
            "cases_dir": "cases",
            "next_pipeline": "qingsheng_skill_eval03",
            "notes": "Built from a multi-batch case plan. Pipeline 3 should read this bundle root.",
        },
    )
    return {
        "output_batch_id": output_batch_id,
        "output_dir": str(output_dir),
        "case_count": len(manifest_rows),
        "review_rows": len(review_rows),
        "error_count": len(errors),
        "max_workers": options["max_workers"],
        "primary_model": models_config["primary"]["model"],
        "review_model": models_config["review"]["model"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run qingsheng case conversion from a cross-batch case plan.")
    parser.add_argument("--plan", required=True, help="CSV with batch_id,input_bundle,case_id columns.")
    parser.add_argument("--output-batch-id", required=True)
    parser.add_argument("--max-workers", type=int)
    args = parser.parse_args()
    result = run_case_plan(args.plan, args.output_batch_id, args.max_workers)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
