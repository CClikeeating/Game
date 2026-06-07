from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .build_assets import build_assets
from .io_utils import load_settings, resolve_path, write_json


def preflight(settings: dict[str, Any], evals_path: Path) -> dict[str, Any]:
    skill_dir = resolve_path(settings["skill"]["skill_dir"])
    runner = resolve_path(settings["skill"]["eval_runner"])
    checks = {
        "skill_dir_exists": skill_dir.exists(),
        "skill_md_exists": (skill_dir / "SKILL.md").exists(),
        "eval_runner_exists": runner.exists(),
        "evals_path_exists": evals_path.exists(),
        "bash": shutil.which("bash") or "",
        "claude": shutil.which("claude") or "",
        "jq": shutil.which("jq") or "",
    }
    missing = [key for key, value in checks.items() if not value]
    return {"ok": not missing, "checks": checks, "missing": missing}


def run_baseline(batch_id: str | None = None, input_bundle: str | None = None, execute: bool = False) -> dict[str, Any]:
    settings = load_settings()
    build = build_assets(batch_id, input_bundle)
    output_root = resolve_path(settings["output"]["root"]) / build["batch_id"]
    evals_path = Path(build["evals_path"])
    status = preflight(settings, evals_path)
    run_info: dict[str, Any] = {
        "batch_id": build["batch_id"],
        "build": build,
        "preflight": status,
        "executed": False,
    }
    if not execute or not status["ok"]:
        write_json(output_root / "baseline_preflight.json", run_info)
        return run_info

    baseline = settings["baseline"]
    runner = resolve_path(settings["skill"]["eval_runner"])
    skill_dir = resolve_path(settings["skill"]["skill_dir"])
    command = [
        "bash",
        str(runner),
        "--skill-dir",
        str(skill_dir),
        "--evals-file",
        str(evals_path),
        "--label",
        baseline["label"],
        "--sut-model",
        baseline["sut_model"],
        "--judge-model",
        baseline["judge_model"],
        "--parallel",
        str(baseline["parallel"]),
    ]
    completed = subprocess.run(command, cwd=runner.parent, text=True, capture_output=True, check=False)
    run_info.update(
        {
            "executed": True,
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    )
    write_json(output_root / "baseline_run.json", run_info)
    return run_info


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight or run qingsheng generated baseline evals.")
    parser.add_argument("--batch-id")
    parser.add_argument("--input-bundle")
    parser.add_argument("--execute", action="store_true", help="Actually run the qingsheng eval shell script.")
    args = parser.parse_args()
    print(json.dumps(run_baseline(args.batch_id, args.input_bundle, args.execute), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
