import json
from pathlib import Path
import sys
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seeg_protect.config import settings
from seeg_protect.security import build_signature


BASE_URL = f"http://{settings.host}:{settings.port}"


def post_json(path: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-SEEG-Signature": build_signature(settings.webhook_secret, body),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    suffix = str(int(time.time()))
    subscription_id = f"api-sub-{suffix}"
    meter_id = f"api-meter-{suffix}"

    subscription = post_json(
        "/webhooks/subscriptions",
        {
            "subscription_id": subscription_id,
            "meter_id": meter_id,
            "phone_number": "+24100000000",
            "customer_ref": "api-demo-client",
        },
    )
    payment = post_json(
        "/webhooks/payments",
        {
            "subscription_id": subscription_id,
            "meter_id": meter_id,
            "transaction_id": f"api-tx-{suffix}",
            "amount_xaf": 250,
            "status": "confirmed",
        },
    )
    low_balance = post_json(
        "/webhooks/low-balance",
        {
            "meter_id": meter_id,
            "balance_kwh": 5.0,
            "daily_average_kwh": 2.0,
            "threshold_kwh": 6.0,
        },
    )
    duplicate_low_balance = post_json(
        "/webhooks/low-balance",
        {
            "meter_id": meter_id,
            "balance_kwh": 4.0,
            "daily_average_kwh": 2.0,
            "threshold_kwh": 6.0,
        },
    )

    print("Subscription:")
    print(json.dumps(subscription, indent=2, ensure_ascii=False))
    print("Payment:")
    print(json.dumps(payment, indent=2, ensure_ascii=False))
    print("Low balance:")
    print(json.dumps(low_balance, indent=2, ensure_ascii=False))
    print("Duplicate low balance:")
    print(json.dumps(duplicate_low_balance, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
