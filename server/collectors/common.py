"""Shared helpers for the dashboard collectors."""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_config() -> dict:
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f) or {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(name: str, payload: dict) -> None:
    """Atomic write so the web server never serves a half-written file."""
    DATA.mkdir(exist_ok=True)
    payload.setdefault("generated_at", now_iso())
    fd, tmp = tempfile.mkstemp(dir=DATA, prefix=f".{name}.", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(payload, f, ensure_ascii=False, default=str)
    os.replace(tmp, DATA / f"{name}.json")


def hermes_latest_response(job_id: str) -> dict:
    """Newest markdown under ~/.hermes/cron/output/<job_id>/ → the '## Response' body plus its run time."""
    import re
    from datetime import datetime
    from pathlib import Path as _P
    root = _P.home() / ".hermes" / "cron" / "output" / str(job_id)
    files = sorted(root.glob("*.md")) if job_id else []
    if not files:
        return {"found": False, "hint": f"waiting for the first run of Hermes job {job_id or '(unset)'}"}
    newest = files[-1]
    text = newest.read_text(errors="replace")
    m = re.search(r"^## Response\s*\n(.*)\Z", text, re.S | re.M)
    run_time = re.search(r"\*\*Run Time:\*\*\s*(.+)", text)
    stamp = run_time.group(1).strip() if run_time else datetime.fromtimestamp(newest.stat().st_mtime).isoformat()
    return {"found": True, "file": newest.name, "run_time": stamp, "text": (m.group(1) if m else text).strip()}
