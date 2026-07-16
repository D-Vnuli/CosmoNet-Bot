from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

import database


SESSION_TTL_MINUTES = 10
TOKEN_TTL_DAYS = 90


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_db(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def init_app_auth_db() -> None:
    with database.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_auth_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                login_code TEXT NOT NULL,
                device_name TEXT,
                platform TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                telegram_id INTEGER,
                display_name TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                approved_at TEXT,
                rejected_at TEXT,
                completed_at TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_app_auth_sessions_code
            ON app_auth_sessions(login_code, status, expires_at)
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_auth_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT UNIQUE NOT NULL,
                telegram_id INTEGER NOT NULL,
                device_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_app_auth_tokens_user
            ON app_auth_tokens(telegram_id, device_id, revoked_at)
        """)
        conn.commit()


class AppAuthService:
    def create_login_session(
        self,
        *,
        device_id: str,
        device_name: str | None,
        platform: str | None,
    ) -> dict[str, Any]:
        init_app_auth_db()
        now = _utc_now()
        expires_at = now + timedelta(minutes=SESSION_TTL_MINUTES)
        session_id = secrets.token_urlsafe(24)

        with database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE app_auth_sessions
                SET status = 'expired'
                WHERE device_id = ? AND status = 'pending'
            """, (device_id,))
            cursor.execute("""
                INSERT INTO app_auth_sessions (
                    device_id, login_code, device_name, platform, status,
                    created_at, expires_at
                )
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """, (
                device_id, session_id, device_name, platform,
                _to_db(now), _to_db(expires_at),
            ))
            conn.commit()

        return {
            "sessionId": session_id,
            "expiresAt": _to_db(expires_at),
        }

    def get_pending_session(self, session_id: str) -> dict[str, Any] | None:
        self._expire_old_sessions()
        return self._get_session(session_id, "pending")

    def approve_session(
        self,
        *,
        session_id: str,
        telegram_id: int,
        display_name: str,
    ) -> bool:
        init_app_auth_db()
        now = _to_db(_utc_now())
        with database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE app_auth_sessions
                SET status = 'approved', telegram_id = ?, display_name = ?,
                    approved_at = ?
                WHERE login_code = ? AND status = 'pending' AND expires_at > ?
            """, (telegram_id, display_name, now, session_id, now))
            conn.commit()
            return cursor.rowcount == 1

    def reject_session(self, *, session_id: str, telegram_id: int) -> bool:
        init_app_auth_db()
        with database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE app_auth_sessions
                SET status = 'rejected', telegram_id = ?, rejected_at = ?
                WHERE login_code = ? AND status = 'pending'
            """, (telegram_id, _to_db(_utc_now()), session_id))
            conn.commit()
            return cursor.rowcount == 1

    def get_status(self, *, device_id: str, session_id: str) -> dict[str, Any]:
        self._expire_old_sessions()
        session = self._get_session(session_id)
        if not session or session["device_id"] != device_id:
            return {
                "isAuthorized": False,
                "isPending": False,
                "message": "Сессия авторизации не найдена.",
            }

        if session["status"] == "pending":
            return {
                "isAuthorized": False,
                "isPending": True,
                "message": "Подтвердите вход в Telegram.",
            }

        if session["status"] == "approved":
            return {
                "isAuthorized": True,
                "isPending": False,
                "displayName": session["display_name"] or "Telegram подключен",
                "telegramId": session["telegram_id"],
                "authToken": self._issue_token(
                    telegram_id=session["telegram_id"],
                    device_id=device_id,
                ),
                "message": "Вход подтвержден.",
            }

        messages = {
            "expired": "Сессия авторизации истекла. Начните вход заново.",
            "rejected": "Вход отклонен в Telegram.",
        }
        return {
            "isAuthorized": False,
            "isPending": False,
            "message": messages.get(session["status"], "Авторизация недоступна."),
        }

    def get_token_owner(self, token: str) -> dict[str, Any] | None:
        init_app_auth_db()
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT telegram_id, device_id
                FROM app_auth_tokens
                WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > ?
                LIMIT 1
            """, (_hash_token(token), _to_db(_utc_now())))
            row = cursor.fetchone()
            return dict(row) if row else None

    def revoke_token(self, token: str) -> bool:
        init_app_auth_db()
        with database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE app_auth_tokens
                SET revoked_at = ?
                WHERE token_hash = ? AND revoked_at IS NULL
            """, (_to_db(_utc_now()), _hash_token(token)))
            conn.commit()
            return cursor.rowcount == 1

    def _get_session(
        self,
        session_id: str,
        status: str | None = None,
    ) -> dict[str, Any] | None:
        init_app_auth_db()
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = "SELECT * FROM app_auth_sessions WHERE login_code = ?"
            values: list[str] = [session_id]
            if status:
                query += " AND status = ?"
                values.append(status)
            query += " ORDER BY id DESC LIMIT 1"
            cursor.execute(query, values)
            row = cursor.fetchone()
            return dict(row) if row else None

    def _expire_old_sessions(self) -> None:
        init_app_auth_db()
        with database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE app_auth_sessions
                SET status = 'expired'
                WHERE status = 'pending' AND expires_at <= ?
            """, (_to_db(_utc_now()),))
            conn.commit()

    def _issue_token(self, *, telegram_id: int, device_id: str) -> str:
        now = _utc_now()
        token = secrets.token_urlsafe(32)
        with database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE app_auth_tokens
                SET revoked_at = ?
                WHERE telegram_id = ? AND device_id = ? AND revoked_at IS NULL
            """, (_to_db(now), telegram_id, device_id))
            cursor.execute("""
                INSERT INTO app_auth_tokens (
                    token_hash, telegram_id, device_id, created_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                _hash_token(token), telegram_id, device_id,
                _to_db(now), _to_db(now + timedelta(days=TOKEN_TTL_DAYS)),
            ))
            conn.commit()
        return token