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


SCHEMA_MIGRATIONS: dict[str, dict[str, str]] = {
    "users": {
        "openid": "openid TEXT DEFAULT ''",
        "nickname": "nickname TEXT DEFAULT ''",
        "avatar_url": "avatar_url TEXT NOT NULL DEFAULT ''",
        "profile_updated_at": "profile_updated_at TEXT NOT NULL DEFAULT ''",
        "plan": "plan TEXT NOT NULL DEFAULT 'trial'",
        "credits_balance": "credits_balance INTEGER NOT NULL DEFAULT 0",
        "initial_credits_granted_at": "initial_credits_granted_at TEXT NOT NULL DEFAULT ''",
        "time_pass_expires_at": "time_pass_expires_at TEXT NOT NULL DEFAULT ''",
        "disabled": "disabled INTEGER NOT NULL DEFAULT 0",
        "created_at": "created_at TEXT NOT NULL DEFAULT ''",
        "updated_at": "updated_at TEXT NOT NULL DEFAULT ''",
    },
    "conversations": {
        "background": "background TEXT NOT NULL DEFAULT ''",
        "status": "status TEXT NOT NULL DEFAULT 'active'",
        "created_at": "created_at TEXT NOT NULL DEFAULT ''",
        "updated_at": "updated_at TEXT NOT NULL DEFAULT ''",
    },
    "reply_runs": {
        "user_context": "user_context TEXT NOT NULL DEFAULT ''",
        "runtime_context": "runtime_context TEXT NOT NULL DEFAULT ''",
        "image_count": "image_count INTEGER NOT NULL DEFAULT 0",
        "image_understanding": "image_understanding TEXT NOT NULL DEFAULT ''",
        "reference_segments_json": "reference_segments_json TEXT NOT NULL DEFAULT '[]'",
        "runtime_run_id": "runtime_run_id TEXT NOT NULL DEFAULT ''",
        "unit_cost": "unit_cost INTEGER NOT NULL DEFAULT 0",
        "charge_source": "charge_source TEXT NOT NULL DEFAULT ''",
    },
    "uploads": {
        "consumed_at": "consumed_at TEXT NOT NULL DEFAULT ''",
    },
    "redeem_codes": {
        "type": "type TEXT NOT NULL DEFAULT 'credits'",
        "credits": "credits INTEGER NOT NULL DEFAULT 0",
        "duration_days": "duration_days INTEGER NOT NULL DEFAULT 0",
        "used_count": "used_count INTEGER NOT NULL DEFAULT 0",
        "expires_at": "expires_at TEXT NOT NULL DEFAULT ''",
        "note": "note TEXT NOT NULL DEFAULT ''",
        "updated_at": "updated_at TEXT NOT NULL DEFAULT ''",
    },
    "redeem_redemptions": {
        "type": "type TEXT NOT NULL DEFAULT 'credits'",
        "credits": "credits INTEGER NOT NULL DEFAULT 0",
        "duration_days": "duration_days INTEGER NOT NULL DEFAULT 0",
        "granted_time_pass_expires_at": "granted_time_pass_expires_at TEXT NOT NULL DEFAULT ''",
    },
}


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
                    avatar_url TEXT NOT NULL DEFAULT '',
                    profile_updated_at TEXT NOT NULL DEFAULT '',
                    plan TEXT NOT NULL DEFAULT 'trial',
                    credits_balance INTEGER NOT NULL DEFAULT 0,
                    initial_credits_granted_at TEXT NOT NULL DEFAULT '',
                    time_pass_expires_at TEXT NOT NULL DEFAULT '',
                    disabled INTEGER NOT NULL DEFAULT 0,
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
                    unit_cost INTEGER NOT NULL DEFAULT 0,
                    charge_source TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id)
                );

                CREATE TABLE IF NOT EXISTS reply_run_images (
                    image_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    original_name TEXT NOT NULL DEFAULT '',
                    path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES reply_runs(run_id),
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
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

                CREATE TABLE IF NOT EXISTS quota_usage (
                    scope TEXT NOT NULL,
                    quota_key TEXT NOT NULL,
                    usage_date TEXT NOT NULL,
                    units INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(scope, quota_key, usage_date)
                );

                CREATE TABLE IF NOT EXISTS time_pass_usage (
                    user_id TEXT NOT NULL,
                    usage_date TEXT NOT NULL,
                    units INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, usage_date),
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS user_quota_overrides (
                    user_id TEXT PRIMARY KEY,
                    daily_reply_quota INTEGER,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS login_events (
                    event_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    ip_hash TEXT NOT NULL,
                    ip_display TEXT NOT NULL,
                    created_at TEXT NOT NULL,
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

                CREATE TABLE IF NOT EXISTS redeem_codes (
                    code TEXT PRIMARY KEY,
                    daily_reply_quota INTEGER NOT NULL DEFAULT 0,
                    type TEXT NOT NULL DEFAULT 'credits',
                    credits INTEGER NOT NULL DEFAULT 0,
                    duration_days INTEGER NOT NULL DEFAULT 0,
                    max_uses INTEGER NOT NULL DEFAULT 1,
                    used_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    expires_at TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS redeem_redemptions (
                    redemption_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    daily_reply_quota INTEGER NOT NULL DEFAULT 0,
                    type TEXT NOT NULL DEFAULT 'credits',
                    credits INTEGER NOT NULL DEFAULT 0,
                    duration_days INTEGER NOT NULL DEFAULT 0,
                    granted_time_pass_expires_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, code),
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(code) REFERENCES redeem_codes(code)
                );

                CREATE TABLE IF NOT EXISTS credit_ledger (
                    ledger_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    delta INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    ref_type TEXT NOT NULL DEFAULT '',
                    ref_id TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );
                """
            )
            self.migrate_schema(conn)

    def migrate_schema(self, conn: sqlite3.Connection) -> None:
        for table, columns in SCHEMA_MIGRATIONS.items():
            existing = table_columns(conn, table)
            if not existing:
                continue
            for name, definition in columns.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
        if "redeem_codes" in existing_tables(conn):
            conn.execute(
                """
                UPDATE redeem_codes
                SET credits = daily_reply_quota
                WHERE credits = 0 AND COALESCE(daily_reply_quota, 0) > 0
                """
            )

    def ensure_user(
        self,
        user_id: str,
        openid: str = "",
        nickname: str = "",
        initial_credits: int = 0,
        grant_initial_credits: bool = False,
    ) -> dict[str, Any]:
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
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row and grant_initial_credits and int(initial_credits) > 0 and not row["initial_credits_granted_at"]:
                balance = int(row["credits_balance"] or 0) + int(initial_credits)
                conn.execute(
                    """
                    UPDATE users
                    SET credits_balance = ?, initial_credits_granted_at = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (balance, stamp, stamp, user_id),
                )
                insert_credit_ledger(conn, user_id, int(initial_credits), balance, "initial_grant", "user", user_id, "")
        self.ensure_default_conversation(user_id)
        return self.get_user(user_id) or {}

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def update_user_profile(self, user_id: str, nickname: str = "", avatar_url: str = "") -> dict[str, Any]:
        self.ensure_user(user_id)
        stamp = now_iso()
        updates = ["profile_updated_at = ?", "updated_at = ?"]
        params: list[Any] = [stamp, stamp]
        if nickname.strip():
            updates.append("nickname = ?")
            params.append(nickname.strip()[:80])
        if avatar_url.strip():
            updates.append("avatar_url = ?")
            params.append(avatar_url.strip()[:500])
        params.append(user_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?", params)
        return self.get_user(user_id) or {}

    def create_session(self, user_id: str, ttl_days: int = 30, ip_hash: str = "", ip_display: str = "") -> str:
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
            if ip_hash:
                conn.execute(
                    """
                    INSERT INTO login_events(event_id, user_id, ip_hash, ip_display, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (new_id("login"), user_id, ip_hash, ip_display, stamp),
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
        if result.get("input_type"):
            answer = {**answer, "_input_type": str(result.get("input_type", ""))}
        answer = {**answer, "_timings": model_timings_from_result(result)}
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

    def add_reply_run_images(self, user_id: str, run_id: str, images: list[dict[str, Any]]) -> None:
        if not images:
            return
        stamp = now_iso()
        rows = []
        for item in images:
            path = str(item.get("path", "")).strip()
            if not path:
                continue
            size = item.get("size_bytes")
            if size is None:
                try:
                    size = Path(path).stat().st_size
                except OSError:
                    size = 0
            rows.append((new_id("img"), run_id, user_id, str(item.get("original_name", "")), path, int(size), stamp))
        if not rows:
            return
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO reply_run_images(image_id, run_id, user_id, original_name, path, size_bytes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

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

    def increment_usage(self, user_id: str, units: int = 1) -> int:
        today = date.today().isoformat()
        stamp = now_iso()
        amount = max(0, int(units))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO daily_usage(user_id, usage_date, reply_count, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, usage_date) DO UPDATE SET
                    reply_count = daily_usage.reply_count + excluded.reply_count,
                    updated_at = excluded.updated_at
                """,
                (user_id, today, amount, stamp),
            )
        return self.usage_today(user_id)

    def quota_units_today(self, scope: str, quota_key: str) -> int:
        today = date.today().isoformat()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT units FROM quota_usage WHERE scope = ? AND quota_key = ? AND usage_date = ?",
                (scope, quota_key, today),
            ).fetchone()
        return int(row["units"] if row else 0)

    def total_usage(self, user_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COALESCE(SUM(reply_count), 0) AS total FROM daily_usage WHERE user_id = ?", (user_id,)).fetchone()
        return int(row["total"] if row else 0)

    def wallet_status(self, user_id: str, time_pass_daily_credit_cap: int = 0) -> dict[str, Any]:
        user = self.get_user(user_id) or {}
        expires_at = str(user.get("time_pass_expires_at", "") or "")
        active = bool(expires_at and expires_at > now_iso())
        used = self.time_pass_usage_today(user_id)
        cap = max(0, int(time_pass_daily_credit_cap or 0))
        return {
            "credits_balance": int(user.get("credits_balance", 0) or 0),
            "time_pass_active": active,
            "time_pass_expires_at": expires_at,
            "time_pass_daily_credit_cap": cap,
            "time_pass_daily_used": used,
            "time_pass_daily_remaining": max(0, cap - used) if active and cap else 0,
            "disabled": bool(int(user.get("disabled", 0) or 0)),
            "initial_credits_granted_at": user.get("initial_credits_granted_at", ""),
        }

    def reply_charge_preview(self, user_id: str, unit_cost: int, time_pass_daily_credit_cap: int) -> tuple[str, str]:
        user = self.get_user(user_id) or {}
        cost = max(0, int(unit_cost))
        if int(user.get("disabled", 0) or 0):
            return "", "user_disabled"
        if cost <= 0:
            return "credits", ""
        cap = max(0, int(time_pass_daily_credit_cap or 0))
        if str(user.get("time_pass_expires_at", "") or "") > now_iso() and cap and self.time_pass_usage_today(user_id) + cost <= cap:
            return "time_pass", ""
        if int(user.get("credits_balance", 0) or 0) >= cost:
            return "credits", ""
        return "", "credits_insufficient"

    def time_pass_usage_today(self, user_id: str) -> int:
        today = date.today().isoformat()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT units FROM time_pass_usage WHERE user_id = ? AND usage_date = ?",
                (user_id, today),
            ).fetchone()
        return int(row["units"] if row else 0)

    def charge_reply_success(self, user_id: str, run_id: str, unit_cost: int, time_pass_daily_credit_cap: int) -> tuple[str, str]:
        cost = max(0, int(unit_cost))
        stamp = now_iso()
        today = date.today().isoformat()
        cap = max(0, int(time_pass_daily_credit_cap or 0))
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            user = conn.execute(
                "SELECT credits_balance, time_pass_expires_at, disabled FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not user:
                return "", "credits_insufficient"
            if int(user["disabled"] or 0):
                return "", "user_disabled"

            source = "credits"
            if cost <= 0:
                source = "credits"
            elif str(user["time_pass_expires_at"] or "") > stamp and cap:
                pass_row = conn.execute(
                    "SELECT units FROM time_pass_usage WHERE user_id = ? AND usage_date = ?",
                    (user_id, today),
                ).fetchone()
                pass_used = int(pass_row["units"] if pass_row else 0)
                if pass_used + cost <= cap:
                    source = "time_pass"
                    conn.execute(
                        """
                        INSERT INTO time_pass_usage(user_id, usage_date, units, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(user_id, usage_date) DO UPDATE SET
                            units = time_pass_usage.units + excluded.units,
                            updated_at = excluded.updated_at
                        """,
                        (user_id, today, cost, stamp),
                    )

            if source == "credits" and cost:
                cur = conn.execute(
                    """
                    UPDATE users
                    SET credits_balance = credits_balance - ?, updated_at = ?
                    WHERE user_id = ? AND disabled = 0 AND credits_balance >= ?
                    """,
                    (cost, stamp, user_id, cost),
                )
                if cur.rowcount <= 0:
                    return "", "credits_insufficient"
                balance_row = conn.execute("SELECT credits_balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
                balance = int(balance_row["credits_balance"] if balance_row else 0)
                insert_credit_ledger(conn, user_id, -cost, balance, "reply_charge", "reply_run", run_id, "")
            conn.execute(
                """
                UPDATE reply_runs SET unit_cost = ?, charge_source = ?, updated_at = ?
                WHERE user_id = ? AND run_id = ?
                """,
                (cost, source, stamp, user_id, run_id),
            )
        return source, ""

    def adjust_user_credits(self, user_id: str, delta: int, note: str = "", reason: str = "admin_adjust") -> dict[str, Any]:
        self.ensure_user(user_id)
        amount = int(delta)
        stamp = now_iso()
        with self.connect() as conn:
            row = conn.execute("SELECT credits_balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
            balance = max(0, int(row["credits_balance"] if row else 0) + amount)
            actual_delta = balance - int(row["credits_balance"] if row else 0)
            conn.execute(
                "UPDATE users SET credits_balance = ?, updated_at = ? WHERE user_id = ?",
                (balance, stamp, user_id),
            )
            insert_credit_ledger(conn, user_id, actual_delta, balance, reason, "admin", "", note)
        return self.get_user(user_id) or {}

    def set_user_wallet(self, user_id: str, credits_delta: int | None = None, time_pass_expires_at: str | None = None, disabled: bool | None = None, note: str = "") -> dict[str, Any]:
        self.ensure_user(user_id)
        user = self.adjust_user_credits(user_id, int(credits_delta), note) if credits_delta is not None else self.get_user(user_id) or {}
        updates = []
        params: list[Any] = []
        if time_pass_expires_at is not None:
            updates.append("time_pass_expires_at = ?")
            params.append(str(time_pass_expires_at).strip())
        if disabled is not None:
            updates.append("disabled = ?")
            params.append(1 if disabled else 0)
        if updates:
            updates.append("updated_at = ?")
            params.extend([now_iso(), user_id])
            with self.connect() as conn:
                conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?", params)
        return self.get_user(user_id) or user

    def increment_quota_units(self, scope: str, quota_key: str, units: int = 1) -> int:
        today = date.today().isoformat()
        stamp = now_iso()
        amount = max(0, int(units))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO quota_usage(scope, quota_key, usage_date, units, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(scope, quota_key, usage_date) DO UPDATE SET
                    units = quota_usage.units + excluded.units,
                    updated_at = excluded.updated_at
                """,
                (scope, quota_key, today, amount, stamp),
            )
        return self.quota_units_today(scope, quota_key)

    def get_user_quota_override(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM user_quota_overrides WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def set_user_quota_override(self, user_id: str, daily_reply_quota: int | None, disabled: bool = False) -> dict[str, Any]:
        self.ensure_user(user_id)
        stamp = now_iso()
        quota = None if daily_reply_quota is None else max(0, int(daily_reply_quota))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_quota_overrides(user_id, daily_reply_quota, disabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    daily_reply_quota = excluded.daily_reply_quota,
                    disabled = excluded.disabled,
                    updated_at = excluded.updated_at
                """,
                (user_id, quota, 1 if disabled else 0, stamp, stamp),
            )
            conn.execute("UPDATE users SET disabled = ?, updated_at = ? WHERE user_id = ?", (1 if disabled else 0, stamp, user_id))
        return self.get_user_quota_override(user_id) or {}

    def clear_user_quota_override(self, user_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM user_quota_overrides WHERE user_id = ?", (user_id,))
            conn.execute("UPDATE users SET disabled = 0, updated_at = ? WHERE user_id = ?", (now_iso(), user_id))
        return cur.rowcount > 0

    def list_admin_users(self, limit: int = 100) -> list[dict[str, Any]]:
        today = date.today().isoformat()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    u.user_id,
                    u.nickname,
                    u.avatar_url,
                    u.profile_updated_at,
                    CASE WHEN COALESCE(u.openid, '') = '' THEN 0 ELSE 1 END AS has_openid,
                    u.plan,
                    u.credits_balance,
                    u.initial_credits_granted_at,
                    u.time_pass_expires_at,
                    u.disabled AS user_disabled,
                    u.created_at,
                    u.updated_at,
                    COALESCE(today_usage.reply_count, 0) AS today_usage,
                    COALESCE(total_usage.total_usage, 0) AS total_usage,
                    quota.daily_reply_quota AS quota_override,
                    COALESCE(u.disabled, quota.disabled, 0) AS disabled,
                    login.ip_hash AS last_ip_hash,
                    login.ip_display AS last_ip_display,
                    login.created_at AS last_login_at,
                    session.last_session_at,
                    activity.last_activity_at
                FROM users u
                LEFT JOIN daily_usage today_usage
                    ON today_usage.user_id = u.user_id AND today_usage.usage_date = ?
                LEFT JOIN (
                    SELECT user_id, SUM(reply_count) AS total_usage
                    FROM daily_usage
                    GROUP BY user_id
                ) total_usage ON total_usage.user_id = u.user_id
                LEFT JOIN user_quota_overrides quota ON quota.user_id = u.user_id
                LEFT JOIN (
                    SELECT user_id, MAX(created_at) AS last_session_at
                    FROM sessions
                    GROUP BY user_id
                ) session ON session.user_id = u.user_id
                LEFT JOIN (
                    SELECT le.user_id, le.ip_hash, le.ip_display, le.created_at
                    FROM login_events le
                    JOIN (
                        SELECT user_id, MAX(created_at) AS created_at
                        FROM login_events
                        GROUP BY user_id
                    ) latest ON latest.user_id = le.user_id AND latest.created_at = le.created_at
                ) login ON login.user_id = u.user_id
                LEFT JOIN (
                    SELECT user_id, MAX(stamp) AS last_activity_at
                    FROM (
                        SELECT user_id, MAX(updated_at) AS stamp FROM reply_runs GROUP BY user_id
                        UNION ALL
                        SELECT user_id, MAX(created_at) AS stamp FROM uploads GROUP BY user_id
                        UNION ALL
                        SELECT user_id, MAX(created_at) AS stamp FROM feedback GROUP BY user_id
                        UNION ALL
                        SELECT user_id, MAX(created_at) AS stamp FROM sessions GROUP BY user_id
                    )
                    GROUP BY user_id
                ) activity ON activity.user_id = u.user_id
                ORDER BY COALESCE(activity.last_activity_at, u.updated_at, u.created_at) DESC
                LIMIT ?
                """,
                (today, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_ip_usage(self, limit: int = 100) -> list[dict[str, Any]]:
        today = date.today().isoformat()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    q.quota_key AS ip_hash,
                    q.units,
                    q.updated_at AS last_request_at,
                    latest.ip_display AS ip_display,
                    latest.user_count,
                    latest.last_login_at
                FROM quota_usage q
                LEFT JOIN (
                    SELECT
                        ip_hash,
                        MAX(ip_display) AS ip_display,
                        COUNT(DISTINCT user_id) AS user_count,
                        MAX(created_at) AS last_login_at
                    FROM login_events
                    GROUP BY ip_hash
                ) latest ON latest.ip_hash = q.quota_key
                WHERE q.scope = 'ip' AND q.usage_date = ?
                ORDER BY q.units DESC, q.updated_at DESC
                LIMIT ?
                """,
                (today, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_reply_run_for_admin(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM reply_runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["answer"] = decode_json(item.pop("answer_json"), {})
        item["reference_segments"] = decode_json(item.pop("reference_segments_json"), [])
        return item

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

    def feedback_export_images(self, run_ids: list[str]) -> list[dict[str, Any]]:
        ids = [item for item in run_ids if item]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT image_id, run_id, user_id, original_name, path, size_bytes, created_at
                FROM reply_run_images
                WHERE run_id IN ({placeholders})
                ORDER BY created_at ASC
                """,
                ids,
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_redeem_code(
        self,
        code: str,
        code_type: str = "credits",
        credits: int = 0,
        duration_days: int = 0,
        max_uses: int = 1,
        expires_at: str = "",
        status: str = "active",
        note: str = "",
    ) -> dict[str, Any]:
        clean_code = normalize_code(code)
        if not clean_code:
            return {}
        clean_type = normalize_redeem_type(code_type)
        stamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO redeem_codes(code, daily_reply_quota, type, credits, duration_days, max_uses, status, expires_at, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    daily_reply_quota = excluded.daily_reply_quota,
                    type = excluded.type,
                    credits = excluded.credits,
                    duration_days = excluded.duration_days,
                    max_uses = excluded.max_uses,
                    status = excluded.status,
                    expires_at = excluded.expires_at,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (
                    clean_code,
                    max(0, int(credits)),
                    clean_type,
                    max(0, int(credits)),
                    max(0, int(duration_days)),
                    max(0, int(max_uses)),
                    status,
                    expires_at,
                    note,
                    stamp,
                    stamp,
                ),
            )
            row = conn.execute("SELECT * FROM redeem_codes WHERE code = ?", (clean_code,)).fetchone()
        return dict(row) if row else {}

    def generate_redeem_codes(
        self,
        code_type: str,
        credits: int,
        duration_days: int,
        max_uses: int = 1,
        count: int = 1,
        prefix: str = "",
        length: int = 8,
        expires_at: str = "",
        status: str = "active",
        note: str = "",
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        target = max(1, int(count))
        for _ in range(target):
            for _attempt in range(20):
                code = make_redeem_code(prefix, length)
                if self.get_redeem_code(code):
                    continue
                item = self.upsert_redeem_code(code, code_type, credits, duration_days, max_uses, expires_at, status, note)
                if item:
                    items.append(item)
                    break
        return items

    def get_redeem_code(self, code: str) -> dict[str, Any] | None:
        clean_code = normalize_code(code)
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM redeem_codes WHERE code = ?", (clean_code,)).fetchone()
        return dict(row) if row else None

    def list_redeem_codes(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM redeem_codes
                ORDER BY created_at DESC, code ASC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_redeem_redemptions(self, code: str, limit: int = 100) -> list[dict[str, Any]]:
        clean_code = normalize_code(code)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM redeem_redemptions
                WHERE code = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (clean_code, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def redeem_code(self, user_id: str, code: str) -> tuple[dict[str, Any] | None, str]:
        clean_code = normalize_code(code)
        if not clean_code:
            return None, "redeem_code_required"
        self.ensure_user(user_id)
        stamp = now_iso()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            code_row = conn.execute("SELECT * FROM redeem_codes WHERE code = ?", (clean_code,)).fetchone()
            if not code_row:
                return None, "redeem_code_invalid"
            item = dict(code_row)
            existing = conn.execute(
                "SELECT * FROM redeem_redemptions WHERE user_id = ? AND code = ?",
                (user_id, clean_code),
            ).fetchone()
            if existing:
                return dict(existing), "redeem_code_already_used"
            if item.get("status") == "exhausted":
                return None, "redeem_code_exhausted"
            if item.get("status") != "active":
                return None, "redeem_code_inactive"
            if item.get("expires_at") and str(item["expires_at"]) < stamp:
                return None, "redeem_code_expired"
            if int(item.get("max_uses", 0) or 0) > 0 and int(item.get("used_count", 0) or 0) >= int(item.get("max_uses", 0) or 0):
                return None, "redeem_code_exhausted"

            code_type = normalize_redeem_type(str(item.get("type") or "credits"))
            credits = max(0, int(item.get("credits", item.get("daily_reply_quota", 0)) or 0))
            duration_days = max(0, int(item.get("duration_days", 0) or 0))
            if code_type == "credits" and credits <= 0:
                return None, "redeem_code_invalid"
            if code_type == "time_pass" and duration_days <= 0:
                return None, "redeem_code_invalid"
            redemption_id = new_id("redeem")
            granted_until = ""
            if code_type == "credits":
                user = conn.execute("SELECT credits_balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
                balance = int(user["credits_balance"] if user else 0) + credits
                conn.execute("UPDATE users SET credits_balance = ?, updated_at = ? WHERE user_id = ?", (balance, stamp, user_id))
                insert_credit_ledger(conn, user_id, credits, balance, "redeem_code", "redeem_code", clean_code, "")
            else:
                current = conn.execute("SELECT time_pass_expires_at FROM users WHERE user_id = ?", (user_id,)).fetchone()
                current_expires = str(current["time_pass_expires_at"] if current else "")
                base = parse_iso_datetime(current_expires) if current_expires > stamp else datetime.now()
                granted_until = (base + timedelta(days=duration_days)).isoformat(timespec="seconds")
                conn.execute("UPDATE users SET time_pass_expires_at = ?, updated_at = ? WHERE user_id = ?", (granted_until, stamp, user_id))
            conn.execute(
                """
                INSERT INTO redeem_redemptions(
                    redemption_id, user_id, code, daily_reply_quota, type, credits, duration_days,
                    granted_time_pass_expires_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (redemption_id, user_id, clean_code, credits, code_type, credits, duration_days, granted_until, stamp),
            )
            conn.execute(
                """
                UPDATE redeem_codes
                SET used_count = used_count + 1,
                    status = CASE
                        WHEN max_uses > 0 AND used_count + 1 >= max_uses THEN 'exhausted'
                        ELSE status
                    END,
                    updated_at = ?
                WHERE code = ?
                """,
                (stamp, clean_code),
            )
        return {
            "code": clean_code,
            "type": code_type,
            "credits": credits,
            "duration_days": duration_days,
            "time_pass_expires_at": granted_until,
        }, ""

    def list_admin_reply_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    run_id, user_id, conversation_id, mode, status, question, image_count,
                    answer_json, reference_segments_json, runtime_run_id, unit_cost, charge_source,
                    created_at, updated_at
                FROM reply_runs
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [decode_admin_reply_run_row(row) for row in rows]

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


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def existing_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row["name"]) for row in rows}


def insert_credit_ledger(
    conn: sqlite3.Connection,
    user_id: str,
    delta: int,
    balance_after: int,
    reason: str,
    ref_type: str = "",
    ref_id: str = "",
    note: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO credit_ledger(ledger_id, user_id, delta, balance_after, reason, ref_type, ref_id, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (new_id("ledger"), user_id, int(delta), int(balance_after), reason, ref_type, ref_id, note, now_iso()),
    )


def normalize_code(code: str) -> str:
    return "".join(str(code or "").strip().upper().split())


def normalize_redeem_type(value: str) -> str:
    return "time_pass" if str(value or "").strip().lower() == "time_pass" else "credits"


def make_redeem_code(prefix: str = "", length: int = 8) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    size = max(6, min(24, int(length or 8)))
    body = "".join(secrets.choice(alphabet) for _ in range(size))
    clean_prefix = normalize_code(prefix)
    return f"{clean_prefix}-{body}" if clean_prefix else body


def parse_iso_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value or ""))
    except ValueError:
        return datetime.now()


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
    item["timings"] = answer.get("_timings", {}) if isinstance(answer, dict) else {}
    item["reference_count"] = len(refs) if isinstance(refs, list) else 0
    return item


def decode_admin_reply_run_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    answer = decode_json(item.pop("answer_json", ""), {})
    refs = decode_json(item.pop("reference_segments_json", ""), [])
    item["reply"] = answer.get("reply", "") if isinstance(answer, dict) else ""
    item["risk_warning"] = answer.get("risk_warning", "") if isinstance(answer, dict) else ""
    item["timings"] = answer.get("_timings", {}) if isinstance(answer, dict) else {}
    item["reference_count"] = len(refs) if isinstance(refs, list) else 0
    return item


def model_timings_from_result(result: dict[str, Any]) -> dict[str, Any]:
    items = {
        "vision": result.get("vision_result", {}),
        "label": result.get("label_result", {}),
        "reply": result.get("reply_result", {}),
    }
    timings: dict[str, Any] = {}
    total = 0.0
    for key, value in items.items():
        value = value if isinstance(value, dict) else {}
        elapsed = numeric_elapsed(value.get("elapsed_seconds"))
        usage = value.get("usage", {}) if isinstance(value.get("usage", {}), dict) else {}
        timings[key] = {
            "elapsed_seconds": elapsed,
            "model": value.get("model", ""),
            "status": value.get("status", ""),
            "total_tokens": usage.get("total_tokens"),
        }
        total += elapsed
    timings["total_model_elapsed_seconds"] = round(total, 2)
    timings["reference_count"] = len(result.get("reference_segments", [])) if isinstance(result.get("reference_segments", []), list) else 0
    return timings


def numeric_elapsed(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0
