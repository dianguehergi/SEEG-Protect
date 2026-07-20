import unittest
from datetime import date

from scripts.algo_protec import calculer_dates


class AlgoProtecTests(unittest.TestCase):
    def test_calculer_dates_uses_average_purchase_cycle(self) -> None:
        date_j0, date_jm2, montant = calculer_dates(
            [
                {"date_achat": "2026-08-01T08:00:00", "montant_f": 5000},
                {"date_achat": "2026-08-11T08:00:00", "montant_f": 6000},
                {"date_achat": "2026-08-21T08:00:00", "montant_f": 7000},
            ]
        )

        self.assertEqual(date_j0, date(2026, 8, 31))
        self.assertEqual(date_jm2, date(2026, 8, 29))
        self.assertEqual(montant, 6000)

    def test_calculer_dates_caps_short_cycles_to_three_days(self) -> None:
        date_j0, date_jm2, montant = calculer_dates(
            [
                {"date_achat": "2026-08-01T08:00:00", "montant_f": 1000},
                {"date_achat": "2026-08-02T08:00:00", "montant_f": 1200},
            ]
        )

        self.assertEqual(date_j0, date(2026, 8, 5))
        self.assertEqual(date_jm2, date(2026, 8, 3))
        self.assertEqual(montant, 1000)

    def test_calculer_dates_skips_insufficient_history(self) -> None:
        self.assertEqual(
            calculer_dates([{"date_achat": "2026-08-01T08:00:00", "montant_f": 5000}]),
            (None, None, None),
        )


if __name__ == "__main__":
    unittest.main()
