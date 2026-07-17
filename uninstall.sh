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
  resolvectl revert vmproxy0 2>/dev/null || true
  ip link delete vmproxy0 2>/dev/null || true
  nft delete table inet vm_proxy_gateway_stats 2>/dev/null || true
  rm -f /etc/systemd/system/vm-proxy-gateway.service
  systemctl daemon-reload || true
  while IFS=: read -r _ _ uid _ _ home _; do
    if [[ "${uid}" -ge 1000 && -f "${home}/.profile" ]]; then
      sed -i '/^# BEGIN VM-PROXY-GATEWAY MANAGED BLOCK$/,/^# END VM-PROXY-GATEWAY MANAGED BLOCK$/d' "${home}/.profile"
    fi
  done < /etc/passwd
fi

# User settings are deliberately preserved, but autostart and runtime lock
# files must not keep affecting login after the application is removed.
while IFS=: read -r _ _ uid _ _ home _; do
  if [[ "${uid}" -ge 1000 && -d "${home}" ]]; then
    rm -f "${home}/.config/autostart/vm-proxy-gateway.desktop"
    rm -f "${home}/.config/vm-proxy-gateway/gui.lock"
  fi
done < /etc/passwd

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
