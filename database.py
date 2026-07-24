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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                tariff_code TEXT NOT NULL,
                devices INTEGER NOT NULL,
                duration_days INTEGER NOT NULL,
                action TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'test',
                status TEXT NOT NULL DEFAULT 'pending',
                target_expiry_ms INTEGER NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)

        cursor.execute("PRAGMA table_info(orders)")
        order_columns = {
            row[1]
            for row in cursor.fetchall()
        }
        new_order_columns = {
            "payment_amount": "INTEGER",
            "currency": "TEXT",
            "invoice_payload": "TEXT",
            "telegram_payment_charge_id": "TEXT",
            "provider_payment_charge_id": "TEXT",
            "paid_at": "TEXT",
        }

        for column_name, column_type in new_order_columns.items():
            if column_name not in order_columns:
                cursor.execute(
                    f"ALTER TABLE orders "
                    f"ADD COLUMN {column_name} {column_type}"
                )

        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_orders_invoice_payload
            ON orders(invoice_payload)
            WHERE invoice_payload IS NOT NULL
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_orders_telegram_payment_charge
            ON orders(telegram_payment_charge_id)
            WHERE telegram_payment_charge_id IS NOT NULL
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


def is_registered_user(telegram_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1
            FROM users
            WHERE telegram_id = ?
            LIMIT 1
        """, (telegram_id,))
        return cursor.fetchone() is not None


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


def create_test_order(
    *,
    telegram_id: int,
    tariff_code: str,
    devices: int,
    duration_days: int,
    action: str,
    target_expiry_ms: int
) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO orders (
                telegram_id,
                tariff_code,
                devices,
                duration_days,
                action,
                provider,
                status,
                target_expiry_ms,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'test', 'pending', ?, ?, ?)
        """, (
            telegram_id,
            tariff_code,
            devices,
            duration_days,
            action,
            target_expiry_ms,
            now,
            now
        ))
        conn.commit()
        return cursor.lastrowid


def create_stars_order(
    *,
    telegram_id: int,
    tariff_code: str,
    devices: int,
    duration_days: int,
    action: str,
    target_expiry_ms: int,
    payment_amount: int
) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO orders (
                telegram_id,
                tariff_code,
                devices,
                duration_days,
                action,
                provider,
                status,
                target_expiry_ms,
                payment_amount,
                currency,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'telegram_stars', 'pending',
                    ?, ?, 'XTR', ?, ?)
        """, (
            telegram_id,
            tariff_code,
            devices,
            duration_days,
            action,
            target_expiry_ms,
            payment_amount,
            now,
            now
        ))
        order_id = cursor.lastrowid
        invoice_payload = f"cosmonet-stars:{order_id}"
        cursor.execute("""
            UPDATE orders
            SET invoice_payload = ?
            WHERE id = ?
        """, (invoice_payload, order_id))
        conn.commit()
        return order_id


def get_order(order_id: int):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT *
            FROM orders
            WHERE id = ?
        """, (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def claim_test_order(order_id: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders
            SET status = 'processing',
                error = NULL,
                updated_at = ?
            WHERE id = ?
              AND provider = 'test'
              AND status IN ('pending', 'failed')
        """, (now, order_id))
        conn.commit()

        if cursor.rowcount != 1:
            return None

    return get_order(order_id)


def claim_stars_payment(
    *,
    order_id: int,
    telegram_id: int,
    currency: str,
    total_amount: int,
    telegram_payment_charge_id: str,
    provider_payment_charge_id: str
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            "SELECT * FROM orders WHERE id = ?",
            (order_id,)
        )
        row = cursor.fetchone()

        if not row:
            return "not_found", None

        order = dict(row)
        expected_charge = order["telegram_payment_charge_id"]

        if (
            order["provider"] != "telegram_stars"
            or order["telegram_id"] != telegram_id
            or order["currency"] != currency
            or order["payment_amount"] != total_amount
        ):
            return "invalid", order

        if (
            expected_charge
            and expected_charge != telegram_payment_charge_id
        ):
            return "invalid", order

        if order["status"] == "paid":
            return "already_paid", order

        if order["status"] == "processing":
            return "processing", order

        if (
            order["status"] == "failed"
            and expected_charge != telegram_payment_charge_id
        ):
            return "invalid", order

        if order["status"] not in {"pending", "failed"}:
            return "invalid", order

        try:
            cursor.execute("""
                UPDATE orders
                SET status = 'processing',
                    telegram_payment_charge_id = ?,
                    provider_payment_charge_id = ?,
                    paid_at = COALESCE(paid_at, ?),
                    error = NULL,
                    updated_at = ?
                WHERE id = ?
            """, (
                telegram_payment_charge_id,
                provider_payment_charge_id,
                now,
                now,
                order_id
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return "duplicate_payment", get_order(order_id)

    return "claimed", get_order(order_id)


def claim_failed_stars_order(order_id: int, telegram_id: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders
            SET status = 'processing',
                error = NULL,
                updated_at = ?
            WHERE id = ?
              AND telegram_id = ?
              AND provider = 'telegram_stars'
              AND telegram_payment_charge_id IS NOT NULL
              AND status = 'failed'
        """, (now, order_id, telegram_id))
        conn.commit()

        if cursor.rowcount != 1:
            return None

    return get_order(order_id)


def complete_order(order_id: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders
            SET status = 'paid',
                error = NULL,
                updated_at = ?,
                completed_at = ?
            WHERE id = ?
        """, (now, now, order_id))
        conn.commit()


def fail_order(order_id: int, error: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders
            SET status = 'failed',
                error = ?,
                updated_at = ?
            WHERE id = ?
        """, (error, now, order_id))
        conn.commit()


def create_yookassa_order(
    *,
    telegram_id: int,
    tariff_code: str,
    devices: int,
    duration_days: int,
    action: str,
    target_expiry_ms: int,
    payment_amount: int,
) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO orders (
                telegram_id,
                tariff_code,
                devices,
                duration_days,
                action,
                provider,
                status,
                target_expiry_ms,
                payment_amount,
                currency,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'yookassa', 'pending',
                    ?, ?, 'RUB', ?, ?)
        """, (
            telegram_id,
            tariff_code,
            devices,
            duration_days,
            action,
            target_expiry_ms,
            payment_amount,
            now,
            now,
        ))
        conn.commit()
        return cursor.lastrowid


def claim_yookassa_payment(*, order_id: int, payment_id: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        if not row:
            return "not_found", None

        order = dict(row)
        if order["provider"] != "yookassa":
            return "invalid", order
        if order["status"] == "paid":
            return "already_paid", order
        if order["status"] == "processing":
            return "processing", order
        if order["status"] not in {"pending", "failed"}:
            return "invalid", order

        cursor.execute("""
            UPDATE orders
            SET status = 'processing',
                provider_payment_charge_id = ?,
                paid_at = COALESCE(paid_at, ?),
                error = NULL,
                updated_at = ?
            WHERE id = ?
        """, (payment_id, now, now, order_id))
        conn.commit()

    return "claimed", get_order(order_id)
