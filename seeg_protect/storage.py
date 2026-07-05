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

                CREATE TABLE IF NOT EXISTS fraud_cases (
                    fraud_case_id TEXT PRIMARY KEY,
                    meter_id TEXT NOT NULL,
                    score_fraud REAL NOT NULL,
                    fraud_code TEXT NOT NULL,
                    pv_amount_xaf INTEGER NOT NULL,
                    nfe_amount_xaf INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    meter_status TEXT NOT NULL,
                    reactivation_reason TEXT,
                    collected_amount_xaf INTEGER NOT NULL,
                    success_fee_xaf INTEGER NOT NULL,
                    audit_flag INTEGER NOT NULL,
                    detected_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_fraud_cases_meter
                ON fraud_cases (meter_id);

                CREATE INDEX IF NOT EXISTS idx_fraud_cases_status
                ON fraud_cases (status, meter_status);

                CREATE TABLE IF NOT EXISTS sos_energy_advances (
                    advance_id TEXT PRIMARY KEY,
                    meter_id TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    amount_advanced_xaf INTEGER NOT NULL,
                    amount_due_xaf INTEGER NOT NULL,
                    amount_paid_xaf INTEGER NOT NULL,
                    margin_xaf INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    due_at TEXT,
                    paid_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sos_energy_meter
                ON sos_energy_advances (meter_id);

                CREATE INDEX IF NOT EXISTS idx_sos_energy_status
                ON sos_energy_advances (status);
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
            fraud_cases = db.execute("SELECT COUNT(*) AS total FROM fraud_cases").fetchone()
            fraud_collected = db.execute(
                "SELECT COALESCE(SUM(collected_amount_xaf), 0) AS total FROM fraud_cases"
            ).fetchone()
            fraud_fee = db.execute(
                "SELECT COALESCE(SUM(success_fee_xaf), 0) AS total FROM fraud_cases"
            ).fetchone()
            sos_advances = db.execute("SELECT COUNT(*) AS total FROM sos_energy_advances").fetchone()
            sos_paid = db.execute(
                "SELECT COALESCE(SUM(amount_paid_xaf), 0) AS total FROM sos_energy_advances"
            ).fetchone()
            sos_margin = db.execute(
                "SELECT COALESCE(SUM(margin_xaf), 0) AS total FROM sos_energy_advances"
            ).fetchone()
            return {
                "subscriptions": int(subscriptions["total"]),
                "active_subscriptions": int(active["total"]),
                "payments": int(payments["total"]),
                "notifications": int(notifications["total"]),
                "fraud_cases": int(fraud_cases["total"]),
                "fraud_collected_xaf": int(fraud_collected["total"]),
                "fraud_success_fee_xaf": int(fraud_fee["total"]),
                "sos_energy_advances": int(sos_advances["total"]),
                "sos_energy_paid_xaf": int(sos_paid["total"]),
                "sos_energy_margin_xaf": int(sos_margin["total"]),
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
            fraud_statuses = db.execute(
                """
                SELECT meter_status AS status, COUNT(*) AS total
                FROM fraud_cases
                GROUP BY meter_status
                ORDER BY total DESC
                """
            ).fetchall()
            fraud_codes = db.execute(
                """
                SELECT fraud_code, COUNT(*) AS total
                FROM fraud_cases
                GROUP BY fraud_code
                ORDER BY total DESC
                LIMIT 8
                """
            ).fetchall()
            sos_statuses = db.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM sos_energy_advances
                GROUP BY status
                ORDER BY total DESC
                """
            ).fetchall()
            return {
                "subscription_statuses": [dict(row) for row in subscription_statuses],
                "notification_statuses": [dict(row) for row in notification_statuses],
                "notification_days": list(reversed([dict(row) for row in notification_days])),
                "event_types": [dict(row) for row in event_types],
                "fraud_statuses": [dict(row) for row in fraud_statuses],
                "fraud_codes": [dict(row) for row in fraud_codes],
                "sos_statuses": [dict(row) for row in sos_statuses],
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

    def upsert_fraud_case(
        self,
        fraud_case_id: str,
        meter_id: str,
        score_fraud: float,
        fraud_code: str,
        pv_amount_xaf: int,
        nfe_amount_xaf: int,
        status: str,
        detected_at: str,
    ) -> dict[str, Any]:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO fraud_cases (
                    fraud_case_id, meter_id, score_fraud, fraud_code, pv_amount_xaf,
                    nfe_amount_xaf, status, meter_status, collected_amount_xaf,
                    success_fee_xaf, audit_flag, detected_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'LISTE_ROUGE', 0, 0, 0, ?, ?)
                ON CONFLICT(fraud_case_id) DO UPDATE SET
                    meter_id = excluded.meter_id,
                    score_fraud = excluded.score_fraud,
                    fraud_code = excluded.fraud_code,
                    pv_amount_xaf = excluded.pv_amount_xaf,
                    nfe_amount_xaf = excluded.nfe_amount_xaf,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    fraud_case_id,
                    meter_id,
                    score_fraud,
                    fraud_code,
                    pv_amount_xaf,
                    nfe_amount_xaf,
                    status,
                    detected_at,
                    utc_now_iso(),
                ),
            )
            row = db.execute(
                "SELECT * FROM fraud_cases WHERE fraud_case_id = ?",
                (fraud_case_id,),
            ).fetchone()
            return dict(row) if row else {}

    def update_fraud_status(
        self,
        fraud_case_id: str,
        meter_id: str,
        meter_status: str,
        reactivation_reason: str | None,
        collected_amount_xaf: int,
        success_fee_xaf: int,
        audit_flag: bool,
        changed_at: str,
    ) -> dict[str, Any]:
        with self.connection() as db:
            db.execute(
                """
                UPDATE fraud_cases
                SET meter_id = ?, meter_status = ?, reactivation_reason = ?,
                    collected_amount_xaf = ?, success_fee_xaf = ?, audit_flag = ?,
                    updated_at = ?
                WHERE fraud_case_id = ?
                """,
                (
                    meter_id,
                    meter_status,
                    reactivation_reason,
                    collected_amount_xaf,
                    success_fee_xaf,
                    1 if audit_flag else 0,
                    changed_at,
                    fraud_case_id,
                ),
            )
            row = db.execute(
                "SELECT * FROM fraud_cases WHERE fraud_case_id = ?",
                (fraud_case_id,),
            ).fetchone()
            return dict(row) if row else {}

    def get_fraud_case(self, fraud_case_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM fraud_cases WHERE fraud_case_id = ?",
                (fraud_case_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_fraud_cases(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT fraud_case_id, meter_id, score_fraud, fraud_code, pv_amount_xaf,
                       nfe_amount_xaf, status, meter_status, reactivation_reason,
                       collected_amount_xaf, success_fee_xaf, audit_flag,
                       detected_at, updated_at
                FROM fraud_cases
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_sos_energy_advance(
        self,
        advance_id: str,
        meter_id: str,
        phone_number: str,
        amount_advanced_xaf: int,
        amount_due_xaf: int,
        status: str,
        requested_at: str,
        due_at: str | None,
    ) -> dict[str, Any]:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO sos_energy_advances (
                    advance_id, meter_id, phone_number, amount_advanced_xaf,
                    amount_due_xaf, amount_paid_xaf, margin_xaf, status,
                    requested_at, due_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?)
                ON CONFLICT(advance_id) DO UPDATE SET
                    meter_id = excluded.meter_id,
                    phone_number = excluded.phone_number,
                    amount_advanced_xaf = excluded.amount_advanced_xaf,
                    amount_due_xaf = excluded.amount_due_xaf,
                    status = excluded.status,
                    requested_at = excluded.requested_at,
                    due_at = excluded.due_at,
                    updated_at = excluded.updated_at
                """,
                (
                    advance_id,
                    meter_id,
                    phone_number,
                    amount_advanced_xaf,
                    amount_due_xaf,
                    status,
                    requested_at,
                    due_at,
                    utc_now_iso(),
                    utc_now_iso(),
                ),
            )
            row = db.execute(
                "SELECT * FROM sos_energy_advances WHERE advance_id = ?",
                (advance_id,),
            ).fetchone()
            return dict(row) if row else {}

    def repay_sos_energy_advance(
        self,
        advance_id: str,
        meter_id: str,
        amount_paid_xaf: int,
        status: str,
        paid_at: str,
    ) -> dict[str, Any]:
        with self.connection() as db:
            existing = db.execute(
                "SELECT * FROM sos_energy_advances WHERE advance_id = ?",
                (advance_id,),
            ).fetchone()
            if not existing:
                return {}
            margin = max(0, amount_paid_xaf - int(existing["amount_advanced_xaf"]))
            db.execute(
                """
                UPDATE sos_energy_advances
                SET meter_id = ?, amount_paid_xaf = ?, margin_xaf = ?,
                    status = ?, paid_at = ?, updated_at = ?
                WHERE advance_id = ?
                """,
                (meter_id, amount_paid_xaf, margin, status, paid_at, utc_now_iso(), advance_id),
            )
            row = db.execute(
                "SELECT * FROM sos_energy_advances WHERE advance_id = ?",
                (advance_id,),
            ).fetchone()
            return dict(row) if row else {}

    def get_sos_energy_advance(self, advance_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM sos_energy_advances WHERE advance_id = ?",
                (advance_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_sos_energy_advances(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT advance_id, meter_id, phone_number, amount_advanced_xaf,
                       amount_due_xaf, amount_paid_xaf, margin_xaf, status,
                       requested_at, due_at, paid_at, updated_at
                FROM sos_energy_advances
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

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
