import json
from pathlib import Path

from baiou.case_pipeline.production import build_segments


class FakeChatJsonClient:
    def __init__(self, section: str, config: dict, user_id: str) -> None:
        self.section = section

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        return {
            "status": "model_json_invalid",
            "model": "fake-model",
            "provider": "fake",
            "raw_text": "not valid json",
            "parsed": {},
            "elapsed_seconds": 0,
            "usage": {},
        }


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_process_job_persists_raw_model_results_on_primary_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(build_segments, "ChatJsonClient", FakeChatJsonClient)
    monkeypatch.setattr(build_segments, "build_case_prompt", lambda case: "prompt")

    job = build_segments.CaseJob(index=1, case={"case_id": "case_001", "blocks": []}, user_id="1")
    result = build_segments.process_job(
        job,
        tmp_path,
        {"case_primary": {"enabled": True}, "case_review": {"enabled": True}},
        skip_review=True,
    )

    case_dir = tmp_path / "cases" / "case_001"
    assert result["manifest_row"]["primary_status"] == "model_json_invalid"
    assert read_json(case_dir / "primary_result.json")["raw_text"] == "not valid json"
    assert read_json(case_dir / "review_result.json")["status"] == "skipped"
