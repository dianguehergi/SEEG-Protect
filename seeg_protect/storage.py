import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator
from typing import Any

from .models import utc_now_iso


class Storage:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = self.connect()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def initialize(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    subscription_id TEXT PRIMARY KEY,
                    meter_id TEXT NOT NULL UNIQUE,
                    phone_number TEXT NOT NULL,
                    customer_ref TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    activated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS payments (
                    transaction_id TEXT PRIMARY KEY,
                    subscription_id TEXT NOT NULL,
                    meter_id TEXT NOT NULL,
                    amount_xaf INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    paid_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meter_id TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS technical_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    reference TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_notifications_meter_channel_created
                ON notifications (meter_id, channel, created_at);

                CREATE INDEX IF NOT EXISTS idx_payments_meter_created
                ON payments (meter_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_events_reference_created
                ON technical_events (reference, created_at);
                """
            )

    def upsert_subscription(
        self,
        subscription_id: str,
        meter_id: str,
        phone_number: str,
        customer_ref: str | None,
        requested_at: str,
    ) -> dict[str, Any]:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO subscriptions (
                    subscription_id, meter_id, phone_number, customer_ref, status, created_at
                ) VALUES (?, ?, ?, ?, 'pending_payment', ?)
                ON CONFLICT(subscription_id) DO UPDATE SET
                    meter_id = excluded.meter_id,
                    phone_number = excluded.phone_number,
                    customer_ref = excluded.customer_ref
                """,
                (subscription_id, meter_id, phone_number, customer_ref, requested_at),
            )
            row = db.execute(
                "SELECT * FROM subscriptions WHERE meter_id = ?",
                (meter_id,),
            ).fetchone()
            return dict(row) if row else {}

    def activate_subscription(
        self,
        subscription_id: str,
        meter_id: str,
        transaction_id: str,
        amount_xaf: int,
        status: str,
        paid_at: str,
    ) -> dict[str, Any]:
        with self.connection() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO payments (
                    transaction_id, subscription_id, meter_id, amount_xaf, status, paid_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (transaction_id, subscription_id, meter_id, amount_xaf, status, paid_at, utc_now_iso()),
            )
            if status in {"confirmed", "paid", "success"}:
                db.execute(
                    """
                    UPDATE subscriptions
                    SET status = 'active', activated_at = ?
                    WHERE subscription_id = ? AND meter_id = ?
                    """,
                    (paid_at, subscription_id, meter_id),
                )
            row = db.execute(
                "SELECT * FROM subscriptions WHERE meter_id = ?",
                (meter_id,),
            ).fetchone()
            return dict(row) if row else {}

    def get_subscription_by_meter(self, meter_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM subscriptions WHERE meter_id = ?",
                (meter_id,),
            ).fetchone()
            return dict(row) if row else None

    def save_notification(self, meter_id: str, phone_number: str, message: str, status: str) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO notifications (meter_id, phone_number, channel, message, status, created_at)
                VALUES (?, ?, 'sms', ?, ?, ?)
                """,
                (meter_id, phone_number, message, status, utc_now_iso()),
            )

    def has_recent_notification(self, meter_id: str, channel: str, since: str) -> bool:
        with self.connection() as db:
            row = db.execute(
                """
                SELECT 1
                FROM notifications
                WHERE meter_id = ? AND channel = ? AND created_at >= ?
                LIMIT 1
                """,
                (meter_id, channel, since),
            ).fetchone()
            return row is not None

    def list_subscriptions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT subscription_id, meter_id, phone_number, customer_ref, status, created_at, activated_at
                FROM subscriptions
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_payments(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT transaction_id, subscription_id, meter_id, amount_xaf, status, paid_at, created_at
                FROM payments
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_notifications(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT id, meter_id, phone_number, channel, message, status, created_at
                FROM notifications
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def dashboard_summary(self) -> dict[str, int]:
        with self.connection() as db:
            subscriptions = db.execute("SELECT COUNT(*) AS total FROM subscriptions").fetchone()
            active = db.execute(
                "SELECT COUNT(*) AS total FROM subscriptions WHERE status = 'active'"
            ).fetchone()
            payments = db.execute("SELECT COUNT(*) AS total FROM payments").fetchone()
            notifications = db.execute("SELECT COUNT(*) AS total FROM notifications").fetchone()
            return {
                "subscriptions": int(subscriptions["total"]),
                "active_subscriptions": int(active["total"]),
                "payments": int(payments["total"]),
                "notifications": int(notifications["total"]),
            }

    def dashboard_metrics(self) -> dict[str, Any]:
        with self.connection() as db:
            subscription_statuses = db.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM subscriptions
                GROUP BY status
                ORDER BY total DESC
                """
            ).fetchall()
            notification_statuses = db.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM notifications
                GROUP BY status
                ORDER BY total DESC
                """
            ).fetchall()
            notification_days = db.execute(
                """
                SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS total
                FROM notifications
                GROUP BY day
                ORDER BY day DESC
                LIMIT 7
                """
            ).fetchall()
            event_types = db.execute(
                """
                SELECT event_type, COUNT(*) AS total
                FROM technical_events
                GROUP BY event_type
                ORDER BY total DESC
                LIMIT 8
                """
            ).fetchall()
            return {
                "subscription_statuses": [dict(row) for row in subscription_statuses],
                "notification_statuses": [dict(row) for row in notification_statuses],
                "notification_days": list(reversed([dict(row) for row in notification_days])),
                "event_types": [dict(row) for row in event_types],
            }

    def meter_detail(self, meter_id: str, limit: int = 20) -> dict[str, Any] | None:
        with self.connection() as db:
            subscription = db.execute(
                """
                SELECT subscription_id, meter_id, phone_number, customer_ref, status, created_at, activated_at
                FROM subscriptions
                WHERE meter_id = ?
                """,
                (meter_id,),
            ).fetchone()
            if not subscription:
                return None

            payments = db.execute(
                """
                SELECT transaction_id, subscription_id, meter_id, amount_xaf, status, paid_at, created_at
                FROM payments
                WHERE meter_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (meter_id, limit),
            ).fetchall()
            notifications = db.execute(
                """
                SELECT id, meter_id, phone_number, channel, message, status, created_at
                FROM notifications
                WHERE meter_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (meter_id, limit),
            ).fetchall()
            events = db.execute(
                """
                SELECT event_type, reference, payload_json, created_at
                FROM technical_events
                WHERE reference = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (meter_id, limit),
            ).fetchall()
            return {
                "subscription": dict(subscription),
                "payments": [dict(row) for row in payments],
                "notifications": [dict(row) for row in notifications],
                "events": [dict(row) for row in events],
            }

    def save_event(self, event_type: str, reference: str | None, payload_json: str) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO technical_events (event_type, reference, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (event_type, reference, payload_json, utc_now_iso()),
            )

    def recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT event_type, reference, payload_json, created_at
                FROM technical_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
