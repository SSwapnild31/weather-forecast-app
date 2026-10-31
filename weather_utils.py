import json
from datetime import datetime
from pathlib import Path


WEATHER_ICONS = {
    "thunderstorm": "⛈",
    "drizzle": "🌦",
    "rain": "🌧",
    "snow": "❄",
    "clear": "☀",
    "clouds": "☁",
    "mist": "🌫",
    "smoke": "🌫",
    "haze": "🌫",
    "dust": "🌫",
    "fog": "🌫",
    "sand": "🌫",
    "ash": "🌫",
    "squall": "💨",
    "tornado": "🌪",
}


def weather_icon(condition):
    return WEATHER_ICONS.get(condition.casefold(), "🌤")


def convert_temperature(value, unit):
    if unit == "F":
        return value * 9 / 5 + 32
    return value


def load_preferences(path, themes):
    defaults = {"favorites": [], "theme": "dark"}
    try:
        preferences = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return defaults, None
    except (OSError, json.JSONDecodeError) as error:
        return defaults, f"Couldn't load saved preferences: {error}"

    if not isinstance(preferences, dict):
        return defaults, "Saved preferences have an invalid format."

    favorites = preferences.get("favorites", [])
    if not isinstance(favorites, list) or not all(
        isinstance(city, str) and city.strip() for city in favorites
    ):
        favorites = []
        warning = "Saved favorite cities were invalid and have been cleared."
    else:
        favorites = list(dict.fromkeys(city.strip() for city in favorites))
        warning = None

    theme = preferences.get("theme", "dark")
    if not isinstance(theme, str) or theme not in themes:
        theme = "dark"
        warning = warning or "Saved theme preference was invalid; using dark mode."
    return {"favorites": favorites, "theme": theme}, warning


def save_preferences(path, favorites, theme):
    Path(path).write_text(
        json.dumps({"favorites": favorites, "theme": theme}, indent=2) + "\n",
        encoding="utf-8",
    )


def weather_error_message(status_code, city):
    if status_code == 401:
        return "OpenWeatherMap rejected the API key."
    if status_code == 404:
        return f"No weather data found for “{city}”."
    return "The weather service returned an error. Try again later."


def hourly_forecasts(forecast_data, tz, limit=8):
    hours = []
    for item in forecast_data.get("list", [])[:limit]:
        local_time = datetime.fromtimestamp(item["dt"], tz)
        condition = item["weather"][0]["main"]
        hours.append(
            {
                "time": local_time.strftime("%I:%M %p").lstrip("0"),
                "temperature": round(item["main"]["temp"]),
                "condition": condition,
                "icon": weather_icon(condition),
                "icon_code": item["weather"][0].get("icon"),
            }
        )
    return hours
