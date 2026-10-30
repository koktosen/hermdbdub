#!/usr/bin/env python3
"""Write a complete set of fictional data files so the wall can be previewed before anything is configured.
Usage:  python3 bin/demo-data.py <dir>     then:  HERMDBW_DATA=<dir> PORT=8471 python3 serve.py
Everything here is invented: the town, the people, the prices."""
import json, random, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else "demo-data"); out.mkdir(parents=True, exist_ok=True)
random.seed(7)
now = datetime.now().astimezone(); tz = now.tzinfo; today = now.replace(hour=0, minute=0, second=0, microsecond=0)
iso = lambda d: d.isoformat(timespec="minutes")
stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

def w(name, payload): payload["generated_at"] = stamp; (out / f"{name}.json").write_text(json.dumps(payload, indent=1))

cals = {"Work": "#3987e5", "Family": "#d95926", "Fitness": "#199e70", "Holidays": "#c98500"}
plan = [  # day offset, hour, minutes, title, source, all_day
    (0, 9, 30, "Design review — wall app", "Work", False), (0, 13, 0, "Lunch with Priya", "Family", False), (0, 18, 0, "Climbing gym", "Fitness", False),
    (1, 0, 0, "Quarterly filing due", "Work", True), (1, 7, 0, "Run club", "Fitness", False), (1, 10, 0, "1:1 with Sam", "Work", False), (1, 15, 30, "Dentist", "Family", False),
    (2, 0, 0, "Market day", "Family", True), (2, 8, 0, "Long ride", "Fitness", False), (3, 0, 0, "Harvest Festival", "Holidays", True), (3, 11, 0, "Sprint planning", "Work", False),
    (4, 19, 0, "Theo's birthday dinner", "Family", False), (5, 9, 0, "Flight to Lakeview", "Family", False), (6, 0, 0, "Lakeview weekend", "Family", True),
]
events = []
for d, h, m, title, src, allday in plan:
    s = today + timedelta(days=d, hours=h, minutes=m); e = s + (timedelta(days=1) if allday else timedelta(hours=1))
    events.append({"title": title, "start": iso(s), "end": iso(e), "all_day": allday, "location": "Room 4" if src == "Work" and not allday else None,
                   "video": "https://meet.example.com/abc" if title.startswith("1:1") else None, "source": src, "color": cals[src]})
events.sort(key=lambda x: x["start"])
w("calendar", {"timezone": str(tz), "sources": [{"name": k, "color": v, "count": sum(e["source"] == k for e in events)} for k, v in cals.items()], "errors": {}, "events": events})

icons = {0: ("Clear", "☀️"), 2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"), 61: ("Light rain", "🌦️"), 80: ("Showers", "🌧️")}
codes = [3, 3, 2, 2, 0, 0, 0, 2, 61, 61, 80, 3, 3, 2, 0, 0, 0, 0, 2, 2, 3, 3, 2, 0]
hourly = [{"time": iso(now.replace(minute=0) + timedelta(hours=i)), "temp": 58 + round(8 * __import__("math").sin((i - 4) / 24 * 6.28)), "pop": [5, 5, 10, 10, 0, 0, 0, 10, 55, 60, 70, 20, 15, 10, 0, 0, 0, 0, 5, 5, 10, 10, 5, 0][i], "icon": icons[codes[i]][1]} for i in range(24)]
daily = [{"date": (today + timedelta(days=i)).strftime("%Y-%m-%d"), "hi": [66, 64, 70, 72, 68, 65, 67][i], "lo": [52, 51, 54, 55, 53, 50, 52][i], "pop": [10, 60, 5, 0, 20, 40, 10][i],
          "label": icons[[2, 61, 0, 0, 2, 80, 2][i]][0], "icon": icons[[2, 61, 0, 0, 2, 80, 2][i]][1], "sunrise": (today + timedelta(days=i, hours=6, minutes=48)).isoformat(timespec="minutes"), "sunset": (today + timedelta(days=i, hours=17, minutes=52)).isoformat(timespec="minutes")} for i in range(7)]
w("weather", {"configured": True, "location": "Springfield", "current": {"temp": 63, "feels": 62, "label": "Partly cloudy", "icon": "⛅", "wind": 7, "humidity": 58, "is_day": 6 <= now.hour < 18, "code": 2}, "hourly": hourly, "daily": daily})

spark = lambda base, drift: [round(base * (1 + drift * i / 40 + random.uniform(-0.02, 0.02)), 4) for i in range(42)]
crypto = [("BTC", "Bitcoin", 64250, 1.8), ("ETH", "Ethereum", 3120, -0.9), ("SOL", "Solana", 142.3, 3.4), ("HBAR", "Hedera", 0.0812, -2.1), ("XRP", "XRP", 0.61, 0.4), ("MANA", "Decentraland", 0.42, -1.2)]
stocks = [("SPY", 512.4, 0.6), ("QQQ", 441.2, 0.9), ("NVDA", 118.6, 2.3), ("AMD", 162.1, -1.1), ("AAPL", 189.3, 0.2), ("MSFT", 415.8, 0.7), ("GOOGL", 171.2, -0.8), ("AMZN", 182.4, 1.4), ("META", 498.9, -0.3), ("TSLA", 238.7, 3.1)]
w("markets", {"crypto": [{"symbol": s, "name": n, "price": p, "change_24h": c, "spark": spark(p, c / 100), "logo": None} for s, n, p, c in crypto],
              "stocks": [{"symbol": s, "price": p, "change_24h": c, "spark": spark(p, c / 100)[:5]} for s, p, c in stocks]})
w("fng", {"value": 54, "label": "Neutral", "history": [48, 50, 52, 51, 55, 53, 54]})
h = lambda t: (datetime.now(timezone.utc) - timedelta(hours=t)).isoformat(timespec="seconds")
w("rss", {"feeds": [{"name": "Tech Daily", "items": [{"title": t, "link": "#", "time": h(i + 1)} for i, t in enumerate(["Open-source dashboard runs on a decade-old Pi", "Why every home server needs a wall display", "Piper TTS gets new voices", "Headscale 1.0 released", "The quiet return of the RSS reader", "A field guide to prompt-driven kiosks"])]},
                    {"name": "Local News", "items": [{"title": t, "link": "#", "time": h(i + 2)} for i, t in enumerate(["Harvest Festival returns to Main Street this weekend", "New bike lane opens along the river", "Library extends weekend hours", "Farmers market moves indoors for winter"])]}], "errors": {}})
w("xtrends", {"found": True, "source": "demo", "trends": [{"name": "Harvest Festival", "category": "Local", "posts": "12K posts", "since": "Trending now"}, {"name": "Pi 2 still going", "category": "Technology", "posts": "4,8K posts", "since": "3 hours ago"}, {"name": "Lakeview", "category": "Travel", "posts": "2,1K posts", "since": "Trending now"}, {"name": "Open-Meteo", "category": "Science", "posts": "980 posts", "since": "5 hours ago"}, {"name": "Rowing finals", "category": "Sports", "posts": "33K posts", "since": "1 hour ago"}]})
w("brief", {"found": True, "run_time": now.strftime("%Y-%m-%d 07:30:00"), "text": "morning brief — 7:30am\n\ntoday: design review at 9:30, lunch with Priya at 1. partly cloudy, 66.\n\nthis week: quarterly filing is due tomorrow. Theo's birthday dinner Friday. you fly to Lakeview Saturday — pack for rain.\n\nmarkets: SOL +3.4% overnight, nothing else moved.\n\n— Hermes", "window": [5, 7]})
w("ops", {"host": "server", "system": {"load1": 0.8, "load5": 0.7, "cpus": 8, "uptime_h": 300.5, "mem_used_pct": 31, "mem_total_gb": 32}, "gpus": [], "comfy": [], "services": {"hermes-gateway": "active"}, "services_on_demand": [],
          "tailscale": {"self": "server", "online": 3, "total": 5, "peers": []}, "disks": [{"path": "/", "used_pct": 41, "free_gb": 120}, {"path": "/home", "used_pct": 22, "free_gb": 700}], "apk": None, "printer": None})
w("xusage", {"local": {"today": 2, "month": 41}, "official": {"project_usage": "41", "cap": "3000000", "reset_day": 1}})
w("status", {"collectors": {k: {"ok": True, "ms": 120} for k in ["calendar", "weather", "brief", "markets", "rss", "xtrends", "fng", "ops"]},
             "config": {"rotate_seconds": 45, "timezone": str(tz), "brief_window": [5, 7], "pages": ["calendar", "feed", "weather"], "rotate_pages": ["calendar", "feed", "weather"], "ticker_rows": ["crypto", "stocks"],
                        "feed_columns": ["headlines", "xtrends"], "dock_tiles": ["upnext", "fng", "hours", "host"], "marquees": ["ticker", "news"], "week_days": 5, "agent_name": "Hermes", "location_image": "img/location.jpg"}})
(out / "alerts.json").write_text("[]"); (out / "trigger.json").write_text(json.dumps({"what": "dismiss", "ts": time.time()}))
print(f"demo data written to {out}")
