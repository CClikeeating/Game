import json
from pathlib import Path

from baiou.product.runtime import reply_engine
from baiou.product.runtime.reply_engine import (
    MODE_BAILIAN_RAG_FAST,
    MODE_BAILIAN_RAG_QUALITY,
    bailian_workflow_app_config,
    build_bailian_workflow_payload,
    parse_bailian_workflow_result,
    run_bailian_rag_fast,
)


def workflow_models() -> dict:
    return {
        "bailian_workflow_apps": {
            "enabled": False,
            "provider": "bailian",
            "base_url": "https://dashscope.aliyuncs.com",
            "endpoint_path": "/api/v1/apps/{app_id}/completion",
            "api_key_env": "DASHSCOPE_API_KEY",
            "input_key": "input",
            "prompt_key": "prompt",
            "parameters_key": "parameters",
            "apps": {
                MODE_BAILIAN_RAG_FAST: {
                    "app_id_env": "BAIOU_BAILIAN_WORKFLOW_FAST_APP_ID",
                    "app_id": "",
                },
                MODE_BAILIAN_RAG_QUALITY: {
                    "app_id_env": "BAIOU_BAILIAN_WORKFLOW_QUALITY_APP_ID",
                    "app_id": "quality_app_from_config",
                },
            },
        },
        "reply_rag_model": {
            "file_search": {
                "vector_store_ids": ["fallback_store"],
                "max_num_results": 3,
            }
        },
    }


def test_workflow_app_config_uses_env_enable_and_mode_app_id(monkeypatch) -> None:
    monkeypatch.setenv("BAIOU_BAILIAN_WORKFLOW_ENABLED", "true")
    monkeypatch.setenv("BAIOU_BAILIAN_WORKFLOW_FAST_APP_ID", "fast_app_from_env")
    monkeypatch.setenv("BAIOU_BAILIAN_WORKFLOW_ENDPOINT_PATH", "/custom/apps/{app_id}/run")

    cfg, app_id = bailian_workflow_app_config(workflow_models(), MODE_BAILIAN_RAG_FAST)

    assert app_id == "fast_app_from_env"
    assert cfg["enabled"] is True
    assert cfg["app_id"] == "fast_app_from_env"
    assert cfg["endpoint_path"] == "/custom/apps/{app_id}/run"


def test_workflow_app_config_can_map_quality_mode_from_config(monkeypatch) -> None:
    monkeypatch.setenv("BAIOU_BAILIAN_WORKFLOW_ENABLED", "1")

    cfg, app_id = bailian_workflow_app_config(workflow_models(), MODE_BAILIAN_RAG_QUALITY)

    assert app_id == "quality_app_from_config"
    assert cfg["app_id"] == "quality_app_from_config"


def test_workflow_payload_has_stable_schema_and_configurable_keys() -> None:
    payload = build_bailian_workflow_payload(
        {
            "input_key": "inputs",
            "prompt_key": "query",
            "parameters_key": "params",
            "app_id_field": "app_id",
            "app_id": "app_123",
            "extra_payload": {"stream": False},
        },
        MODE_BAILIAN_RAG_FAST,
        "怎么回",
        "关系背景",
        "截图理解",
        "完整输入",
        {"推进空间": "中"},
        "user_1",
    )

    assert payload["inputs"]["schema_version"] == "baiou_reply_workflow_v1"
    assert payload["inputs"]["query"] == "完整输入"
    assert payload["inputs"]["question"] == "怎么回"
    assert payload["inputs"]["context"] == "关系背景"
    assert payload["inputs"]["image_understanding"] == "截图理解"
    assert payload["inputs"]["quality_guidance"]["推进空间"] == "中"
    assert payload["params"] == {"schema_version": "baiou_reply_workflow_v1", "mode": MODE_BAILIAN_RAG_FAST, "user_id": "user_1"}
    assert payload["app_id"] == "app_123"
    assert payload["stream"] is False


def test_workflow_result_parser_accepts_output_text_json() -> None:
    answer = {
        "reply": "那就先这样回",
        "coach_analysis": "低压力承接。",
        "labels": {},
        "risk_warning": "",
        "next_step": "等她回应",
        "reference_segments": [{"segment_id": "seg_1", "content": "sample"}],
    }
    parsed, references, status = parse_bailian_workflow_result(
        {
            "status": "workflow_success",
            "raw_response": {"output": {"text": json.dumps(answer, ensure_ascii=False)}},
        }
    )

    assert status == "workflow_success"
    assert parsed["reply"] == "那就先这样回"
    assert references[0]["segment_id"] == "seg_1"
    assert references[0]["text"] == "sample"


def test_workflow_result_parser_rejects_missing_reply() -> None:
    parsed, references, status = parse_bailian_workflow_result(
        {
            "status": "workflow_success",
            "raw_response": {"output": {"answer": {"coach_analysis": "missing reply"}}},
        }
    )

    assert status == "workflow_reply_missing"
    assert parsed["coach_analysis"] == "missing reply"
    assert references == []


def test_workflow_failure_falls_back_to_bailian_rag(monkeypatch, tmp_path: Path) -> None:
    class FakeWorkflowClient:
        def __init__(self, *_args):
            pass

        def run(self, _payload):
            return {
                "status": "workflow_call_failed",
                "client": "workflow",
                "model": "bailian_workflow_app",
                "app_id": "fast_app",
                "error": "timeout",
                "elapsed_seconds": 1,
                "usage": {},
            }

    class FakeRuntimeModelClient:
        def __init__(self, *_args):
            pass

        def chat(self, *_args):
            return {
                "status": "model_success",
                "raw_text": json.dumps({"reply": "fallback reply", "coach_analysis": "fallback"}),
                "references": [{"filename": "seg_1.md", "text": "hit"}],
            }

    monkeypatch.setenv("BAIOU_BAILIAN_WORKFLOW_ENABLED", "1")
    monkeypatch.setenv("BAIOU_BAILIAN_WORKFLOW_FAST_APP_ID", "fast_app")
    monkeypatch.setenv("BAIOU_ADMIN_CONFIG", str(tmp_path / "missing_admin_config.json"))
    monkeypatch.setattr(reply_engine, "BailianWorkflowClient", FakeWorkflowClient)
    monkeypatch.setattr(reply_engine, "RuntimeModelClient", FakeRuntimeModelClient)

    summary = run_bailian_rag_fast(
        "run_1",
        tmp_path,
        "怎么回",
        "",
        [],
        {"model_result": {}},
        "",
        "用户问题：\n怎么回",
        workflow_models(),
        "user_1",
        dry_run=False,
    )

    assert summary["status"] == "model_success"
    assert summary["answer"]["reply"] == "fallback reply"
    assert summary["workflow_attempt"]["status"] == "workflow_call_failed"
    assert summary["reply_result"]["status"] == "model_success"
