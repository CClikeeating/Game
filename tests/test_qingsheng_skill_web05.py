from io import BytesIO
from pathlib import Path

from workflow.qingsheng_skill_web05 import app as web_app


def test_run_page_calls_runtime_and_renders_result(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_run_skill(**kwargs):
        captured.update(kwargs)
        return {
            "status": "dry_run",
            "answer": "测试回复",
            "mode": kwargs["mode"],
            "vision_result": {"raw_text": "图片摘要"},
            "model_result": {"status": "dry_run"},
            "prompt_preview": "prompt.json",
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
            "dry_run": "on",
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "测试回复" in html
    assert "图片摘要" in html
    assert "dry_run" in html
    assert captured["question"] == "她什么意思？"
    assert captured["context"] == "微信聊天"
    assert captured["mode"] == "fast"
    assert captured["dry_run"] is True


def test_run_page_saves_uploaded_images(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_run_skill(**kwargs):
        captured.update(kwargs)
        return {
            "status": "model_success",
            "answer": "已处理图片",
            "mode": kwargs["mode"],
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
            "images": [image],
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert captured["images"]
    saved = Path(captured["images"][0])
    assert saved.exists()
    assert saved.name == "chat.jpg"
    assert "outputs" in saved.parts
    summary_files = list((tmp_path / "outputs" / "qingsheng_skill_web05" / "runs").glob("*/summary.json"))
    assert summary_files
