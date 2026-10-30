"""X / Twitter trending summary written by a Hermes cron job (x_search toolset) → data/xtrends.json."""
from common import hermes_latest_response, load_config, write_json


def main() -> None:
    cfg = load_config()
    if (cfg.get("x_api") or {}).get("enabled") and (cfg.get("x_api") or {}).get("trends", True):
        return  # the X API collector (xapi.py) owns data/xtrends.json in this configuration
    job = cfg.get("hermes_xtrends_job")
    out = hermes_latest_response(job) if job else {"found": False, "hint": "set hermes_xtrends_job in config.yaml"}
    write_json("xtrends", out)


if __name__ == "__main__":
    main()
