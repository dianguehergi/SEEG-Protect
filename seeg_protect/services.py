import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings
from .logging_utils import append_event
from .models import LowBalanceAlert, PaymentConfirmation, SubscriptionRequest
from .sms import SmsGateway
from .storage import Storage


class SeegProtectService:
    def __init__(self, settings: Settings, storage: Storage, sms_gateway: SmsGateway) -> None:
        self.settings = settings
        self.storage = storage
        self.sms_gateway = sms_gateway

    def register_subscription(self, request: SubscriptionRequest) -> dict[str, Any]:
        subscription = self.storage.upsert_subscription(
            request.subscription_id,
            request.meter_id,
            request.phone_number,
            request.customer_ref,
            request.requested_at,
        )
        self._record_event("subscription.received", request.meter_id, request.__dict__)
        return {
            "status": "accepted",
            "subscription": subscription,
        }

    def confirm_payment(self, payment: PaymentConfirmation) -> dict[str, Any]:
        subscription = self.storage.activate_subscription(
            payment.subscription_id,
            payment.meter_id,
            payment.transaction_id,
            payment.amount_xaf,
            payment.status,
            payment.paid_at,
        )
        self._record_event("payment.received", payment.transaction_id, payment.__dict__)
        return {
            "status": "accepted",
            "subscription": subscription,
        }

    def handle_low_balance(self, alert: LowBalanceAlert) -> dict[str, Any]:
        subscription = self.storage.get_subscription_by_meter(alert.meter_id)
        self._record_event("low_balance.received", alert.meter_id, alert.__dict__)

        if not subscription:
            return {
                "status": "ignored",
                "reason": "unknown_meter",
                "meter_id": alert.meter_id,
            }
        if subscription["status"] != "active":
            return {
                "status": "ignored",
                "reason": "subscription_not_active",
                "meter_id": alert.meter_id,
            }

        daily_average = alert.daily_average_kwh or self.settings.daily_average_kwh
        days_remaining = self.calculate_days_remaining(alert.balance_kwh, daily_average)
        if self.settings.low_balance_sms_cooldown_hours > 0:
            cooldown_since = (
                datetime.now(timezone.utc)
                - timedelta(hours=self.settings.low_balance_sms_cooldown_hours)
            ).isoformat()
            if self.storage.has_recent_notification(alert.meter_id, "sms", cooldown_since):
                self._record_event(
                    "sms.skipped_recent_notification",
                    alert.meter_id,
                    {
                        "meter_id": alert.meter_id,
                        "days_remaining": days_remaining,
                        "cooldown_hours": self.settings.low_balance_sms_cooldown_hours,
                    },
                )
                return {
                    "status": "ignored",
                    "reason": "recent_notification",
                    "meter_id": alert.meter_id,
                    "days_remaining": days_remaining,
                }

        message = (
            f"SEEG Protect: votre compteur {alert.meter_id} a environ "
            f"{days_remaining} jour(s) d'electricite restant(s). Pensez a recharger."
        )
        sms_result = self.sms_gateway.send(subscription["phone_number"], message)
        self.storage.save_notification(
            alert.meter_id,
            subscription["phone_number"],
            message,
            sms_result.status,
        )
        self._record_event(
            "sms.queued",
            sms_result.provider_reference,
            {
                "meter_id": alert.meter_id,
                "phone_number": subscription["phone_number"],
                "days_remaining": days_remaining,
                "provider_reference": sms_result.provider_reference,
            },
        )
        return {
            "status": "notified",
            "meter_id": alert.meter_id,
            "days_remaining": days_remaining,
            "sms_status": sms_result.status,
        }

    @staticmethod
    def calculate_days_remaining(balance_kwh: float, daily_average_kwh: float) -> int:
        if daily_average_kwh <= 0:
            raise ValueError("daily_average_kwh must be greater than zero")
        return max(0, math.ceil(balance_kwh / daily_average_kwh))

    def _record_event(self, event_type: str, reference: str | None, payload: dict[str, Any]) -> None:
        payload_json = json.dumps(payload, ensure_ascii=False)
        self.storage.save_event(event_type, reference, payload_json)
        append_event(self.settings.event_log_path, event_type, payload)
