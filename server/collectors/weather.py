"""Open-Meteo current + hourly + 7-day forecast (no API key)."""
import requests

from common import load_config, write_json

# WMO weather interpretation codes -> (label, icon)
CODES = {
    0: ("Clear", "☀️"), 1: ("Mostly clear", "🌤️"), 2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"), 48: ("Rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌦️"), 55: ("Heavy drizzle", "🌧️"),
    56: ("Freezing drizzle", "🌧️"), 57: ("Freezing drizzle", "🌧️"),
    61: ("Light rain", "🌦️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
    66: ("Freezing rain", "🌧️"), 67: ("Freezing rain", "🌧️"),
    71: ("Light snow", "🌨️"), 73: ("Snow", "🌨️"), 75: ("Heavy snow", "❄️"), 77: ("Snow grains", "🌨️"),
    80: ("Showers", "🌦️"), 81: ("Showers", "🌧️"), 82: ("Violent showers", "⛈️"),
    85: ("Snow showers", "🌨️"), 86: ("Snow showers", "❄️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm, hail", "⛈️"), 99: ("Thunderstorm, hail", "⛈️"),
}


def describe(code):
    return CODES.get(code, ("Unknown", "❔"))


def main() -> None:
    cfg = load_config()
    loc = cfg.get("location") or {}
    if loc.get("lat") is None or loc.get("lon") is None:
        write_json("weather", {"configured": False, "hint": "set location.lat/lon in config.yaml"})
        return
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=20, params={
        "latitude": loc["lat"], "longitude": loc["lon"],
        "timezone": cfg.get("timezone", "auto"),
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch",
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m,is_day",
        "hourly": "temperature_2m,weather_code,precipitation_probability",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
        "forecast_days": 7, "forecast_hours": 24,
    })
    r.raise_for_status()
    d = r.json()
    cur = d["current"]
    label, icon = describe(cur["weather_code"])
    hourly = [
        {"time": t, "temp": round(tmp), "pop": pop, "icon": describe(c)[1]}
        for t, tmp, c, pop in zip(d["hourly"]["time"], d["hourly"]["temperature_2m"],
                                   d["hourly"]["weather_code"], d["hourly"]["precipitation_probability"])
    ]
    daily = [
        {"date": dt, "hi": round(hi), "lo": round(lo), "pop": pop, "label": describe(c)[0], "icon": describe(c)[1],
         "sunrise": sr, "sunset": ss}
        for dt, c, hi, lo, pop, sr, ss in zip(d["daily"]["time"], d["daily"]["weather_code"],
                                              d["daily"]["temperature_2m_max"], d["daily"]["temperature_2m_min"],
                                              d["daily"]["precipitation_probability_max"],
                                              d["daily"]["sunrise"], d["daily"]["sunset"])
    ]
    write_json("weather", {
        "configured": True,
        "location": loc.get("name", "Home"),
        "current": {"temp": round(cur["temperature_2m"]), "feels": round(cur["apparent_temperature"]),
                    "label": label, "icon": icon, "wind": round(cur["wind_speed_10m"]),
                    "humidity": cur["relative_humidity_2m"], "is_day": bool(cur.get("is_day", 1)), "code": cur["weather_code"]},
        "hourly": hourly, "daily": daily,
    })


if __name__ == "__main__":
    main()
