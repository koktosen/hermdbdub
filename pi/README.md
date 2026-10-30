# hermdbw wall — Raspberry Pi kiosk

One Raspberry Pi, one HDMI screen, no desktop: `cog` (WPE WebKit) runs full-screen on KMS and shows the server's page.
Tested on a 2014 Pi 2 Model B (1 GB, armv7); anything newer is easier. Index: [`../README.md`](../README.md) · Server: [`../server/README.md`](../server/README.md)

## 1. Flash
Raspberry Pi OS **Lite** (Trixie or later): 32-bit for Pi 1/2, 64-bit for Pi 3+. In Raspberry Pi Imager's settings set
the hostname, user, Wi-Fi and enable SSH. If you flash with `dd` instead, drop `cloud-init/user-data.example` and
`cloud-init/network-config.example` (edited) onto the boot partition as `user-data` / `network-config`.

Pi 1/2/3 have no EEPROM: the firmware lives on the SD card and `sudo apt full-upgrade` updates it. Pi 4/5 also have an
EEPROM bootloader (`rpi-eeprom-update`).

## 2. Bootstrap
```bash
scp bootstrap-pi.sh <user>@<pi>:~
ssh <user>@<pi> 'bash bootstrap-pi.sh http://<server-ip>:8470/ && sudo reboot'
```
Idempotent. Installs `cog`, `wpewebkit-driver`, `libgles2` (without it the renderer crash-loops), `seatd`, GStreamer
audio plugins (for the spoken brief over HDMI), `fbi`, `log2ram` (spares the SD card); sets the Wi-Fi regulatory
domain (`WIFI_COUNTRY=US` by default), `gpu_mem=128`, HDMI audio as the ALSA default, tty1 autologin, and a
`systemd --user` `kiosk.service` (with linger) that runs `~/.local/bin/kiosk.sh`. The launcher waits until the URL
answers before starting the browser, so a server reboot or a network move just delays the picture.

```bash
systemctl --user status kiosk        # on the Pi
journalctl --user -u kiosk -n 30     # (or: sudo journalctl _SYSTEMD_USER_UNIT=kiosk.service)
bash set-url.sh http://<other-host>:8470/   # point the kiosk elsewhere
```

## 3. Keys
Plug in any USB keyboard, numpad or macro pad — the page maps digits to pages, `0`/`Enter` to the brief, `+`/`-` to
next/previous (see the key table in the root README). Numpads work with NumLock on or off.

## No monitor attached?
Without a display there is no EDID, the DRM connector reads *disconnected*, `cog` can't start and HDMI audio can't
open. The bootstrap adds `video=HDMI-A-1:1920x1080@60D` to `/boot/firmware/cmdline.txt` so the output is forced on;
audio still needs a real sink, so test the spoken brief with the TV connected.

## Wall on another network
```bash
bash tailscale-up.sh                                        # Tailscale (official apt repo); prints a login link
LOGIN_SERVER=https://your.headscale.example bash tailscale-up.sh   # Headscale: then register the printed key on the Headscale host
bash set-url.sh http://<server-tailnet-ip>:8470/
```
If the server runs a firewall, allow the port from the tailnet interface (e.g. `sudo ufw allow in on tailscale0 to any port 8470 proto tcp`).

## Framebuffer fallback
If `cog` can't drive your board, the server can render each page to PNG with headless Chromium and the Pi can show it
with `fbi -T 1 -noverbose -a page.png` in a loop — no browser at all. Not wired up by default.
