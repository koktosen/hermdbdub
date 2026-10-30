#!/usr/bin/env bash
# hermdbw server install — idempotent. Creates the venv, config (if missing), systemd --user units pointing
# at THIS checkout, the `wallctl` wrapper, and starts everything. Re-run after moving the repo or pulling.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8470}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
BIN_DIR="${HOME}/.local/bin"
log() { printf '\n==> %s\n' "$*"; }

log "python venv + deps"
if command -v uv >/dev/null; then
	[[ -x "$HERE/.venv/bin/python" ]] || uv venv -q "$HERE/.venv"
	uv pip install -q --python "$HERE/.venv/bin/python" icalendar recurring-ical-events requests pyyaml feedparser ruamel.yaml
else
	[[ -x "$HERE/.venv/bin/python" ]] || python3 -m venv "$HERE/.venv"
	"$HERE/.venv/bin/pip" install -q icalendar recurring-ical-events requests pyyaml feedparser ruamel.yaml
fi

log "config"
if [[ ! -f "$HERE/config.yaml" ]]; then
	cp "$HERE/config.yaml.example" "$HERE/config.yaml"; chmod 600 "$HERE/config.yaml"
	echo "  created config.yaml from the example — add your calendars/location (or ask your Hermes agent to)"
fi
mkdir -p "$HERE/data" "$HERE/web/logos"

log "systemd --user units → $UNIT_DIR"
mkdir -p "$UNIT_DIR" "$BIN_DIR"
PY="$HERE/.venv/bin/python"
cat > "$UNIT_DIR/hermdbw-web.service" <<UNIT
[Unit]
Description=hermdbw dashboard static server (:$PORT)
After=network-online.target
[Service]
Environment=PORT=$PORT
ExecStart=$PY $HERE/serve.py
WorkingDirectory=$HERE
Restart=on-failure
RestartSec=3
[Install]
WantedBy=default.target
UNIT
cat > "$UNIT_DIR/hermdbw-collect.service" <<UNIT
[Unit]
Description=hermdbw collectors (calendar, weather, brief, markets, rss, xtrends, fng)
[Service]
Type=oneshot
WorkingDirectory=$HERE/collectors
ExecStart=$PY $HERE/collectors/run_all.py calendar weather brief markets rss xtrends fng   # xtrends is a no-op when x_api.trends is on
UNIT
cat > "$UNIT_DIR/hermdbw-collect.timer" <<'UNIT'
[Unit]
Description=Run hermdbw collectors every 5 min
[Timer]
OnBootSec=30s
OnUnitActiveSec=5min
AccuracySec=30s
[Install]
WantedBy=timers.target
UNIT
cat > "$UNIT_DIR/hermdbw-ops.service" <<UNIT
[Unit]
Description=hermdbw host-status collector
[Service]
Type=oneshot
WorkingDirectory=$HERE/collectors
ExecStart=$PY $HERE/collectors/run_all.py ops
UNIT
cat > "$UNIT_DIR/hermdbw-ops.timer" <<'UNIT'
[Unit]
Description=Run hermdbw host-status collector every minute
[Timer]
OnBootSec=20s
OnUnitActiveSec=1min
AccuracySec=10s
[Install]
WantedBy=timers.target
UNIT

# personal-X collector: its own timer so paid reads stay at the configured handful per day
"$PY" - "$HERE/config.yaml" > "$UNIT_DIR/hermdbw-xapi.timer" <<'PYEOF'
import sys, yaml
c = yaml.safe_load(open(sys.argv[1])) or {}
times = (c.get("x_api") or c.get("x_personal") or {}).get("times") or ["07:00", "10:00", "13:00", "16:00", "19:00"]
print("[Unit]\nDescription=hermdbw X API collector schedule\n[Timer]")
for t in times:
    print(f"OnCalendar=*-*-* {t}:00")
print("Persistent=false\n[Install]\nWantedBy=timers.target")
PYEOF
cat > "$UNIT_DIR/hermdbw-xapi.service" <<UNIT
[Unit]
Description=hermdbw X API collector (trends / mentions / usage; metered)
[Service]
Type=oneshot
WorkingDirectory=$HERE/collectors
ExecStart=$PY $HERE/collectors/run_all.py xapi
UNIT

log "wallctl wrapper → $BIN_DIR/wallctl"
rm -f "$BIN_DIR/wallctl"
cat > "$BIN_DIR/wallctl" <<WRAP
#!/usr/bin/env bash
exec "$PY" "$HERE/bin/wallctl" "\$@"
WRAP
chmod +x "$BIN_DIR/wallctl"
rm -f "$BIN_DIR/hermdbw"
cat > "$BIN_DIR/hermdbw" <<WRAP
#!/usr/bin/env bash
exec "$PY" "$HERE/bin/hermdbw" "\$@"
WRAP
chmod +x "$BIN_DIR/hermdbw"

log "retire old unit names, enable new ones"
for old in hermdbw-xme.timer hermdbw-xme.service rpi-dashboard-web.service rpi-dashboard-collect.timer rpi-dashboard-collect.service rpi-dashboard-ops.timer rpi-dashboard-ops.service; do
	systemctl --user disable --now "$old" >/dev/null 2>&1 || true
	rm -f "$UNIT_DIR/$old"
done
systemctl --user daemon-reload
systemctl --user enable --now hermdbw-web.service hermdbw-collect.timer hermdbw-ops.timer hermdbw-xapi.timer
systemctl --user start hermdbw-collect.service hermdbw-ops.service || true
loginctl enable-linger "$USER" >/dev/null 2>&1 || true

log "done"
echo "  dashboard: http://$(hostname -I 2>/dev/null | awk '{print $1}'):$PORT/   (open this port to your LAN if a firewall is on, e.g. ufw)"
echo "  edit:      $HERE/config.yaml   or   wallctl show"
echo "  Pi kiosk:  see ../pi/README.md"
