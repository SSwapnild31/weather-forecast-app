# 🌦️ Weather Forecast Application (Python)

## 📌 Overview

This project is a **desktop-based Weather Forecast Application** built using **Python** and **Tkinter**. It provides real-time weather updates for any city, including temperature, humidity, and timezone-specific information through an interactive GUI.

## 🚀 Features

* 🌍 **City-based Weather Search**
* 📍 Displays the **selected city and country**
* 🌡️ Displays **Temperature, Humidity, and Weather Conditions**
* 🕒 Shows **Timezone-specific Local Time**
* 🌅 Displays local **sunrise and sunset** times
* 🕒 Shows an **8-step hourly outlook** with weather icons
* 🌬️ Shows current **visibility, cloud cover, and wind direction** below the hourly outlook
* 🌤️ Displays weather icons using Pillow
* 🔁 Refreshes the current city's weather
* ⌛ Searches in the background so the window stays responsive
* 🌡️ Switches temperature display between **Celsius and Fahrenheit**
* ⭐ Saves favorite cities between app launches
* 🌡️ Shows temperatures alongside saved favorites
* 🎨 Switches between **dark and light themes**
* ↺ Resets the current weather display
* 🖥️ Interactive and user-friendly **GUI using Tkinter**
* 🔄 **Real-time Weather Data Integration**
* ⚠️ Proper **Exception Handling** for invalid inputs

Favorite cities and the selected theme are saved locally in
`~/.weather_forecast_favorites.json`.

## 🛠️ Technologies Used

* **Python**
* **Tkinter** – GUI development
* **threading** – Background weather and image requests
* **Pillow** – Weather icon images
* **geopy** – City geocoding
* **timezonefinder / pytz** – Timezone lookup and conversion
* **Requests / OpenWeatherMap API** – Fetch real-time weather data

## 📷 Application Workflow

1. User enters a **city name**
2. Application fetches **real-time weather data**
3. Displays:

   * Temperature 🌡️
   * Humidity 💧
   * Weather condition ☁️
   * Local time 🕒
   * Wind speed and air pressure
   * Sunrise and sunset
   * An hourly outlook with weather icons
   * Visibility, cloud cover, and wind direction
4. Add cities to favorites; select a saved city to search it again
5. Switch between dark and light mode, or reset the current display
6. Handles errors for invalid or unavailable cities without freezing the window

## 📦 Installation

### 1️⃣ Clone the repository

```bash
git clone https://github.com/SSwapnild31/weather-forecast-app.git
```
```bash
cd weather-forecast-app
```

### 2️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

### 3️⃣ Configure the OpenWeatherMap API key

Create an API key in your OpenWeatherMap account, then set it as an environment
variable before starting the app:

```bash
export OPENWEATHER_API_KEY="your_api_key"
```

In PowerShell, use:

```powershell
$env:OPENWEATHER_API_KEY = "your_api_key"
```

Do not commit your API key to the repository.

### 4️⃣ Run the application

```bash
python weather.py
```

### 5️⃣ Run the tests

```bash
python -m unittest discover -s tests
```

## 🧠 Concepts Used

* GUI Development (Tkinter)
* API Integration
* Exception Handling
* Timezone Conversion
* Event-driven Programming

## ❗ Error Handling

* Invalid city name
* API request failure
* Network issues
* Empty input handling

## 🤝 Contributing

Feel free to fork this repo and improve the project. Contributions are welcome!

## 📜 License

This project is for lerning purpose.

---

## 👨‍💻 Author

**Swapnil Divate**
