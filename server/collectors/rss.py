"""Headlines from configured RSS/Atom feeds → data/rss.json (newest first per feed)."""
import calendar as _cal
from datetime import datetime, timezone

import feedparser

from common import load_config, write_json

PER_FEED = 6


def entry_time(e) -> str | None:
    t = e.get("published_parsed") or e.get("updated_parsed")
    return datetime.fromtimestamp(_cal.timegm(t), tz=timezone.utc).isoformat() if t else None


def main() -> None:
    feeds, errors = [], {}
    for f in load_config().get("rss_feeds", []):
        try:
            p = feedparser.parse(f["url"], agent="rpi-dashboard/1.0")
            if p.bozo and not p.entries:
                raise RuntimeError(str(p.bozo_exception)[:80])
            items = [{"title": e.get("title", "").strip(), "link": e.get("link"), "time": entry_time(e)} for e in p.entries[:PER_FEED]]
            feeds.append({"name": f.get("name") or p.feed.get("title", f["url"]), "items": items})
        except Exception as e:
            errors[f.get("name", f["url"])] = f"{type(e).__name__}: {e}"
    write_json("rss", {"feeds": feeds, "errors": errors})


if __name__ == "__main__":
    main()
