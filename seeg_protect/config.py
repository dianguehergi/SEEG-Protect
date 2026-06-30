from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_name: str = "SEEG Protect"
    version: str = "0.1.0"
    host: str = os.getenv("SEEG_PROTECT_HOST", "127.0.0.1")
    port: int = int(os.getenv("SEEG_PROTECT_PORT", "8000"))
    database_path: str = os.getenv("SEEG_PROTECT_DB", "data/seeg_protect.sqlite3")
    event_log_path: str = os.getenv("SEEG_PROTECT_EVENT_LOG", "logs/events.jsonl")
    webhook_secret: str = os.getenv("SEEG_PROTECT_WEBHOOK_SECRET", "dev-secret-change-me")
    daily_average_kwh: float = float(os.getenv("SEEG_PROTECT_DAILY_AVERAGE_KWH", "4.0"))
    sms_sender_name: str = os.getenv("SEEG_PROTECT_SMS_SENDER", "SEEG Protect")
    sms_provider: str = os.getenv("SEEG_PROTECT_SMS_PROVIDER", "stub")
    sms_api_url: str = os.getenv("SEEG_PROTECT_SMS_API_URL", "")
    sms_api_token: str = os.getenv("SEEG_PROTECT_SMS_API_TOKEN", "")
    sms_timeout_seconds: float = float(os.getenv("SEEG_PROTECT_SMS_TIMEOUT_SECONDS", "10"))
    sms_outbox_path: str = os.getenv("SEEG_PROTECT_SMS_OUTBOX", "logs/sms_outbox.jsonl")
    low_balance_sms_cooldown_hours: float = float(
        os.getenv("SEEG_PROTECT_LOW_BALANCE_SMS_COOLDOWN_HOURS", "24")
    )
    admin_token: str = os.getenv("SEEG_PROTECT_ADMIN_TOKEN", "")


settings = Settings()
