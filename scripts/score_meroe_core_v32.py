import argparse
import csv
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = [
    "numero_compteur",
    "index_n",
    "index_n_1",
    "conso",
    "etat_sts",
    "recharges",
    "canal_paiement",
]

RED_LIST_THRESHOLD = 80
CSV_SEP = ";"
ANORMAL_STS = {"COUVERCLE_OUVERT", "BYPASS", "TAMPER", "ERREUR_STS", "COUPE"}
ATYPICAL_PAYMENT_CHANNELS = {"AUTRE", "INCONNU", "MANUEL"}


def parse_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default


def parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return default


def score_meter(row: dict[str, Any]) -> dict[str, Any]:
    index_n = parse_float(row.get("index_n"))
    index_n_1 = parse_float(row.get("index_n_1"))
    conso = parse_float(row.get("conso"))
    conso_moyenne_90j = parse_float(row.get("conso_moyenne_90j"))
    recharges = parse_int(row.get("recharges"))
    etat_sts = str(row.get("etat_sts", "")).strip().upper()
    canal_paiement = str(row.get("canal_paiement", "")).strip().upper()

    score = 0
    reasons: list[str] = []

    if index_n < index_n_1:
        score += 35
        reasons.append("INDEX_INCOHERENT")

    if conso == 0 and recharges > 0:
        score += 25
        reasons.append("CONSO_NULLE_AVEC_RECHARGE")

    if conso_moyenne_90j > 0 and conso < conso_moyenne_90j * 0.60:
        score += 25
        reasons.append("CHUTE_CONSO_40")

    if etat_sts in ANORMAL_STS:
        score += 25
        reasons.append(f"STS_{etat_sts}")

    if canal_paiement in ATYPICAL_PAYMENT_CHANNELS:
        score += 10
        reasons.append(f"CANAL_{canal_paiement}")

    anomaly_count = parse_int(row.get("anomalies_90j"))
    if anomaly_count >= 2:
        score += 15
        reasons.append("REPETITION_ANOMALIE")

    score = min(100, score)
    statut = "LISTE_ROUGE" if score >= RED_LIST_THRESHOLD else "SURVEILLANCE" if score >= 50 else "NORMAL"

    return {
        "numero_compteur": str(row.get("numero_compteur", "")).strip(),
        "quartier": str(row.get("quartier", "")).strip(),
        "score": score,
        "statut": statut,
        "type_anomalie": ",".join(reasons) if reasons else "AUCUNE",
        "montant_potentiel": parse_int(row.get("montant_potentiel")),
    }


def validate_columns(fieldnames: list[str] | None) -> None:
    if fieldnames is None:
        raise SystemExit("[V3.2] Fichier vide.")
    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise SystemExit(f"[V3.2] Colonnes manquantes: {missing}")


def score_file(input_path: Path, output_path: Path) -> tuple[int, int]:
    with input_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, delimiter=CSV_SEP)
        validate_columns(reader.fieldnames)
        scored_rows = [score_meter(row) for row in reader]

    red_list = [row for row in scored_rows if row["statut"] == "LISTE_ROUGE"]

    with output_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(
            target,
            delimiter=CSV_SEP,
            fieldnames=["numero_compteur", "quartier", "score", "statut", "type_anomalie", "montant_potentiel"],
        )
        writer.writeheader()
        writer.writerows(red_list)

    return len(scored_rows), len(red_list)


def main() -> None:
    parser = argparse.ArgumentParser(description="MEROE CORE V3.2 - scoring fraude explicable")
    parser.add_argument("input_csv", help="Fichier SEEG J+1")
    parser.add_argument(
        "--output",
        default="Liste_Rouge_MEROE_CORE_V3_2.csv",
        help="Fichier Liste Rouge genere",
    )
    args = parser.parse_args()

    total, red = score_file(Path(args.input_csv), Path(args.output))
    print(f"[V3.2] Scoring OK: {total} compteurs analyses.")
    print(f"[V3.2] Liste Rouge: {red} compteurs exportes dans {args.output}.")


if __name__ == "__main__":
    main()
