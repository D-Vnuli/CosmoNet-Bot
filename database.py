import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("database/cosmonet.db")


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language_code TEXT,
                registered_at TEXT NOT NULL,
                vpn_uuid TEXT,
                devices_count INTEGER DEFAULT 0,
                last_connection TEXT,
                notes TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'inactive',
                tariff TEXT,
                started_at TEXT,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        conn.commit()


def add_user_if_not_exists(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None = None,
    language_code: str | None = None
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO users (
                telegram_id,
                username,
                first_name,
                last_name,
                language_code,
                registered_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            telegram_id,
            username,
            first_name,
            last_name,
            language_code,
            now
        ))

        conn.commit()

        cursor.execute("""
            SELECT id FROM users WHERE telegram_id = ?
        """, (telegram_id,))

        user = cursor.fetchone()

        if user:
            user_id = user[0]

            cursor.execute("""
                INSERT OR IGNORE INTO subscriptions (
                    user_id,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, 'inactive', ?, ?)
            """, (
                user_id,
                now,
                now
            ))

            conn.commit()


def get_user_with_subscription(telegram_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                users.id,
                users.telegram_id,
                users.username,
                users.first_name,
                users.last_name,
                users.language_code,
                users.registered_at,
                users.vpn_uuid,
                users.devices_count,
                users.last_connection,
                subscriptions.status,
                subscriptions.tariff,
                subscriptions.started_at,
                subscriptions.expires_at
            FROM users
            LEFT JOIN subscriptions ON subscriptions.user_id = users.id
            WHERE users.telegram_id = ?
            ORDER BY subscriptions.id DESC
            LIMIT 1
        """, (telegram_id,))

        return cursor.fetchone()


def get_users_count():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0]


def get_active_subscriptions_count():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM subscriptions
            WHERE status = 'active'
        """)

        return cursor.fetchone()[0]


def get_inactive_subscriptions_count():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM subscriptions
            WHERE status = 'inactive'
        """)

        return cursor.fetchone()[0]

def get_all_users(limit: int = 20):
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                users.telegram_id,
                users.username,
                users.first_name,
                users.registered_at
            FROM users
            ORDER BY users.id DESC
            LIMIT ?
        """, (limit,))

        return cursor.fetchall()


def get_all_telegram_ids():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM users")
        return [row[0] for row in cursor.fetchall()]


def get_users_stats():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM users
            LEFT JOIN subscriptions ON subscriptions.user_id = users.id
            WHERE subscriptions.status = 'active'
        """)
        active_users = cursor.fetchone()[0]

        inactive_users = total_users - active_users

        return {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": inactive_users
        }
