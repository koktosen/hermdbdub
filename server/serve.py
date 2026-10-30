#!/usr/bin/env python3
"""Static server for web/ and data/ on 0.0.0.0:8470 with no-cache headers (the kiosk polls data/*.json)."""
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("HERMDBW_DATA", ROOT / "data"))   # demo mode points this at generated sample data
PORT = int(os.environ.get("PORT", "8470"))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / "web"), **kw)

    def do_GET(self):
        if self.path.split("?")[0] in ("/setup", "/setup/"):
            self.path = "/setup.html"
        if self.path.startswith("/api/setup"):
            return self.setup_api()
        if self.path.startswith("/api/trigger"):
            return self.trigger()
        if self.path.startswith("/api/alert"):
            return self.alert()
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/setup"):
            return self.setup_api()
        if self.path.startswith("/api/trigger"):
            return self.trigger()
        if self.path.startswith("/api/alert"):
            return self.alert()
        self.send_error(404)

    def alert(self):
        """Flash alerts for the wall (your agent posts these).
        POST /api/alert  JSON {"title","body","image"?,"level"?("info"|"warn"|"urgent"),"ttl_minutes"?,"flash_seconds"?}
        GET  /api/alert?dismiss=ID | ?clear=1 | (no args → list)
        Alerts live in data/alerts.json; the page polls it every 5 s, flashes new ones full-screen, then pins a banner until ttl/dismiss."""
        import json, time, uuid
        from urllib.parse import parse_qs, urlparse
        path = DATA_DIR / "alerts.json"
        alerts = json.loads(path.read_text()) if path.exists() else []
        now = time.time()
        alerts = [a for a in alerts if a.get("expires", 0) > now]
        q = parse_qs(urlparse(self.path).query)
        if self.command == "POST":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self.send_error(400, "body must be JSON")
            if not body.get("title"):
                return self.send_error(400, "title required")
            ttl = float(body.get("ttl_minutes", 720))
            alerts.append({"id": uuid.uuid4().hex[:8], "title": str(body["title"])[:120], "body": str(body.get("body", ""))[:600],
                           "image": body.get("image"), "level": body.get("level", "info"), "created": now, "expires": now + ttl * 60,
                           "flash_seconds": int(body.get("flash_seconds", 20))})
        elif "dismiss" in q:
            alerts = [a for a in alerts if a["id"] != q["dismiss"][0]]
        elif "clear" in q:
            alerts = []
        path.write_text(json.dumps(alerts))
        payload = json.dumps({"alerts": alerts})
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(payload.encode())

    def setup_api(self):
        """Setup API: GET /api/setup · POST /api/setup {answers…} (header X-Source: agent|browser) ·
        POST /api/setup/validate {url} · POST /api/setup/apply · GET /api/setup/cloudinit"""
        import json
        import lib_setup as ls
        from urllib.parse import urlparse
        sub = urlparse(self.path).path.removeprefix("/api/setup").strip("/")
        body = {}
        if self.command == "POST":
            n = int(self.headers.get("Content-Length") or 0)
            try: body = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError: return self.send_error(400, "body must be JSON")
        state = ls.load()
        if sub == "" and self.command == "GET": out = ls.redacted(state)
        elif sub == "" and self.command == "POST":
            ls.save(ls.update(state, body, self.headers.get("X-Source", "browser"))); out = ls.redacted(ls.load())
        elif sub == "validate": out = ls.validate_calendar(body.get("url", ""))
        elif sub == "apply": out = ls.apply(state)
        elif sub == "cloudinit": out = ls.cloudinit(state)
        else: return self.send_error(404)
        payload = json.dumps(out)
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(payload.encode())

    def trigger(self):
        """GET/POST /api/trigger?what=brief → data/trigger.json; the kiosk polls it and starts the takeover."""
        import json, time
        from urllib.parse import parse_qs, urlparse
        what = parse_qs(urlparse(self.path).query).get("what", ["brief"])[0]
        if what not in ("brief", "dismiss"):
            return self.send_error(400, "what must be brief|dismiss")
        payload = json.dumps({"what": what, "ts": time.time()})
        (DATA_DIR / "trigger.json").write_text(payload)
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(payload.encode())

    def translate_path(self, path):
        clean = path.split("?", 1)[0]
        if clean.startswith("/data/"):
            return str(DATA_DIR / os.path.basename(clean))
        if clean == "/healthz":
            return str(DATA_DIR / "status.json")
        return super().translate_path(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "/data/" not in str(args[0] if args else ""):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"rpi-dashboard serving {ROOT/'web'} on :{PORT}", file=sys.stderr, flush=True)
    srv.serve_forever()
