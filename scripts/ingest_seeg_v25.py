import csv
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:  # pragma: no cover - message shown only when run manually
    psycopg2 = None
    execute_values = None


CSV_SEP = ";"
DATE_FORMAT = "%d/%m/%Y %H:%M"
MAX_ERROR_RATE = 0.05
MAX_PURCHASES_PER_CLIENT = 12


def db_config() -> dict[str, str]:
    return {
        "host": os.getenv("PROTEC_DB_HOST", "localhost"),
        "dbname": os.getenv("PROTEC_DB_NAME", "protec_db"),
        "user": os.getenv("PROTEC_DB_USER", "protec_user"),
        "password": os.getenv("PROTEC_DB_PASS", "CHANGE_ME"),
        "port": os.getenv("PROTEC_DB_PORT", "5432"),
    }


def is_valid_compteur(value: str) -> bool:
    return bool(re.fullmatch(r"\d{10,12}", value.strip()))


def parse_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT)
    except ValueError:
        return None


def parse_montant(value: str) -> int | None:
    try:
        montant = int(value.strip())
    except ValueError:
        return None
    if 1000 <= montant <= 100000:
        return montant
    return None


def hash_file(path: Path) -> str:
    hasher = hashlib.md5()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def read_csv(path: Path) -> tuple[list[dict[str, object]], list[list[object]], int]:
    errors: list[list[object]] = []
    valid_rows: list[dict[str, object]] = []
    seen: set[tuple[str, datetime, int]] = set()

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter=CSV_SEP)
        required_cols = ["numero_compteur", "date_achat", "montant_f"]
        if reader.fieldnames != required_cols:
            raise SystemExit(
                f"[ERREUR FATALE] Colonnes KO. Attendu: {required_cols} | Recu: {reader.fieldnames}"
            )

        total_rows = 0
        for line_number, row in enumerate(reader, start=2):
            total_rows += 1
            numero = (row.get("numero_compteur") or "").strip()
            date_raw = (row.get("date_achat") or "").strip()
            montant_raw = (row.get("montant_f") or "").strip()

            if not is_valid_compteur(numero):
                errors.append([line_number, numero, date_raw, montant_raw, "numero_compteur invalide"])
                continue

            date_achat = parse_date(date_raw)
            if date_achat is None:
                errors.append([line_number, numero, date_raw, montant_raw, "date_achat format DD/MM/YYYY HH:MM KO"])
                continue

            montant = parse_montant(montant_raw)
            if montant is None:
                errors.append([line_number, numero, date_raw, montant_raw, "montant_f hors borne 1000-100000"])
                continue

            dedupe_key = (numero, date_achat, montant)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            valid_rows.append({"numero_compteur": numero, "date_achat": date_achat, "montant_f": montant})

    return valid_rows, errors, total_rows


def keep_last_purchases(rows: list[dict[str, object]]) -> list[tuple[str, str, str]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["numero_compteur"])].append(row)

    upserts: list[tuple[str, str, str]] = []
    for numero, purchases in grouped.items():
        sorted_purchases = sorted(purchases, key=lambda item: item["date_achat"], reverse=True)
        last_purchases = sorted_purchases[:MAX_PURCHASES_PER_CLIENT]
        achats = [
            {
                "date_achat": purchase["date_achat"].isoformat(),
                "montant_f": int(purchase["montant_f"]),
            }
            for purchase in last_purchases
        ]
        upserts.append((numero, json.dumps(achats, ensure_ascii=False), "ACTIF"))
    return upserts


def upsert_clients(rows: list[tuple[str, str, str]]) -> None:
    if psycopg2 is None or execute_values is None:
        raise SystemExit("[ERREUR FATALE] Installe psycopg2-binary: pip install psycopg2-binary")
    if not rows:
        print("[M1] Aucun client valide a importer.")
        return

    sql = """
    INSERT INTO clients_histo (numero_compteur, achats, statut)
    VALUES %s
    ON CONFLICT (numero_compteur)
    DO UPDATE SET achats = EXCLUDED.achats, statut = 'ACTIF';
    """

    conn = psycopg2.connect(**db_config())
    try:
        with conn:
            with conn.cursor() as cur:
                execute_values(cur, sql, rows)
    finally:
        conn.close()


def write_error_report(source_path: Path, errors: list[list[object]]) -> Path | None:
    if not errors:
        return None

    report_path = source_path.with_name(f"Erreurs_{source_path.name}")
    with report_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter=CSV_SEP)
        writer.writerow(["Ligne", "Compteur", "Date", "Montant", "Raison"])
        writer.writerows(errors)
    return report_path


def main(csv_path: str) -> None:
    path = Path(csv_path)
    if not path.exists():
        raise SystemExit(f"[ERREUR FATALE] Fichier introuvable: {path}")

    print(f"[M1] Lancement ingestion: {path}")
    print(f"[M1] Hash fichier: {hash_file(path)}")

    valid_rows, errors, total_rows = read_csv(path)
    error_rate = len(errors) / total_rows if total_rows else 1
    if error_rate > MAX_ERROR_RATE:
        report = write_error_report(path, errors)
        suffix = f" Rapport: {report}" if report else ""
        raise SystemExit(f"[BLOCAGE CEO] Taux erreur {error_rate:.2%} > 5%. Corrige le CSV SEEG.{suffix}")

    rows_to_upsert = keep_last_purchases(valid_rows)
    upsert_clients(rows_to_upsert)
    print(f"[M1] UPSERT OK: {len(rows_to_upsert)} clients importes.")

    report = write_error_report(path, errors)
    if report:
        print(f"[M1] ATTENTION: {len(errors)} lignes rejetees. Voir: {report}")

    print("[M1] INGESTION TERMINEE. Lancer M2 Algo maintenant.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts\\ingest_seeg_v25.py fichier.csv")
    main(sys.argv[1])
