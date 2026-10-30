"""Newest Hermes morning-brief (the agent's scheduled cron) → data/brief.json, plus spoken audio data/brief.mp3
rendered with Piper in the agent's voice whenever the brief text changes."""
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from common import DATA, hermes_latest_response, load_config, write_json

DEFAULT_VOICE = "~/.local/share/piper/en_GB-southern_english_female-low.onnx"
STAMP = DATA / ".brief_audio.json"


def speakable(text: str) -> str:
    """Strip markdown/emoji so Piper doesn't read asterisks and symbols aloud."""
    t = re.sub(r"[*_`#>]+", "", text)
    t = re.sub(r"https?://\S+", "link", t)
    t = re.sub(r"[^\x00-\x7F]+", " ", t)          # emoji / symbols
    t = re.sub(r"\s*\n\s*\n\s*", ". ", t)        # paragraph breaks → pauses
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def synth(text: str, voice: str | None) -> dict | None:
    VOICE = Path(os.path.expanduser(voice or DEFAULT_VOICE))
    if not VOICE.exists() or not text:
        return None
    digest = hashlib.sha1(text.encode()).hexdigest()
    prev = json.loads(STAMP.read_text()) if STAMP.exists() else {}
    if prev.get("sha1") == digest and (DATA / "brief.mp3").exists():
        return prev
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "brief.wav"
        subprocess.run(["piper", "--model", str(VOICE), "--sentence-silence", "0.4", "--output_file", str(wav)],
                       input=speakable(text), text=True, check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "64k",
                        str(DATA / "brief.mp3")], check=True)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(DATA / "brief.mp3")], capture_output=True, text=True).stdout.strip() or 0)
    info = {"sha1": digest, "audio": "data/brief.mp3", "duration_s": round(dur, 1)}
    STAMP.write_text(json.dumps(info))
    return info


def main() -> None:
    cfg = load_config()
    out = hermes_latest_response(cfg.get("hermes_brief_job"))
    if out.get("found"):
        try:
            audio = synth(out["text"], cfg.get("piper_voice"))
            if audio:
                out.update(audio=audio["audio"], duration_s=audio["duration_s"])
        except Exception as e:  # audio is optional; never block the text
            out["audio_error"] = f"{type(e).__name__}: {e}"
    out["window"] = cfg.get("brief_window", [5, 7])
    write_json("brief", out)


if __name__ == "__main__":
    main()
