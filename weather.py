import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tkinter as tk

from PIL import Image, ImageTk
import pytz
import requests
from geopy.exc import GeocoderServiceError
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from weather_utils import (
    convert_temperature,
    hourly_forecasts,
    load_preferences as load_saved_preferences,
    save_preferences as save_saved_preferences,
    weather_error_message,
    weather_icon,
)


THEMES = {
    "dark": {
        "background": "#0B1220",
        "panel": "#151F32",
        "panel_light": "#1C2940",
        "text": "#F3F6FC",
        "muted": "#A2B0C5",
        "accent": "#7DD3FC",
        "accent_hover": "#BAE6FD",
        "secondary_hover": "#2A3A54",
        "error": "#FDA4AF",
        "primary_text": "#0B1220",
    },
    "light": {
        "background": "#EFF4FA",
        "panel": "#FFFFFF",
        "panel_light": "#E4ECF5",
        "text": "#152238",
        "muted": "#596A80",
        "accent": "#087EA4",
        "accent_hover": "#D8F3FC",
        "secondary_hover": "#D3DEE9",
        "error": "#B42336",
        "primary_text": "#FFFFFF",
    },
}
PREFERENCES_FILE = Path.home() / ".weather_forecast_favorites.json"


preferences, preference_warning = load_saved_preferences(PREFERENCES_FILE, THEMES)
current_theme = preferences["theme"]
BACKGROUND = THEMES[current_theme]["background"]
PANEL = THEMES[current_theme]["panel"]
PANEL_LIGHT = THEMES[current_theme]["panel_light"]
TEXT = THEMES[current_theme]["text"]
MUTED = THEMES[current_theme]["muted"]
ACCENT = THEMES[current_theme]["accent"]
ERROR = THEMES[current_theme]["error"]

root = tk.Tk()
root.title("Weather Forecast")
root.geometry("1360x880")
root.minsize(1020, 840)
root.configure(bg=BACKGROUND)

last_city = ""
weather_data = None
forecast_data = None
current_timezone = None
favorite_cities = preferences["favorites"]
favorite_temperatures = {}
selected_favorite_city = None
display_unit = tk.StringVar(root, value="C")
worker_results = queue.Queue()
search_token = 0
weather_icon_label = None
weather_icon_bytes = {}


def set_status(message, is_error=False):
    colors = THEMES[current_theme]
    status_label.config(
        text=message, fg=colors["error"] if is_error else colors["muted"]
    )


def update_unit_buttons():
    unit = display_unit.get()
    colors = THEMES[current_theme]
    unit_button.config(
        bg=colors["accent"] if unit == "C" else colors["panel_light"],
        fg=colors["primary_text"] if unit == "C" else colors["text"],
    )
    unit_f_button.config(
        bg=colors["accent"] if unit == "F" else colors["panel_light"],
        fg=colors["primary_text"] if unit == "F" else colors["text"],
    )


def update_weather_display():
    update_unit_buttons()
    if weather_data is None:
        update_condition_details()
        return

    unit = display_unit.get()
    temperature = convert_temperature(weather_data["main"]["temp"], unit)
    feels_like = convert_temperature(weather_data["main"]["feels_like"], unit)

    city_name = weather_data["name"]
    country = weather_data.get("sys", {}).get("country", "")
    location_label.config(text=f"{city_name}, {country}" if country else city_name)
    temperature_label.config(text=f"{round(temperature)}°")
    unit_label.config(text=f"°{unit}")
    feels_like_label.config(text=f"Feels like {round(feels_like)}°{unit}")
    condition_label.config(text=weather_data["weather"][0]["main"])
    weather_icon_label.config(
        text=weather_icon(weather_data["weather"][0]["main"]),
        image="",
    )
    icon_code = weather_data["weather"][0].get("icon")
    if icon_code:
        set_weather_image(weather_icon_label, icon_code, (72, 72))
    description_label.config(
        text=weather_data["weather"][0]["description"].capitalize()
    )
    humidity_value.config(text=f'{weather_data["main"]["humidity"]}%')
    wind_value.config(text=f'{weather_data["wind"]["speed"]:g} m/s')
    pressure_value.config(text=f'{weather_data["main"]["pressure"]} hPa')
    sunrise_value.config(text=format_sun_time(weather_data["sys"]["sunrise"]))
    sunset_value.config(text=format_sun_time(weather_data["sys"]["sunset"]))
    favorite_button.config(
        text=(
            "★ Saved"
            if city_name.casefold() in favorite_cities_normalized()
            else "☆ Add favorite"
        )
    )
    set_status(f"Weather updated for {city_name}.")
    update_clock()
    update_condition_details()
    update_hourly_display()


def update_condition_details():
    if weather_data is None:
        visibility_detail.config(text="—")
        clouds_detail.config(text="—")
        wind_direction_detail.config(text="—")
        return

    visibility = weather_data.get("visibility")
    visibility_detail.config(
        text=f"{visibility / 1000:g} km" if isinstance(visibility, (int, float)) else "—"
    )
    cloud_cover = (weather_data.get("clouds") or {}).get("all")
    clouds_detail.config(
        text=f"{cloud_cover}%" if isinstance(cloud_cover, (int, float)) else "—"
    )

    direction = (weather_data.get("wind") or {}).get("deg")
    if isinstance(direction, (int, float)):
        compass_points = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
        compass_direction = compass_points[int((direction % 360 + 22.5) // 45) % 8]
        wind_direction_detail.config(text=f"{compass_direction} · {round(direction)}°")
    else:
        wind_direction_detail.config(text="—")


def set_weather_image(label, icon_code, size):
    image_data = weather_icon_bytes.get(icon_code)
    if image_data is None:
        return
    try:
        image = Image.open(BytesIO(image_data)).convert("RGBA")
        image.thumbnail(size, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
    except (OSError, ValueError):
        return
    label.config(image=photo, text="")
    label.image = photo


def fetch_weather_icons(icon_codes, token):
    images = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(
                requests.get,
                f"https://openweathermap.org/img/wn/{icon_code}@2x.png",
                timeout=5,
            ): icon_code
            for icon_code in set(icon_codes)
            if icon_code
        }
        for future in as_completed(futures):
            icon_code = futures[future]
            try:
                response = future.result()
                response.raise_for_status()
                images[icon_code] = response.content
            except requests.RequestException:
                continue
    worker_results.put(("icons", token, images))


def update_hourly_display():
    for child in hourly_cards.winfo_children():
        child.destroy()

    colors = THEMES[current_theme]
    if not forecast_data:
        tk.Label(
            hourly_cards,
            text="Hourly outlook will appear after a search.",
            font=("TkDefaultFont", 10),
            fg=colors["muted"],
            bg=colors["panel"],
        ).pack(anchor="w", padx=12, pady=20)
        return

    local_timezone = (
        pytz.timezone(current_timezone)
        if current_timezone
        else timezone(timedelta(seconds=weather_data.get("timezone", 0)))
    )
    for index, forecast in enumerate(hourly_forecasts(forecast_data, local_timezone)):
        card = tk.Frame(
            hourly_cards, bg=colors["panel_light"], padx=8, pady=10
        )
        card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 6, 0))
        hourly_cards.columnconfigure(index, weight=1, uniform="hour")
        tk.Label(
            card,
            text=forecast["time"],
            font=("TkDefaultFont", 8, "bold"),
            fg=colors["muted"],
            bg=colors["panel_light"],
        ).pack()
        icon_label = tk.Label(
            card,
            text=forecast["icon"],
            font=("TkDefaultFont", 24),
            fg=colors["text"],
            bg=colors["panel_light"],
        )
        icon_label.pack(pady=(8, 5))
        if forecast["icon_code"]:
            set_weather_image(icon_label, forecast["icon_code"], (38, 38))
        temperature = convert_temperature(forecast["temperature"], display_unit.get())
        tk.Label(
            card,
            text=f"{round(temperature)}°",
            font=("TkDefaultFont", 15, "bold"),
            fg=colors["text"],
            bg=colors["panel_light"],
        ).pack()
        tk.Label(
            card,
            text=forecast["condition"],
            font=("TkDefaultFont", 8),
            fg=colors["muted"],
            bg=colors["panel_light"],
            wraplength=64,
        ).pack(pady=(4, 0))


def format_sun_time(timestamp):
    if current_timezone is not None:
        local_time = datetime.fromtimestamp(
            timestamp, pytz.timezone(current_timezone)
        )
    else:
        offset = timedelta(seconds=weather_data.get("timezone", 0))
        local_time = datetime.fromtimestamp(timestamp, timezone.utc) + offset
    return local_time.strftime("%I:%M %p").lstrip("0")


def favorite_cities_normalized():
    return {city.casefold() for city in favorite_cities}


def save_preferences():
    global preference_warning
    preferences["favorites"] = favorite_cities
    preferences["theme"] = current_theme
    try:
        save_saved_preferences(PREFERENCES_FILE, favorite_cities, current_theme)
    except OSError as error:
        preference_warning = f"Couldn't save preferences: {error}"
        set_status(preference_warning, is_error=True)
        return False
    preference_warning = None
    return True


def refresh_favorite_list():
    global selected_favorite_city
    for child in favorite_cards.winfo_children():
        child.destroy()
    if selected_favorite_city not in favorite_cities:
        selected_favorite_city = None

    colors = THEMES[current_theme]
    if not favorite_cities:
        tk.Label(
            favorite_cards,
            text="Add a city to favorites to see it here.",
            font=("TkDefaultFont", 10),
            fg=colors["muted"],
            bg=colors["panel"],
            wraplength=900,
            justify="left",
        ).pack(fill="x", pady=8)
        return

    for index, city in enumerate(favorite_cities):
        key = city.casefold()
        temperature = favorite_temperatures.get(key)
        if key in favorite_temperatures and temperature is None:
            temperature_text = "N/A"
        elif temperature is not None:
            temperature = round(convert_temperature(temperature, display_unit.get()))
            temperature_text = f"{temperature}°{display_unit.get()}"
        else:
            temperature_text = "—"
        card = tk.Frame(favorite_cards, bg=colors["panel_light"], padx=10, pady=7)
        row_index, column_index = divmod(index, 5)
        card.grid(
            row=row_index,
            column=column_index,
            sticky="nsew",
            padx=(0, 8),
            pady=(0, 8),
        )
        card.bind("<Button-1>", lambda _event, name=city: select_favorite(name))
        country = tk.Label(
            card,
            text="FAVORITE CITY",
            font=("TkDefaultFont", 8, "bold"),
            fg=colors["muted"],
            bg=colors["panel_light"],
        )
        country.pack(anchor="w")
        country.bind("<Button-1>", lambda _event, name=city: select_favorite(name))
        row = tk.Frame(card, bg=colors["panel_light"])
        row.pack(fill="x", pady=(2, 0))
        row.bind("<Button-1>", lambda _event, name=city: select_favorite(name))
        city_label = tk.Label(
            row,
            text=city,
            font=("TkDefaultFont", 11, "bold"),
            fg=colors["text"],
            bg=colors["panel_light"],
            wraplength=155,
            justify="left",
        )
        city_label.pack(side="left", fill="x", expand=True)
        city_label.bind("<Button-1>", lambda _event, name=city: select_favorite(name))
        temp_label = tk.Label(
            row,
            text=temperature_text,
            font=("TkDefaultFont", 12, "bold"),
            fg=colors["text"],
            bg=colors["panel_light"],
        )
        temp_label.pack(side="right", padx=(6, 0))
        temp_label.bind("<Button-1>", lambda _event, name=city: select_favorite(name))


def select_favorite(city):
    global selected_favorite_city
    selected_favorite_city = city
    search_selected_favorite(city)


def toggle_current_favorite():
    global selected_favorite_city
    if weather_data is None:
        set_status("Search for a city before adding it to favorites.", True)
        return

    city = weather_data["name"]
    matching_city = next(
        (saved for saved in favorite_cities if saved.casefold() == city.casefold()),
        None,
    )
    if matching_city is None:
        favorite_cities.append(city)
        selected_favorite_city = city
        favorite_temperatures[city.casefold()] = weather_data["main"]["temp"]
        message = f"Added {city} to favorites."
    else:
        favorite_cities.remove(matching_city)
        favorite_temperatures.pop(matching_city.casefold(), None)
        message = f"Removed {city} from favorites."
    refresh_favorite_list()
    update_weather_display()
    if save_preferences():
        set_status(message)


def remove_selected_favorite():
    if selected_favorite_city is None:
        set_status("Select a favorite city to remove.", is_error=True)
        return
    city = selected_favorite_city
    favorite_cities.remove(city)
    favorite_temperatures.pop(city.casefold(), None)
    refresh_favorite_list()
    update_weather_display()
    if save_preferences():
        set_status(f"Removed {city} from favorites.")


def search_selected_favorite(city):
    city_entry.delete(0, tk.END)
    city_entry.focus_set()
    city_entry.insert(0, city)
    search_weather(city)


def toggle_theme():
    global current_theme
    old_palette = THEMES[current_theme]
    current_theme = "light" if current_theme == "dark" else "dark"
    new_palette = THEMES[current_theme]
    color_map = {
        old_palette[key]: new_palette[key]
        for key in old_palette
        if key != "primary_text"
    }

    def recolor(widget):
        for option in (
            "background",
            "foreground",
            "activebackground",
            "activeforeground",
            "insertbackground",
            "highlightbackground",
            "highlightcolor",
            "troughcolor",
            "selectbackground",
            "selectforeground",
        ):
            try:
                color = widget.cget(option)
            except tk.TclError:
                continue
            if color in color_map:
                widget.configure(**{option: color_map[color]})
        for child in widget.winfo_children():
            recolor(child)

    recolor(root)
    search_button.config(
        fg=new_palette["primary_text"],
        activeforeground=new_palette["primary_text"],
    )
    theme_button.config(
        text="☀ Light mode" if current_theme == "dark" else "☾ Dark mode"
    )
    refresh_favorite_list()
    update_hourly_display()
    save_preferences()


def show_loading_status(message):
    loading_label.grid()
    loading_label.config(text=message)


def clear_loading_status():
    if "loading_label" in globals():
        loading_label.grid_remove()


def fetch_weather_in_background(city, api_key, token, location):
    try:
        params = {
            "lat": location["latitude"],
            "lon": location["longitude"],
            "appid": api_key,
            "units": "metric",
        }
        current_response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params=params,
            timeout=10,
        )
        current_response.raise_for_status()
        current_data = current_response.json()
        if (
            "sunrise" not in current_data["sys"]
            or "sunset" not in current_data["sys"]
        ):
            raise ValueError("Sunrise or sunset time is missing.")

        forecast_data = None
        forecast_error = None
        try:
            forecast_response = requests.get(
                "https://api.openweathermap.org/data/2.5/forecast",
                params=params,
                timeout=10,
            )
            forecast_response.raise_for_status()
            forecast_data = forecast_response.json()
            if not isinstance(forecast_data, dict) or not isinstance(
                forecast_data.get("list"), list
            ):
                forecast_data = None
                forecast_error = "Current weather loaded, but the forecast is unavailable."
        except requests.RequestException:
            forecast_error = "Current weather loaded, but the forecast is unavailable."

        worker_results.put(
            ("weather", token, (current_data, forecast_data, forecast_error, location))
        )
        icon_codes = [current_data["weather"][0].get("icon")]
        if forecast_data:
            icon_codes.extend(
                item["weather"][0].get("icon")
                for item in forecast_data["list"]
                if item.get("weather")
            )
        threading.Thread(
            target=fetch_weather_icons,
            args=(icon_codes, token),
            daemon=True,
        ).start()
    except requests.Timeout:
        worker_results.put(("error", token, "The weather service timed out. Try again shortly."))
    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else None
        message = weather_error_message(status_code, city)
        worker_results.put(("error", token, message))
    except requests.RequestException:
        worker_results.put(("error", token, "Couldn't connect to the weather service."))
    except (KeyError, IndexError, TypeError, ValueError):
        worker_results.put(("error", token, "The service returned incomplete weather data."))


def fetch_favorite_temperatures(api_key, cities, token):
    results = {}
    for city in cities:
        try:
            response = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": api_key, "units": "metric"},
                timeout=6,
            )
            response.raise_for_status()
            results[city.casefold()] = response.json()["main"]["temp"]
        except (requests.RequestException, KeyError, TypeError, ValueError):
            results[city.casefold()] = None
    worker_results.put(("favorite_temperatures", token, results))


def poll_worker_results():
    global current_timezone, last_city, weather_data, forecast_data
    try:
        while True:
            result_type, token, payload = worker_results.get_nowait()
            if result_type == "icons":
                if token != search_token:
                    continue
                weather_icon_bytes.update(payload)
                if weather_data:
                    update_weather_display()
                    update_hourly_display()
                continue
            if result_type == "favorite_temperatures":
                if token != search_token:
                    continue
                favorite_temperatures.update(payload)
                refresh_favorite_list()
                continue
            if token != search_token:
                continue

            clear_loading_status()
            if result_type == "locations":
                city, candidate, api_key = payload
                begin_weather_fetch(city, candidate, api_key, token)
            elif result_type == "weather":
                weather_data, forecast_data, forecast_error, location = payload
                current_timezone = location["timezone"]
                last_city = weather_data["name"]
                update_weather_display()
                if forecast_error:
                    set_status(forecast_error, is_error=True)
                elif not favorite_cities:
                    set_status(f"Weather updated for {last_city}.")
                if favorite_cities:
                    threading.Thread(
                        target=fetch_favorite_temperatures,
                        args=(
                            os.getenv("OPENWEATHER_API_KEY", ""),
                            tuple(favorite_cities),
                            search_token,
                        ),
                        daemon=True,
                    ).start()
            elif result_type == "error":
                set_status(payload, is_error=True)
    except queue.Empty:
        pass
    root.after(100, poll_worker_results)


def begin_weather_fetch(city, candidate, api_key, token):
    show_loading_status(f"Loading weather for {city}…")
    threading.Thread(
        target=fetch_weather_in_background,
        args=(city, api_key, token, candidate),
        daemon=True,
    ).start()


def update_clock():
    if current_timezone is not None:
        local_now = datetime.now(pytz.timezone(current_timezone))
        clock_label.config(text=local_now.strftime("%I:%M %p  •  %A, %b %d"))


def tick_clock():
    update_clock()
    root.after(30_000, tick_clock)


def toggle_temperature_unit():
    display_unit.set("F" if display_unit.get() == "C" else "C")
    update_weather_display()
    refresh_favorite_list()
    update_hourly_display()


def resolve_city_in_background(city, api_key, token):
    try:
        result = Nominatim(user_agent="weather-forecast-app").geocode(
            city, exactly_one=True, timeout=10
        )
        if result is None:
            worker_results.put(
                ("error", token, f"Couldn't find “{city}”. Check the spelling and try again.")
            )
            return

        candidate = {
            "address": result.address,
            "latitude": result.latitude,
            "longitude": result.longitude,
            "timezone": TimezoneFinder().timezone_at(
                lng=result.longitude, lat=result.latitude
            ),
        }
        worker_results.put(("locations", token, (city, candidate, api_key)))
    except GeocoderServiceError:
        worker_results.put(
            ("error", token, "The location service is unavailable. Try again shortly.")
        )
    except (TypeError, ValueError):
        worker_results.put(
            ("error", token, "Couldn't determine the timezone for that location.")
        )


def search_weather(city=None):
    global search_token

    city = (city if city is not None else city_entry.get()).strip()
    if not city:
        set_status("Type a city name to search.", is_error=True)
        city_entry.focus_set()
        return

    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        set_status("Set OPENWEATHER_API_KEY before searching.", is_error=True)
        return

    search_token += 1
    token = search_token
    show_loading_status(f"Finding {city}…")
    threading.Thread(
        target=resolve_city_in_background,
        args=(city, api_key, token),
        daemon=True,
    ).start()


def reset_weather():
    global current_timezone, forecast_data, last_city, search_token
    global weather_data

    search_token += 1
    clear_loading_status()
    last_city = ""
    weather_data = None
    forecast_data = None
    current_timezone = None
    display_unit.set("C")
    update_unit_buttons()
    city_entry.delete(0, tk.END)
    location_label.config(text="Search for a city")
    clock_label.config(text="Your local weather at a glance")
    weather_icon_label.config(text="🌤", font=("TkDefaultFont", 38, "bold"))
    temperature_label.config(text="—")
    unit_label.config(text="°C")
    feels_like_label.config(text="")
    condition_label.config(text="—")
    description_label.config(text="Current conditions")
    humidity_value.config(text="—")
    wind_value.config(text="—")
    pressure_value.config(text="—")
    sunrise_value.config(text="—")
    sunset_value.config(text="—")
    favorite_button.config(text="☆ Add favorite")
    weather_icon_label.config(image="")
    weather_icon_label.image = None
    update_condition_details()
    refresh_favorite_list()
    for child in hourly_cards.winfo_children():
        child.destroy()
    update_hourly_display()
    set_status("Weather display reset.")


def refresh_weather():
    if last_city:
        search_weather(last_city)
    else:
        set_status("Search for a city before refreshing.")


def make_metric(parent, title):
    card = tk.Frame(parent, bg=PANEL_LIGHT, padx=8, pady=8)
    tk.Label(
        card,
        text=title.upper(),
        font=("TkDefaultFont", 8, "bold"),
        fg=MUTED,
        bg=PANEL_LIGHT,
    ).pack(anchor="w")
    value_widget = tk.Label(
        card, font=("TkDefaultFont", 13, "bold"), fg=TEXT, bg=PANEL_LIGHT
    )
    value_widget.pack(anchor="w", pady=(4, 0))
    return card, value_widget


def make_condition_detail(parent, title, column):
    card = tk.Frame(parent, bg=PANEL_LIGHT, padx=10, pady=9)
    card.grid(
        row=0,
        column=column,
        sticky="ew",
        padx=(0 if column == 0 else 8, 0),
    )
    tk.Label(
        card,
        text=title.upper(),
        font=("TkDefaultFont", 8, "bold"),
        fg=MUTED,
        bg=PANEL_LIGHT,
    ).pack(anchor="w")
    value_label = tk.Label(
        card,
        text="—",
        font=("TkDefaultFont", 13, "bold"),
        fg=TEXT,
        bg=PANEL_LIGHT,
    )
    value_label.pack(anchor="w", pady=(5, 0))
    return value_label


content = tk.Frame(root, bg=BACKGROUND, padx=26, pady=14)
content.pack(fill="both", expand=True)
content.columnconfigure(0, weight=1)
content.rowconfigure(2, weight=1)

header = tk.Frame(content, bg=BACKGROUND)
header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
header.columnconfigure(0, weight=1)
tk.Label(
    header,
    text="WEATHER",
    font=("TkDefaultFont", 10, "bold"),
    fg=ACCENT,
    bg=BACKGROUND,
).pack(anchor="w")
tk.Label(
    header,
    text="Weather at a glance",
    font=("TkDefaultFont", 23, "bold"),
    fg=TEXT,
    bg=BACKGROUND,
).pack(anchor="w", pady=(3, 0))

header_actions = tk.Frame(header, bg=BACKGROUND)
header_actions.place(relx=1.0, rely=0.5, anchor="e")
unit_button = tk.Button(
    header_actions,
    text="°C",
    command=toggle_temperature_unit,
    cursor="hand2",
    font=("TkDefaultFont", 10, "bold"),
    bg=ACCENT,
    fg=THEMES[current_theme]["primary_text"],
    activebackground=THEMES[current_theme]["accent_hover"],
    activeforeground=THEMES[current_theme]["primary_text"],
    relief="flat",
    padx=12,
    pady=6,
)
unit_button.pack(side="left", padx=(0, 5))
unit_f_button = tk.Button(
    header_actions,
    text="°F",
    command=toggle_temperature_unit,
    cursor="hand2",
    font=("TkDefaultFont", 10, "bold"),
    bg=PANEL_LIGHT,
    fg=TEXT,
    activebackground=THEMES[current_theme]["secondary_hover"],
    activeforeground=TEXT,
    relief="flat",
    padx=12,
    pady=6,
)
unit_f_button.pack(side="left")

search_panel = tk.Frame(content, bg=PANEL, padx=14, pady=10)
search_panel.grid(row=1, column=0, sticky="ew", pady=(0, 10))
search_panel.columnconfigure(0, weight=1)
city_entry = tk.Entry(
    search_panel,
    font=("TkDefaultFont", 12),
    relief="flat",
    bg=BACKGROUND,
    fg=TEXT,
    insertbackground=TEXT,
    highlightthickness=1,
    highlightbackground=PANEL,
    highlightcolor=ACCENT,
)
city_entry.grid(row=0, column=0, sticky="ew", ipady=9, padx=(0, 10))
city_entry.bind("<Return>", lambda _event: search_weather())

search_button = tk.Button(
    search_panel,
    text="Search",
    command=search_weather,
    cursor="hand2",
    font=("TkDefaultFont", 10, "bold"),
    bg=ACCENT,
    fg=THEMES[current_theme]["primary_text"],
    activebackground=THEMES[current_theme]["accent_hover"],
    activeforeground=THEMES[current_theme]["primary_text"],
    relief="flat",
    padx=18,
    pady=9,
)
search_button.grid(row=0, column=1, padx=(0, 8))
refresh_button = tk.Button(
    search_panel,
    text="Refresh",
    command=refresh_weather,
    cursor="hand2",
    font=("TkDefaultFont", 10, "bold"),
    bg=PANEL_LIGHT,
    fg=TEXT,
    activebackground="#2A3A54",
    activeforeground=TEXT,
    relief="flat",
    padx=14,
    pady=9,
)
refresh_button.grid(row=0, column=2, padx=(0, 8))
reset_button = tk.Button(
    search_panel,
    text="Reset",
    command=reset_weather,
    cursor="hand2",
    font=("TkDefaultFont", 10, "bold"),
    bg=PANEL_LIGHT,
    fg=TEXT,
    activebackground=THEMES[current_theme]["secondary_hover"],
    activeforeground=TEXT,
    relief="flat",
    padx=14,
    pady=9,
)
reset_button.grid(row=0, column=3)
loading_label = tk.Label(
    search_panel,
    text="",
    font=("TkDefaultFont", 9, "bold"),
    fg=ACCENT,
    bg=PANEL,
)
loading_label.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
loading_label.grid_remove()

body = tk.Frame(content, bg=BACKGROUND)
body.grid(row=2, column=0, sticky="nsew")
body.columnconfigure(0, weight=4, minsize=360)
body.columnconfigure(1, weight=6, minsize=540)
body.rowconfigure(0, weight=3, minsize=390)
body.rowconfigure(1, weight=2, minsize=230)

weather_panel = tk.Frame(body, bg=PANEL, padx=24, pady=20)
weather_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 14), pady=(0, 14))
weather_panel.columnconfigure(0, weight=1)

location_label = tk.Label(
    weather_panel,
    text="Search for a city",
    font=("TkDefaultFont", 15, "bold"),
    fg=TEXT,
    bg=PANEL,
)
location_label.grid(row=0, column=0, sticky="w")
favorite_button = tk.Button(
    weather_panel,
    text="☆ Add favorite",
    command=toggle_current_favorite,
    cursor="hand2",
    font=("TkDefaultFont", 9, "bold"),
    bg=PANEL_LIGHT,
    fg=ACCENT,
    activebackground="#2A3A54",
    activeforeground=TEXT,
    relief="flat",
    padx=10,
    pady=6,
)
favorite_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
clock_label = tk.Label(
    weather_panel,
    text="Your local weather at a glance",
    font=("TkDefaultFont", 10),
    fg=MUTED,
    bg=PANEL,
)
clock_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 7))

condition_row = tk.Frame(weather_panel, bg=PANEL)
condition_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
temperature_label = tk.Label(
    condition_row,
    text="—",
    font=("TkDefaultFont", 36, "bold"),
    fg=TEXT,
    bg=PANEL,
)
temperature_label.pack(side="left")
weather_icon_label = tk.Label(
    condition_row,
    text="🌤",
    font=("TkDefaultFont", 26, "bold"),
    fg=TEXT,
    bg=PANEL,
)
weather_icon_label.pack(side="right", padx=(8, 0))
unit_label = tk.Label(
    condition_row,
    text="",
    font=("TkDefaultFont", 22),
    fg=ACCENT,
    bg=PANEL,
)
unit_label.pack(side="left", anchor="n", pady=(8, 0), padx=(3, 0))
condition_details = tk.Frame(condition_row, bg=PANEL)
condition_details.pack(side="left", anchor="center", padx=(10, 0))
condition_label = tk.Label(
    condition_details,
    text="—",
    font=("TkDefaultFont", 17, "bold"),
    fg=TEXT,
    bg=PANEL,
)
condition_label.pack(anchor="w")
description_label = tk.Label(
    condition_details,
    text="Current conditions",
    font=("TkDefaultFont", 10),
    fg=MUTED,
    bg=PANEL,
)
description_label.pack(anchor="w", pady=(2, 0))
feels_like_label = tk.Label(
    weather_panel,
    text="",
    font=("TkDefaultFont", 11, "bold"),
    fg=ACCENT,
    bg=PANEL,
)
feels_like_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 12))

metrics = tk.Frame(weather_panel, bg=PANEL)
metrics.grid(row=4, column=0, columnspan=2, sticky="ew")
for column in range(3):
    metrics.columnconfigure(column, weight=1, uniform="metric")

metric_cards = tuple(
    make_metric(metrics, title)
    for title in ("Wind", "Humidity", "Pressure", "Sunrise", "Sunset")
)
wind_value = metric_cards[0][1]
humidity_value = metric_cards[1][1]
pressure_value = metric_cards[2][1]
sunrise_value = metric_cards[3][1]
sunset_value = metric_cards[4][1]
for index, (card, _value) in enumerate(metric_cards):
    row, column = divmod(index, 3)
    card.grid(
        row=row,
        column=column,
        sticky="ew",
        padx=(0 if column == 0 else 6, 0),
        pady=(0, 0) if row == 0 else (7, 0),
    )

favorites_panel = tk.Frame(body, bg=PANEL, padx=16, pady=12)
favorites_panel.grid(row=1, column=0, columnspan=2, sticky="nsew")
favorites_panel.columnconfigure(0, weight=1)
tk.Label(
    favorites_panel,
    text="Favorite cities",
    font=("TkDefaultFont", 14, "bold"),
    fg=TEXT,
    bg=PANEL,
).pack(anchor="w")
tk.Label(
    favorites_panel,
    text="Select a saved city to view its weather",
    font=("TkDefaultFont", 9),
    fg=MUTED,
    bg=PANEL,
    wraplength=220,
    justify="left",
).pack(anchor="w", pady=(3, 10))
favorite_list = tk.Frame(favorites_panel, bg=PANEL)
favorite_list.pack(fill="both", expand=True)
favorite_cards = tk.Frame(favorite_list, bg=PANEL)
favorite_cards.pack(fill="both", expand=True)
for column in range(5):
    favorite_cards.columnconfigure(column, weight=1, uniform="favorite")
remove_favorite_button = tk.Button(
    favorites_panel,
    text="Remove selected  ×",
    command=remove_selected_favorite,
    cursor="hand2",
    font=("TkDefaultFont", 8, "bold"),
    bg=PANEL_LIGHT,
    fg=TEXT,
    activebackground="#2A3A54",
    activeforeground=TEXT,
    relief="flat",
    padx=10,
    pady=5,
)
remove_favorite_button.pack(anchor="e", pady=(4, 0))
refresh_favorite_list()

hourly_panel = tk.Frame(body, bg=PANEL, padx=14, pady=12)
hourly_panel.grid(row=0, column=1, sticky="nsew", pady=(0, 14))
tk.Label(
    hourly_panel,
    text="HOURLY FORECAST",
    font=("TkDefaultFont", 10, "bold"),
    fg=ACCENT,
    bg=PANEL,
).pack(anchor="w", padx=4, pady=(0, 8))
hourly_cards = tk.Frame(hourly_panel, bg=PANEL)
hourly_cards.pack(fill="x")
tk.Label(
    hourly_cards,
    text="Search for a city to see the hourly outlook",
    font=("TkDefaultFont", 10),
    fg=MUTED,
    bg=PANEL,
).pack(anchor="w", padx=12, pady=14)

conditions_details_panel = tk.Frame(hourly_panel, bg=PANEL)
conditions_details_panel.pack(fill="x", expand=True, pady=(20, 0))
tk.Frame(
    conditions_details_panel,
    height=1,
    bg=PANEL_LIGHT,
).pack(fill="x", pady=(0, 14))
tk.Label(
    conditions_details_panel,
    text="CURRENT CONDITIONS",
    font=("TkDefaultFont", 9, "bold"),
    fg=MUTED,
    bg=PANEL,
).pack(anchor="w", padx=4, pady=(0, 10))
condition_detail_cards = tk.Frame(conditions_details_panel, bg=PANEL)
condition_detail_cards.pack(fill="x")
for column in range(3):
    condition_detail_cards.columnconfigure(column, weight=1, uniform="detail")

visibility_detail = make_condition_detail(condition_detail_cards, "Visibility", 0)
clouds_detail = make_condition_detail(condition_detail_cards, "Cloud cover", 1)
wind_direction_detail = make_condition_detail(
    condition_detail_cards, "Wind direction", 2
)

footer = tk.Frame(content, bg=BACKGROUND)
footer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
status_label = tk.Label(
    footer,
    text=preference_warning or "Enter a city to see the latest conditions.",
    font=("TkDefaultFont", 9),
    fg=ERROR if preference_warning else MUTED,
    bg=BACKGROUND,
    anchor="w",
)
status_label.pack(side="left", fill="x", expand=True)
theme_button = tk.Button(
    footer,
    text="☀ Light mode" if current_theme == "dark" else "☾ Dark mode",
    command=toggle_theme,
    cursor="hand2",
    font=("TkDefaultFont", 9, "bold"),
    bg=BACKGROUND,
    fg=ACCENT,
    activebackground=BACKGROUND,
    activeforeground=TEXT,
    relief="flat",
    padx=10,
    pady=5,
)
theme_button.pack(side="right")

city_entry.focus_set()
root.after(30_000, tick_clock)
root.after(100, poll_worker_results)
if favorite_cities and os.getenv("OPENWEATHER_API_KEY"):
    threading.Thread(
        target=fetch_favorite_temperatures,
        args=(
            os.environ["OPENWEATHER_API_KEY"],
            tuple(favorite_cities),
            search_token,
        ),
        daemon=True,
    ).start()
root.mainloop()
