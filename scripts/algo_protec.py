import json
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:  # pragma: no cover - message shown only when run manually
    psycopg2 = None
    execute_values = None


MIN_CYCLE_DAYS = 3
MAX_CYCLE_DAYS = 90
ROUND_AMOUNT_TO = 500


def db_config() -> dict[str, str]:
    return {
        "host": os.getenv("PROTEC_DB_HOST", "localhost"),
        "dbname": os.getenv("PROTEC_DB_NAME", "protec_db"),
        "user": os.getenv("PROTEC_DB_USER", "protec_user"),
        "password": os.getenv("PROTEC_DB_PASS", "CHANGE_ME"),
        "port": os.getenv("PROTEC_DB_PORT", "5432"),
    }


def parse_achats(achats_value: Any) -> list[dict[str, Any]]:
    if isinstance(achats_value, list):
        return achats_value
    if isinstance(achats_value, str):
        return json.loads(achats_value)
    raise ValueError("achats doit etre une liste JSON ou une chaine JSON")


def round_to_nearest_amount(amount: float) -> int:
    return max(ROUND_AMOUNT_TO, int(round(amount / ROUND_AMOUNT_TO) * ROUND_AMOUNT_TO))


def calculer_dates(achats_json: list[dict[str, Any]]) -> tuple[date | None, date | None, int | None]:
    """
    Input: [{"date_achat": "2026-08-12T14:23:00", "montant_f": 5000}, ...]
    Output: date_j0, date_jm2, montant_conseille
    """
    if len(achats_json) < 2:
        return None, None, None

    achats = sorted(achats_json, key=lambda item: item["date_achat"])
    dates = [datetime.fromisoformat(str(achat["date_achat"])).date() for achat in achats]
    montants = [int(achat["montant_f"]) for achat in achats]

    deltas = [(dates[index] - dates[index - 1]).days for index in range(1, len(dates))]
    deltas = [delta for delta in deltas if delta > 0]
    if not deltas:
        return None, None, None

    nb_jours_moyen = sum(deltas) / len(deltas)
    nb_jours_moyen = max(MIN_CYCLE_DAYS, min(MAX_CYCLE_DAYS, nb_jours_moyen))

    montant_moyen = sum(montants) / len(montants)
    montant_conseille = round_to_nearest_amount(montant_moyen)

    dernier_achat = dates[-1]
    date_j0 = dernier_achat + timedelta(days=round(nb_jours_moyen))
    date_jm2 = date_j0 - timedelta(days=2)

    return date_j0, date_jm2, montant_conseille


def ensure_prediction_columns(cur: Any) -> None:
    cur.execute(
        """
        ALTER TABLE clients_histo
        ADD COLUMN IF NOT EXISTS date_j0 DATE,
        ADD COLUMN IF NOT EXISTS date_jm2 DATE,
        ADD COLUMN IF NOT EXISTS montant_conseille INT;
        """
    )


def update_predictions() -> int:
    if psycopg2 is None or execute_values is None:
        raise SystemExit("[ERREUR FATALE] Installe psycopg2-binary: pip install psycopg2-binary")

    conn = psycopg2.connect(**db_config())
    try:
        with conn:
            with conn.cursor() as cur:
                ensure_prediction_columns(cur)
                cur.execute("SELECT numero_compteur, achats FROM clients_histo WHERE statut = 'ACTIF';")
                clients = cur.fetchall()
                print(f"[M2] Calcul en cours pour {len(clients)} clients ACTIFS...")

                updates = []
                skipped = 0
                for numero_compteur, achats_value in clients:
                    try:
                        achats = parse_achats(achats_value)
                        date_j0, date_jm2, montant = calculer_dates(achats)
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                        skipped += 1
                        print(f"[M2] SKIP {numero_compteur}: historique invalide ({exc})")
                        continue

                    if date_j0 is None or date_jm2 is None or montant is None:
                        skipped += 1
                        continue

                    updates.append((date_j0, date_jm2, montant, numero_compteur))

                if updates:
                    sql = """
                    UPDATE clients_histo AS c
                    SET date_j0 = u.date_j0,
                        date_jm2 = u.date_jm2,
                        montant_conseille = u.montant
                    FROM (VALUES %s) AS u(date_j0, date_jm2, montant, numero_compteur)
                    WHERE c.numero_compteur = u.numero_compteur;
                    """
                    execute_values(cur, sql, updates)

                print(f"[M2] MAJ OK: {len(updates)} clients calcules pour J-2 et J0.")
                if skipped:
                    print(f"[M2] INFO: {skipped} clients ignores faute d'historique suffisant ou valide.")
                return len(updates)
    finally:
        conn.close()


def main() -> None:
    update_predictions()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("[M2] Interrompu.")
