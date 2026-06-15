from __future__ import annotations

import json
import secrets
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from baiou.common.io import resolve_path


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class ProductStore:
    def __init__(self, path: str | Path):
        self.path = resolve_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    openid TEXT,
                    nickname TEXT,
                    plan TEXT NOT NULL DEFAULT 'trial',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    background TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS reply_runs (
                    run_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    question TEXT NOT NULL,
                    user_context TEXT NOT NULL DEFAULT '',
                    runtime_context TEXT NOT NULL DEFAULT '',
                    image_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    answer_json TEXT NOT NULL DEFAULT '{}',
                    image_understanding TEXT NOT NULL DEFAULT '',
                    reference_segments_json TEXT NOT NULL DEFAULT '[]',
                    runtime_run_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id)
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id),
                    FOREIGN KEY(run_id) REFERENCES reply_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS daily_usage (
                    user_id TEXT NOT NULL,
                    usage_date TEXT NOT NULL,
                    reply_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, usage_date),
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS announcements (
                    announcement_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    starts_at TEXT NOT NULL DEFAULT '',
                    ends_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS uploads (
                    upload_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    consumed_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );
                """
            )

    def ensure_user(self, user_id: str, openid: str = "", nickname: str = "") -> dict[str, Any]:
        stamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users(user_id, openid, nickname, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    openid=COALESCE(NULLIF(excluded.openid, ''), users.openid),
                    nickname=COALESCE(NULLIF(excluded.nickname, ''), users.nickname),
                    updated_at=excluded.updated_at
                """,
                (user_id, openid, nickname, stamp, stamp),
            )
        self.ensure_default_conversation(user_id)
        return self.get_user(user_id) or {}

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def create_session(self, user_id: str, ttl_days: int = 30) -> str:
        token = secrets.token_urlsafe(32)
        stamp = now_iso()
        expires_at = (datetime.now() + timedelta(days=max(1, int(ttl_days)))).isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(token, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, user_id, stamp, expires_at),
            )
        return token

    def user_id_for_session(self, token: str) -> str:
        if not token:
            return ""
        stamp = now_iso()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM sessions WHERE token = ? AND expires_at >= ?",
                (token, stamp),
            ).fetchone()
        return str(row["user_id"]) if row else ""

    def ensure_default_conversation(self, user_id: str) -> dict[str, Any]:
        existing = self.list_conversations(user_id, include_archived=False)
        if existing:
            return existing[0]
        return self.create_conversation(user_id, "默认聊天", "")

    def list_conversations(self, user_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM conversations WHERE user_id = ?"
        params: list[Any] = [user_id]
        if not include_archived:
            query += " AND status = 'active'"
        query += " ORDER BY updated_at DESC, created_at DESC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def active_conversation_count(self, user_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM conversations WHERE user_id = ? AND status = 'active'",
                (user_id,),
            ).fetchone()
        return int(row["count"] if row else 0)

    def create_conversation(self, user_id: str, title: str, background: str = "") -> dict[str, Any]:
        stamp = now_iso()
        conversation_id = new_id("conv")
        clean_title = title.strip() or "新的聊天"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations(conversation_id, user_id, title, background, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
                """,
                (conversation_id, user_id, clean_title, background.strip(), stamp, stamp),
            )
        return self.get_conversation(user_id, conversation_id) or {}

    def get_conversation(self, user_id: str, conversation_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE user_id = ? AND conversation_id = ?",
                (user_id, conversation_id),
            ).fetchone()
        return dict(row) if row else None

    def update_conversation(self, user_id: str, conversation_id: str, title: str | None, background: str | None) -> dict[str, Any] | None:
        current = self.get_conversation(user_id, conversation_id)
        if not current or current.get("status") != "active":
            return None
        next_title = (title.strip() if title is not None else current["title"]) or current["title"]
        next_background = background.strip() if background is not None else current["background"]
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE conversations SET title = ?, background = ?, updated_at = ?
                WHERE user_id = ? AND conversation_id = ?
                """,
                (next_title, next_background, now_iso(), user_id, conversation_id),
            )
        return self.get_conversation(user_id, conversation_id)

    def archive_conversation(self, user_id: str, conversation_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                """
                UPDATE conversations SET status = 'archived', updated_at = ?
                WHERE user_id = ? AND conversation_id = ? AND status = 'active'
                """,
                (now_iso(), user_id, conversation_id),
            )
        return cur.rowcount > 0

    def recent_reply_runs(self, user_id: str, conversation_id: str, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT run_id, mode, question, user_context, answer_json, status, created_at
                FROM reply_runs
                WHERE user_id = ? AND conversation_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (user_id, conversation_id, int(limit)),
            ).fetchall()
        items = [dict(row) for row in rows]
        items.reverse()
        for item in items:
            item["answer"] = decode_json(item.pop("answer_json"), {})
        return items

    def create_reply_run(
        self,
        user_id: str,
        conversation_id: str,
        mode: str,
        question: str,
        user_context: str,
        runtime_context: str,
        image_count: int,
    ) -> dict[str, Any]:
        stamp = now_iso()
        run_id = new_id("run")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO reply_runs(
                    run_id, user_id, conversation_id, mode, question, user_context, runtime_context,
                    image_count, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)
                """,
                (run_id, user_id, conversation_id, mode, question, user_context, runtime_context, image_count, stamp, stamp),
            )
        return self.get_reply_run(user_id, run_id) or {}

    def update_reply_run(self, user_id: str, run_id: str, result: dict[str, Any]) -> dict[str, Any] | None:
        answer = result.get("answer", {}) if isinstance(result.get("answer", {}), dict) else {}
        references = result.get("reference_segments", [])
        if not isinstance(references, list):
            references = []
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE reply_runs SET
                    status = ?, answer_json = ?, image_understanding = ?, reference_segments_json = ?,
                    runtime_run_id = ?, updated_at = ?
                WHERE user_id = ? AND run_id = ?
                """,
                (
                    str(result.get("status", "")),
                    json.dumps(answer, ensure_ascii=False),
                    str(result.get("image_understanding", "")),
                    json.dumps(references, ensure_ascii=False),
                    str(result.get("run_id", "")),
                    now_iso(),
                    user_id,
                    run_id,
                ),
            )
        return self.get_reply_run(user_id, run_id)

    def fail_reply_run(self, user_id: str, run_id: str, error: str) -> dict[str, Any] | None:
        return self.update_reply_run(
            user_id,
            run_id,
            {"status": "api_error", "answer": {"reply": "", "coach_analysis": "", "risk_warning": error}, "reference_segments": []},
        )

    def get_reply_run(self, user_id: str, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM reply_runs WHERE user_id = ? AND run_id = ?", (user_id, run_id)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["answer"] = decode_json(item.pop("answer_json"), {})
        item["reference_segments"] = decode_json(item.pop("reference_segments_json"), [])
        return item

    def usage_today(self, user_id: str) -> int:
        today = date.today().isoformat()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT reply_count FROM daily_usage WHERE user_id = ? AND usage_date = ?",
                (user_id, today),
            ).fetchone()
        return int(row["reply_count"] if row else 0)

    def increment_usage(self, user_id: str) -> int:
        today = date.today().isoformat()
        stamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO daily_usage(user_id, usage_date, reply_count, updated_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id, usage_date) DO UPDATE SET
                    reply_count = daily_usage.reply_count + 1,
                    updated_at = excluded.updated_at
                """,
                (user_id, today, stamp),
            )
        return self.usage_today(user_id)

    def add_feedback(self, user_id: str, conversation_id: str, run_id: str, rating: str, notes: str = "") -> dict[str, Any] | None:
        if not self.get_conversation(user_id, conversation_id) or not self.get_reply_run(user_id, run_id):
            return None
        feedback_id = new_id("fb")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO feedback(feedback_id, user_id, conversation_id, run_id, rating, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (feedback_id, user_id, conversation_id, run_id, rating.strip(), notes.strip(), now_iso()),
            )
            row = conn.execute("SELECT * FROM feedback WHERE feedback_id = ?", (feedback_id,)).fetchone()
        return dict(row) if row else None

    def admin_stats(self) -> dict[str, Any]:
        today = date.today().isoformat()
        with self.connect() as conn:
            totals = {
                "users": scalar(conn, "SELECT COUNT(*) FROM users"),
                "conversations": scalar(conn, "SELECT COUNT(*) FROM conversations WHERE status = 'active'"),
                "reply_runs": scalar(conn, "SELECT COUNT(*) FROM reply_runs"),
                "uploads": scalar(conn, "SELECT COUNT(*) FROM uploads"),
                "feedback": scalar(conn, "SELECT COUNT(*) FROM feedback"),
                "today_reply_runs": scalar(conn, "SELECT COUNT(*) FROM reply_runs WHERE substr(created_at, 1, 10) = ?", (today,)),
                "today_uploads": scalar(conn, "SELECT COUNT(*) FROM uploads WHERE substr(created_at, 1, 10) = ?", (today,)),
                "today_feedback": scalar(conn, "SELECT COUNT(*) FROM feedback WHERE substr(created_at, 1, 10) = ?", (today,)),
                "today_active_users": scalar(
                    conn,
                    """
                    SELECT COUNT(DISTINCT user_id) FROM (
                        SELECT user_id FROM reply_runs WHERE substr(created_at, 1, 10) = ?
                        UNION
                        SELECT user_id FROM uploads WHERE substr(created_at, 1, 10) = ?
                    )
                    """,
                    (today, today),
                ),
            }
            status_rows = conn.execute("SELECT status, COUNT(*) AS count FROM reply_runs GROUP BY status").fetchall()
            mode_rows = conn.execute("SELECT mode, COUNT(*) AS count FROM reply_runs GROUP BY mode").fetchall()
            feedback_rows = conn.execute("SELECT rating, COUNT(*) AS count FROM feedback GROUP BY rating").fetchall()
            latest_failures = conn.execute(
                """
                SELECT run_id, user_id, conversation_id, mode, status, question, updated_at
                FROM reply_runs
                WHERE status NOT IN ('model_success', 'dry_run')
                ORDER BY updated_at DESC
                LIMIT 20
                """
            ).fetchall()
        return {
            "date": today,
            "totals": totals,
            "reply_statuses": rows_to_counts(status_rows, "status"),
            "reply_modes": rows_to_counts(mode_rows, "mode"),
            "feedback_ratings": rows_to_counts(feedback_rows, "rating"),
            "latest_failures": [dict(row) for row in latest_failures],
        }

    def list_feedback_detail(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    f.feedback_id, f.user_id, f.conversation_id, f.run_id, f.rating, f.notes, f.created_at,
                    r.mode, r.status, r.question, r.user_context, r.image_count, r.answer_json, r.reference_segments_json
                FROM feedback f
                JOIN reply_runs r ON r.run_id = f.run_id
                ORDER BY f.created_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [decode_feedback_row(row) for row in rows]

    def feedback_export_rows(self, limit: int = 1000) -> list[dict[str, Any]]:
        return self.list_feedback_detail(limit)

    def delete_upload_rows_before(self, cutoff_iso: str) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT path FROM uploads WHERE created_at < ?", (cutoff_iso,)).fetchall()
            conn.execute("DELETE FROM uploads WHERE created_at < ?", (cutoff_iso,))
        return [str(row["path"]) for row in rows]

    def list_announcements(self) -> list[dict[str, Any]]:
        stamp = now_iso()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT announcement_id, title, content, status, starts_at, ends_at, created_at
                FROM announcements
                WHERE status = 'active'
                  AND (starts_at = '' OR starts_at <= ?)
                  AND (ends_at = '' OR ends_at >= ?)
                ORDER BY created_at DESC
                """,
                (stamp, stamp),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_upload(self, user_id: str, original_name: str, path: str | Path, size_bytes: int) -> dict[str, Any]:
        upload_id = new_id("upl")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO uploads(upload_id, user_id, original_name, path, size_bytes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (upload_id, user_id, original_name, str(path), int(size_bytes), now_iso()),
            )
            row = conn.execute("SELECT * FROM uploads WHERE upload_id = ?", (upload_id,)).fetchone()
        return dict(row) if row else {}

    def get_uploads(self, user_id: str, upload_ids: list[str]) -> list[dict[str, Any]]:
        ids = [item for item in upload_ids if item]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM uploads
                WHERE user_id = ? AND consumed_at = '' AND upload_id IN ({placeholders})
                ORDER BY created_at ASC
                """,
                [user_id, *ids],
            ).fetchall()
        found = {row["upload_id"]: dict(row) for row in rows}
        return [found[item] for item in ids if item in found]

    def mark_uploads_consumed(self, user_id: str, upload_ids: list[str]) -> None:
        ids = [item for item in upload_ids if item]
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE uploads SET consumed_at = ? WHERE user_id = ? AND upload_id IN ({placeholders})",
                [now_iso(), user_id, *ids],
            )


def decode_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except json.JSONDecodeError:
        return fallback


def scalar(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(query, params).fetchone()
    return int(row[0] if row else 0)


def rows_to_counts(rows: list[sqlite3.Row], key: str) -> dict[str, int]:
    return {str(row[key] or ""): int(row["count"]) for row in rows}


def decode_feedback_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    answer = decode_json(item.pop("answer_json", ""), {})
    refs = decode_json(item.pop("reference_segments_json", ""), [])
    item["reply"] = answer.get("reply", "") if isinstance(answer, dict) else ""
    item["coach_analysis"] = answer.get("coach_analysis", "") if isinstance(answer, dict) else ""
    item["risk_warning"] = answer.get("risk_warning", "") if isinstance(answer, dict) else ""
    item["reference_count"] = len(refs) if isinstance(refs, list) else 0
    return item
