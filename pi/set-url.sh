#!/usr/bin/env bash
# Point the kiosk at a different dashboard URL (e.g. after moving the Pi to another network and reaching the
# server over Tailscale). Run ON THE PI:  bash set-url.sh http://100.x.y.z:8470/
set -euo pipefail
URL="${1:?usage: set-url.sh http://host:8470/}"
UNIT="$HOME/.config/systemd/user/kiosk.service"
sed -i -E "s|^ExecStart=(.*/kiosk.sh) .*$|ExecStart=\1 ${URL}|" "$UNIT"
sed -i -E "s|^URL_TO_LOAD=.*$|URL_TO_LOAD=\"\${1:-${URL}}\"|" "$HOME/.local/bin/kiosk.sh"
systemctl --user daemon-reload
systemctl --user restart kiosk
echo "kiosk now loads: $URL"
