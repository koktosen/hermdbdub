#!/usr/bin/env python3
"""Static server for web/ and data/ on 0.0.0.0:8470, plus the small API the agent and the setup page use.

Trust model: requests from the server itself (loopback — the agent, wallctl, the CLI) are trusted. Anyone else must
present the token in data/.api_token (generated on first start, mode 600) as an `X-Wall-Token` header or `?token=`.
Reads of the wall's own data files are open to whoever can reach the port (the kiosk needs them); only the files
the page uses are served, never setup state or dotfiles."""
import json
import os
import re
import secrets
import sys
import tempfile
import threading
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DATA_DIR = Path(os.environ.get("HERMDBW_DATA", ROOT / "data"))   # demo mode points this at generated sample data
PORT = int(os.environ.get("PORT", "8470"))
TOKEN_FILE = DATA_DIR / ".api_token"
PUBLIC_DATA = {f"{n}.json" for n in ("calendar", "weather", "brief", "ops", "markets", "rss", "xtrends", "xme", "xusage",
                                     "fng", "status", "alerts", "trigger")} | {"brief.mp3"}
MAX_BODY = 64 * 1024
LEVELS = ("info", "warn", "urgent")
IMAGE_RE = re.compile(r"^img/alerts/[\w.-]+\.(?:jpe?g|png|webp)$", re.I)
LOOPBACK = ("127.0.0.1", "::1", "::ffff:127.0.0.1")
STALE_AFTER = {"ops": 5 * 60}          # seconds a collector may go without a run before /healthz complains
STALE_DEFAULT = 15 * 60
IGNORE_IN_HEALTH = {"xapi", "xtrends"}  # metered / optional
_lock = threading.Lock()


def api_token() -> str:
    try:
        return TOKEN_FILE.read_text().strip()
    except FileNotFoundError:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tok = secrets.token_urlsafe(24)
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(tok)
        return tok


def write_atomic(path: Path, obj) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    # ---------- routing ----------
    def route(self):
        p = urlparse(self.path).path
        if p in ("/setup", "/setup/"):
            self.path = "/setup.html"; return None
        if p.startswith("/api/setup"): return self.setup_api
        if p.startswith("/api/trigger"): return self.trigger
        if p.startswith("/api/alert"): return self.alert
        if p == "/healthz": return self.healthz
        if p.startswith("/api/"): return lambda: self.send_error(404)
        return None

    def do_GET(self):
        h = self.route()
        return h() if h else super().do_GET()

    def do_POST(self):
        h = self.route()
        return h() if h else self.send_error(404)

    # ---------- helpers ----------
    def trusted(self) -> bool:
        if self.client_address[0] in LOOPBACK:
            return True
        tok = self.headers.get("X-Wall-Token") or parse_qs(urlparse(self.path).query).get("token", [""])[0]
        return bool(tok) and secrets.compare_digest(tok, TOKEN)

    def deny(self):
        self.send_error(403, "this needs the wall token (server/data/.api_token) or a request from the server itself")

    def body_json(self):
        """Parsed JSON object from a POST body, or None after an error response has been sent."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self.send_error(400, "bad Content-Length"); return None
        if n > MAX_BODY:
            self.send_error(413, f"body over {MAX_BODY} bytes"); return None
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            self.send_error(400, "body must be JSON"); return None
        if not isinstance(body, dict):
            self.send_error(400, "body must be a JSON object"); return None
        return body

    def send_error(self, code, message=None, explain=None):
        """API callers (the agent, curl) get JSON errors; static paths keep the stock HTML page."""
        if self.path.startswith("/api/") or self.path == "/healthz":
            return self.send_json({"error": message or str(code)}, code)
        super().send_error(code, message, explain)

    def send_json(self, obj, code=200):
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    # ---------- API ----------
    def alert(self):
        """Flash alerts for the wall (your agent posts these).
        POST /api/alert  JSON {"title","body","image"?,"level"?("info"|"warn"|"urgent"),"ttl_minutes"?,"flash_seconds"?}
        GET  /api/alert            → list (open)
        GET  /api/alert?dismiss=ID | ?clear=1   (trusted)
        Alerts live in data/alerts.json; the page polls it every 5 s, flashes new ones full-screen, then pins a banner until ttl/dismiss."""
        path = DATA_DIR / "alerts.json"
        q = parse_qs(urlparse(self.path).query)
        mutating = self.command == "POST" or "dismiss" in q or "clear" in q
        if mutating and not self.trusted():
            return self.deny()
        new = None
        if self.command == "POST":
            body = self.body_json()
            if body is None: return
            title = str(body.get("title") or "").strip()
            if not title: return self.send_error(400, "title required")
            level = str(body.get("level") or "info")
            if level not in LEVELS: return self.send_error(400, f"level must be one of {LEVELS}")
            image = body.get("image")
            if image is not None:
                image = str(image)
                if not IMAGE_RE.match(image) or not (WEB / image).is_file():
                    return self.send_error(400, "image must name an existing file under web/img/alerts/, e.g. img/alerts/trip.jpg")
            try:
                ttl = float(body.get("ttl_minutes", 720)); flash = int(body.get("flash_seconds", 20))
            except (TypeError, ValueError):
                return self.send_error(400, "ttl_minutes and flash_seconds must be numbers")
            now = time.time()
            new = {"id": uuid.uuid4().hex[:8], "title": title[:120], "body": str(body.get("body") or "")[:600],
                   "image": image, "level": level, "created": now, "expires": now + max(1, ttl) * 60,
                   "flash_seconds": max(0, min(flash, 120))}
        with _lock:
            now = time.time()
            alerts = [a for a in read_json(path, []) if isinstance(a, dict) and a.get("expires", 0) > now]
            if new: alerts.append(new)
            elif "dismiss" in q: alerts = [a for a in alerts if a.get("id") != q["dismiss"][0]]
            elif "clear" in q: alerts = []
            if mutating: write_atomic(path, alerts)
        self.send_json({"alerts": alerts})

    def setup_api(self):
        """Setup API (trusted only): GET /api/setup · POST /api/setup {answers…} (header X-Source: agent|browser) ·
        POST /api/setup/validate {url} · POST /api/setup/apply · GET /api/setup/cloudinit"""
        if not self.trusted():
            return self.deny()
        import lib_setup as ls
        sub = urlparse(self.path).path.removeprefix("/api/setup").strip("/")
        body = {}
        if self.command == "POST":
            body = self.body_json()
            if body is None: return
        state = ls.load()
        if sub == "" and self.command == "GET": out = ls.redacted(state)
        elif sub == "" and self.command == "POST":
            ls.save(ls.update(state, body, self.headers.get("X-Source", "browser"))); out = ls.redacted(ls.load())
        elif sub == "validate":
            url = str(body.get("url") or "")
            if not re.match(r"^(https?|webcal)://", url, re.I): return self.send_error(400, "url must start with https://")
            out = ls.validate_calendar(url)
        elif sub == "apply": out = ls.apply(state)
        elif sub == "cloudinit": out = ls.cloudinit(state)
        else: return self.send_error(404)
        self.send_json(out)

    def trigger(self):
        """GET/POST /api/trigger?what=brief|dismiss (trusted) → data/trigger.json; the kiosk polls it and starts the takeover."""
        if not self.trusted():
            return self.deny()
        what = parse_qs(urlparse(self.path).query).get("what", ["brief"])[0]
        if what not in ("brief", "dismiss"):
            return self.send_error(400, "what must be brief|dismiss")
        payload = {"what": what, "ts": time.time()}
        with _lock:
            write_atomic(DATA_DIR / "trigger.json", payload)
        self.send_json(payload)

    def healthz(self):
        """200 when every collector ran recently and succeeded, else 503 with the reasons."""
        st = read_json(DATA_DIR / "status.json", None)
        if not st:
            return self.send_json({"ok": False, "error": "collectors have not run yet"}, 503)
        now = time.time(); failed, stale = [], []
        for name, c in (st.get("collectors") or {}).items():
            if name in IGNORE_IN_HEALTH: continue
            if not c.get("ok"): failed.append(name)
            at = c.get("at_epoch")
            if at and now - at > STALE_AFTER.get(name, STALE_DEFAULT): stale.append(name)
        ok = not failed and not stale
        self.send_json({"ok": ok, "failed": failed, "stale": stale, "generated_at": st.get("generated_at")}, 200 if ok else 503)

    # ---------- static ----------
    def translate_path(self, path):
        clean = path.split("?", 1)[0]
        if clean.startswith("/data/"):
            name = os.path.basename(clean)
            return str(DATA_DIR / name) if name in PUBLIC_DATA else str(DATA_DIR / "__not_served__")
        return super().translate_path(path)

    def list_directory(self, path):
        self.send_error(404)
        return None

    def end_headers(self):
        p = self.path.split("?", 1)[0]
        self.send_header("Cache-Control", "max-age=3600" if p.startswith(("/logos/", "/img/")) else "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        line = str(args[0] if args else "")
        if not any(s in line for s in ("/data/", "/logos/", "/img/")):
            super().log_message(fmt, *args)


TOKEN = api_token()

if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"hermdbw serving {WEB} on :{PORT} — API token for non-local callers in {TOKEN_FILE}", file=sys.stderr, flush=True)
    srv.serve_forever()
