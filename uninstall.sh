#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run with sudo: sudo ./uninstall.sh" >&2
  exit 1
fi

if [[ -x /opt/vm-proxy-gateway/vm_proxy_gateway.py ]]; then
  /opt/vm-proxy-gateway/vm_proxy_gateway.py uninstall || true
fi

if [[ -f /etc/vm-proxy-gateway/sing-box.managed ]]; then
  rm -f /usr/local/bin/sing-box
fi

# Always repeat cleanup independently. This also handles upgrades where the
# installed controller is older, incomplete, or failed partway through.
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

# Complete uninstall removes user settings, autostart, and runtime locks.
while IFS=: read -r _ _ uid _ _ home _; do
  if [[ "${uid}" -ge 1000 && -d "${home}" ]]; then
    rm -f "${home}/.config/autostart/vm-proxy-gateway.desktop"
    rm -rf "${home}/.config/vm-proxy-gateway"
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

residual=0
for path in \
  /opt/vm-proxy-gateway \
  /etc/vm-proxy-gateway \
  /etc/systemd/system/vm-proxy-gateway.service \
  /etc/sudoers.d/vm-proxy-gateway \
  /usr/local/bin/vm-proxy-gateway \
  /usr/local/bin/vm-proxy-gateway-gui \
  /usr/share/applications/vm-proxy-gateway.desktop; do
  if [[ -e "${path}" || -L "${path}" ]]; then
    echo "Uninstall residue remains: ${path}" >&2
    residual=1
  fi
done
if systemctl is-active --quiet vm-proxy-gateway.service; then
  echo "Uninstall residue remains: vm-proxy-gateway.service is active" >&2
  residual=1
fi
if ip link show vmproxy0 >/dev/null 2>&1; then
  echo "Uninstall residue remains: network interface vmproxy0" >&2
  residual=1
fi
while IFS=: read -r _ _ uid _ _ home _; do
  if [[ "${uid}" -ge 1000 ]]; then
    if [[ -e "${home}/.config/autostart/vm-proxy-gateway.desktop" || -e "${home}/.config/vm-proxy-gateway" ]]; then
      echo "Uninstall residue remains in ${home}/.config" >&2
      residual=1
    fi
    if [[ -f "${home}/.profile" ]] && grep -q '^# BEGIN VM-PROXY-GATEWAY MANAGED BLOCK$' "${home}/.profile"; then
      echo "Uninstall residue remains in ${home}/.profile" >&2
      residual=1
    fi
  fi
done < /etc/passwd
if [[ "${residual}" != "0" ]]; then
  echo "VM Proxy Gateway uninstall did not complete cleanly." >&2
  exit 1
fi

echo "VM Proxy Gateway was completely removed; no managed user or system configuration was kept."
