"""Open-Meteo current + hourly + 7-day forecast (no API key), plus a second "away" place for the dock:
the destination of a trip in the next week (data/trip.json, or a trip spotted on the calendar), else one of
config `away_places` rotated daily."""
import json
import math
import re
from datetime import date, datetime, timedelta, timezone

import requests

from common import DATA, load_config, write_json

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

GEOCACHE = DATA / ".geocache.json"      # dotfile: never served
TRIP = DATA / "trip.json"               # written by POST /api/trip
AWAY_DAYS = 7                           # a trip counts once it starts within this many days
AWAY_MIN_KM = 80                        # a calendar location closer than this is an errand, not a trip
# "Flight to Austin", "trip to Lake Tahoe, NV": the keyword is case-insensitive, the place must be capitalised.
TRIP_RE = re.compile(r"\b(?i:trip|travel(?:l?ing)?|flight|fly(?:ing)?|visit(?:ing)?|driv(?:e|ing))\s+(?i:to|in|at)\s+"
                     r"([A-Z][A-Za-z.'-]+(?:[ ,]+[A-Z][A-Za-z.'-]+){0,2})")


def describe(code):
    return CODES.get(code, ("Unknown", "❔"))


def hour_label(t: str) -> str:
    h = int(t[11:13])
    return f"{h % 12 or 12}{'a' if h < 12 else 'p'}"


def forecast(lat, lon, tz, hours=24, days=7) -> dict:
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=20, params={
        "latitude": lat, "longitude": lon, "timezone": tz,
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch",
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m,is_day",
        "hourly": "temperature_2m,weather_code,precipitation_probability,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
        "forecast_days": days, "forecast_hours": hours,
    })
    r.raise_for_status()
    d = r.json()
    off = timezone(timedelta(seconds=d.get("utc_offset_seconds", 0)))
    epoch = lambda t: datetime.fromisoformat(t).replace(tzinfo=off).timestamp()
    cur = d["current"]
    label, icon = describe(cur["weather_code"])
    hourly = [
        {"time": t, "epoch": epoch(t), "hour": hour_label(t), "temp": round(tmp), "pop": pop, "code": c,
         "is_day": bool(day), "icon": describe(c)[1]}
        for t, tmp, c, pop, day in zip(d["hourly"]["time"], d["hourly"]["temperature_2m"], d["hourly"]["weather_code"],
                                       d["hourly"]["precipitation_probability"], d["hourly"].get("is_day") or [1] * 999)
    ]
    daily = [
        {"date": dt, "hi": round(hi), "lo": round(lo), "pop": pop, "code": c, "label": describe(c)[0],
         "icon": describe(c)[1], "sunrise": sr, "sunset": ss}
        for dt, c, hi, lo, pop, sr, ss in zip(d["daily"]["time"], d["daily"]["weather_code"],
                                              d["daily"]["temperature_2m_max"], d["daily"]["temperature_2m_min"],
                                              d["daily"]["precipitation_probability_max"],
                                              d["daily"]["sunrise"], d["daily"]["sunset"])
    ]
    return {
        "timezone": d.get("timezone"), "utc_offset_seconds": d.get("utc_offset_seconds", 0),
        "current": {"temp": round(cur["temperature_2m"]), "feels": round(cur["apparent_temperature"]),
                    "label": label, "icon": icon, "wind": round(cur["wind_speed_10m"]),
                    "humidity": cur["relative_humidity_2m"], "is_day": bool(cur.get("is_day", 1)), "code": cur["weather_code"]},
        "hourly": hourly, "daily": daily,
    }


# ---------- the away place ----------
def geocode(name: str) -> dict | None:
    """Open-Meteo's free geocoder, cached (misses too) so a bad calendar location is looked up once, not every run."""
    key = re.sub(r"\s+", " ", name.strip().lower())
    try:
        cache = json.loads(GEOCACHE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}
    if key in cache:
        return cache[key]
    hit = None
    try:
        r = requests.get("https://geocoding-api.open-meteo.com/v1/search", timeout=15,
                         params={"name": key, "count": 1, "language": "en", "format": "json"})
        res = (r.json().get("results") or [None])[0] if r.ok else None
        if res:
            hit = {"name": res["name"], "admin1": res.get("admin1"), "country": res.get("country_code"),
                   "lat": res["latitude"], "lon": res["longitude"], "timezone": res.get("timezone")}
    except Exception:
        return None            # network trouble: don't cache, try again next run
    cache[key] = hit
    if len(cache) > 200:
        cache = dict(list(cache.items())[-200:])
    GEOCACHE.write_text(json.dumps(cache))
    return hit


def km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


def trip_from_file(today: date) -> dict | None:
    try:
        t = json.loads(TRIP.read_text())
        start, end = date.fromisoformat(t["start"]), date.fromisoformat(t["end"])
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None
    if end < today or start > today + timedelta(days=AWAY_DAYS):
        return None
    place = {"lat": t["lat"], "lon": t["lon"], "timezone": t.get("timezone", "auto")} if t.get("lat") is not None and t.get("lon") is not None else geocode(t["destination"])
    if not place:
        return None
    return {**place, "name": str(t["destination"])[:40], "reason": "trip", "trip": {"start": t["start"], "end": t["end"]},
            "notes": str(t.get("notes") or "")[:200]}


def trip_from_calendar(home: dict, today: date) -> dict | None:
    """A timed or all-day event in the next week whose title says "trip to X" / "flight to X", or whose location is
    a place name (not a meeting link) far enough from home to be a trip."""
    try:
        events = json.loads((DATA / "calendar.json").read_text()).get("events") or []
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    horizon = today + timedelta(days=AWAY_DAYS)
    for e in events:
        try:
            s, en = date.fromisoformat(e["start"][:10]), date.fromisoformat(e["end"][:10])
        except (KeyError, ValueError, TypeError):
            continue
        if en < today or s > horizon:
            continue
        cands = []
        m = TRIP_RE.search(e.get("title") or "")
        if m:
            cands.append(m.group(1))
        loc = (e.get("location") or "").strip()
        # Only "City, ST" / "street, City, ST" shapes count; a bare word ("Discord", "Office") is not a place.
        parts = [p.strip() for p in loc.split(",") if p.strip()]
        if len(parts) >= 2 and not re.match(r"https?://|www\.", loc, re.I) and re.fullmatch(r"[A-Za-z .'-]+", parts[-2]):
            cands.append(parts[-2])
        for c in cands:
            if len(c) < 3:
                continue
            g = geocode(c)
            # The geocoder is fuzzy; insist the hit is actually the name we asked for.
            if g and g["name"].lower().startswith(c.lower().split(",")[0]) and km(home["lat"], home["lon"], g["lat"], g["lon"]) >= AWAY_MIN_KM:
                end = en if e.get("all_day") and en > s else max(s, en)
                return {"name": c.title() if c.islower() else c, "reason": "calendar",
                        "trip": {"start": s.isoformat(), "end": end.isoformat()}, "event": str(e.get("title") or "")[:80], **g}
    return None


def rotated_place(cfg: dict, today: date) -> dict | None:
    places = [p for p in (cfg.get("away_places") or []) if isinstance(p, (str, dict))]
    if not places:
        return None
    p = places[today.toordinal() % len(places)]
    if isinstance(p, dict) and p.get("lat") is not None:
        return {"name": str(p.get("name") or "away"), "reason": "rotation", "lat": p["lat"], "lon": p["lon"], "timezone": p.get("timezone", "auto")}
    name = p if isinstance(p, str) else str(p.get("name") or "")
    g = geocode(name)
    return {"name": name, "reason": "rotation", **g} if g else None


def away(cfg: dict, home: dict) -> dict | None:
    today = date.today()
    place = trip_from_file(today) or trip_from_calendar(home, today) or rotated_place(cfg, today)
    if not place:
        return None
    f = forecast(place["lat"], place["lon"], place.get("timezone") or "auto", hours=12, days=3)
    return {k: place[k] for k in ("name", "reason", "trip", "event", "notes", "admin1", "country") if place.get(k)} | f


def main() -> None:
    cfg = load_config()
    loc = cfg.get("location") or {}
    if loc.get("lat") is None or loc.get("lon") is None:
        write_json("weather", {"configured": False, "hint": "set location.lat/lon in config.yaml"})
        return
    out = {"configured": True, "location": loc.get("name", "Home")} | forecast(loc["lat"], loc["lon"], cfg.get("timezone", "auto"))
    try:
        a = away(cfg, loc)
        if a:
            out["away"] = a
    except Exception as e:                      # the second place is a bonus; home weather never waits on it
        out["away_error"] = f"{type(e).__name__}"
    write_json("weather", out)


if __name__ == "__main__":
    main()
