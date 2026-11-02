#!/usr/bin/env bash
# Switch the TV on or off over HDMI-CEC:  tv-power.sh on|off|status
# Works on any TV that exposes a CEC physical address (its EDID carries a CEA extension block). A bare monitor or
# a TV without CEC has none; then this prints why and exits 0, so the night-mode timers never fail.
set -uo pipefail
dev=/dev/cec0
[[ -e $dev ]] || { echo "no CEC adapter ($dev)"; exit 0; }
# Claim the Playback logical address once; the kernel keeps it until the device is reconfigured.
if ! cec-ctl -d "$dev" 2>/dev/null | grep -q "Logical Address  *: [0-9]"; then
	cec-ctl -d "$dev" --playback -S >/dev/null 2>&1
fi
if cec-ctl -d "$dev" 2>/dev/null | grep -q "Physical Address *: f.f.f.f"; then
	echo "TV exposes no CEC physical address (no CEA block in its EDID): CEC control unavailable"; exit 0
fi
case "${1:-status}" in
	on)   cec-ctl -d "$dev" --to 0 --image-view-on >/dev/null 2>&1 && cec-ctl -d "$dev" --to 0 --active-source phys-addr="$(cec-ctl -d "$dev" 2>/dev/null | sed -nE 's/.*Physical Address *: ([0-9a-f.]+).*/\1/p' | head -1)" >/dev/null 2>&1; echo "tv: on" ;;
	off)  cec-ctl -d "$dev" --to 0 --standby >/dev/null 2>&1; echo "tv: standby" ;;
	*)    cec-ctl -d "$dev" --to 0 --give-device-power-status 2>/dev/null | sed -nE 's/.*pwr-state: ([a-z-]+).*/tv: \1/p' | head -1 ;;
esac
