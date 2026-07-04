#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run with sudo: sudo ./uninstall.sh" >&2
  exit 1
fi

if [[ -x /opt/vm-proxy-gateway/vm_proxy_gateway.py ]]; then
  /opt/vm-proxy-gateway/vm_proxy_gateway.py uninstall || true
else
  systemctl disable --now vm-proxy-gateway.service 2>/dev/null || true
  rm -f /etc/systemd/system/vm-proxy-gateway.service
  systemctl daemon-reload || true
fi

rm -f /usr/local/bin/vm-proxy-gateway
rm -f /usr/local/bin/vm-proxy-gateway-gui
rm -f /usr/share/applications/vm-proxy-gateway.desktop
rm -f /usr/share/icons/hicolor/16x16/apps/vm-proxy-gateway.png
rm -f /usr/share/icons/hicolor/24x24/apps/vm-proxy-gateway.png
rm -f /usr/share/icons/hicolor/32x32/apps/vm-proxy-gateway.png
rm -f /usr/share/icons/hicolor/48x48/apps/vm-proxy-gateway.png
rm -f /usr/share/icons/hicolor/64x64/apps/vm-proxy-gateway.png
rm -f /usr/share/icons/hicolor/128x128/apps/vm-proxy-gateway.png
rm -f /usr/share/icons/hicolor/256x256/apps/vm-proxy-gateway.png
rm -f /usr/share/icons/hicolor/scalable/apps/vm-proxy-gateway.svg
rm -f /etc/sudoers.d/vm-proxy-gateway
gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
rm -rf /opt/vm-proxy-gateway
rm -rf /etc/vm-proxy-gateway

echo "VM Proxy Gateway application files removed."
echo "User config under ~/.config/vm-proxy-gateway is not removed."
echo "System config under /etc/vm-proxy-gateway was removed."
