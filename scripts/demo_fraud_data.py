from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seeg_protect.config import settings
from seeg_protect.models import (
    FraudCase,
    FraudStatusUpdate,
    LowBalanceAlert,
    PaymentConfirmation,
    SosEnergyAdvance,
    SosEnergyRepayment,
    SubscriptionRequest,
)
from seeg_protect.services import SeegProtectService
from seeg_protect.sms import SmsGateway
from seeg_protect.storage import Storage


def main() -> None:
    service = SeegProtectService(settings, Storage(settings.database_path), SmsGateway(settings))

    meters = [
        {
            "meter_id": "demo-fraud-001",
            "phone": "+24100000001",
            "fraud_case_id": "FR-DEMO-001",
            "score": 0.98,
            "code": "BYPASS_AIMANT",
            "pv": 1_000_000,
            "nfe": 420_000,
            "meter_status": "REACTIVE",
            "reason": "PAIEMENT_PV",
            "collected": 1_420_000,
            "balance": 4.5,
        },
        {
            "meter_id": "demo-fraud-002",
            "phone": "+24100000002",
            "fraud_case_id": "FR-DEMO-002",
            "score": 0.96,
            "code": "BYPASS_SHUNT",
            "pv": 1_500_000,
            "nfe": 850_000,
            "meter_status": "COUPE",
            "reason": None,
            "collected": 0,
            "balance": 8.0,
        },
        {
            "meter_id": "demo-fraud-003",
            "phone": "+24100000003",
            "fraud_case_id": "FR-DEMO-003",
            "score": 0.99,
            "code": "FRAUDE_SW",
            "pv": 2_000_000,
            "nfe": 1_200_000,
            "meter_status": "REACTIVE",
            "reason": "ERREUR_TECH",
            "collected": 0,
            "balance": 2.0,
        },
        {
            "meter_id": "demo-fraud-004",
            "phone": "+24100000004",
            "fraud_case_id": "FR-DEMO-004",
            "score": 0.91,
            "code": "INV_PHASE",
            "pv": 750_000,
            "nfe": 300_000,
            "meter_status": "REACTIVE",
            "reason": "PAIEMENT_PV",
            "collected": 500_000,
            "balance": 3.0,
        },
    ]

    for index, meter in enumerate(meters, start=1):
        subscription_id = f"sub-{meter['meter_id']}"
        service.register_subscription(
            SubscriptionRequest(
                subscription_id=subscription_id,
                meter_id=str(meter["meter_id"]),
                phone_number=str(meter["phone"]),
                customer_ref=f"client-demo-{index}",
                requested_at="2026-09-01T08:00:00+00:00",
            )
        )
        service.confirm_payment(
            PaymentConfirmation(
                subscription_id=subscription_id,
                meter_id=str(meter["meter_id"]),
                transaction_id=f"tx-{meter['meter_id']}",
                amount_xaf=250,
                status="confirmed",
                paid_at="2026-09-01T08:05:00+00:00",
            )
        )
        service.handle_low_balance(
            LowBalanceAlert(
                meter_id=str(meter["meter_id"]),
                balance_kwh=float(meter["balance"]),
                daily_average_kwh=2.0,
                threshold_kwh=6.0,
                observed_at="2026-09-02T10:00:00+00:00",
            )
        )
        service.register_fraud_case(
            FraudCase(
                fraud_case_id=str(meter["fraud_case_id"]),
                meter_id=str(meter["meter_id"]),
                score_fraud=float(meter["score"]),
                fraud_code=str(meter["code"]),
                pv_amount_xaf=int(meter["pv"]),
                nfe_amount_xaf=int(meter["nfe"]),
                status="LISTE_ROUGE",
                detected_at="2026-09-03T06:00:00+00:00",
            )
        )
        service.update_fraud_status(
            FraudStatusUpdate(
                fraud_case_id=str(meter["fraud_case_id"]),
                meter_id=str(meter["meter_id"]),
                meter_status=str(meter["meter_status"]),
                reactivation_reason=meter["reason"],
                collected_amount_xaf=int(meter["collected"]),
                changed_at="2026-09-05T09:12:00+00:00",
            )
        )

    service.request_sos_energy(
        SosEnergyAdvance(
            advance_id="SOS-DEMO-001",
            meter_id="demo-fraud-001",
            phone_number="+24100000001",
            amount_advanced_xaf=2_000,
            amount_due_xaf=2_400,
            status="ADVANCED",
            requested_at="2026-09-06T08:00:00+00:00",
            due_at="2026-09-09T08:00:00+00:00",
        )
    )
    service.repay_sos_energy(
        SosEnergyRepayment(
            advance_id="SOS-DEMO-001",
            meter_id="demo-fraud-001",
            amount_paid_xaf=2_400,
            status="REPAID",
            paid_at="2026-09-09T08:00:00+00:00",
        )
    )

    service.request_sos_energy(
        SosEnergyAdvance(
            advance_id="SOS-DEMO-002",
            meter_id="demo-fraud-004",
            phone_number="+24100000004",
            amount_advanced_xaf=2_000,
            amount_due_xaf=2_400,
            status="ADVANCED",
            requested_at="2026-09-07T08:00:00+00:00",
            due_at="2026-09-10T08:00:00+00:00",
        )
    )

    print("Demo fraude chargee.")
    print("Ouvre /dashboard pour voir les compteurs, SMS, SOS Energie et dossiers fraude.")
    print("Ouvre /fraud-cases?limit=20 pour le JSON des dossiers.")


if __name__ == "__main__":
    main()
