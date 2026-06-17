from io import BytesIO
from pathlib import Path

from baiou.product.web import app as web_app


def test_baiou_web_config_uses_baiou_output(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "web.json"
    config_path.write_text(
        """
{
  "server": {"host": "0.0.0.0", "port": 9002, "debug": true},
  "upload": {"max_content_mb": 5, "allowed_image_extensions": [".png"]},
  "output": {"root": "outputs/baiou/product-test", "feedback_log": "feedback.jsonl"}
}
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(web_app, "PROJECT_ROOT", tmp_path)
    config = web_app.load_web_config(config_path)
    app = web_app.create_app(config)

    assert app.config["MAX_CONTENT_LENGTH"] == 5 * 1024 * 1024
    assert config["output_root"] == Path("outputs/baiou/product-test")
    assert web_app.allowed_image("chat.PNG", config)
    assert not web_app.allowed_image("chat.jpg", config)


def test_baiou_web_default_mode_is_bailian_rag_fast(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(web_app, "PROJECT_ROOT", tmp_path)
    config = web_app.load_web_config()

    assert config["default_mode"] == "bailian_rag_fast"
    assert "quality_local" in config["modes"]
    assert "bailian_rag_quality" in config["modes"]
    assert "bailian_rag_strategy_fast" in config["modes"]
    assert "bailian_rag_strategy_quality" in config["modes"]


def test_baiou_web_run_uses_product_runtime(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_run_reply(**kwargs):
        captured.update(kwargs)
        return {
            "status": "dry_run",
            "mode": kwargs["mode"],
            "image_understanding": "dry_run image summary",
            "answer": {
                "reply": "测试回复",
                "coach_analysis": "判断说明",
                "labels": {"聊天阶段": "破冰期"},
                "reference_segments": [],
            },
            "labels": {"聊天阶段": "破冰期"},
            "reference_segments": [],
            "output_dir": str(tmp_path / "runtime-output"),
            "reply_result": {"status": "skipped"},
        }

    monkeypatch.setattr(web_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(web_app, "run_reply", fake_run_reply)
    config = web_app.load_web_config()
    config["output_root"] = tmp_path / "outputs" / "baiou" / "product"
    client = web_app.create_app(config).test_client()

    response = client.post(
        "/run",
        data={
            "question": "怎么回？",
            "context": "刚认识",
            "mode": "quality_local",
            "dry_run": "on",
            "images": [(BytesIO(b"fake image bytes"), "chat.jpg")],
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert captured["question"] == "怎么回？"
    assert captured["context"] == "刚认识"
    assert captured["mode"] == "quality_local"
    assert captured["dry_run"] is True
    assert captured["images"]
    assert Path(captured["images"][0]).exists()
    assert "outputs" in Path(captured["images"][0]).parts
    assert "baiou" in Path(captured["images"][0]).parts
    assert "测试回复" in response.get_data(as_text=True)
    assert list((tmp_path / "outputs" / "baiou" / "product" / "runs").glob("*/summary.json"))
