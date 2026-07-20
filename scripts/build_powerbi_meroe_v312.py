"""Build an anonymised demo dataset for the MEROE V3.12 Power BI dashboard."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "powerbi_meroe_v312" / "data"
RNG = random.Random(312)
START = date(2026, 1, 1)
DAYS = 181
ZONES = ["Libreville-Centre", "Nkembo", "Nzeng-Ayong", "Owendo", "Akanda", "Port-Gentil"]
MOTIFS = ["CAPOT_OUVERT", "SAUT_INDEX", "CHUTE_CONSO", "BYPASS_SHUNT", "INVERSION_PHASE"]


def write_csv(name: str, rows: list[dict]) -> None:
    path = OUT / name
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def meter_hash(value: int) -> str:
    return hashlib.sha256(f"MEROE-DEMO-{value}".encode()).hexdigest()[:16].upper()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    calendar, airtel, guichets, sms, calls = [], [], [], [], []
    anomalies, seeg_returns, admin = [], [], []
    active = 4250
    anomaly_id = 1

    for i in range(DAYS):
        day = START + timedelta(days=i)
        weekend = day.weekday() >= 5
        new_airtel = max(2, int(RNG.gauss(24 if not weekend else 15, 5)))
        churn_airtel = max(0, int(RNG.gauss(4, 2)))
        new_counter = max(1, int(RNG.gauss(9 if not weekend else 4, 3)))
        churn_counter = max(0, int(RNG.gauss(2, 1)))
        active += new_airtel + new_counter - churn_airtel - churn_counter

        airtel.append({"date": day, "subscriptions": new_airtel, "unsubscriptions": churn_airtel,
                       "gross_revenue_xaf": new_airtel * 300, "paid_to_meroe_xaf": int(new_airtel * 300 * .70 * (i < DAYS - 7))})
        guichets.append({"date": day, "subscriptions": new_counter, "unsubscriptions": churn_counter,
                         "gross_revenue_xaf": new_counter * 300, "paid_to_meroe_xaf": int(new_counter * 300 * .70 * (i < DAYS - 30))})
        sent = max(20, int(active * RNG.uniform(.055, .085)))
        delivered = int(sent * RNG.uniform(.91, .985))
        recharged = int(delivered * RNG.uniform(.29, .43))
        sms.append({"date": day, "sent_j3": sent, "delivered": delivered, "recharged_72h": recharged})
        calls.append({"date": day, "priority_calls": max(1, int(RNG.gauss(19 if not weekend else 8, 5)))})

        daily_anomalies = max(3, int(RNG.gauss(10, 3)))
        for _ in range(daily_anomalies):
            zone = RNG.choices(ZONES, weights=[14, 22, 20, 21, 10, 13])[0]
            motif = RNG.choices(MOTIFS, weights=[28, 21, 23, 17, 11])[0]
            potential = RNG.randrange(150_000, 2_500_001, 25_000)
            score = round(RNG.uniform(.72, .99), 3)
            anomaly_key = f"ANO-{anomaly_id:06d}"
            anomalies.append({"anomaly_id": anomaly_key, "date": day, "meter_hash": meter_hash(anomaly_id),
                              "zone": zone, "motif": motif, "score": score, "estimated_loss_xaf": potential})
            qualified = RNG.random() < .27
            recovered = int(potential * RNG.uniform(.25, .90)) if qualified and RNG.random() < .76 else 0
            return_day = min(day + timedelta(days=RNG.randint(8, 35)), START + timedelta(days=DAYS - 1))
            seeg_returns.append({"anomaly_id": anomaly_key, "return_date": return_day,
                                 "qualification_status": "QUALIFIE_FRAUDE" if qualified else "NON_QUALIFIE",
                                 "recovered_amount_xaf": recovered})
            anomaly_id += 1

    for month in range(1, 7):
        month_date = date(2026, month, 1)
        admin.extend([
            {"month": month_date, "document_type": "RELEVE_AIRTEL", "status": "RECU", "invoice_amount_xaf": 0, "tickets": 0, "sftp_status": "OK", "cndp_log_hash": meter_hash(9000 + month)},
            {"month": month_date, "document_type": "BORDEREAU_SEEG", "status": "RECU" if month < 6 else "ATTENDU", "invoice_amount_xaf": 0, "tickets": 0, "sftp_status": "OK" if month != 4 else "KO", "cndp_log_hash": meter_hash(9100 + month)},
            {"month": month_date, "document_type": "FACTURE_MEROE", "status": "EMISE", "invoice_amount_xaf": 1_200_000 + month * 175_000, "tickets": RNG.randint(1, 9), "sftp_status": "OK", "cndp_log_hash": meter_hash(9200 + month)},
        ])

    for i in range(DAYS):
        day = START + timedelta(days=i)
        calendar.append({"date": day, "year": day.year, "month_number": day.month,
                         "month": day.strftime("%Y-%m"), "week": day.isocalendar().week, "day_name": day.strftime("%A")})

    write_csv("dim_date.csv", calendar)
    write_csv("flux_airtel.csv", airtel)
    write_csv("flux_guichets_seeg.csv", guichets)
    write_csv("flux_sms.csv", sms)
    write_csv("flux_calls.csv", calls)
    write_csv("flux_ia_anomalies.csv", anomalies)
    write_csv("flux_retour_seeg.csv", seeg_returns)
    write_csv("flux_administratif.csv", admin)
    manifest = {"version": "MEROE V3.12", "generated": str(date.today()), "demo": True,
                "privacy": "No names, phone numbers or raw meter identifiers", "active_subscribers_end": active}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generated {len(anomalies)} anomalies in {OUT}")


if __name__ == "__main__":
    main()
