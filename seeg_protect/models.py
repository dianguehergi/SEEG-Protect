from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class ValidationError(ValueError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"Field '{field}' is required and must be a non-empty string.")
    return value.strip()


def require_number(payload: dict[str, Any], field: str) -> float:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"Field '{field}' is required and must be a number.")
    return float(value)


def optional_number(payload: dict[str, Any], field: str) -> float | None:
    value = payload.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"Field '{field}' must be a number when provided.")
    return float(value)


@dataclass(frozen=True)
class SubscriptionRequest:
    subscription_id: str
    meter_id: str
    phone_number: str
    customer_ref: str | None
    requested_at: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SubscriptionRequest":
        return cls(
            subscription_id=require_string(payload, "subscription_id"),
            meter_id=require_string(payload, "meter_id"),
            phone_number=require_string(payload, "phone_number"),
            customer_ref=payload.get("customer_ref"),
            requested_at=payload.get("requested_at") or utc_now_iso(),
        )


@dataclass(frozen=True)
class PaymentConfirmation:
    subscription_id: str
    meter_id: str
    transaction_id: str
    amount_xaf: int
    status: str
    paid_at: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PaymentConfirmation":
        amount = require_number(payload, "amount_xaf")
        if amount <= 0:
            raise ValidationError("Field 'amount_xaf' must be greater than zero.")
        return cls(
            subscription_id=require_string(payload, "subscription_id"),
            meter_id=require_string(payload, "meter_id"),
            transaction_id=require_string(payload, "transaction_id"),
            amount_xaf=int(amount),
            status=(payload.get("status") or "confirmed").strip().lower(),
            paid_at=payload.get("paid_at") or utc_now_iso(),
        )


@dataclass(frozen=True)
class LowBalanceAlert:
    meter_id: str
    balance_kwh: float
    daily_average_kwh: float | None
    threshold_kwh: float | None
    observed_at: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LowBalanceAlert":
        balance = require_number(payload, "balance_kwh")
        if balance < 0:
            raise ValidationError("Field 'balance_kwh' must be greater than or equal to zero.")
        daily_average = optional_number(payload, "daily_average_kwh")
        if daily_average is not None and daily_average <= 0:
            raise ValidationError("Field 'daily_average_kwh' must be greater than zero.")
        return cls(
            meter_id=require_string(payload, "meter_id"),
            balance_kwh=balance,
            daily_average_kwh=daily_average,
            threshold_kwh=optional_number(payload, "threshold_kwh"),
            observed_at=payload.get("observed_at") or utc_now_iso(),
        )

