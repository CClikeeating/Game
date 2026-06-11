from io import BytesIO
from pathlib import Path

from workflow.qingsheng_skill_web05 import app as web_app


def test_web_config_controls_upload_output_and_limits(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "web.json"
    config_path.write_text(
        """
{
  "server": {
    "host": "0.0.0.0",
    "port": 9001,
    "debug": true
  },
  "upload": {
    "max_content_mb": 3,
    "allowed_image_extensions": [".png"]
  },
  "output": {
    "root": "custom-web-output"
  }
}
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(web_app, "ROOT", tmp_path)
    config = web_app.load_web_config(config_path)
    app = web_app.create_app(config)

    assert app.config["MAX_CONTENT_LENGTH"] == 3 * 1024 * 1024
    assert config["output_root"] == Path("custom-web-output")
    assert web_app.allowed_image(".chat.PNG", config)
    assert not web_app.allowed_image("chat.jpg", config)


def test_run_page_calls_runtime_and_renders_diagnostics(monkeypatch, tmp_path: Path) -> None:
    captured = {}
    prompt_path = tmp_path / "prompt.json"
    prompt_path.write_text(
        """
{
  "answer_style": "analysis",
  "system_prompt_chars": 123,
  "system_prompt_preview": "系统提示词预览",
  "user_prompt": "用户提示词内容",
  "image_understanding": "图片理解内容"
}
""".strip(),
        encoding="utf-8",
    )

    def fake_run_skill(**kwargs):
        captured.update(kwargs)
        return {
            "status": "model_success",
            "answer": "测试回复",
            "mode": kwargs["mode"],
            "answer_style": kwargs["answer_style"],
            "vision_result": {
                "client": "vision_model",
                "model": "qwen3-vl-flash",
                "status": "model_success",
                "elapsed_seconds": 2.5,
                "user_id": "51",
                "raw_text": "图片摘要",
                "usage": {"total_tokens": 30, "prompt_tokens": 20, "completion_tokens": 10},
            },
            "model_result": {
                "client": "text_model",
                "model": "qwen3.7-plus",
                "status": "model_success",
                "elapsed_seconds": 4.0,
                "user_id": "51",
                "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
                "references": [{"filename": "case_001.md", "score": 0.86, "text": "引用片段"}],
            },
            "prompt_preview": str(prompt_path),
            "result_path": "result.json",
        }

    monkeypatch.setattr(web_app, "ROOT", tmp_path)
    monkeypatch.setattr(web_app, "run_skill", fake_run_skill)
    client = web_app.create_app().test_client()

    response = client.post(
        "/run",
        data={
            "question": "她什么意思？",
            "context": "微信聊天",
            "mode": "fast",
            "answer_style": "analysis",
            "dry_run": "on",
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "测试回复" in html
    assert "图片摘要" in html
    assert "qwen3-vl-flash" in html
    assert "total=150" in html
    assert "case_001.md" in html
    assert "用户提示词内容" in html
    assert "系统提示词预览" in html
    assert captured["question"] == "她什么意思？"
    assert captured["context"] == "微信聊天"
    assert captured["mode"] == "fast"
    assert captured["answer_style"] == "analysis"
    assert captured["dry_run"] is True


def test_run_page_saves_uploaded_images(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_run_skill(**kwargs):
        captured.update(kwargs)
        return {
            "status": "model_success",
            "answer": "已处理图片",
            "mode": kwargs["mode"],
            "answer_style": kwargs["answer_style"],
            "vision_result": {},
            "model_result": {"status": "model_success"},
            "prompt_preview": "",
            "result_path": "",
        }

    monkeypatch.setattr(web_app, "ROOT", tmp_path)
    monkeypatch.setattr(web_app, "run_skill", fake_run_skill)
    client = web_app.create_app().test_client()
    image = (BytesIO(b"fake image bytes"), "chat.jpg")

    response = client.post(
        "/run",
        data={
            "question": "怎么回？",
            "mode": "rag",
            "answer_style": "simple",
            "images": [image],
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert captured["images"]
    assert captured["answer_style"] == "simple"
    saved = Path(captured["images"][0])
    assert saved.exists()
    assert saved.name == "chat.jpg"
    assert "outputs" in saved.parts
    summary_files = list((tmp_path / "outputs" / "qingsheng_skill_web05" / "runs").glob("*/summary.json"))
    assert summary_files
