import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("database/cosmonet.db")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                registered_at TEXT NOT NULL,
                subscription_status TEXT NOT NULL DEFAULT 'inactive',
                subscription_until TEXT,
                tariff TEXT
            )
        """)

        conn.commit()


def add_user_if_not_exists(telegram_id: int, username: str | None, first_name: str | None):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO users (
                telegram_id,
                username,
                first_name,
                registered_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            telegram_id,
            username,
            first_name,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()


def get_user(telegram_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                telegram_id,
                username,
                first_name,
                registered_at,
                subscription_status,
                subscription_until,
                tariff
            FROM users
            WHERE telegram_id = ?
        """, (telegram_id,))

        return cursor.fetchone()