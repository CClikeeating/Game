from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from baiou.common.io import PROJECT_ROOT, write_json
from baiou.common.project import baiou_output_root

DEFAULT_EVAL_ROOT = baiou_output_root() / "evals" / "product_cases"


def sample_case() -> dict[str, Any]:
    return {
        "case_id": "product_eval_001",
        "question": "我该怎么回？",
        "context": "",
        "images": ["tt/1 (1).jpg"],
        "expected_mode": "bailian_rag_fast",
        "expected_speaker_rule": {
            "default": "left_or_white_is_female_right_or_green_is_male",
            "allow_override_when": "user_context_or_screenshot_nickname_avatar_system_notice_is_explicit",
        },
        "expected_female_last_message": "",
        "expected_male_recent_reply": "",
        "expected_reference_topics": [],
        "human_score": {
            "speaker_attribution": "",
            "reply_quality": "",
            "retrieval_relevance": "",
            "notes": "",
        },
    }


def template_payload() -> dict[str, Any]:
    return {
        "schema_version": "baiou_product_eval_cases_v01",
        "description": "Product reply evaluation cases. Fill expected fields after manual review.",
        "cases": [sample_case()],
    }


def write_template(output_path: str | Path | None = None, overwrite: bool = False) -> dict[str, Any]:
    target = Path(output_path) if output_path else DEFAULT_EVAL_ROOT / "eval_cases_template.json"
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    if target.exists() and not overwrite:
        raise FileExistsError(f"{target} already exists. Use --overwrite to replace it.")
    payload = template_payload()
    write_json(target, payload)
    return {"template_path": str(target), "case_count": len(payload["cases"])}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a Baiou product evaluation case template.")
    parser.add_argument("--output-path")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    print(json.dumps(write_template(args.output_path, args.overwrite), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
