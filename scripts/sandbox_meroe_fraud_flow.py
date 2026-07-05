from __future__ import annotations

from dataclasses import dataclass


SUCCESS_FEE_RATE = 0.05


@dataclass(frozen=True)
class SandboxMeter:
    id_compteur: str
    statut: str
    motif_reactivation: str
    montant_pv_reference: int
    montant_encaisse: int


SANDBOX_METERS = {
    "999000001": SandboxMeter(
        id_compteur="999000001",
        statut="REACTIVE",
        motif_reactivation="PAIEMENT_PV",
        montant_pv_reference=1_500_000,
        montant_encaisse=1_500_000,
    ),
    "999000002": SandboxMeter(
        id_compteur="999000002",
        statut="COUPE",
        motif_reactivation="",
        montant_pv_reference=1_500_000,
        montant_encaisse=0,
    ),
    "999000003": SandboxMeter(
        id_compteur="999000003",
        statut="REACTIVE",
        motif_reactivation="ERREUR_TECH",
        montant_pv_reference=1_500_000,
        montant_encaisse=0,
    ),
}


def calculate_success_fee(meter: SandboxMeter) -> int:
    return round(meter.montant_encaisse * SUCCESS_FEE_RATE)


def simulate_meter(id_compteur: str) -> str:
    meter = SANDBOX_METERS[id_compteur]
    lines = [f"### TEST COMPTEUR {meter.id_compteur} ###", f"Statut EDAN: {meter.statut}"]

    if meter.statut == "COUPE":
        lines.append("0 FCFA. Dossier toujours coupe.")
        return "\n".join(lines)

    if meter.motif_reactivation != "PAIEMENT_PV":
        lines.append(
            "ALERTE ART 7.4: reactivation sans PAIEMENT_PV. Notification audit DSI SEEG."
        )
        return "\n".join(lines)

    fee = calculate_success_fee(meter)
    lines.append(f"Webhook recu. Facture MEROE: {fee} FCFA")
    return "\n".join(lines)


def main() -> None:
    for id_compteur in SANDBOX_METERS:
        print(simulate_meter(id_compteur))
        print()


if __name__ == "__main__":
    main()
