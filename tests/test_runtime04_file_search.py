import json

from workflow.qingsheng_skill_runtime04.model_client import RuntimeModelClient


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(
            {
                "output_text": "可以这样回。",
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": "可以这样回。",
                                "annotations": [
                                    {
                                        "type": "file_citation",
                                        "file_id": "file_001",
                                        "filename": "case_001.md",
                                        "quote": "相似案例片段",
                                        "score": 0.91,
                                    }
                                ],
                            }
                        ]
                    }
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")


def test_file_search_client_uses_responses_api_and_extracts_references(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = RuntimeModelClient(
        "text_model",
        {
            "enabled": True,
            "provider": "qwen_dashscope",
            "api_style": "openai_compatible_responses_file_search",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen3.7-plus",
            "api_key_env": "DASHSCOPE_API_KEY",
            "temperature": 0.2,
            "timeout_seconds": 180,
            "max_tokens": 5000,
            "enable_thinking": False,
            "file_search": {
                "enabled": True,
                "vector_store_ids": ["vc8y71trwg"],
                "max_num_results": 3,
                "include_results": True,
                "tool_choice": "required",
            },
        },
        "51",
    )

    result = client.chat("skill prompt", "用户问题", [])

    assert result["status"] == "model_success"
    assert result["raw_text"] == "可以这样回。"
    assert result["references"][0]["filename"] == "case_001.md"
    assert result["references"][0]["text"] == "相似案例片段"
    assert captured["url"].endswith("/responses")
    assert captured["payload"]["instructions"] == "skill prompt"
    assert captured["payload"]["input"] == "用户问题"
    assert captured["payload"]["user_id"] == "51"
    assert captured["payload"]["include"] == ["file_search_call.results"]
    assert captured["payload"]["tool_choice"] == "required"
    assert captured["payload"]["enable_thinking"] is False
    assert captured["payload"]["tools"] == [
        {
            "type": "file_search",
            "vector_store_ids": ["vc8y71trwg"],
            "max_num_results": 3,
        }
    ]
