"""Run collectors by name (default: all). One failure never stops the others; data/status.json records outcomes."""
import importlib
import sys
import time
import traceback

from common import load_config, write_json

# "calendar" would shadow the stdlib module, so the feed collector lives in cal_feeds.py
MODULES = {"calendar": "cal_feeds", "weather": "weather", "brief": "brief", "ops": "ops",
           "markets": "markets", "rss": "rss", "xtrends": "xtrends", "fng": "fng", "xapi": "xapi"}
ALL = list(MODULES)


def main(names: list) -> int:
    status, failed = {}, 0
    for name in names:
        t0 = time.time()
        try:
            importlib.import_module(MODULES[name]).main()
            status[name] = {"ok": True, "ms": round((time.time() - t0) * 1000)}
        except Exception:
            failed += 1
            status[name] = {"ok": False, "error": traceback.format_exc().strip().splitlines()[-1]}
            print(f"[{name}] FAILED\n{traceback.format_exc()}", file=sys.stderr)
    cfg = load_config()
    write_json("status", {"collectors": status,
                          "config": {**{k: cfg.get(k) for k in ("rotate_seconds", "timezone", "brief_window")}, **(cfg.get("layout") or {}), "agent_name": cfg.get("agent_name", "Brief"), "location_image": (cfg.get("location") or {}).get("image"), "week_days": (cfg.get("layout") or {}).get("week_days", 5)}})
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ALL))
