#!/usr/bin/env bash
# Join the Pi to your tailnet so the kiosk can reach the server from any network. Run ON THE PI (or:
#   ssh <user>@<pi> 'bash -s' < pi/tailscale-up.sh ). Uses Tailscale's official Debian repo.
set -euo pipefail
CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
sudo mkdir -p /usr/share/keyrings
curl -fsSL "https://pkgs.tailscale.com/stable/debian/${CODENAME}.noarmor.gpg" | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
curl -fsSL "https://pkgs.tailscale.com/stable/debian/${CODENAME}.tailscale-keyring.list" | sudo tee /etc/apt/sources.list.d/tailscale.list >/dev/null
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq tailscale
sudo systemctl enable --now tailscaled
echo "==> approve this device: a login link follows (open it on your phone)"
sudo tailscale up --hostname "$(hostname)" ${LOGIN_SERVER:+--login-server "$LOGIN_SERVER"}   # Headscale users: LOGIN_SERVER=https://your.headscale bash tailscale-up.sh
echo "==> joined as $(tailscale ip -4)"
echo "Now point the kiosk at the server's tailnet address, e.g.:  bash set-url.sh http://100.x.y.z:8470/"
