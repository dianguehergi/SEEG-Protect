import unittest

from scripts.score_meroe_core_v32 import score_meter


class ScoreMeroeCoreV32Tests(unittest.TestCase):
    def test_score_meter_marks_red_list_for_combined_anomalies(self) -> None:
        result = score_meter(
            {
                "numero_compteur": "1234567890",
                "index_n": "950",
                "index_n_1": "1000",
                "conso": "0",
                "conso_moyenne_90j": "120",
                "etat_sts": "COUVERCLE_OUVERT",
                "recharges": "2",
                "canal_paiement": "AIRTEL",
            }
        )

        self.assertEqual(result["score"], 100)
        self.assertEqual(result["statut"], "LISTE_ROUGE")
        self.assertIn("INDEX_INCOHERENT", result["type_anomalie"])
        self.assertIn("STS_COUVERCLE_OUVERT", result["type_anomalie"])

    def test_score_meter_keeps_normal_meter_below_surveillance(self) -> None:
        result = score_meter(
            {
                "numero_compteur": "1234567891",
                "index_n": "1120",
                "index_n_1": "1000",
                "conso": "120",
                "conso_moyenne_90j": "125",
                "etat_sts": "OK",
                "recharges": "1",
                "canal_paiement": "AIRTEL",
            }
        )

        self.assertEqual(result["score"], 0)
        self.assertEqual(result["statut"], "NORMAL")


if __name__ == "__main__":
    unittest.main()
