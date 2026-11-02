"""Run collectors by name (default: all). One failure never stops the others; data/status.json records outcomes."""
import importlib
import json
import pathlib
import socket
import sys
import time
import traceback

from common import DATA, load_config, scrub_urls, write_json

# "calendar" would shadow the stdlib module, so the feed collector lives in cal_feeds.py
MODULES = {"calendar": "cal_feeds", "weather": "weather", "brief": "brief", "ops": "ops",
           "markets": "markets", "rss": "rss", "xtrends": "xtrends", "fng": "fng", "xapi": "xapi"}
ALL = list(MODULES)


def main(names: list) -> int:
    socket.setdefaulttimeout(20)   # no collector may hang the pipeline on a silent host
    status, failed = {}, 0
    for name in names:
        t0 = time.time()
        stamp = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "at_epoch": round(t0)}
        try:
            importlib.import_module(MODULES[name]).main()
            status[name] = {"ok": True, "ms": round((time.time() - t0) * 1000), **stamp}
        except Exception:
            failed += 1
            status[name] = {"ok": False, "error": scrub_urls(traceback.format_exc().strip().splitlines()[-1]), **stamp}
            print(f"[{name}] FAILED\n{scrub_urls(traceback.format_exc())}", file=sys.stderr)
    # Several timers write status.json (collect every 5 min, ops every minute): merge, never clobber.
    try:
        previous = json.loads((DATA / "status.json").read_text()).get("collectors", {})
    except (FileNotFoundError, json.JSONDecodeError):
        previous = {}
    status = {**previous, **status}
    cfg = load_config()
    web = pathlib.Path(__file__).resolve().parent.parent / "web"
    assets_version = str(int(max(((web / f).stat().st_mtime for f in ("index.html", "app.js", "style.css") if (web / f).exists()), default=0)))
    write_json("status", {"collectors": status, "assets_version": assets_version,
                          "config": {**{k: cfg.get(k) for k in ("rotate_seconds", "timezone", "brief_window")}, **(cfg.get("layout") or {}), "agent_name": cfg.get("agent_name", "Brief"), "attention": cfg.get("attention") or {}, "location_image": (cfg.get("location") or {}).get("image"), "week_days": (cfg.get("layout") or {}).get("week_days", 5)}})
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ALL))
