from pathlib import Path

from workflow.qingsheng_skill_runtime04 import run_skill as runner


class FakeClient:
    calls = []

    def __init__(self, name, config, user_id):
        self.name = name
        self.config = config
        self.user_id = user_id

    def chat(self, system_prompt, user_prompt, image_paths):
        self.__class__.calls.append(
            {
                "name": self.name,
                "user_id": self.user_id,
                "user_prompt": user_prompt,
                "image_count": len(image_paths),
            }
        )
        if self.name == "vision_model":
            return {
                "status": "model_success",
                "raw_text": "图片理解摘要：女生说让男生接她下班，男生还没回复。",
                "usage": {},
            }
        return {
            "status": "model_success",
            "raw_text": "可以回：行啊，几点下班？",
            "usage": {},
        }


def test_image_input_is_summarized_before_file_search(monkeypatch, tmp_path: Path) -> None:
    image = tmp_path / "chat.jpg"
    image.write_bytes(b"fake")
    FakeClient.calls = []
    monkeypatch.setattr(runner, "RuntimeModelClient", FakeClient)

    result = runner.run_skill(
        question="这张截图里我该怎么回？",
        images=[str(image)],
        batch_id="test_image_to_retrieval",
    )

    assert result["status"] == "model_success"
    assert result["mode"] == "rag"
    assert result["answer"] == "可以回：行啊，几点下班？"
    assert [call["name"] for call in FakeClient.calls] == ["vision_model", "text_model"]
    assert FakeClient.calls[0]["image_count"] == 1
    assert FakeClient.calls[0]["user_id"] == "51"
    assert "右侧绿色气泡=男方/用户" in FakeClient.calls[0]["user_prompt"]
    assert FakeClient.calls[1]["image_count"] == 0
    assert FakeClient.calls[1]["user_id"] == "51"
    assert "图片理解摘要：女生说让男生接她下班" in FakeClient.calls[1]["user_prompt"]
    assert "请用以上图片理解内容作为知识库检索查询的一部分" in FakeClient.calls[1]["user_prompt"]
    assert result["vision_result"]["status"] == "model_success"


def test_fast_mode_uses_vision_model_directly(monkeypatch, tmp_path: Path) -> None:
    image = tmp_path / "chat.jpg"
    image.write_bytes(b"fake")
    FakeClient.calls = []
    monkeypatch.setattr(runner, "RuntimeModelClient", FakeClient)

    result = runner.run_skill(
        question="这张截图里我该怎么回？",
        images=[str(image)],
        batch_id="test_image_fast",
        mode="fast",
    )

    assert result["status"] == "model_success"
    assert result["mode"] == "fast"
    assert result["answer"] == "图片理解摘要：女生说让男生接她下班，男生还没回复。"
    assert [call["name"] for call in FakeClient.calls] == ["vision_model"]
    assert FakeClient.calls[0]["user_id"] == "51"
    assert "右侧绿色气泡=男方/用户" in FakeClient.calls[0]["user_prompt"]
