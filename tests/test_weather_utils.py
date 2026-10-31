import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from weather_utils import (
    convert_temperature,
    hourly_forecasts,
    load_preferences,
    save_preferences,
    weather_error_message,
    weather_icon,
)


class WeatherUtilityTests(unittest.TestCase):
    def test_temperature_conversion(self):
        self.assertEqual(convert_temperature(0, "F"), 32)
        self.assertEqual(convert_temperature(20, "C"), 20)

    def test_condition_icon_is_case_insensitive(self):
        self.assertEqual(weather_icon("Rain"), "🌧")
        self.assertEqual(weather_icon("unknown"), "🌤")

    def test_hourly_forecasts_returns_local_times_and_icons(self):
        timestamps = (
            datetime(2026, 11, 1, 9, tzinfo=timezone.utc).timestamp(),
            datetime(2026, 11, 1, 12, tzinfo=timezone.utc).timestamp(),
        )
        entries = [
            {
                "dt": timestamp,
                "main": {"temp": temperature},
                "weather": [{"main": condition, "icon": icon_code}],
            }
            for timestamp, temperature, condition, icon_code in zip(
                timestamps, (8.2, 12.6), ("Rain", "Clear"), ("10d", "01d")
            )
        ]

        result = hourly_forecasts({"list": entries}, timezone.utc)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["time"], "9:00 AM")
        self.assertEqual(result[0]["temperature"], 8)
        self.assertEqual(result[0]["icon"], "🌧")
        self.assertEqual(result[0]["icon_code"], "10d")
        self.assertEqual(result[1]["condition"], "Clear")

    def test_hourly_forecasts_respects_limit(self):
        entries = [
            {
                "dt": datetime(2026, 11, 1, hour, tzinfo=timezone.utc).timestamp(),
                "main": {"temp": hour},
                "weather": [{"main": "Clear"}],
            }
            for hour in range(5)
        ]

        self.assertEqual(
            len(hourly_forecasts({"list": entries}, timezone.utc, limit=3)), 3
        )

    def test_preferences_save_and_load_favorites_and_theme(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_preferences(path, ["Paris", "Tokyo"], "light")

            preferences, warning = load_preferences(
                path, {"dark": {}, "light": {}}
            )

        self.assertIsNone(warning)
        self.assertEqual(preferences, {"favorites": ["Paris", "Tokyo"], "theme": "light"})

    def test_preferences_remove_duplicate_favorites(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(
                '{"favorites": ["Paris", "Paris", " Tokyo "], "theme": "dark"}',
                encoding="utf-8",
            )

            preferences, warning = load_preferences(
                path, {"dark": {}, "light": {}}
            )

        self.assertIsNone(warning)
        self.assertEqual(preferences["favorites"], ["Paris", "Tokyo"])

    def test_preferences_invalid_file_returns_warning(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("{", encoding="utf-8")

            preferences, warning = load_preferences(
                path, {"dark": {}, "light": {}}
            )

        self.assertEqual(preferences, {"favorites": [], "theme": "dark"})
        self.assertIn("Couldn't load saved preferences", warning)

    def test_weather_api_errors_have_clear_messages(self):
        self.assertIn("rejected", weather_error_message(401, "Paris"))
        self.assertIn("Paris", weather_error_message(404, "Paris"))
        self.assertIn("error", weather_error_message(500, "Paris"))


if __name__ == "__main__":
    unittest.main()
