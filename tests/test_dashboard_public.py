import unittest
from unittest.mock import MagicMock

from seeg_protect.app import ApiHandler, MEROE_BACKGROUND, MEROE_DASHBOARD


class PublicDashboardTests(unittest.TestCase):
    def test_public_dashboard_files_exist_and_are_anonymised(self):
        self.assertTrue(MEROE_DASHBOARD.exists())
        self.assertTrue(MEROE_BACKGROUND.exists())
        html = MEROE_DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("MÉROÉ CONTROL CENTER", html)
        self.assertIn("Aucune donnée nominative", html)
        self.assertIn("/assets/meroe-dashboard-background.png", html)

    def test_send_bytes_sets_cache_header(self):
        handler = object.__new__(ApiHandler)
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = MagicMock()
        handler.send_bytes(200, b"png", "image/png", cache=True)
        handler.send_header.assert_any_call("Cache-Control", "public, max-age=86400")
        handler.wfile.write.assert_called_once_with(b"png")


if __name__ == "__main__":
    unittest.main()
