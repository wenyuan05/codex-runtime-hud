import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_hud import load_settings, save_settings


class UiConfigTests(unittest.TestCase):
    def test_ui_preferences_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            with patch("codex_hud.settings_path", return_value=path):
                save_settings({"x": 100, "y": 80, "expanded": True, "scope": "session", "language": "en", "always_on_top": False})
                self.assertEqual(load_settings()["scope"], "session")
                self.assertTrue(load_settings()["expanded"])
                self.assertFalse(load_settings()["always_on_top"])

    def test_corrupt_settings_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            path.write_text("{not-json", encoding="utf-8")
            with patch("codex_hud.settings_path", return_value=path):
                self.assertEqual(load_settings(), {})


if __name__ == "__main__":
    unittest.main()

