"""Merge every configured iCal feed into data/calendar.json."""
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests

from common import load_config, write_json

VIDEO_RE = re.compile(r"https?://[^\s<>\"']*(?:meet\.google|zoom\.us|teams\.microsoft|webex|whereby)[^\s<>\"']*")


def fetch(url: str) -> bytes:
    url = re.sub(r"^webcal://", "https://", url.strip())
    r = requests.get(url, timeout=20, headers={"User-Agent": "rpi-dashboard/1.0"})
    r.raise_for_status()
    return r.content


def to_dt(value, tz: ZoneInfo):
    """icalendar hands back date (all-day) or datetime (naive or aware)."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        return value.astimezone(tz), False
    return datetime.combine(value, time.min, tzinfo=tz), True


def events_from(ics: bytes, source: dict, tz: ZoneInfo, start: datetime, end: datetime) -> list:
    cal = icalendar.Calendar.from_ical(ics)
    out = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        dtstart, all_day = to_dt(ev.get("DTSTART").dt, tz)
        dtend_raw = ev.get("DTEND")
        if dtend_raw is not None:
            dtend, _ = to_dt(dtend_raw.dt, tz)
        else:
            dtend = dtstart + (timedelta(days=1) if all_day else timedelta(hours=1))
        text = " ".join(str(ev.get(k, "")) for k in ("DESCRIPTION", "LOCATION", "URL"))
        video = VIDEO_RE.search(text)
        out.append({
            "title": str(ev.get("SUMMARY", "(untitled)")),
            "start": dtstart.isoformat(),
            "end": dtend.isoformat(),
            "all_day": all_day,
            "location": str(ev.get("LOCATION", "")) or None,
            "video": video.group(0) if video else None,
            "source": source["name"],
            "color": source.get("color", "#888"),
        })
    return out


def main() -> None:
    cfg = load_config()
    tz = ZoneInfo(cfg.get("timezone", "UTC"))
    today = datetime.combine(date.today(), time.min, tzinfo=tz)
    horizon = today + timedelta(days=int(cfg.get("calendar_days", 14)))
    events, sources, errors = [], [], {}
    for src in cfg.get("calendars", []):
        if not src.get("url"):
            continue
        try:
            got = events_from(fetch(src["url"]), src, tz, today, horizon)
            events.extend(got)
            sources.append({"name": src["name"], "color": src.get("color"), "count": len(got)})
        except Exception as e:  # one bad feed must not blank the wall
            errors[src["name"]] = f"{type(e).__name__}: {e}"
    events.sort(key=lambda e: (e["start"], not e["all_day"]))
    write_json("calendar", {
        "timezone": str(tz),
        "window": {"start": today.isoformat(), "end": horizon.isoformat()},
        "sources": sources,
        "errors": errors,
        "events": events,
    })


if __name__ == "__main__":
    main()
