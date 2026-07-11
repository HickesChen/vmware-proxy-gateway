#!/usr/bin/env python3
"""
vm-proxy-gateway

Ubuntu VM transparent proxy controller for a Windows-hosted proxy.
The GUI writes user preferences; this controller turns them into a
sing-box TUN configuration and a systemd service.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import pwd
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


APP_NAME = "vm-proxy-gateway"
SYSTEM_DIR = Path("/etc/vm-proxy-gateway")
SYSTEM_CONFIG = SYSTEM_DIR / "config.json"
SING_BOX_CONFIG = SYSTEM_DIR / "sing-box.json"
SYSTEMD_UNIT = Path("/etc/systemd/system/vm-proxy-gateway.service")
TUN_INTERFACE = "vmproxy0"
APT_DIR = Path("/etc/apt")
SING_BOX_BIN = "/usr/local/bin/sing-box"
DEFAULT_PORT = 10086
DEFAULT_BYPASS_CIDRS = [
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "224.0.0.0/4",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
]
DEFAULT_BYPASS_DOMAINS = [
    "localhost",
    ".local",
    ".lan",
    ".home",
]
DEFAULT_DNS_STRATEGY = "ipv4_only"
PRESET_BYPASS_DOMAINS = {
    "bypass_system_packages": [
        ".ubuntu.com",
        ".canonical.com",
        ".launchpad.net",
        ".debian.org",
        ".debian.net",
        ".snapcraft.io",
        ".snapcraftcontent.com",
        ".flathub.org",
        ".flatpak.org",
        ".aliyun.com",
        ".tuna.tsinghua.edu.cn",
        ".ustc.edu.cn",
        ".huaweicloud.com",
        ".cloud.tencent.com",
        ".nju.edu.cn",
        ".sjtu.edu.cn",
        ".163.com",
    ],
    "bypass_container_registries": [
        ".docker.io",
        ".docker.com",
        ".gcr.io",
        ".pkg.dev",
        ".quay.io",
        ".ghcr.io",
        ".k8s.io",
    ],
}
PRESET_BYPASS_DEFAULTS = {
    "bypass_system_packages": True,
    "bypass_container_registries": False,
}
SYSTEM_PACKAGE_PROCESSES = [
    "apt",
    "apt-get",
    "apt-helper",
    "apt-config",
    "http",
    "https",
    "dpkg",
    "unattended-upgr",
    "snap",
    "snapd",
    "flatpak",
]
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;:]*m")
TRAFFIC_LOG_RE = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?"
    r"\[(?P<connection_id>\d+) [^]]+\] outbound/(?P<outbound_type>[^[]+)"
    r"\[(?P<route>[^]]+)\]: outbound (?P<packet>packet )?connection to (?P<destination>.+)$"
)


class GatewayError(RuntimeError):
    pass


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def require_root() -> None:
    if not is_root():
        raise GatewayError("This command must run as root. Use sudo or pkexec.")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def get_default_gateway() -> str | None:
    try:
        result = run(["ip", "-4", "route", "show", "default"], check=False)
    except FileNotFoundError:
        return None
    for line in result.stdout.splitlines():
        parts = line.split()
        if "via" in parts:
            return parts[parts.index("via") + 1]
    return None


def get_system_dns_server(resolv_conf: Path = Path("/etc/resolv.conf"), runner=run) -> str:
    try:
        result = runner(["resolvectl", "dns"], check=False)
        for line in result.stdout.splitlines():
            parts = line.replace(":", " ").split()
            for part in parts[1:]:
                try:
                    ipaddress.ip_address(part)
                except ValueError:
                    continue
                if not part.startswith("127.") and part != "::1":
                    return part
    except FileNotFoundError:
        pass

    if resolv_conf.exists():
        for line in resolv_conf.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "nameserver":
                server = parts[1]
                try:
                    ipaddress.ip_address(server)
                except ValueError:
                    continue
                if not server.startswith("127.") and server != "::1":
                    return server

    return get_default_gateway() or "1.1.1.1"


def domain_suffix(host: str) -> str | None:
    host = host.strip().lower().strip("[]")
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    if host in {"localhost", "localhost.localdomain"}:
        return None
    return "." + host


def normalize_bypass_domain(value: str) -> str | None:
    value = value.strip().lower().rstrip(".")
    if not value:
        return None
    if "://" in value:
        host = host_from_url(value)
        value = host or ""
    if not value or value.startswith("#"):
        return None
    if value.startswith("*."):
        value = "." + value[2:]
    if value.startswith("."):
        suffix = domain_suffix(value[1:])
        return suffix if suffix else None
    suffix = domain_suffix(value)
    return suffix[1:] if suffix else value


def host_from_url(value: str) -> str | None:
    value = value.strip()
    if not value or value.startswith("#"):
        return None
    parsed = urlparse(value if "://" in value else "http://" + value)
    return parsed.hostname


def ip_cidr_for_host(host: str) -> str | None:
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None
    return f"{ip}/{ip.max_prefixlen}"


def normalize_bypass_cidr(value: str) -> str:
    value = value.strip()
    if "*" not in value:
        return str(ipaddress.ip_network(value, strict=False))

    if value == "*":
        return "0.0.0.0/0"
    parts = value.split(".")
    if len(parts) != 4:
        raise ValueError("IPv4 wildcard patterns must contain four octets, for example 192.168.*.*")

    first_wildcard = next((index for index, part in enumerate(parts) if part == "*"), None)
    if first_wildcard is None or any(part != "*" for part in parts[first_wildcard:]):
        raise ValueError("wildcards must be trailing complete octets, for example 192.168.1.*")
    octets: list[int] = []
    for part in parts[:first_wildcard]:
        if not part.isdigit() or not 0 <= int(part) <= 255:
            raise ValueError(f"invalid IPv4 octet '{part}'")
        octets.append(int(part))
    octets.extend([0] * (4 - len(octets)))
    prefix = first_wildcard * 8
    return str(ipaddress.ip_network(f"{'.'.join(str(part) for part in octets)}/{prefix}", strict=False))


BYPASS_RULE_TYPES = {
    "ip_cidr",
    "domain",
    "domain_prefix",
    "domain_suffix",
    "domain_keyword",
    "domain_regex",
}


def normalize_bypass_rule(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("rule must be an object")
    rule_type = str(raw.get("type") or "").strip().lower()
    value = str(raw.get("value") or "").strip()
    if rule_type not in BYPASS_RULE_TYPES:
        raise ValueError(f"unsupported rule type '{rule_type}'")
    if not value:
        raise ValueError("rule value cannot be empty")

    if rule_type == "ip_cidr":
        value = normalize_bypass_cidr(value)
    elif rule_type in {"domain", "domain_suffix"}:
        domain = normalize_bypass_domain(value)
        if not domain:
            raise ValueError("invalid domain")
        value = domain.lstrip(".")
    elif rule_type in {"domain_prefix", "domain_keyword"}:
        value = value.lower().rstrip(".")
    else:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid regular expression: {exc}") from exc
    if not value:
        raise ValueError("rule value cannot be empty")

    return {"type": rule_type, "value": value, "invert": bool(raw.get("invert", False))}


def sing_box_match_rule(rule: dict[str, Any]) -> dict[str, Any]:
    rule_type = str(rule["type"])
    value = str(rule["value"])
    if rule_type == "domain_prefix":
        match = {"domain_regex": ["^" + re.escape(value)]}
    else:
        match = {rule_type: [value]}
    if rule.get("invert"):
        match["invert"] = True
    return match


def get_apt_source_domains(apt_dir: Path = APT_DIR) -> list[str]:
    files: list[Path] = []
    for path in [apt_dir / "sources.list"]:
        if path.exists():
            files.append(path)
    sources_dir = apt_dir / "sources.list.d"
    if sources_dir.exists():
        files.extend(sorted(sources_dir.glob("*.list")))
        files.extend(sorted(sources_dir.glob("*.sources")))

    domains: set[str] = set()
    for path in files:
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("uris:"):
                candidates = line.split(":", 1)[1].split()
            elif line.startswith(("deb ", "deb-src ")):
                parts = line.split()
                candidates = []
                for part in parts[1:]:
                    if part.startswith("[") or part.endswith("]"):
                        continue
                    candidates = [part]
                    break
            else:
                continue
            for candidate in candidates:
                host = host_from_url(candidate)
                suffix = domain_suffix(host or "")
                if suffix:
                    domains.add(suffix)
    return sorted(domains)


def default_user_config_path() -> Path | None:
    for name in [os.environ.get("SUDO_USER"), os.environ.get("USER"), os.environ.get("LOGNAME")]:
        if not name or name == "root":
            continue
        try:
            home = Path(pwd.getpwnam(name).pw_dir)
        except KeyError:
            continue
        path = home / ".config" / APP_NAME / "config.json"
        if path.exists():
            return path
    return None


def get_local_ipv4_cidrs() -> list[str]:
    try:
        result = run(["ip", "-4", "-o", "addr", "show", "scope", "global"], check=False)
    except FileNotFoundError:
        return []
    cidrs: list[str] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if "inet" not in parts:
            continue
        value = parts[parts.index("inet") + 1]
        try:
            iface = ipaddress.ip_interface(value)
        except ValueError:
            continue
        cidrs.append(str(iface.network))
        cidrs.append(str(iface.ip) + "/32")
    return sorted(set(cidrs))


def tcp_connect(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "ok"
    except OSError as exc:
        return False, str(exc)


def detect_proxy_protocol(host: str, port: int) -> str:
    ok, err = tcp_connect(host, port)
    if not ok:
        raise GatewayError(f"Proxy {host}:{port} is not reachable: {err}")

    proxy_url = f"socks5h://{host}:{port}"
    # urllib cannot speak SOCKS; protocol probing is intentionally conservative.
    # mixed-port proxies such as Clash/mihomo accept SOCKS5, so prefer it.
    return "socks5"


def normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    host = str(raw.get("proxy_host") or "").strip()
    if not host:
        host = get_default_gateway() or ""
    if not host:
        raise GatewayError("Proxy host is empty and default gateway could not be detected.")

    try:
        port = int(raw.get("proxy_port") or DEFAULT_PORT)
    except (TypeError, ValueError) as exc:
        raise GatewayError("proxy_port must be a number.") from exc
    if port <= 0 or port > 65535:
        raise GatewayError("proxy_port must be between 1 and 65535.")
    protocol = str(raw.get("proxy_protocol") or "auto").lower()
    if protocol not in {"auto", "socks5", "http"}:
        raise GatewayError("proxy_protocol must be auto, socks5, or http.")
    if protocol == "auto":
        protocol = detect_proxy_protocol(host, port)
    else:
        ok, err = tcp_connect(host, port)
        if not ok:
            raise GatewayError(f"Proxy {host}:{port} is not reachable: {err}")

    bypass_cidrs = list(DEFAULT_BYPASS_CIDRS)
    bypass_cidrs.extend(get_local_ipv4_cidrs())
    gateway = get_default_gateway()
    if gateway:
        bypass_cidrs.append(f"{gateway}/32")
    host_cidr = ip_cidr_for_host(host)
    if host_cidr:
        bypass_cidrs.append(host_cidr)
    bypass_cidrs.extend(str(x).strip() for x in raw.get("bypass_cidrs", []) if str(x).strip())

    validated_cidrs: list[str] = []
    for cidr in bypass_cidrs:
        try:
            validated_cidrs.append(normalize_bypass_cidr(cidr))
        except ValueError as exc:
            raise GatewayError(f"Invalid bypass CIDR '{cidr}': {exc}") from exc

    bypass_domains = list(DEFAULT_BYPASS_DOMAINS)
    for key, domains in PRESET_BYPASS_DOMAINS.items():
        if raw.get(key, PRESET_BYPASS_DEFAULTS[key]):
            bypass_domains.extend(domains)
    if raw.get("bypass_system_packages", PRESET_BYPASS_DEFAULTS["bypass_system_packages"]):
        bypass_domains.extend(get_apt_source_domains())
    for item in raw.get("bypass_domains", []):
        domain = normalize_bypass_domain(str(item))
        if domain:
            bypass_domains.append(domain)
    bypass_rules: list[dict[str, Any]] = []
    for index, item in enumerate(raw.get("bypass_rules", []), start=1):
        try:
            bypass_rules.append(normalize_bypass_rule(item))
        except ValueError as exc:
            raise GatewayError(f"Invalid bypass rule #{index}: {exc}") from exc
    local_dns = get_system_dns_server()

    return {
        "proxy_host": host,
        "proxy_port": port,
        "proxy_protocol": protocol,
        "local_dns": local_dns,
        "dns_strategy": str(raw.get("dns_strategy") or DEFAULT_DNS_STRATEGY),
        "apt_source_domains": get_apt_source_domains(),
        "bypass_cidrs": sorted(set(validated_cidrs)),
        "bypass_domains": sorted(set(normalize_bypass_domain(str(domain)) or str(domain) for domain in bypass_domains)),
        "bypass_rules": bypass_rules,
        "block_udp_when_unsupported": bool(raw.get("block_udp_when_unsupported", False)),
        "bypass_system_packages": bool(raw.get("bypass_system_packages", PRESET_BYPASS_DEFAULTS["bypass_system_packages"])),
        "bypass_container_registries": bool(raw.get("bypass_container_registries", PRESET_BYPASS_DEFAULTS["bypass_container_registries"])),
        "bypass_processes": SYSTEM_PACKAGE_PROCESSES
        if raw.get("bypass_system_packages", PRESET_BYPASS_DEFAULTS["bypass_system_packages"])
        else [],
    }


def build_sing_box_config(config: dict[str, Any]) -> dict[str, Any]:
    outbound_type = "socks" if config["proxy_protocol"] == "socks5" else "http"
    local_dns = str(config.get("local_dns") or get_system_dns_server())
    route_rules: list[dict[str, Any]] = [
        {
            "protocol": "dns",
            "outbound": "dns-out",
        },
        {
            "ip_cidr": config["bypass_cidrs"],
            "outbound": "direct",
        },
        {
            "domain": [d for d in config["bypass_domains"] if not d.startswith(".")],
            "domain_suffix": [d[1:] for d in config["bypass_domains"] if d.startswith(".")],
            "outbound": "direct",
        },
    ]
    custom_route_rules = [
        {**sing_box_match_rule(rule), "outbound": "direct"}
        for rule in config.get("bypass_rules", [])
    ]
    route_rules[1:1] = custom_route_rules
    if config.get("bypass_processes"):
        route_rules.insert(1, {"process_name": config["bypass_processes"], "outbound": "direct"})
    if config.get("block_udp_when_unsupported"):
        route_rules.insert(1, {"network": "udp", "outbound": "block"})

    return {
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "strategy": str(config.get("dns_strategy") or DEFAULT_DNS_STRATEGY),
            "servers": [
                {"tag": "proxy-dns", "address": "https://1.1.1.1/dns-query", "detour": "proxy"},
                {"tag": "local-dns", "address": local_dns, "detour": "direct"},
            ],
            "rules": [
                *[
                    {**sing_box_match_rule(rule), "server": "local-dns"}
                    for rule in config.get("bypass_rules", [])
                ],
                {
                    "ip_cidr": config["bypass_cidrs"],
                    "server": "local-dns",
                },
                {
                    "domain": [d for d in config["bypass_domains"] if not d.startswith(".")],
                    "domain_suffix": [d[1:] for d in config["bypass_domains"] if d.startswith(".")],
                    "server": "local-dns",
                },
            ],
            "final": "proxy-dns",
        },
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": "vmproxy0",
                "address": ["172.19.0.1/30"],
                "auto_route": True,
                "strict_route": True,
                "sniff": True,
                "sniff_override_destination": True,
            }
        ],
        "outbounds": [
            {
                "type": outbound_type,
                "tag": "proxy",
                "server": config["proxy_host"],
                "server_port": config["proxy_port"],
            },
            {"type": "direct", "tag": "direct"},
            {"type": "dns", "tag": "dns-out"},
            {"type": "block", "tag": "block"},
        ],
        "route": {
            "auto_detect_interface": True,
            "rules": route_rules,
            "final": "proxy",
        },
    }


def write_systemd_unit() -> None:
    content = f"""[Unit]
Description=VM Proxy Gateway transparent proxy
Documentation=file:///opt/vm-proxy-gateway/README.md
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={SING_BOX_BIN} run -c {SING_BOX_CONFIG}
Restart=on-failure
RestartSec=2s
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW
NoNewPrivileges=true
ExecStopPost=-/usr/bin/resolvectl revert vmproxy0
ExecStopPost=-/usr/sbin/ip link delete vmproxy0

[Install]
WantedBy=multi-user.target
"""
    SYSTEMD_UNIT.write_text(content, encoding="utf-8")


def cleanup_runtime_network_state() -> None:
    for cmd in (["resolvectl", "revert", "vmproxy0"], ["ip", "link", "delete", "vmproxy0"]):
        try:
            run(cmd, check=False)
        except FileNotFoundError:
            pass


def is_service_active() -> bool:
    result = run(["systemctl", "is-active", "vm-proxy-gateway.service"], check=False)
    return result.stdout.strip() == "active"


def apply_config(config_path: Path, restart_active: bool = False) -> None:
    require_root()
    raw = read_json(config_path)
    config = normalize_config(raw)
    SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
    write_json(SYSTEM_CONFIG, config)
    write_json(SING_BOX_CONFIG, build_sing_box_config(config))
    write_systemd_unit()
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "vm-proxy-gateway.service"])
    if restart_active and is_service_active():
        cleanup_runtime_network_state()
        run(["systemctl", "restart", "vm-proxy-gateway.service"])


def apply_and_start(config_path: Path) -> None:
    apply_config(config_path)
    service_action("restart" if is_service_active() else "start", refresh_config=False)


def service_action(action: str, refresh_config: bool = True) -> None:
    require_root()
    if action not in {"start", "stop", "restart"}:
        raise GatewayError(f"Unsupported action: {action}")
    if action in {"start", "restart"}:
        cleanup_runtime_network_state()
    if refresh_config and action in {"start", "restart"}:
        user_config = default_user_config_path()
        if user_config:
            apply_config(user_config)
    result = run(["systemctl", action, "vm-proxy-gateway.service"], check=False)
    if result.returncode == 0:
        if action == "stop":
            cleanup_runtime_network_state()
        return
    missing_unit = result.returncode == 5 or "not loaded" in result.stderr.lower() or "could not be found" in result.stderr.lower()
    if action == "stop" and (missing_unit or not SYSTEMD_UNIT.exists()):
        cleanup_runtime_network_state()
        return
    raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)


def service_status() -> dict[str, Any]:
    active = run(["systemctl", "is-active", "vm-proxy-gateway.service"], check=False)
    enabled = run(["systemctl", "is-enabled", "vm-proxy-gateway.service"], check=False)
    gateway = get_default_gateway()
    config = read_json(SYSTEM_CONFIG) if SYSTEM_CONFIG.exists() else {}
    proxy_host = config.get("proxy_host")
    try:
        proxy_port = int(config.get("proxy_port") or DEFAULT_PORT)
    except (TypeError, ValueError):
        proxy_port = DEFAULT_PORT
    reachable = None
    error = None
    if proxy_host:
        reachable, error = tcp_connect(str(proxy_host), proxy_port)
    return {
        "active": active.stdout.strip() or active.stderr.strip(),
        "enabled": enabled.stdout.strip() or enabled.stderr.strip(),
        "default_gateway": gateway,
        "system_config_exists": SYSTEM_CONFIG.exists(),
        "sing_box_config_exists": SING_BOX_CONFIG.exists(),
        "proxy_host": proxy_host,
        "proxy_port": proxy_port if proxy_host else None,
        "proxy_reachable": reachable,
        "proxy_error": error,
        "local_dns": config.get("local_dns") or get_system_dns_server(),
        "apt_source_domains": get_apt_source_domains(),
        "local_cidrs": get_local_ipv4_cidrs(),
        "bypass_cidrs": list(config.get("bypass_cidrs") or []),
        "bypass_domains": list(config.get("bypass_domains") or []),
        "bypass_rules": list(config.get("bypass_rules") or []),
    }


def traffic_stats() -> dict[str, Any]:
    """Return byte counters for traffic crossing the transparent proxy TUN."""
    statistics = Path("/sys/class/net") / TUN_INTERFACE / "statistics"

    def read_counter(name: str) -> int:
        try:
            return int((statistics / name).read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return 0

    active = is_service_active()
    available = active and statistics.is_dir()
    return {
        "active": active,
        "interface": TUN_INTERFACE,
        "available": available,
        "upload_bytes": read_counter("tx_bytes") if available else 0,
        "download_bytes": read_counter("rx_bytes") if available else 0,
    }


def split_destination(value: str) -> tuple[str, int | None]:
    host, separator, port_text = value.rpartition(":")
    if not separator:
        return value.strip("[]"), None
    try:
        return host.strip("[]"), int(port_text)
    except ValueError:
        return value.strip("[]"), None


def parse_traffic_logs(content: str, proxy_target: str | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw_line in content.splitlines():
        line = ANSI_ESCAPE_RE.sub("", raw_line)
        match = TRAFFIC_LOG_RE.search(line)
        if not match:
            continue
        destination, port = split_destination(match.group("destination"))
        route = match.group("route")
        entries.append({
            "time": match.group("timestamp"),
            "destination": destination,
            "port": port,
            "network": "udp" if match.group("packet") else "tcp",
            "route": route,
            "outbound_type": match.group("outbound_type"),
            "via": proxy_target if route == "proxy" else route,
            "connection_id": match.group("connection_id"),
        })
    entries.reverse()
    return entries


def traffic_logs(limit: int = 300) -> dict[str, Any]:
    limit = max(1, min(limit, 2000))
    config = read_json(SYSTEM_CONFIG) if SYSTEM_CONFIG.exists() else {}
    proxy_target = None
    if config.get("proxy_host"):
        proxy_target = f"{config['proxy_host']}:{config.get('proxy_port') or DEFAULT_PORT}"
    result = run(
        [
            "journalctl",
            "-u",
            "vm-proxy-gateway.service",
            "--no-pager",
            "--no-hostname",
            "--output=cat",
            "--grep=outbound/",
            f"--lines={limit}",
        ],
        check=False,
    )
    if result.returncode != 0:
        raise GatewayError(result.stderr.strip() or "Could not read service logs.")
    entries = parse_traffic_logs(result.stdout, proxy_target)
    return {"entries": entries, "proxy_target": proxy_target, "count": len(entries)}


def test_network(config_path: Path | None = None) -> dict[str, Any]:
    raw = read_json(config_path) if config_path else (read_json(SYSTEM_CONFIG) if SYSTEM_CONFIG.exists() else {})
    config = normalize_config(raw)
    ok, err = tcp_connect(config["proxy_host"], int(config["proxy_port"]))
    result: dict[str, Any] = {
        "proxy": f"{config['proxy_protocol']}://{config['proxy_host']}:{config['proxy_port']}",
        "proxy_reachable": ok,
        "proxy_error": None if ok else err,
    }
    curl_proxy = (
        f"socks5h://{config['proxy_host']}:{config['proxy_port']}"
        if config["proxy_protocol"] == "socks5"
        else f"http://{config['proxy_host']}:{config['proxy_port']}"
    )
    curl = run(
        [
            "curl",
            "-fsSL",
            "--max-time",
            "12",
            "--proxy",
            curl_proxy,
            "https://api.ipify.org",
        ],
        check=False,
    )
    result["proxy_http_test"] = "ok" if curl.returncode == 0 else "failed"
    result["proxy_public_ip"] = curl.stdout.strip() if curl.returncode == 0 else None
    result["proxy_http_error"] = None if curl.returncode == 0 else (curl.stderr.strip() or f"curl exit {curl.returncode}")
    result["proxy_http_note"] = "This test uses the proxy directly. For SOCKS5, socks5h makes DNS resolve through the proxy."
    return result


def diagnose(config_path: Path | None = None) -> dict[str, Any]:
    raw = read_json(config_path) if config_path and config_path.exists() else {}
    host = str(raw.get("proxy_host") or "").strip()
    port = int(raw.get("proxy_port") or DEFAULT_PORT)
    gateway = get_default_gateway()
    target = host or gateway

    checks: dict[str, Any] = {
        "note": "ICMP ping can be blocked by Windows Firewall. Proxy reachability is tested with TCP connect instead.",
        "default_gateway": gateway,
        "local_dns": get_system_dns_server(),
        "apt_source_domains": get_apt_source_domains(),
        "local_cidrs": get_local_ipv4_cidrs(),
        "configured_proxy_host": host or None,
        "configured_proxy_port": port,
        "tcp_checks": [],
        "advice": [],
    }

    tcp_checks: list[dict[str, Any]] = []
    for candidate in [target, gateway]:
        if not candidate:
            continue
        label = "configured_proxy" if candidate == host else "default_gateway"
        ok, err = tcp_connect(candidate, port)
        tcp_checks.append({
            "label": label,
            "target": f"{candidate}:{port}",
            "reachable": ok,
            "error": None if ok else err,
        })
    checks["tcp_checks"] = tcp_checks

    if not target:
        checks["advice"].append("No proxy host is configured and no default gateway was detected.")
    elif not any(item["reachable"] for item in tcp_checks):
        checks["advice"].extend([
            f"Make sure the Windows proxy listens on {target}:{port}, not only on 127.0.0.1:{port}.",
            "If you use Clash/mihomo/v2rayN, enable LAN access / allow LAN / bind 0.0.0.0.",
            f"Allow inbound TCP {port} in Windows Defender Firewall for the private network.",
            "Do not use ping as the final test; Windows commonly blocks ICMP while TCP still works.",
        ])
    else:
        checks["advice"].append("The proxy TCP port is reachable from the Ubuntu VM.")

    return checks


def discover() -> dict[str, Any]:
    gateway = get_default_gateway()
    candidates = [x for x in [gateway] if x]
    return {
        "default_gateway": gateway,
        "local_cidrs": get_local_ipv4_cidrs(),
        "proxy_candidates": candidates,
    }


def uninstall() -> None:
    require_root()
    run(["systemctl", "disable", "--now", "vm-proxy-gateway.service"], check=False)
    if SYSTEMD_UNIT.exists():
        SYSTEMD_UNIT.unlink()
    run(["systemctl", "daemon-reload"], check=False)
    # Keep /etc/vm-proxy-gateway for diagnostics and deliberate re-install reuse.


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    sub = parser.add_subparsers(dest="command", required=True)
    p_apply = sub.add_parser("apply")
    p_apply.add_argument("--config", required=True, type=Path)
    p_apply_start = sub.add_parser("apply-start")
    p_apply_start.add_argument("--config", required=True, type=Path)
    for name in ["start", "stop", "restart", "status", "traffic-stats", "discover", "uninstall"]:
        sub.add_parser(name)
    p_logs = sub.add_parser("logs")
    p_logs.add_argument("--limit", type=int, default=300)
    p_test = sub.add_parser("test")
    p_test.add_argument("--config", type=Path)
    p_diagnose = sub.add_parser("diagnose")
    p_diagnose.add_argument("--config", type=Path)
    args = parser.parse_args()

    try:
        if args.command == "apply":
            apply_config(args.config, restart_active=True)
            print("Configuration applied.")
        elif args.command == "apply-start":
            apply_and_start(args.config)
            print("Configuration applied and service started.")
        elif args.command in {"start", "stop", "restart"}:
            service_action(args.command)
            print(f"Service {args.command} complete.")
        elif args.command == "status":
            print(json.dumps(service_status(), indent=2, sort_keys=True))
        elif args.command == "traffic-stats":
            print(json.dumps(traffic_stats(), indent=2, sort_keys=True))
        elif args.command == "logs":
            print(json.dumps(traffic_logs(args.limit), indent=2, sort_keys=True))
        elif args.command == "test":
            print(json.dumps(test_network(args.config), indent=2, sort_keys=True))
        elif args.command == "diagnose":
            print(json.dumps(diagnose(args.config), indent=2, sort_keys=True))
        elif args.command == "discover":
            print(json.dumps(discover(), indent=2, sort_keys=True))
        elif args.command == "uninstall":
            uninstall()
            print("Service uninstalled. System config was kept in /etc/vm-proxy-gateway.")
        return 0
    except (GatewayError, subprocess.CalledProcessError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
