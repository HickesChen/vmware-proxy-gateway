#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/vm-proxy-gateway"
BIN="/usr/local/bin/vm-proxy-gateway"
GUI_BIN="/usr/local/bin/vm-proxy-gateway-gui"
DESKTOP_FILE="/usr/share/applications/vm-proxy-gateway.desktop"
SING_BOX_BIN="/usr/local/bin/sing-box"
SING_BOX_MARKER="/etc/vm-proxy-gateway/sing-box.managed"
ICON_NAME="vm-proxy-gateway"
SUDOERS_FILE="/etc/sudoers.d/vm-proxy-gateway"
SKIP_DEPS="${VM_PROXY_GATEWAY_SKIP_DEPS:-0}"
SKIP_SING_BOX="${VM_PROXY_GATEWAY_SKIP_SING_BOX:-0}"
INSTALL_SUDOERS="${VM_PROXY_GATEWAY_INSTALL_SUDOERS:-1}"
OFFLINE_ONLY="${VM_PROXY_GATEWAY_OFFLINE_ONLY:-0}"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENDOR_DIR="${SOURCE_DIR}/vendor"

usage() {
  cat <<'EOF'
Usage: sudo ./install.sh [options]

Options:
  --skip-deps        Do not install OS/Python dependencies.
  --skip-sing-box    Use an already installed sing-box instead of the bundle.
  --no-sudoers       Do not install the optional NOPASSWD sudoers rule.
  --offline           Strict offline mode; fail instead of downloading missing platform resources.
  -h, --help         Show this help.

Environment variables:
  VM_PROXY_GATEWAY_SKIP_DEPS=1
  VM_PROXY_GATEWAY_SKIP_SING_BOX=1
  VM_PROXY_GATEWAY_INSTALL_SUDOERS=0
  VM_PROXY_GATEWAY_OFFLINE_ONLY=1
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-deps) SKIP_DEPS=1 ;;
    --skip-sing-box) SKIP_SING_BOX=1 ;;
    --no-sudoers) INSTALL_SUDOERS=0 ;;
    --offline) OFFLINE_ONLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run with sudo: sudo ./install.sh" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi

cd "${SOURCE_DIR}"

verify_offline_bundle() {
  local manifest="${VENDOR_DIR}/SHA256SUMS"
  if [[ -f "${manifest}" ]]; then
    echo "Verifying offline bundle checksums..."
    (cd "${VENDOR_DIR}" && sha256sum --check --strict SHA256SUMS)
  elif find "${VENDOR_DIR}" -type f ! -name README.md -print -quit 2>/dev/null | grep -q .; then
    echo "Offline files exist but ${manifest} is missing; refusing unverified installation." >&2
    exit 1
  fi
}

stop_running_service_before_network() {
  if systemctl list-unit-files vm-proxy-gateway.service >/dev/null 2>&1; then
    echo "Stopping existing VM Proxy Gateway service before network-dependent installation steps..."
    systemctl stop vm-proxy-gateway.service 2>/dev/null || true
  fi
}

install_packages() {
  if [[ "${SKIP_DEPS}" == "1" ]]; then
    echo "Skipping dependency installation."
    return
  fi

  local packages=(python3-tk python3-pil gir1.2-ayatanaappindicator3-0.1 curl ca-certificates unzip nftables)
  local missing=()
  local package
  for package in "${packages[@]}"; do
    dpkg-query -W -f='${db:Status-Status}' "${package}" 2>/dev/null | grep -qx installed || missing+=("${package}")
  done

  if [[ ${#missing[@]} -gt 0 ]] && command -v apt-get >/dev/null 2>&1; then
    local codename arch deb_dir
    codename="$(. /etc/os-release && printf '%s' "${VERSION_CODENAME:-unknown}")"
    arch="$(dpkg --print-architecture)"
    deb_dir="${VENDOR_DIR}/debs/${codename}/${arch}"
    if compgen -G "${deb_dir}/*.deb" >/dev/null; then
      echo "Installing OS dependencies from offline bundle ${deb_dir}..."
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-download "${deb_dir}"/*.deb
    elif [[ "${OFFLINE_ONLY}" == "1" ]]; then
      echo "Offline dependency bundle is missing for Ubuntu ${codename}/${arch}: ${deb_dir}" >&2
      echo "Obtain a release bundle for this platform or rerun without --offline." >&2
      exit 1
    else
      echo "No bundled OS dependencies match Ubuntu ${codename}/${arch}."
      echo "Downloading only missing application packages: ${missing[*]}"
      if ! DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}"; then
        echo "Package metadata may be stale; refreshing it once and retrying the same minimal package set..."
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}"
      fi
    fi
  elif [[ ${#missing[@]} -gt 0 ]]; then
    echo "Missing packages: ${missing[*]}; apt-get is unavailable." >&2
    exit 1
  else
    echo "All OS dependencies are already installed; no package network access is needed."
  fi

  missing=()
  for package in "${packages[@]}"; do
    dpkg-query -W -f='${db:Status-Status}' "${package}" 2>/dev/null | grep -qx installed || missing+=("${package}")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Required Ubuntu Desktop baseline packages are missing: ${missing[*]}" >&2
    echo "The offline bundle intentionally does not duplicate operating-system components." >&2
    echo "Install/repair Ubuntu Desktop Minimal first, or prepare a custom bundle for this system." >&2
    exit 1
  fi

}

install_bundled_python_runtime() {
  local runtime_dir="${APP_DIR}/vendor-python"
  local wheels=("${VENDOR_DIR}"/python/*.whl)
  if [[ ! -e "${wheels[0]}" ]]; then
    echo "Bundled Python runtime is missing from ${VENDOR_DIR}/python." >&2
    echo "The target system will not use pip; rebuild the release bundle first." >&2
    exit 1
  fi
  mkdir -p "${runtime_dir}"
  python3 - "${runtime_dir}" "${wheels[@]}" <<'PY'
import sys
import zipfile
from pathlib import Path

target = Path(sys.argv[1]).resolve()
for wheel_name in sys.argv[2:]:
    with zipfile.ZipFile(wheel_name) as wheel:
        for member in wheel.infolist():
            destination = (target / member.filename).resolve()
            if target not in destination.parents and destination != target:
                raise SystemExit(f"unsafe wheel path: {member.filename}")
        wheel.extractall(target)
PY
}

install_sing_box() {
  if [[ "${SKIP_SING_BOX}" == "1" ]]; then
    echo "Skipping sing-box installation."
    rm -f "${SING_BOX_MARKER}"
    return
  fi

  local arch
  arch="$(uname -m)"
  case "${arch}" in
    x86_64|amd64) arch="amd64" ;;
    aarch64|arm64) arch="arm64" ;;
    *) echo "Unsupported CPU architecture for automatic sing-box install: ${arch}" >&2; exit 1 ;;
  esac

  local version bundled tmp url
  version="1.10.7"
  bundled="${VENDOR_DIR}/sing-box/${version}/linux-${arch}/sing-box"
  if [[ -x "${bundled}" ]]; then
    echo "Installing bundled sing-box ${version} for linux-${arch}..."
    install -m 0755 "${bundled}" "${SING_BOX_BIN}"
    mkdir -p "$(dirname "${SING_BOX_MARKER}")"
    touch "${SING_BOX_MARKER}"
    return
  fi
  if [[ -x "${SING_BOX_BIN}" ]]; then
    rm -f "${SING_BOX_MARKER}"
    return
  fi
  if command -v sing-box >/dev/null 2>&1; then
    local existing
    existing="$(command -v sing-box)"
    echo "Using existing sing-box from ${existing}."
    install -m 0755 "${existing}" "${SING_BOX_BIN}"
    rm -f "${SING_BOX_MARKER}"
    return
  fi
  if [[ "${OFFLINE_ONLY}" == "1" ]]; then
    echo "Bundled sing-box is missing: ${bundled}" >&2
    echo "Obtain a release bundle for linux-${arch} or rerun without --offline." >&2
    exit 1
  fi
  tmp="$(mktemp -d)"
  trap 'rm -rf "${tmp}"' RETURN
  url="https://github.com/SagerNet/sing-box/releases/download/v${version}/sing-box-${version}-linux-${arch}.tar.gz"
  echo "No bundled sing-box matches linux-${arch}; downloading only sing-box ${version}..."
  curl -fL "${url}" -o "${tmp}/sing-box.tar.gz"
  tar -xzf "${tmp}/sing-box.tar.gz" -C "${tmp}"
  install -m 0755 "${tmp}/sing-box-${version}-linux-${arch}/sing-box" "${SING_BOX_BIN}"
  mkdir -p "$(dirname "${SING_BOX_MARKER}")"
  touch "${SING_BOX_MARKER}"
  trap - RETURN
  rm -rf "${tmp}"
}

verify_sing_box() {
  if [[ ! -x "${SING_BOX_BIN}" ]]; then
    echo "sing-box was not installed at ${SING_BOX_BIN}." >&2
    echo "Restore the bundled sing-box or provide it before using --skip-sing-box." >&2
    exit 1
  fi
  "${SING_BOX_BIN}" version >/dev/null
}

cleanup_old_install() {
  echo "Cleaning old VM Proxy Gateway installation..."
  systemctl disable --now vm-proxy-gateway.service 2>/dev/null || true
  rm -f /etc/systemd/system/vm-proxy-gateway.service
  systemctl daemon-reload 2>/dev/null || true

  rm -f "${BIN}"
  rm -f "${GUI_BIN}"
  rm -f "${DESKTOP_FILE}"
  rm -rf "${APP_DIR}"
  rm -f "/usr/share/icons/hicolor/16x16/apps/${ICON_NAME}.png"
  rm -f "/usr/share/icons/hicolor/24x24/apps/${ICON_NAME}.png"
  rm -f "/usr/share/icons/hicolor/32x32/apps/${ICON_NAME}.png"
  rm -f "/usr/share/icons/hicolor/48x48/apps/${ICON_NAME}.png"
  rm -f "/usr/share/icons/hicolor/64x64/apps/${ICON_NAME}.png"
  rm -f "/usr/share/icons/hicolor/128x128/apps/${ICON_NAME}.png"
  rm -f "/usr/share/icons/hicolor/256x256/apps/${ICON_NAME}.png"
  rm -f "/usr/share/icons/hicolor/scalable/apps/${ICON_NAME}.svg"
  rm -f "${SUDOERS_FILE}"

  mkdir -p /etc/vm-proxy-gateway
  rm -f /etc/vm-proxy-gateway/sing-box.json
}

install_files() {
  mkdir -p "${APP_DIR}"
  install -m 0755 "app/vm_proxy_gateway.py" "${APP_DIR}/vm_proxy_gateway.py"
  install -m 0755 "app/vm_proxy_gateway_gui.py" "${APP_DIR}/vm_proxy_gateway_gui.py"
  install -m 0644 "README.md" "${APP_DIR}/README.md"
  install -m 0644 "README.zh-CN.md" "${APP_DIR}/README.zh-CN.md"
  install -m 0644 "LICENSE" "${APP_DIR}/LICENSE"
  install -m 0644 "SECURITY.md" "${APP_DIR}/SECURITY.md"
  install -m 0644 "SECURITY.zh-CN.md" "${APP_DIR}/SECURITY.zh-CN.md"
  install_bundled_python_runtime
  mkdir -p "${APP_DIR}/assets"
  install -m 0644 "assets/${ICON_NAME}.png" "${APP_DIR}/assets/${ICON_NAME}.png"
  install -m 0644 "assets/${ICON_NAME}.svg" "${APP_DIR}/assets/${ICON_NAME}.svg"

  for size in 16 24 32 48 64 128; do
    mkdir -p "/usr/share/icons/hicolor/${size}x${size}/apps"
    install -m 0644 "assets/${ICON_NAME}-${size}.png" "/usr/share/icons/hicolor/${size}x${size}/apps/${ICON_NAME}.png"
  done
  mkdir -p "/usr/share/icons/hicolor/256x256/apps" "/usr/share/icons/hicolor/scalable/apps"
  install -m 0644 "assets/${ICON_NAME}.png" "/usr/share/icons/hicolor/256x256/apps/${ICON_NAME}.png"
  install -m 0644 "assets/${ICON_NAME}.svg" "/usr/share/icons/hicolor/scalable/apps/${ICON_NAME}.svg"

  ln -sf "${APP_DIR}/vm_proxy_gateway.py" "${BIN}"
  ln -sf "${APP_DIR}/vm_proxy_gateway_gui.py" "${GUI_BIN}"

  cat > "${DESKTOP_FILE}" <<'EOF'
[Desktop Entry]
Type=Application
Name=VM Proxy Gateway
Comment=Transparent proxy controller for Ubuntu virtual machines
Exec=/usr/local/bin/vm-proxy-gateway-gui
Icon=vm-proxy-gateway
Terminal=false
Categories=Network;Settings;
StartupWMClass=VmProxyGateway
EOF

  gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
}

install_sudoers() {
  if [[ "${INSTALL_SUDOERS}" != "1" ]]; then
    echo "Skipping sudoers rule installation."
    return
  fi

  cat > "${SUDOERS_FILE}" <<'EOF'
# Allow local sudo users to control only VM Proxy Gateway without repeated prompts.
%sudo ALL=(root) NOPASSWD: /usr/bin/python3 /opt/vm-proxy-gateway/vm_proxy_gateway.py apply --config /home/*/.config/vm-proxy-gateway/config.json
%sudo ALL=(root) NOPASSWD: /usr/bin/python3 /opt/vm-proxy-gateway/vm_proxy_gateway.py apply-start --config /home/*/.config/vm-proxy-gateway/config.json
%sudo ALL=(root) NOPASSWD: /usr/bin/python3 /opt/vm-proxy-gateway/vm_proxy_gateway.py start
%sudo ALL=(root) NOPASSWD: /usr/bin/python3 /opt/vm-proxy-gateway/vm_proxy_gateway.py stop
%sudo ALL=(root) NOPASSWD: /usr/bin/python3 /opt/vm-proxy-gateway/vm_proxy_gateway.py restart
%sudo ALL=(root) NOPASSWD: /usr/bin/python3 /opt/vm-proxy-gateway/vm_proxy_gateway.py traffic-stats
%sudo ALL=(root) NOPASSWD: /usr/bin/python3 /opt/vm-proxy-gateway/vm_proxy_gateway.py diagnose --config /home/*/.config/vm-proxy-gateway/config.json --repair
%sudo ALL=(root) NOPASSWD: /usr/bin/python3 /opt/vm-proxy-gateway/vm_proxy_gateway.py uninstall
EOF
  chmod 0440 "${SUDOERS_FILE}"
  if command -v visudo >/dev/null 2>&1; then
    visudo -cf "${SUDOERS_FILE}" >/dev/null
  fi
}

stop_running_service_before_network
verify_offline_bundle
install_packages
install_sing_box
verify_sing_box
cleanup_old_install
install_files
install_sudoers

echo
echo "Installed VM Proxy Gateway."
echo "Launch it from the app menu, or run: vm-proxy-gateway-gui"
echo "CLI status: vm-proxy-gateway status"
