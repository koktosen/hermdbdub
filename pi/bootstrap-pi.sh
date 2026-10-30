#!/usr/bin/env bash
# One-shot setup for a Raspberry Pi (tested: Pi 2B v1.1, Raspberry Pi OS Lite 32-bit Trixie) as an HDMI kiosk
# showing the hermdbw dashboard. Idempotent: safe to re-run. Run on the Pi as the login user with sudo rights:
#   bash bootstrap-pi.sh [DASHBOARD_URL]
set -euo pipefail

URL="${1:?usage: bootstrap-pi.sh http://<server>:8470/}"
USER_NAME="$(id -un)"
USER_HOME="$HOME"
WIFI_COUNTRY="${WIFI_COUNTRY:-US}"

log() { printf '\n==> %s\n' "$*"; }

log "apt: kiosk browser (cog/WPE), seatd, framebuffer fallback, log2ram"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cog wpewebkit-driver libgles2 seatd fbi log2ram fonts-noto-core fonts-noto-color-emoji \
  gstreamer1.0-alsa gstreamer1.0-plugins-good gstreamer1.0-libav   # libgles2: WPE renderer crash-loops without it; gstreamer: audio for the brief takeover

log "wifi: regulatory domain ${WIFI_COUNTRY} (unlocks wlan0 for the USB dongle)"
sudo raspi-config nonint do_wifi_country "$WIFI_COUNTRY" || true
sudo rfkill unblock wifi || true

log "audio: default ALSA device = HDMI (card 1)"
printf 'defaults.pcm.card 1\ndefaults.ctl.card 1\n' | sudo tee /etc/asound.conf >/dev/null

log "boot config: gpu_mem=128, no overscan, keep HDMI alive"
CFG=/boot/firmware/config.txt
grep -q '^gpu_mem=' "$CFG" || echo 'gpu_mem=128' | sudo tee -a "$CFG" >/dev/null
grep -q '^hdmi_blanking=' "$CFG" || echo 'hdmi_blanking=0' | sudo tee -a "$CFG" >/dev/null

log "console: disable blanking, autologin ${USER_NAME} on tty1"
sudo raspi-config nonint do_boot_behaviour B2 || true   # B2 = console autologin
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf >/dev/null <<UNIT
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin ${USER_NAME} --noclear %I \$TERM
UNIT

log "seatd: let the kiosk user open DRM/input without X"
sudo systemctl enable --now seatd
sudo usermod -aG video,input,render "$USER_NAME"

log "kiosk unit (systemd --user) running cog on KMS"
mkdir -p "$USER_HOME/.config/systemd/user" "$USER_HOME/.local/bin"
cat > "$USER_HOME/.local/bin/kiosk.sh" <<SH
#!/usr/bin/env bash
# Runs the WPE kiosk full-screen on the DRM backend. Restarted by systemd if it dies.
export COG_PLATFORM_DRM_CURSOR=0
export WPE_BACKEND_FDO_DRM_CURSOR=0
export LIBSEAT_BACKEND=seatd
URL_TO_LOAD="\${1:-${URL}}"
# Wait until the dashboard answers; otherwise WPE shows a dead error page and never retries.
until curl -fsS -m 5 "\$URL_TO_LOAD" >/dev/null 2>&1; do sleep 5; done
exec cog --platform=drm --enable-developer-extras=false "\$URL_TO_LOAD"
SH
chmod +x "$USER_HOME/.local/bin/kiosk.sh"
cat > "$USER_HOME/.config/systemd/user/kiosk.service" <<UNIT
[Unit]
Description=hermdbw HDMI kiosk (cog -> dashboard)
After=network-online.target
StartLimitIntervalSec=0

[Service]
ExecStart=${USER_HOME}/.local/bin/kiosk.sh ${URL}
Restart=always
RestartSec=5
Environment=XDG_RUNTIME_DIR=/run/user/%U

[Install]
WantedBy=default.target
UNIT
sudo loginctl enable-linger "$USER_NAME"
systemctl --user daemon-reload
systemctl --user enable kiosk.service

log "done. Reboot to start the kiosk:  sudo reboot"
echo "Dashboard URL: ${URL}"
echo "Fallback if cog shows nothing: see README.md 'framebuffer fallback' (fbi)."
