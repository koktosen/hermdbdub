"""Official X API via the xurl CLI (OAuth 2.0 user login done by the owner with `xurl auth oauth2`).
Metered on purpose: runs only on its own timer (config x_api.times) and makes at most one request per enabled
feature per run. Writes data/xtrends.json (personalized trends), optionally data/xme.json (mentions/timeline),
and data/xusage.json (X's own monthly count, if app-only auth is registered). Every request is appended to
data/x_usage.jsonl so the local count is exact."""
import json
import subprocess
from datetime import datetime, timezone

from common import DATA, load_config, write_json

USER_CACHE = DATA / ".xme_user.json"
USAGE_LOG = DATA / "x_usage.jsonl"


def log_usage(endpoint: str, status: str) -> None:
    DATA.mkdir(exist_ok=True)
    with open(USAGE_LOG, "a") as f:
        f.write(json.dumps({"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "endpoint": endpoint, "status": status}) + "\n")


def usage_summary() -> dict:
    if not USAGE_LOG.exists():
        return {"today": 0, "month": 0}
    now = datetime.now(timezone.utc); day, mon = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")
    today = month = 0; last_err = None
    for line in USAGE_LOG.read_text().splitlines():
        try: e = json.loads(line)
        except json.JSONDecodeError: continue
        if e["t"].startswith(mon): month += 1
        if e["t"].startswith(day): today += 1
        if e["status"] != "ok": last_err = {"t": e["t"], "status": e["status"]}
    return {"today": today, "month": month, "last_error": last_err}


def xurl(path: str, auth: str | None = None) -> dict:
    endpoint = path.split("?")[0]
    cmd = ["xurl"] + (["--auth", auth] if auth else []) + [path]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    out = r.stdout.strip()
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        log_usage(endpoint, "no-json"); raise RuntimeError((r.stderr or out or "xurl returned nothing").strip()[:120])
    if "status" in data and "detail" in data and "data" not in data:
        log_usage(endpoint, f"{data['status']} {data.get('title', '')}".strip()); raise RuntimeError(f"X API {data['status']}: {data['detail']}")
    log_usage(endpoint, "ok")
    return data


def me() -> dict:
    if USER_CACHE.exists():
        return json.loads(USER_CACHE.read_text())
    d = xurl("/2/users/me")["data"]
    DATA.mkdir(exist_ok=True); USER_CACHE.write_text(json.dumps(d))
    return d


def prev(name: str) -> dict:
    p = DATA / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def trends(n: int) -> None:
    try:
        d = xurl("/2/users/personalized_trends")
        items = [{"name": t.get("trend_name"), "category": t.get("category"), "posts": t.get("post_count"), "since": t.get("trending_since")} for t in d.get("data", [])][:n]
        write_json("xtrends", {"found": True, "source": "x-api personalized", "trends": items})
    except Exception as e:
        write_json("xtrends", {**prev("xtrends"), "error": f"{type(e).__name__}: {e}"})


def mentions(kind: str, n: int) -> None:
    try:
        u = me()
        fields = "tweet.fields=created_at,author_id&expansions=author_id&user.fields=username,name"
        path = {"mentions": f"/2/users/{u['id']}/mentions?max_results={n}&{fields}",
                "timeline": f"/2/users/{u['id']}/timelines/reverse_chronological?max_results={n}&{fields}"}[kind]
        d = xurl(path)
        users = {x["id"]: x for x in d.get("includes", {}).get("users", [])}
        posts = [{"id": t["id"], "text": t["text"], "time": t.get("created_at"),
                  "handle": users.get(t.get("author_id"), {}).get("username"), "name": users.get(t.get("author_id"), {}).get("name")} for t in d.get("data", [])]
        write_json("xme", {"found": True, "me": u.get("username"), "source": kind, "posts": posts})
    except Exception as e:
        write_json("xme", {**prev("xme"), "found": bool(prev("xme").get("posts")), "error": f"{type(e).__name__}: {e}"})


def official_usage() -> dict | None:
    """X's own project usage (needs app-only auth registered in xurl). Not metered against credits as far as we can tell."""
    try:
        d = xurl("/2/usage/tweets", auth="app")["data"]
        return {"project_usage": d.get("project_usage"), "cap": d.get("project_cap"), "reset_day": d.get("cap_reset_day")}
    except Exception as e:
        return {"error": str(e)[:100]}


def main() -> None:
    cfg = load_config().get("x_api") or {}
    if not cfg.get("enabled", False):
        write_json("xusage", {"local": usage_summary(), "hint": "x_api.enabled is false"}); return
    if cfg.get("trends", True):
        trends(int(cfg.get("max_trends", 12)))
    if cfg.get("mentions", False):
        mentions(cfg.get("mentions_source", "mentions"), int(cfg.get("max_results", 10)))
    write_json("xusage", {"local": usage_summary(), "official": official_usage() if cfg.get("official_usage", True) else None})


if __name__ == "__main__":
    main()
