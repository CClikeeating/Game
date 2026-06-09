from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .run_skill import read_json, resolve_path, run_skill, write_json


def run_eval_sample(
    evals_file: str,
    batch_id: str,
    limit: int,
    mode: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    data = read_json(resolve_path(evals_file))
    evals = data.get("evals", [])
    if mode:
        evals = [item for item in evals if item.get("mode") == mode]
    evals = evals[:limit]
    results = []
    for item in evals:
        result = run_skill(
            question=item.get("prompt", ""),
            context=f"这是自动测试题。expected_output 给评估者参考，不要在回答中复述：\n{item.get('expected_output', '')}",
            batch_id=batch_id,
            dry_run=dry_run,
        )
        results.append(
            {
                "eval_id": item.get("id"),
                "case_id": item.get("case_id"),
                "mode": item.get("mode"),
                "status": result.get("status"),
                "result_path": result.get("result_path"),
            }
        )
    output_root = resolve_path("outputs/qingsheng_skill_runtime04") / batch_id
    summary = {"batch_id": batch_id, "evals_file": evals_file, "count": len(results), "results": results}
    write_json(output_root / "eval_sample_summary.json", summary)
    return summary


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run qingsheng runtime on generated eval samples.")
    parser.add_argument("--evals-file", required=True)
    parser.add_argument("--batch-id", default="eval_sample")
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--mode", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run_eval_sample(args.evals_file, args.batch_id, args.limit, args.mode, args.dry_run),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
