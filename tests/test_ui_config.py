import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_runtime_hud import load_settings, save_settings


class UiConfigTests(unittest.TestCase):
    def test_ui_preferences_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            with patch("codex_runtime_hud.settings_path", return_value=path):
                save_settings({"x": 100, "y": 80, "expanded": True, "scope": "session", "language": "en", "always_on_top": False})
                self.assertEqual(load_settings()["scope"], "session")
                self.assertTrue(load_settings()["expanded"])
                self.assertFalse(load_settings()["always_on_top"])

    def test_corrupt_settings_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            path.write_text("{not-json", encoding="utf-8")
            with patch("codex_runtime_hud.settings_path", return_value=path), patch(
                "codex_runtime_hud.legacy_app_data_dir", return_value=Path(temp) / "missing-legacy"
            ):
                self.assertEqual(load_settings(), {})

    def test_legacy_settings_are_read_after_brand_rename(self):
        with tempfile.TemporaryDirectory() as temp:
            new_path = Path(temp) / "new" / "settings.json"
            legacy_path = Path(temp) / "legacy" / "settings.json"
            legacy_path.parent.mkdir(parents=True)
            legacy_path.write_text('{"x": 321, "language": "zh-CN"}', encoding="utf-8")
            with patch("codex_runtime_hud.settings_path", return_value=new_path), patch(
                "codex_runtime_hud.legacy_app_data_dir", return_value=legacy_path.parent
            ):
                self.assertEqual(load_settings()["x"], 321)
                self.assertEqual(load_settings()["language"], "zh-CN")


if __name__ == "__main__":
    unittest.main()
