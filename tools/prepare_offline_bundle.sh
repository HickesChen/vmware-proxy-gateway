#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="${ROOT}/vendor"
SING_BOX_VERSION="1.10.7"
PACKAGES=(python3-tk python3-pil gir1.2-ayatanaappindicator3-0.1 curl ca-certificates unzip nftables)
BASE_SYSTEM_PACKAGES=(ubuntu-desktop-minimal bash coreutils dpkg apt python3 systemd iproute2 tar gzip sed grep findutils util-linux)
REFRESH=0

if [[ "${1:-}" == "--refresh" ]]; then
  REFRESH=1
elif [[ $# -gt 0 ]]; then
  echo "Usage: tools/prepare_offline_bundle.sh [--refresh]" >&2
  exit 2
fi

command -v apt-get >/dev/null || { echo "This bundle builder requires Ubuntu/Debian apt tools." >&2; exit 1; }
command -v curl >/dev/null || { echo "curl is required." >&2; exit 1; }

codename="$(. /etc/os-release && printf '%s' "${VERSION_CODENAME:-unknown}")"
arch="$(dpkg --print-architecture)"
deb_dir="${VENDOR}/debs/${codename}/${arch}"
wheel_dir="${VENDOR}/python"
sing_dir="${VENDOR}/sing-box/${SING_BOX_VERSION}/linux-${arch}"
mkdir -p "${deb_dir}" "${wheel_dir}" "${sing_dir}"
find "${deb_dir}" -maxdepth 1 -type f -name '*.deb' -delete

if [[ "${REFRESH}" == "1" ]]; then
  echo "Refreshing package metadata for ${codename}/${arch}..."
  sudo apt-get update
else
  echo "Using existing APT metadata for ${codename}/${arch}; pass --refresh to update it first."
fi
mapfile -t dependency_packages < <(
  apt-cache depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances "${PACKAGES[@]}" \
    | sed -n '/^[^[:space:]<]/p' | sort -u
)
mapfile -t base_packages < <(
  apt-cache depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances "${BASE_SYSTEM_PACKAGES[@]}" \
    | sed -n '/^[^[:space:]<]/p' | sort -u
)
mapfile -t all_packages < <(comm -23 <(printf '%s\n' "${PACKAGES[@]}" "${dependency_packages[@]}" | sort -u) <(printf '%s\n' "${base_packages[@]}" | sort -u))
echo "Downloading ${#all_packages[@]} OS packages..."
(cd "${deb_dir}" && apt-get download "${all_packages[@]}")

required_wheels=(
  "${wheel_dir}/pystray-0.19.5-py2.py3-none-any.whl"
  "${wheel_dir}/python_xlib-0.33-py2.py3-none-any.whl"
  "${wheel_dir}/six-1.17.0-py2.py3-none-any.whl"
)
for wheel in "${required_wheels[@]}"; do
  if [[ ! -f "${wheel}" ]]; then
    echo "Required committed Python runtime file is missing: ${wheel}" >&2
    echo "Restore it from version control before preparing a release bundle." >&2
    exit 1
  fi
done
echo "Using committed Python runtime wheels; no PyPI access is needed."

case "${arch}" in
  amd64|arm64) ;;
  *) echo "Unsupported sing-box architecture: ${arch}" >&2; exit 1 ;;
esac
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
archive="${tmp}/sing-box.tar.gz"
url="https://github.com/SagerNet/sing-box/releases/download/v${SING_BOX_VERSION}/sing-box-${SING_BOX_VERSION}-linux-${arch}.tar.gz"
echo "Downloading sing-box ${SING_BOX_VERSION}..."
curl -fL "${url}" -o "${archive}"
tar -xzf "${archive}" -C "${tmp}"
install -m 0755 "${tmp}/sing-box-${SING_BOX_VERSION}-linux-${arch}/sing-box" "${sing_dir}/sing-box"

(cd "${VENDOR}" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
echo "Offline bundle prepared in ${VENDOR}."
echo "Commit that directory or include it in the release archive, then install with: sudo ./install.sh --offline"
