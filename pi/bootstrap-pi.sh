#!/usr/bin/env bash
# One-shot setup for a Raspberry Pi (tested: Pi 2B v1.1, Raspberry Pi OS Lite 32-bit Trixie) as an HDMI kiosk
# showing the hermdbw dashboard. Idempotent: safe to re-run. Run on the Pi as the login user with sudo rights:
#   bash bootstrap-pi.sh [DASHBOARD_URL]
set -euo pipefail

URL="${1:?usage: bootstrap-pi.sh http://<server>:8470/}"
USER_NAME="$(id -un)"
USER_HOME="$HOME"
WIFI_COUNTRY="${WIFI_COUNTRY:-US}"
REBOOT_TIME="${REBOOT_TIME:-04:30}"   # unattended-upgrades may reboot the kiosk at this local time when required

log() { printf '\n==> %s\n' "$*"; }

log "apt: kiosk browser (cog/WPE), seatd, framebuffer fallback, log2ram"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cog wpewebkit-driver libgles2 seatd fbi log2ram fonts-noto-core fonts-noto-color-emoji \
  gstreamer1.0-alsa gstreamer1.0-plugins-good gstreamer1.0-libav   # libgles2: WPE renderer crash-loops without it; gstreamer: audio for the brief takeover

log "unattended security updates (daily; reboots at ${REBOOT_TIME:-04:30} only when an update requires it)"
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unattended-upgrades apt-listchanges >/dev/null
sudo tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
APT
sudo tee /etc/apt/apt.conf.d/52hermdbw-unattended >/dev/null <<APT
// hermdbw kiosk: take security + stable updates from Debian, Raspberry Pi and Tailscale; reboot off-hours if needed.
Unattended-Upgrade::Origins-Pattern {
    "origin=Debian,codename=\${distro_codename},label=Debian-Security";
    "origin=Debian,codename=\${distro_codename}-security,label=Debian-Security";
    "origin=Debian,codename=\${distro_codename},label=Debian";
    "origin=Debian,codename=\${distro_codename}-updates";
    "origin=Raspberry Pi Foundation,codename=\${distro_codename}";
    "origin=Raspbian,codename=\${distro_codename}";
    "origin=Tailscale";
};
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Remove-New-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-WithUsers "true";
Unattended-Upgrade::Automatic-Reboot-Time "${REBOOT_TIME:-04:30}";
Unattended-Upgrade::SyslogEnable "true";
APT
sudo systemctl enable --now apt-daily.timer apt-daily-upgrade.timer >/dev/null

log "wifi: regulatory domain ${WIFI_COUNTRY} (unlocks wlan0 for the USB dongle)"
sudo raspi-config nonint do_wifi_country "$WIFI_COUNTRY" || true
sudo rfkill unblock wifi || true

# Default ALSA device. AUDIO_CARD=1 is HDMI; most small TVs expose no HDMI audio sink at all (128-byte EDID,
# no ELD), in which case the 3.5 mm jack (card 0) with a powered speaker is the only thing that will play.
AUDIO_CARD="${AUDIO_CARD:-0}"
log "audio: default ALSA device = card ${AUDIO_CARD} (0 = 3.5 mm jack, 1 = HDMI)"
printf 'defaults.pcm.card %s\ndefaults.ctl.card %s\n' "$AUDIO_CARD" "$AUDIO_CARD" | sudo tee /etc/asound.conf >/dev/null

log "boot config: gpu_mem=16 (full KMS renders on the ARM side; the firmware needs almost nothing), no overscan"
CFG=/boot/firmware/config.txt
if grep -q '^gpu_mem=' "$CFG"; then sudo sed -i 's/^gpu_mem=.*/gpu_mem=16/' "$CFG"; else echo 'gpu_mem=16' | sudo tee -a "$CFG" >/dev/null; fi
sudo sed -i '/^hdmi_blanking=/d' "$CFG"      # legacy firmware knob, no effect under vc4-kms

# Force the HDMI output on at the TV's real mode even when the TV is off at boot (no EDID -> no connector otherwise).
# HDMI_MODE must be one the TV lists in /sys/class/drm/card0-HDMI-A-1/modes; a mode it lacks is ignored by the kernel.
HDMI_MODE="${HDMI_MODE:-1600x900}"
log "cmdline: video=HDMI-A-1:${HDMI_MODE}@60D"
CMD=/boot/firmware/cmdline.txt
if grep -q 'video=HDMI-A-1:' "$CMD"; then sudo sed -i -E "s/video=HDMI-A-1:[^ ]*/video=HDMI-A-1:${HDMI_MODE}@60D/" "$CMD"
else sudo sed -i -E "s/\s*$/ video=HDMI-A-1:${HDMI_MODE}@60D/" "$CMD"; fi

log "console: no autologin (a root-capable shell must not sit behind the kiosk; the numpad's keys reach tty1 too)"
sudo raspi-config nonint do_boot_behaviour B1 || true   # B1 = console, login required
sudo rm -f /etc/systemd/system/getty@tty1.service.d/autologin.conf

log "journal: persistent and capped, so yesterday's kiosk crash is still readable"
sudo mkdir -p /var/log/journal
sudo sed -i 's/^#\?Storage=.*/Storage=persistent/; s/^#\?SystemMaxUse=.*/SystemMaxUse=32M/' /etc/systemd/journald.conf

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
StartLimitIntervalSec=0

[Service]
ExecStart=${USER_HOME}/.local/bin/kiosk.sh ${URL}
Restart=always
RestartSec=5
MemoryMax=600M
Environment=XDG_RUNTIME_DIR=/run/user/%U

[Install]
WantedBy=default.target
UNIT
# WPE's web process grows over days (450 MB seen after three); a nightly restart bounds it and also picks up
# the WebKit packages unattended-upgrades installed overnight.
cat > "$USER_HOME/.config/systemd/user/kiosk-restart.service" <<UNIT
[Unit]
Description=restart the kiosk browser (bounds WPE memory growth; picks up overnight WebKit upgrades)

[Service]
Type=oneshot
ExecStart=/usr/bin/systemctl --user restart kiosk.service
UNIT
cat > "$USER_HOME/.config/systemd/user/kiosk-restart.timer" <<UNIT
[Unit]
Description=nightly kiosk restart

[Timer]
OnCalendar=*-*-* 04:35:00
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
UNIT
sudo loginctl enable-linger "$USER_NAME"
systemctl --user daemon-reload
systemctl --user enable kiosk.service kiosk-restart.timer

log "done. Reboot to start the kiosk:  sudo reboot"
echo "Dashboard URL: ${URL}"
echo "Fallback if cog shows nothing: see README.md 'framebuffer fallback' (fbi)."
