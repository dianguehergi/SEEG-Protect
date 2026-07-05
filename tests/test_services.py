import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from seeg_protect.config import Settings
from seeg_protect.models import FraudCase, FraudStatusUpdate, LowBalanceAlert, PaymentConfirmation, SubscriptionRequest
from seeg_protect.services import SeegProtectService
from seeg_protect.sms import SmsGateway
from seeg_protect.storage import Storage


class ServiceTests(unittest.TestCase):
    def make_service(self) -> SeegProtectService:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base = Path(temp_dir.name)
        settings = Settings(
            database_path=str(base / "test.sqlite3"),
            event_log_path=str(base / "events.jsonl"),
            sms_outbox_path=str(base / "sms_outbox.jsonl"),
            daily_average_kwh=4.0,
        )
        return SeegProtectService(settings, Storage(settings.database_path), SmsGateway(settings))

    def test_days_remaining_rounds_up(self) -> None:
        self.assertEqual(SeegProtectService.calculate_days_remaining(7.2, 4.0), 2)

    def test_low_balance_notifies_active_subscription(self) -> None:
        service = self.make_service()
        service.register_subscription(
            SubscriptionRequest(
                subscription_id="sub-1",
                meter_id="meter-1",
                phone_number="+24100000000",
                customer_ref="client-1",
                requested_at="2026-06-30T00:00:00+00:00",
            )
        )
        service.confirm_payment(
            PaymentConfirmation(
                subscription_id="sub-1",
                meter_id="meter-1",
                transaction_id="tx-1",
                amount_xaf=250,
                status="confirmed",
                paid_at="2026-06-30T00:01:00+00:00",
            )
        )

        result = service.handle_low_balance(
            LowBalanceAlert(
                meter_id="meter-1",
                balance_kwh=5.0,
                daily_average_kwh=2.0,
                threshold_kwh=6.0,
                observed_at="2026-06-30T00:02:00+00:00",
            )
        )

        self.assertEqual(result["status"], "notified")
        self.assertEqual(result["days_remaining"], 3)

    def test_low_balance_skips_recent_duplicate_notification(self) -> None:
        service = self.make_service()
        service.register_subscription(
            SubscriptionRequest(
                subscription_id="sub-dup",
                meter_id="meter-dup",
                phone_number="+24100000000",
                customer_ref="client-dup",
                requested_at="2026-06-30T00:00:00+00:00",
            )
        )
        service.confirm_payment(
            PaymentConfirmation(
                subscription_id="sub-dup",
                meter_id="meter-dup",
                transaction_id="tx-dup",
                amount_xaf=250,
                status="confirmed",
                paid_at="2026-06-30T00:01:00+00:00",
            )
        )
        alert = LowBalanceAlert(
            meter_id="meter-dup",
            balance_kwh=5.0,
            daily_average_kwh=2.0,
            threshold_kwh=6.0,
            observed_at="2026-06-30T00:02:00+00:00",
        )

        first = service.handle_low_balance(alert)
        second = service.handle_low_balance(alert)

        self.assertEqual(first["status"], "notified")
        self.assertEqual(second["status"], "ignored")
        self.assertEqual(second["reason"], "recent_notification")

    def test_http_sms_gateway_posts_provider_payload(self) -> None:
        settings = Settings(
            sms_provider="http",
            sms_api_url="https://sms.example.test/messages",
            sms_api_token="token-1",
            sms_sender_name="SEEG Protect",
        )
        response = MagicMock()
        response.status = 202
        response.read.return_value = b'{"message_id":"msg-1","status":"queued"}'
        response.__enter__.return_value = response

        with patch("seeg_protect.sms.urlopen", return_value=response) as urlopen_mock:
            result = SmsGateway(settings).send("+24100000000", "Bonjour")

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(result.status, "queued")
        self.assertEqual(result.provider_reference, "msg-1")
        self.assertEqual(request.headers["Authorization"], "Bearer token-1")
        self.assertEqual(request.full_url, "https://sms.example.test/messages")

    def test_stub_sms_gateway_writes_visible_outbox(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        outbox_path = Path(temp_dir.name) / "sms_outbox.jsonl"
        settings = Settings(sms_outbox_path=str(outbox_path))

        result = SmsGateway(settings).send("+24100000000", "Bonjour")

        lines = outbox_path.read_text(encoding="utf-8").splitlines()
        sms = json.loads(lines[0])
        self.assertEqual(result.status, "queued")
        self.assertEqual(sms["to"], "+24100000000")
        self.assertEqual(sms["message"], "Bonjour")
        self.assertEqual(sms["provider"], "stub")

    def test_storage_dashboard_lists_business_records(self) -> None:
        service = self.make_service()
        service.register_subscription(
            SubscriptionRequest(
                subscription_id="sub-dashboard",
                meter_id="meter-dashboard",
                phone_number="+24100000000",
                customer_ref="client-dashboard",
                requested_at="2026-06-30T00:00:00+00:00",
            )
        )
        service.confirm_payment(
            PaymentConfirmation(
                subscription_id="sub-dashboard",
                meter_id="meter-dashboard",
                transaction_id="tx-dashboard",
                amount_xaf=250,
                status="confirmed",
                paid_at="2026-06-30T00:01:00+00:00",
            )
        )
        service.handle_low_balance(
            LowBalanceAlert(
                meter_id="meter-dashboard",
                balance_kwh=5.0,
                daily_average_kwh=2.0,
                threshold_kwh=6.0,
                observed_at="2026-06-30T00:02:00+00:00",
            )
        )

        summary = service.storage.dashboard_summary()
        self.assertEqual(summary["subscriptions"], 1)
        self.assertEqual(summary["active_subscriptions"], 1)
        self.assertEqual(summary["payments"], 1)
        self.assertEqual(summary["notifications"], 1)
        self.assertEqual(service.storage.list_subscriptions()[0]["meter_id"], "meter-dashboard")
        self.assertEqual(service.storage.list_payments()[0]["transaction_id"], "tx-dashboard")
        self.assertEqual(service.storage.list_notifications()[0]["meter_id"], "meter-dashboard")

    def test_storage_meter_detail_groups_meter_history(self) -> None:
        service = self.make_service()
        service.register_subscription(
            SubscriptionRequest(
                subscription_id="sub-meter-detail",
                meter_id="meter-detail",
                phone_number="+24100000000",
                customer_ref="client-detail",
                requested_at="2026-06-30T00:00:00+00:00",
            )
        )
        service.confirm_payment(
            PaymentConfirmation(
                subscription_id="sub-meter-detail",
                meter_id="meter-detail",
                transaction_id="tx-meter-detail",
                amount_xaf=250,
                status="confirmed",
                paid_at="2026-06-30T00:01:00+00:00",
            )
        )
        service.handle_low_balance(
            LowBalanceAlert(
                meter_id="meter-detail",
                balance_kwh=5.0,
                daily_average_kwh=2.0,
                threshold_kwh=6.0,
                observed_at="2026-06-30T00:02:00+00:00",
            )
        )

        detail = service.storage.meter_detail("meter-detail")

        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["subscription"]["subscription_id"], "sub-meter-detail")
        self.assertEqual(detail["payments"][0]["transaction_id"], "tx-meter-detail")
        self.assertEqual(detail["notifications"][0]["meter_id"], "meter-detail")
        self.assertTrue(detail["events"])

    def test_fraud_case_reactivation_calculates_success_fee(self) -> None:
        service = self.make_service()
        service.register_fraud_case(
            FraudCase(
                fraud_case_id="FR-1",
                meter_id="meter-fraud",
                score_fraud=0.98,
                fraud_code="BYPASS_AIMANT",
                pv_amount_xaf=1000000,
                nfe_amount_xaf=420000,
                status="LISTE_ROUGE",
                detected_at="2026-09-03T06:00:00+00:00",
            )
        )

        result = service.update_fraud_status(
            FraudStatusUpdate(
                fraud_case_id="FR-1",
                meter_id="meter-fraud",
                meter_status="REACTIVE",
                reactivation_reason="PAIEMENT_PV",
                collected_amount_xaf=1420000,
                changed_at="2026-09-05T09:12:00+00:00",
            )
        )

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["fraud_case"]["success_fee_xaf"], 71000)
        self.assertEqual(result["fraud_case"]["audit_flag"], 0)

    def test_fraud_case_reactivation_without_payment_flags_audit(self) -> None:
        service = self.make_service()
        service.register_fraud_case(
            FraudCase(
                fraud_case_id="FR-AUDIT",
                meter_id="meter-audit",
                score_fraud=0.99,
                fraud_code="FRAUDE_SW",
                pv_amount_xaf=2000000,
                nfe_amount_xaf=1200000,
                status="LISTE_ROUGE",
                detected_at="2026-09-03T06:00:00+00:00",
            )
        )

        result = service.update_fraud_status(
            FraudStatusUpdate(
                fraud_case_id="FR-AUDIT",
                meter_id="meter-audit",
                meter_status="REACTIVE",
                reactivation_reason="ERREUR_TECH",
                collected_amount_xaf=0,
                changed_at="2026-09-05T09:12:00+00:00",
            )
        )

        self.assertEqual(result["fraud_case"]["success_fee_xaf"], 0)
        self.assertEqual(result["fraud_case"]["audit_flag"], 1)


if __name__ == "__main__":
    unittest.main()
