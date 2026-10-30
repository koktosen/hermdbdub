"""Setup state + apply logic behind /api/setup. Answers live in data/setup.json (mode 600; the Wi-Fi password and
calendar URLs are secrets). `apply()` merges answers into config.yaml with ruamel (comments survive) and runs the
collectors. Pure functions; serve.py is the only caller."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("HERMDBW_DATA", ROOT / "data"))
CONFIG = Path(os.environ.get("HERMDBW_CONFIG", ROOT / "config.yaml"))
STATE = DATA / "setup.json"
SECRET_KEYS = {"wifi_password", "pi_password"}
PALETTE = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
IMAGES = {  # pi model → Raspberry Pi OS Lite image family
    "pi1": "raspios_lite_armhf", "pizero": "raspios_lite_armhf", "pi2": "raspios_lite_armhf",
    "pi3": "raspios_lite_arm64", "pizero2": "raspios_lite_arm64", "pi4": "raspios_lite_arm64", "pi5": "raspios_lite_arm64",
}


def load() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"answers": {}, "sources": {}}


def save(state: dict) -> None:
    DATA.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(state, indent=1)); tmp.chmod(0o600); tmp.replace(STATE)


def redacted(state: dict) -> dict:
    a = dict(state.get("answers", {}))
    for k in SECRET_KEYS:
        if a.get(k): a[k] = "••••••"
    a["calendars"] = [{**c, "url": "(set)" if c.get("url") else ""} for c in a.get("calendars", [])]
    return {"answers": a, "sources": state.get("sources", {}), "missing": missing(state)}


def missing(state: dict) -> list:
    a = state.get("answers", {})
    need = []
    if not a.get("pi_model"): need.append("pi_model")
    if not a.get("pi_hostname"): need.append("pi_hostname")
    if not a.get("pi_password"): need.append("pi_password")
    if not a.get("wifi_ssid"): need.append("wifi_ssid")
    if not (a.get("location") or {}).get("lat"): need.append("city")
    if not any(c.get("url") for c in a.get("calendars", [])): need.append("calendars")
    return need


def update(state: dict, patch: dict, source: str) -> dict:
    """Merge a partial answer set. Calendars merge by name. Records who answered what."""
    a = state.setdefault("answers", {}); src = state.setdefault("sources", {})
    for k, v in patch.items():
        if k == "calendars":
            cur = {c.get("name", "").lower(): c for c in a.get("calendars", [])}
            for c in v or []:
                if c.get("name"): cur[c["name"].lower()] = {**cur.get(c["name"].lower(), {}), **c}
            a["calendars"] = list(cur.values())
        elif v in (None, ""):
            continue
        else:
            a[k] = v
        src[k] = source
    return state


def validate_calendar(url: str) -> dict:
    """Fetch + parse an iCal URL the way the collector does; returns a count or an error."""
    sys.path.insert(0, str(ROOT / "collectors"))
    from datetime import date, datetime, time, timedelta
    from zoneinfo import ZoneInfo
    import cal_feeds
    try:
        tz = ZoneInfo("UTC"); start = datetime.combine(date.today(), time.min, tzinfo=tz)
        ev = cal_feeds.events_from(cal_feeds.fetch(url), {"name": "test", "color": "#000"}, tz, start, start + timedelta(days=14))
        return {"ok": True, "events_14d": len(ev), "sample": [e["title"] for e in ev[:3]]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}


def cloudinit(state: dict) -> dict:
    """First-boot files from the answers (Raspberry Pi OS Trixie+ cloud-init)."""
    a = state.get("answers", {})
    pw = a.get("pi_password", "")
    h = subprocess.run(["openssl", "passwd", "-6", pw], capture_output=True, text=True).stdout.strip() if pw else "!"
    user = a.get("pi_user", "wall")
    user_data = f"""#cloud-config
hostname: {a.get('pi_hostname', 'wall')}
manage_etc_hosts: true
timezone: {a.get('timezone', 'UTC')}
ssh_pwauth: true
users:
- name: {user}
  shell: /bin/bash
  groups: users,adm,dialout,audio,netdev,video,plugdev,cdrom,games,input,gpio,spi,i2c,render,sudo
  lock_passwd: false
  passwd: "{h}"
  sudo: ALL=(ALL) NOPASSWD:ALL
packages:
- avahi-daemon
runcmd:
- [systemctl, enable, --now, ssh]
"""
    wifi = ""
    if a.get("wifi_ssid"):
        wifi = f"""  wifis:
    wlan0:
      dhcp4: true
      optional: true
      access-points:
        "{a['wifi_ssid']}":
          password: "{a.get('wifi_password', '')}"
"""
    network = "network:\n  version: 2\n  ethernets:\n    eth0:\n      dhcp4: true\n      optional: true\n" + wifi
    fam = IMAGES.get(a.get("pi_model", ""), "raspios_lite_arm64")
    return {"user-data": user_data, "network-config": network, "image_family": fam,
            "image_url": f"https://downloads.raspberrypi.com/{fam}/images/",
            "flash_hint": "xzcat <image>.img.xz | sudo dd of=/dev/sdX bs=4M conv=fsync   # then copy user-data + network-config onto the bootfs partition"}


def apply(state: dict) -> dict:
    """Write config.yaml from the answers (only the keys we have) and run the collectors."""
    from ruamel.yaml import YAML
    yaml = YAML(); yaml.preserve_quotes = True; yaml.width = 4096
    a = state.get("answers", {})
    if not CONFIG.exists():
        CONFIG.write_text((ROOT / "config.yaml.example").read_text()); CONFIG.chmod(0o600)
    cfg = yaml.load(CONFIG.read_text()) or {}
    loc = a.get("location") or {}
    if loc.get("lat") is not None:
        cfg.setdefault("location", {}); cfg["location"]["name"] = loc.get("name") or a.get("city", "Home")
        cfg["location"]["lat"] = float(loc["lat"]); cfg["location"]["lon"] = float(loc["lon"])
    if a.get("timezone"): cfg["timezone"] = a["timezone"]
    if a.get("agent_name"): cfg["agent_name"] = a["agent_name"]
    if a.get("calendars"):
        used = set(); out = []
        for i, c in enumerate(c for c in a["calendars"] if c.get("url")):
            color = c.get("color") or next((p for p in PALETTE if p not in used), PALETTE[i % len(PALETTE)]); used.add(color)
            out.append({"name": c["name"], "url": c["url"], "color": color})
        if out: cfg["calendars"] = out
    show = a.get("show") or {}
    if show:
        cfg.setdefault("layout", {})
        for k in ("pages", "rotate_pages", "ticker_rows", "feed_columns", "dock_tiles", "marquees"):
            if k in show: cfg["layout"][k] = list(show[k])
        if "pages" in show and "rotate_pages" not in show: cfg["layout"]["rotate_pages"] = list(show["pages"])
    if a.get("rss_feeds"): cfg["rss_feeds"] = [{"name": f["name"], "url": f["url"]} for f in a["rss_feeds"] if f.get("url")]
    if a.get("crypto"): cfg.setdefault("markets", {})["crypto"] = list(a["crypto"])
    if a.get("stocks"): cfg.setdefault("markets", {})["stocks"] = list(a["stocks"])
    if a.get("x_enabled") is not None: cfg.setdefault("x_api", {})["enabled"] = bool(a["x_enabled"])
    tmp = CONFIG.with_suffix(".yaml.tmp")
    with open(tmp, "w") as f: yaml.dump(cfg, f)
    tmp.chmod(0o600); tmp.replace(CONFIG)
    py = ROOT / ".venv/bin/python"; py = py if py.exists() else Path(sys.executable)
    r = subprocess.run([str(py), str(ROOT / "collectors/run_all.py"), "calendar", "weather", "markets", "rss", "fng", "ops"],
                       cwd=ROOT / "collectors", capture_output=True, text=True, env={**os.environ, "HERMDBW_CONFIG": str(CONFIG)})
    status = json.loads((DATA / "status.json").read_text()).get("collectors", {}) if (DATA / "status.json").exists() else {}
    return {"ok": r.returncode == 0, "collectors": status, "config": str(CONFIG)}
