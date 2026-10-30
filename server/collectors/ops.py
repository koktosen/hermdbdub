"""Host status: GPUs, ComfyUI, user services, Tailscale, disks, load, newest build artifact, printer."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import requests

from common import load_config, write_json


def read(p: Path, default=None):
    try:
        return p.read_text().strip()
    except OSError:
        return default


def gpus() -> list:
    out = []
    for dev in sorted(Path("/sys/class/drm").glob("card[0-9]/device")):
        busy = read(dev / "gpu_busy_percent")
        if busy is None:
            continue
        hwmon = next(iter((dev / "hwmon").glob("hwmon*")), None)
        temp = read(hwmon / "temp1_input") if hwmon else None
        power = read(hwmon / "power1_average") if hwmon else None
        used, total = read(dev / "mem_info_vram_used", "0"), read(dev / "mem_info_vram_total", "0")
        out.append({
            "card": dev.parent.name, "busy": int(busy),
            "temp_c": round(int(temp) / 1000) if temp else None,
            "power_w": round(int(power) / 1e6) if power else None,
            "vram_used_gb": round(int(used) / 2**30, 1), "vram_total_gb": round(int(total) / 2**30, 1),
        })
    return out


def comfy(endpoints: list) -> list:
    out = []
    for base in endpoints:
        item = {"url": base, "up": False}
        try:
            q = requests.get(f"{base}/queue", timeout=2).json()
            item.update(up=True, running=len(q.get("queue_running", [])), pending=len(q.get("queue_pending", [])))
        except Exception:
            pass
        out.append(item)
    return out


def services(names: list) -> dict:
    if not names:
        return {}
    r = subprocess.run(["systemctl", "--user", "is-active", *names], capture_output=True, text=True)
    return dict(zip(names, r.stdout.split()))


def tailscale() -> dict:
    try:
        d = json.loads(subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=5).stdout)
    except Exception as e:
        return {"error": str(e)}
    peers = [{"host": p["HostName"], "os": p.get("OS"), "online": p.get("Online", False)} for p in d.get("Peer", {}).values()]
    peers.sort(key=lambda p: (not p["online"], p["host"].lower()))
    return {"self": d["Self"]["HostName"], "online": sum(p["online"] for p in peers), "total": len(peers), "peers": peers}


def disks(paths: list) -> list:
    out = []
    for p in paths:
        try:
            u = shutil.disk_usage(p)
            out.append({"path": p, "used_pct": round(100 * u.used / u.total), "free_gb": round(u.free / 2**30)})
        except OSError:
            pass
    return out


def system() -> dict:
    load1, load5, _ = os.getloadavg()
    mem = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":")
        mem[k] = int(v.split()[0])
    return {
        "load1": round(load1, 1), "load5": round(load5, 1), "cpus": os.cpu_count(),
        "uptime_h": round(float(read(Path("/proc/uptime"), "0 0").split()[0]) / 3600, 1),
        "mem_used_pct": round(100 * (1 - mem["MemAvailable"] / mem["MemTotal"])),
        "mem_total_gb": round(mem["MemTotal"] / 2**20),
    }


def newest_apk(apk_dir: str, prefix: str = "") -> dict | None:
    """Newest entry in a build/artifact directory (optional; shown on the host tile)."""
    d = Path(os.path.expanduser(apk_dir or ""))
    if not d.is_dir():
        return None
    entries = [p for p in d.iterdir() if p.name.startswith(prefix)]
    if not entries:
        return None
    newest = max(entries, key=lambda p: p.stat().st_mtime)
    return {"name": newest.name, "mtime": newest.stat().st_mtime}


def printer(cfg: dict) -> dict | None:
    if not cfg or not cfg.get("url"):
        return None
    item = {"name": cfg.get("name", "printer"), "up": False}
    try:
        r = requests.get(f"{cfg['url'].rstrip('/')}/printer/objects/query",
                         params={"print_stats": "", "extruder": "", "heater_bed": "", "display_status": ""}, timeout=2)
        s = r.json()["result"]["status"]
        item.update(up=True, state=s["print_stats"]["state"], file=s["print_stats"].get("filename"),
                    progress=round(100 * s["display_status"].get("progress", 0)),
                    nozzle=round(s["extruder"]["temperature"]), bed=round(s["heater_bed"]["temperature"]))
    except Exception:
        pass
    return item


def main() -> None:
    cfg = load_config()
    write_json("ops", {
        "host": os.uname().nodename,
        "system": system(),
        "gpus": gpus(),
        "comfy": comfy(cfg.get("comfy_endpoints", [])),
        "services": services(cfg.get("services", [])),
        "services_on_demand": cfg.get("services_on_demand", []),
        "tailscale": tailscale(),
        "disks": disks(cfg.get("disks", [])),
        "apk": newest_apk(cfg.get("apk_dir"), cfg.get("apk_prefix", "")),
        "printer": printer(cfg.get("printer")),
    })


if __name__ == "__main__":
    main()
