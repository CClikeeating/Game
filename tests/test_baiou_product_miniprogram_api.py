from __future__ import annotations

import sqlite3
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from baiou.product.api import app as api_app
from baiou.product.storage import ProductStore


def make_config(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    config = api_app.load_api_config()
    config.update(
        {
            "sqlite_path": str(tmp_path / "app.db"),
            "upload_root": str(tmp_path / "uploads"),
            "max_conversations_per_user": 2,
            "history_turns_for_reply": 1,
            "daily_reply_quota": 10,
            "grant_initial_credits_to_non_wechat_users": True,
            "max_images_per_reply": 2,
            "min_images_per_reply": 0,
            "max_image_mb": 1,
            "max_image_bytes": 1024 * 1024,
            "default_user_id": "test_user",
        }
    )
    config.update(overrides)
    return config


def client_with_runtime(monkeypatch, tmp_path: Path, config: dict[str, Any] | None = None):
    captured: list[dict[str, Any]] = []

    def fake_run_reply(**kwargs):
        captured.append(kwargs)
        return {
            "status": "model_success",
            "run_id": f"runtime_{len(captured)}",
            "image_understanding": "image summary" if kwargs.get("images") else "",
            "answer": {
                "reply": f"reply {len(captured)}",
                "coach_analysis": "coach",
                "risk_warning": "",
                "next_step": "next",
                "labels": {"stage": "test"},
                "reference_segments": ["seg_1"],
            },
            "labels": {"stage": "test"},
            "reference_segments": [{"segment_id": "seg_1", "text": "sample", "filename": "seg_1.md", "match_reasons": ["hit"]}],
            "output_dir": str(tmp_path / "secret-output"),
            "vision_result": {"status": "model_success", "model": "vision-test", "elapsed_seconds": 1.25, "usage": {"total_tokens": 101}},
            "label_result": {"status": "model_success", "model": "label-test", "elapsed_seconds": 2.5, "usage": {"total_tokens": 202}},
            "reply_result": {"status": "model_success", "model": "reply-test", "elapsed_seconds": 3.75, "usage": {"total_tokens": 303}},
        }

    monkeypatch.setattr(api_app, "run_reply", fake_run_reply)
    app = api_app.create_app(config or make_config(tmp_path))
    return app.test_client(), captured


def auth_headers(user_id: str = "test_user") -> dict[str, str]:
    return {"Authorization": f"Bearer {user_id}"}


def admin_headers(token: str = "admin-secret") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login_and_default_conversation(client) -> str:
    response = client.post("/api/v1/auth/login", json={"user_id": "test_user"})
    assert response.status_code == 200
    response = client.get("/api/v1/conversations", headers=auth_headers())
    data = response.get_json()
    assert data["ok"] is True
    assert len(data["conversations"]) == 1
    return data["conversations"][0]["conversation_id"]


def test_login_creates_default_conversation_and_reports_limits(monkeypatch, tmp_path: Path) -> None:
    client, _captured = client_with_runtime(monkeypatch, tmp_path)

    response = client.post("/api/v1/auth/login", json={"user_id": "test_user"})
    data = response.get_json()

    assert response.status_code == 200
    assert data["user"]["user_id"] == "test_user"
    assert data["limits"]["daily_reply_remaining"] == 10
    conversations = client.get("/api/v1/conversations", headers=auth_headers()).get_json()["conversations"]
    assert len(conversations) == 1
    assert conversations[0]["status"] == "active"


def test_wechat_code_login_creates_session_token(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, dev_login_enabled=False, wechat_appid="wx_app", wechat_secret="secret")
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)
    monkeypatch.setattr(api_app, "wechat_code_to_session", lambda _config, code: ({"openid": f"openid_{code}"}, ""))

    response = client.post("/api/v1/auth/login", json={"code": "login-code"})
    data = response.get_json()
    token = data["token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    forged = client.get("/api/v1/me", headers={"Authorization": "Bearer fake_user"})

    assert response.status_code == 200
    assert token != data["user"]["user_id"]
    assert data["user"]["user_id"].startswith("wx_")
    assert me.status_code == 200
    assert forged.status_code == 401


def test_login_requires_code_when_dev_login_is_disabled(monkeypatch, tmp_path: Path) -> None:
    client, _captured = client_with_runtime(monkeypatch, tmp_path, make_config(tmp_path, dev_login_enabled=False))

    response = client.post("/api/v1/auth/login", json={})

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "login_code_required"


def test_sqlite_store_migrates_existing_product_db(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE users (
                user_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE conversations (
                conversation_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE reply_runs (
                run_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                question TEXT NOT NULL,
                status TEXT NOT NULL,
                answer_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE uploads (
                upload_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                original_name TEXT NOT NULL,
                path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )

    ProductStore(db_path)

    with sqlite3.connect(db_path) as conn:
        columns = {
            table: {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for table in ["users", "conversations", "reply_runs", "uploads"]
        }
    assert {"openid", "nickname", "plan"} <= columns["users"]
    assert {"background", "status"} <= columns["conversations"]
    assert {"runtime_context", "image_understanding", "reference_segments_json", "runtime_run_id"} <= columns["reply_runs"]
    assert "consumed_at" in columns["uploads"]


def test_web_alpha_access_code_creates_session_without_exposing_code(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, web_access_required=True, web_access_codes=["test-code"])
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)

    html = client.get("/app").get_data(as_text=True)
    denied = client.post("/api/v1/auth/web-login", json={"access_code": "wrong"})
    dev_login = client.post("/api/v1/auth/login", json={})
    login = client.post("/api/v1/auth/web-login", json={"access_code": "test-code"})
    token = login.get_json()["token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    forged = client.get("/api/v1/me", headers={"Authorization": "Bearer fake_user"})
    anonymous = client.get("/api/v1/me")

    assert "Baiou" in html
    assert "文字极速" in html
    assert "截图回复" in html
    assert "input_type" in html
    assert "截图理解" not in html
    assert "参考片段" not in html
    assert "已选择 0 张 / 最多 3 张" in html
    assert "格式不支持" in html
    assert "正在理解截图" in html
    assert "正在生成回复" in html
    assert "已等待" in html
    assert "日常接话" in html
    assert "安全无压力，接住话题" in html
    assert "暧昧推荐" in html
    assert "破解测试，高框架推拉" in html
    assert "文字接话" in html
    assert "bailian_rag_quality" not in html
    assert "bailian_rag_strategy_fast" not in html
    assert "test-code" not in html
    assert denied.status_code == 401
    assert dev_login.status_code == 401
    assert login.status_code == 200
    assert token
    assert me.status_code == 200
    assert forged.status_code == 401
    assert anonymous.status_code == 401


def test_conversation_limit_is_enforced_on_server(monkeypatch, tmp_path: Path) -> None:
    client, _captured = client_with_runtime(monkeypatch, tmp_path)
    login_and_default_conversation(client)

    first = client.post("/api/v1/conversations", headers=auth_headers(), json={"title": "second"})
    second = client.post("/api/v1/conversations", headers=auth_headers(), json={"title": "third"})

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.get_json()["error"]["code"] == "conversation_limit_reached"


def test_reply_uses_only_current_conversation_recent_history(monkeypatch, tmp_path: Path) -> None:
    client, captured = client_with_runtime(monkeypatch, tmp_path)
    conv_a = login_and_default_conversation(client)
    conv_b = client.post("/api/v1/conversations", headers=auth_headers(), json={"title": "other", "background": "other background"}).get_json()[
        "conversation"
    ]["conversation_id"]
    client.patch(f"/api/v1/conversations/{conv_a}", headers=auth_headers(), json={"background": "current background"})

    client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv_a, "question": "old question"})
    client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv_a, "question": "recent question"})
    client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv_b, "question": "other question"})
    client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv_a, "question": "final question", "context": "fresh note"})

    final_context = captured[-1]["context"]
    assert "current background" in final_context
    assert "fresh note" in final_context
    assert "recent question" in final_context
    assert "old question" not in final_context
    assert "other background" not in final_context
    assert "other question" not in final_context


def test_credits_balance_blocks_generation(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, daily_reply_quota=100, initial_credits=1)
    client, captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)

    first = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "one"})
    second = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "two"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.get_json()["error"]["code"] == "credits_insufficient"
    assert len(captured) == 1


def test_web_ip_quota_uses_mode_unit_cost_and_dry_run_is_free(monkeypatch, tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        web_access_required=True,
        web_access_codes=["test-code"],
        web_ip_daily_quota=3,
        web_site_daily_quota=10,
        mode_unit_costs={"bailian_rag_fast": 1, "bailian_rag_strategy_quality": 2},
    )
    client, captured = client_with_runtime(monkeypatch, tmp_path, config)
    login = client.post("/api/v1/auth/web-login", json={"access_code": "test-code"}).get_json()
    headers = {"Authorization": f"Bearer {login['token']}", "X-Forwarded-For": "203.0.113.8"}
    conv = client.get("/api/v1/conversations", headers=headers).get_json()["conversations"][0]["conversation_id"]

    dry = client.post(
        "/api/v1/replies",
        headers=headers,
        json={"conversation_id": conv, "question": "dry", "mode": "bailian_rag_strategy_quality", "dry_run": True},
    )
    first = client.post(
        "/api/v1/replies",
        headers=headers,
        json={"conversation_id": conv, "question": "one", "mode": "bailian_rag_strategy_quality"},
    )
    second = client.post(
        "/api/v1/replies",
        headers=headers,
        json={"conversation_id": conv, "question": "two", "mode": "bailian_rag_strategy_quality"},
    )

    assert dry.status_code == 200
    assert first.status_code == 200
    assert first.get_json()["limits"]["web_ip_daily_remaining"] == 1
    assert second.status_code == 429
    assert second.get_json()["error"]["code"] == "ip_daily_quota_exhausted"
    assert len(captured) == 2


def test_legacy_user_modes_fall_back_to_fast_mode(monkeypatch, tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        min_images_per_reply=0,
        default_mode="bailian_rag_quality",
        modes={
            "bailian_rag_fast": "日常接话",
            "bailian_rag_quality": "旧质量模式",
            "bailian_rag_strategy_fast": "旧策略模式",
            "bailian_rag_strategy_quality": "暧昧推荐",
        },
        mode_unit_costs={
            "bailian_rag_fast": 1,
            "bailian_rag_quality": 9,
            "bailian_rag_strategy_fast": 8,
            "bailian_rag_strategy_quality": 2,
        },
    )
    client, captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)
    health = client.get("/api/v1/health").get_json()

    old_quality = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "old quality", "mode": "bailian_rag_quality"})
    old_strategy = client.post(
        "/api/v1/replies",
        headers=auth_headers(),
        json={"conversation_id": conv, "question": "old strategy", "mode": "bailian_rag_strategy_fast"},
    )
    old_default = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "old default"})
    allowed = client.post(
        "/api/v1/replies",
        headers=auth_headers(),
        json={"conversation_id": conv, "question": "allowed", "mode": "bailian_rag_strategy_quality"},
    )

    assert health["default_mode"] == "bailian_rag_fast"
    assert health["modes"] == {"bailian_rag_fast": "日常接话", "bailian_rag_strategy_quality": "暧昧推荐"}
    assert health["limits"]["mode_unit_costs"] == {"bailian_rag_fast": 1, "bailian_rag_strategy_quality": 2}
    assert old_quality.status_code == 200
    assert old_strategy.status_code == 200
    assert old_default.status_code == 200
    assert allowed.status_code == 200
    assert [item["mode"] for item in captured] == [
        "bailian_rag_fast",
        "bailian_rag_fast",
        "bailian_rag_fast",
        "bailian_rag_strategy_quality",
    ]


def test_upload_limits_and_staged_upload_ids(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, max_images_per_reply=1)
    client, captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)

    too_many = client.post(
        "/api/v1/replies",
        headers=auth_headers(),
        data={
            "conversation_id": conv,
            "question": "with images",
            "images": [(BytesIO(b"a"), "a.jpg"), (BytesIO(b"b"), "b.jpg")],
        },
        content_type="multipart/form-data",
    )
    assert too_many.status_code == 400
    assert too_many.get_json()["error"]["code"] == "too_many_images"

    upload = client.post(
        "/api/v1/uploads",
        headers=auth_headers(),
        data={"file": (BytesIO(b"image-bytes"), "chat.jpg")},
        content_type="multipart/form-data",
    )
    upload_id = upload.get_json()["upload"]["upload_id"]
    reply = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "use image", "upload_ids": [upload_id]})

    assert upload.status_code == 201
    assert reply.status_code == 200
    assert captured[-1]["images"]
    assert Path(captured[-1]["images"][0]).exists()


def test_reply_requires_image_when_configured(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, min_images_per_reply=1)
    client, captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)

    response = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "no image"})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "image_required"
    assert captured == []


def test_text_only_reply_allows_no_image_and_forces_fast_mode(monkeypatch, tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        min_images_per_reply=1,
        mode_unit_costs={"bailian_rag_fast": 1, "bailian_rag_strategy_quality": 2},
    )
    client, captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)

    response = client.post(
        "/api/v1/replies",
        headers=auth_headers(),
        json={
            "conversation_id": conv,
            "question": "女生说：刚到家，有点累",
            "mode": "bailian_rag_strategy_quality",
            "input_type": "text_only",
        },
    )
    data = response.get_json()

    assert response.status_code == 200
    assert captured[-1]["images"] == []
    assert captured[-1]["mode"] == "bailian_rag_fast"
    assert data["reply_run"]["input_type"] == "text_only"
    assert data["reply_run"]["image_count"] == 0
    assert data["limits"]["daily_reply_remaining"] == 9


def test_text_only_reply_rejects_images_to_keep_entry_unambiguous(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, min_images_per_reply=1)
    client, captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)

    response = client.post(
        "/api/v1/replies",
        headers=auth_headers(),
        data={
            "conversation_id": conv,
            "question": "女生说：刚到家",
            "input_type": "text_only",
            "images": (BytesIO(b"image-bytes"), "chat.jpg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "text_only_images_not_allowed"
    assert captured == []


def test_feedback_binds_to_reply_without_exposing_internal_paths(monkeypatch, tmp_path: Path) -> None:
    client, _captured = client_with_runtime(monkeypatch, tmp_path)
    conv = login_and_default_conversation(client)

    response = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "hello"})
    data = response.get_json()
    run_id = data["reply_run"]["run_id"]
    feedback = client.post(
        "/api/v1/feedback",
        headers=auth_headers(),
        json={"conversation_id": conv, "run_id": run_id, "rating": "good", "notes": "works"},
    )

    assert feedback.status_code == 201
    assert feedback.get_json()["feedback"]["run_id"] == run_id
    assert "secret-output" not in str(data)
    assert "output_dir" not in str(data)
    assert "image_understanding" not in data["reply_run"]
    assert "reference_segments" not in data["reply_run"]


def test_admin_stats_and_feedback_export_require_token(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, admin_token="admin-secret")
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)
    response = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "hello"})
    run_id = response.get_json()["reply_run"]["run_id"]
    client.post(
        "/api/v1/feedback",
        headers=auth_headers(),
        json={"conversation_id": conv, "run_id": run_id, "rating": "bad", "notes": "too much"},
    )

    denied = client.get("/api/v1/admin/stats")
    query_token = client.get("/api/v1/admin/stats?token=admin-secret")
    stats = client.get("/api/v1/admin/stats", headers=admin_headers())
    feedback = client.get("/api/v1/admin/feedback", headers=admin_headers())
    export = client.get("/api/v1/admin/feedback/export.csv", headers=admin_headers())

    assert denied.status_code == 401
    assert query_token.status_code == 401
    assert stats.status_code == 200
    assert stats.get_json()["stats"]["totals"]["reply_runs"] == 1
    assert "site_quota" in stats.get_json()["stats"]
    assert feedback.get_json()["feedback"][0]["notes"] == "too much"
    assert feedback.get_json()["feedback"][0]["reply"] == "reply 1"
    assert export.status_code == 200
    assert "too much" in export.get_data(as_text=True)
    assert "reply 1" in export.get_data(as_text=True)


def test_admin_page_exports_csv_with_authorization_header(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, admin_token="admin-secret")
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)

    html = client.get("/admin").get_data(as_text=True)

    assert "?token=" not in html
    assert 'fetch("/api/v1/admin/feedback/export.zip"' in html
    assert "/api/v1/admin/reply-runs?limit=20" in html
    assert '"Authorization": "Bearer " + tokenInput.value.trim()' in html


def test_admin_feedback_review_zip_includes_csv_and_screenshots(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, admin_token="admin-secret", min_images_per_reply=1)
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)
    upload = client.post(
        "/api/v1/uploads",
        headers=auth_headers(),
        data={"file": (BytesIO(b"image-bytes"), "chat.jpg")},
        content_type="multipart/form-data",
    )
    upload_id = upload.get_json()["upload"]["upload_id"]
    response = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "hello", "upload_ids": [upload_id]})
    run_id = response.get_json()["reply_run"]["run_id"]
    client.post(
        "/api/v1/feedback",
        headers=auth_headers(),
        json={"conversation_id": conv, "run_id": run_id, "rating": "bad", "notes": "review"},
    )

    export = client.get("/api/v1/admin/feedback/export.zip", headers=admin_headers())

    assert export.status_code == 200
    with ZipFile(BytesIO(export.data)) as archive:
        names = archive.namelist()
        assert "feedback.csv" in names
        assert any(name.startswith(f"screenshots/{run_id}/") and name.endswith(".jpg") for name in names)
        assert "review" in archive.read("feedback.csv").decode("utf-8-sig")


def test_redeem_code_adds_user_credits(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, admin_token="admin-secret", daily_reply_quota=10)
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)
    login_and_default_conversation(client)
    created = client.post(
        "/api/v1/admin/redeem-codes",
        headers=admin_headers(),
        json={"code": "MORE20", "daily_reply_quota": 20, "max_uses": 1},
    )

    redeemed = client.post("/api/v1/redeem-codes/redeem", headers=auth_headers(), json={"code": " more20 "})
    again = client.post("/api/v1/redeem-codes/redeem", headers=auth_headers(), json={"code": "MORE20"})

    assert created.status_code == 200
    assert redeemed.status_code == 200
    assert redeemed.get_json()["limits"]["credits_balance"] == 30
    assert redeemed.get_json()["limits"]["daily_reply_remaining"] == 30
    assert again.status_code == 409


def test_exhausted_redeem_code_reports_exhausted_for_other_user(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, admin_token="admin-secret")
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)
    client.post("/api/v1/auth/login", json={"user_id": "user_a"})
    client.post("/api/v1/auth/login", json={"user_id": "user_b"})
    client.post(
        "/api/v1/admin/redeem-codes",
        headers=admin_headers(),
        json={"code": "ONE", "type": "credits", "credits": 1, "max_uses": 1},
    )

    first = client.post("/api/v1/redeem-codes/redeem", headers=auth_headers("user_a"), json={"code": "ONE"})
    second = client.post("/api/v1/redeem-codes/redeem", headers=auth_headers("user_b"), json={"code": "ONE"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.get_json()["error"]["code"] == "redeem_code_exhausted"


def test_admin_can_generate_redeem_codes(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, admin_token="admin-secret")
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)

    generated = client.post(
        "/api/v1/admin/redeem-codes/generate",
        headers=admin_headers(),
        json={"type": "credits", "credits": 5, "count": 2, "prefix": "VIP", "max_uses": 1},
    )
    listed = client.get("/api/v1/admin/redeem-codes", headers=admin_headers())

    assert generated.status_code == 200
    codes = generated.get_json()["redeem_codes"]
    assert len(codes) == 2
    assert all(item["code"].startswith("VIP-") for item in codes)
    assert listed.status_code == 200
    assert len(listed.get_json()["redeem_codes"]) == 2


def test_time_pass_takes_priority_until_daily_cap(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, admin_token="admin-secret", initial_credits=1, time_pass_daily_credit_cap=2)
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)
    client.post(
        "/api/v1/admin/redeem-codes",
        headers=admin_headers(),
        json={"code": "WEEK", "type": "time_pass", "duration_days": 7, "max_uses": 1},
    )
    redeemed = client.post("/api/v1/redeem-codes/redeem", headers=auth_headers(), json={"code": "WEEK"})

    first = client.post(
        "/api/v1/replies",
        headers=auth_headers(),
        json={"conversation_id": conv, "question": "one", "mode": "bailian_rag_strategy_quality"},
    )
    second = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "two"})

    assert redeemed.status_code == 200
    assert first.status_code == 200
    assert first.get_json()["reply_run"]["charge_source"] == "time_pass"
    assert first.get_json()["limits"]["credits_balance"] == 1
    assert second.status_code == 200
    assert second.get_json()["reply_run"]["charge_source"] == "credits"
    assert second.get_json()["limits"]["credits_balance"] == 0


def test_time_pass_cap_excludes_prior_credit_usage(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, admin_token="admin-secret", initial_credits=3, time_pass_daily_credit_cap=2)
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)
    before_pass = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "before"})
    client.post(
        "/api/v1/admin/redeem-codes",
        headers=admin_headers(),
        json={"code": "PASS", "type": "time_pass", "duration_days": 7, "max_uses": 1},
    )
    redeemed = client.post("/api/v1/redeem-codes/redeem", headers=auth_headers(), json={"code": "PASS"})

    with_pass = client.post(
        "/api/v1/replies",
        headers=auth_headers(),
        json={"conversation_id": conv, "question": "after", "mode": "bailian_rag_strategy_quality"},
    )

    assert before_pass.status_code == 200
    assert before_pass.get_json()["reply_run"]["charge_source"] == "credits"
    assert redeemed.status_code == 200
    assert with_pass.status_code == 200
    assert with_pass.get_json()["reply_run"]["charge_source"] == "time_pass"
    assert with_pass.get_json()["limits"]["credits_balance"] == 2
    assert with_pass.get_json()["limits"]["time_pass_daily_used"] == 2


def test_expired_time_pass_falls_back_to_credits(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, admin_token="admin-secret", initial_credits=1, time_pass_daily_credit_cap=20)
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)
    client.patch(
        "/api/v1/admin/users/test_user/wallet",
        headers=admin_headers(),
        json={"time_pass_expires_at": "2000-01-01T00:00:00"},
    )

    response = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "one"})

    assert response.status_code == 200
    assert response.get_json()["reply_run"]["charge_source"] == "credits"
    assert response.get_json()["limits"]["credits_balance"] == 0


def test_failed_model_result_does_not_charge_credits(monkeypatch, tmp_path: Path) -> None:
    def fake_failed_reply(**_kwargs):
        return {
            "status": "model_unavailable",
            "run_id": "runtime_failed",
            "answer": {"reply": "", "coach_analysis": "", "risk_warning": "down"},
            "reference_segments": [],
        }

    monkeypatch.setattr(api_app, "run_reply", fake_failed_reply)
    app = api_app.create_app(make_config(tmp_path, initial_credits=1))
    client = app.test_client()
    conv = login_and_default_conversation(client)

    response = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "one"})

    assert response.status_code == 200
    assert response.get_json()["reply_run"]["status"] == "model_unavailable"
    assert response.get_json()["reply_run"]["charge_source"] == ""
    assert response.get_json()["limits"]["credits_balance"] == 1


def test_web_login_does_not_get_initial_credits_by_default(monkeypatch, tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        web_access_required=True,
        web_access_codes=["test-code"],
        grant_initial_credits_to_non_wechat_users=False,
    )
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)

    login = client.post("/api/v1/auth/web-login", json={"access_code": "test-code"})

    assert login.status_code == 200
    assert login.get_json()["limits"]["credits_balance"] == 0


def test_admin_reply_runs_include_segmented_model_timings(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, admin_token="admin-secret")
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)

    response = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "hello", "input_type": "text_only"})
    runs = client.get("/api/v1/admin/reply-runs", headers=admin_headers()).get_json()["reply_runs"]
    feedback = client.get("/api/v1/admin/feedback", headers=admin_headers()).get_json()["feedback"]

    assert response.status_code == 200
    assert runs[0]["input_type"] == "text_only"
    assert runs[0]["image_count"] == 0
    assert runs[0]["timings"]["vision"]["elapsed_seconds"] == 1.25
    assert runs[0]["timings"]["label"]["elapsed_seconds"] == 2.5
    assert runs[0]["timings"]["reply"]["elapsed_seconds"] == 3.75
    assert runs[0]["timings"]["total_model_elapsed_seconds"] == 7.5
    assert runs[0]["reference_count"] == 1
    assert feedback == []


def test_admin_lists_users_and_ip_usage(monkeypatch, tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        admin_token="admin-secret",
        web_access_required=True,
        web_access_codes=["test-code"],
        web_ip_daily_quota=10,
        web_site_daily_quota=10,
    )
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)
    login_headers = {"X-Forwarded-For": "203.0.113.8"}
    login = client.post("/api/v1/auth/web-login", headers=login_headers, json={"access_code": "test-code"}).get_json()
    headers = {"Authorization": f"Bearer {login['token']}", "X-Forwarded-For": "203.0.113.8"}
    conv = client.get("/api/v1/conversations", headers=headers).get_json()["conversations"][0]["conversation_id"]
    client.post("/api/v1/replies", headers=headers, json={"conversation_id": conv, "question": "hello"})

    users = client.get("/api/v1/admin/users", headers=admin_headers()).get_json()["users"]
    ip_usage = client.get("/api/v1/admin/ip-usage", headers=admin_headers()).get_json()["ip_usage"]

    assert users[0]["user_id"].startswith("web_")
    assert users[0]["last_ip_display"] == "203.0.113.*"
    assert users[0]["last_ip_hash"]
    assert users[0]["today_usage"] == 1
    assert ip_usage[0]["ip_display"] == "203.0.113.*"
    assert ip_usage[0]["today_units"] == 1


def test_client_ip_ignores_forwarded_for_from_untrusted_remote(monkeypatch, tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        admin_token="admin-secret",
        web_access_required=True,
        web_access_codes=["test-code"],
        web_ip_daily_quota=10,
        trusted_proxy_ips=["127.0.0.1"],
    )
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)
    login = client.post(
        "/api/v1/auth/web-login",
        headers={"X-Forwarded-For": "203.0.113.8"},
        environ_base={"REMOTE_ADDR": "198.51.100.9"},
        json={"access_code": "test-code"},
    ).get_json()
    headers = {
        "Authorization": f"Bearer {login['token']}",
        "X-Forwarded-For": "203.0.113.8",
    }
    conv = client.get("/api/v1/conversations", headers=headers, environ_base={"REMOTE_ADDR": "198.51.100.9"}).get_json()["conversations"][0]["conversation_id"]
    client.post(
        "/api/v1/replies",
        headers=headers,
        environ_base={"REMOTE_ADDR": "198.51.100.9"},
        json={"conversation_id": conv, "question": "hello"},
    )

    users = client.get("/api/v1/admin/users", headers=admin_headers()).get_json()["users"]
    ip_usage = client.get("/api/v1/admin/ip-usage", headers=admin_headers()).get_json()["ip_usage"]

    assert users[0]["last_ip_display"] == "198.51.100.*"
    assert ip_usage[0]["ip_display"] == "198.51.100.*"


def test_user_disable_and_clear_restore_default(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, admin_token="admin-secret", daily_reply_quota=2)
    client, captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)

    blocked_override = client.patch(
        "/api/v1/admin/users/test_user/quota",
        headers=admin_headers(),
        json={"disabled": True},
    )
    blocked = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "blocked"})
    cleared = client.delete("/api/v1/admin/users/test_user/quota", headers=admin_headers())
    restored = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "restored"})

    assert blocked_override.status_code == 200
    assert blocked.status_code == 429
    assert blocked.get_json()["error"]["code"] == "user_disabled"
    assert cleared.status_code == 200
    assert restored.status_code == 200
    assert len(captured) == 1


def test_admin_wallet_adjustment_restores_credits(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, admin_token="admin-secret", initial_credits=1)
    client, captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)

    first = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "one"})
    second = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "two"})
    adjusted = client.patch("/api/v1/admin/users/test_user/wallet", headers=admin_headers(), json={"credits_delta": 2})
    third = client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "three"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.get_json()["error"]["code"] == "credits_insufficient"
    assert adjusted.status_code == 200
    assert adjusted.get_json()["user"]["credits_balance"] == 2
    assert third.status_code == 200
    assert len(captured) == 2


def test_admin_site_quota_reports_used_and_remaining(monkeypatch, tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        admin_token="admin-secret",
        web_site_daily_quota=3,
        mode_unit_costs={"bailian_rag_fast": 1, "bailian_rag_strategy_quality": 2},
    )
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)
    conv = login_and_default_conversation(client)
    client.post("/api/v1/replies", headers=auth_headers(), json={"conversation_id": conv, "question": "one", "mode": "bailian_rag_strategy_quality"})

    stats = client.get("/api/v1/admin/stats", headers=admin_headers()).get_json()["stats"]

    assert stats["site_quota"]["daily_quota"] == 3
    assert stats["site_quota"]["daily_used"] == 2
    assert stats["site_quota"]["daily_remaining"] == 1


def test_admin_config_can_be_saved_and_refreshed(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, admin_token="admin-secret", admin_config_path=str(tmp_path / "admin_config.json"))
    client, _captured = client_with_runtime(monkeypatch, tmp_path, config)

    response = client.post(
        "/api/v1/admin/config",
        headers=admin_headers(),
        json={
            "runtime": {"default_mode": "bailian_rag_strategy_quality"},
            "rag": {"vector_store_ids": "new_store", "max_num_results": 4},
            "limits": {
                "daily_reply_quota": 33,
                "mode_unit_costs": {"bailian_rag_fast": 1, "bailian_rag_strategy_quality": 3},
                "max_images_per_reply": 4,
                "min_images_per_reply": 1,
                "max_image_mb": 9,
            },
            "retention": {"upload_days": 30, "run_days": 45},
            "announcement": {"title": "notice", "content": "hello", "status": "active"},
        },
    )
    data = response.get_json()
    current = client.get("/api/v1/admin/config", headers=admin_headers()).get_json()["config"]
    health = client.get("/api/v1/health").get_json()

    assert response.status_code == 200
    assert Path(data["saved"]).exists()
    assert current["runtime"]["default_mode"] == "bailian_rag_strategy_quality"
    assert current["rag"]["vector_store_ids"] == ["new_store"]
    assert current["rag"]["max_num_results"] == 4
    assert current["limits"]["daily_reply_quota"] == 33
    assert current["limits"]["mode_unit_costs"]["bailian_rag_fast"] == 1
    assert current["limits"]["mode_unit_costs"]["bailian_rag_strategy_quality"] == 3
    assert current["retention"]["run_days"] == 45
    assert current["announcement"]["title"] == "notice"
    assert health["default_mode"] == "bailian_rag_strategy_quality"
