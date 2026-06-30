from dataclasses import dataclass
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import Settings
from .models import utc_now_iso


@dataclass(frozen=True)
class SmsResult:
    status: str
    provider_reference: str


class SmsGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, phone_number: str, message: str) -> SmsResult:
        if self.settings.sms_provider.lower() == "http":
            return self._send_http(phone_number, message)
        provider_reference = f"stub-{abs(hash((phone_number, message))) % 10_000_000}"
        result = SmsResult(status="queued", provider_reference=provider_reference)
        self._write_stub_outbox(phone_number, message, result)
        return result

    def _write_stub_outbox(self, phone_number: str, message: str, result: SmsResult) -> None:
        outbox_path = Path(self.settings.sms_outbox_path)
        outbox_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": utc_now_iso(),
            "provider": "stub",
            "sender": self.settings.sms_sender_name,
            "to": phone_number,
            "message": message,
            "status": result.status,
            "provider_reference": result.provider_reference,
        }
        with outbox_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _send_http(self, phone_number: str, message: str) -> SmsResult:
        if not self.settings.sms_api_url:
            return SmsResult(status="failed", provider_reference="missing-sms-api-url")

        payload = {
            "to": phone_number,
            "message": message,
            "sender": self.settings.sms_sender_name,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.settings.sms_api_token:
            headers["Authorization"] = f"Bearer {self.settings.sms_api_token}"

        request = Request(self.settings.sms_api_url, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.settings.sms_timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
                return self._parse_http_response(response.status, response_body)
        except HTTPError as exc:
            return SmsResult(status="failed", provider_reference=f"http-{exc.code}")
        except URLError as exc:
            return SmsResult(status="failed", provider_reference=f"network-{exc.reason}")
        except TimeoutError:
            return SmsResult(status="failed", provider_reference="timeout")

    @staticmethod
    def _parse_http_response(status_code: int, response_body: str) -> SmsResult:
        if status_code >= 400:
            return SmsResult(status="failed", provider_reference=f"http-{status_code}")

        provider_reference = f"http-{status_code}"
        status = "sent" if status_code < 300 else "queued"
        if response_body:
            try:
                payload = json.loads(response_body)
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                provider_reference = str(
                    payload.get("message_id")
                    or payload.get("id")
                    or payload.get("reference")
                    or provider_reference
                )
                status = str(payload.get("status") or status)

        return SmsResult(status=status, provider_reference=provider_reference)
