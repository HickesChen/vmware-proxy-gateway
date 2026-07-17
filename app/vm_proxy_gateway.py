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
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


APP_NAME = "vm-proxy-gateway"
SYSTEM_DIR = Path("/etc/vm-proxy-gateway")
SYSTEM_CONFIG = SYSTEM_DIR / "config.json"
SING_BOX_CONFIG = SYSTEM_DIR / "sing-box.json"
SYSTEMD_UNIT = Path("/etc/systemd/system/vm-proxy-gateway.service")
TUN_INTERFACE = "vmproxy0"
TRAFFIC_TABLE_FAMILY = "inet"
TRAFFIC_TABLE_NAME = "vm_proxy_gateway_stats"
APT_DIR = Path("/etc/apt")
SING_BOX_BIN = "/usr/local/bin/sing-box"
DEFAULT_PORT = 10086
SHELL_BLOCK_BEGIN = "# BEGIN VM-PROXY-GATEWAY MANAGED BLOCK"
SHELL_BLOCK_END = "# END VM-PROXY-GATEWAY MANAGED BLOCK"
SHELL_NO_PROXY = "localhost,127.0.0.1,::1,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12"
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


def user_home_for_config(config_path: Path | None = None) -> Path | None:
    """Resolve the unprivileged user's home, including pkexec invocations."""
    if config_path:
        path = config_path.resolve()
        if path.name == "config.json" and path.parent.name == APP_NAME and path.parent.parent.name == ".config":
            return path.parent.parent.parent
    for name in [os.environ.get("SUDO_USER"), os.environ.get("PKEXEC_UID"), os.environ.get("USER"), os.environ.get("LOGNAME")]:
        if not name:
            continue
        try:
            entry = pwd.getpwuid(int(name)) if name.isdigit() else pwd.getpwnam(name)
        except (KeyError, ValueError):
            continue
        if entry.pw_uid != 0:
            return Path(entry.pw_dir)
    return None


def _strip_managed_shell_block(content: str) -> str:
    lines = content.splitlines(keepends=True)
    output: list[str] = []
    inside = False
    for line in lines:
        marker = line.strip()
        if marker == SHELL_BLOCK_BEGIN:
            inside = True
            continue
        if marker == SHELL_BLOCK_END and inside:
            inside = False
            continue
        if not inside:
            output.append(line)
    # A truncated managed block owns everything after its begin marker.
    return "".join(output)


def _strip_legacy_shell_proxy(content: str, old_config: dict[str, Any] | None) -> str:
    """Migrate only the exact consecutive block emitted by older releases."""
    legacy_pattern = re.compile(
        r"(?m)^export HTTP_PROXY=http://(?P<endpoint>[^\s/]+:\d+)\n"
        r"export HTTPS_PROXY=http://(?P=endpoint)\n"
        r"export ALL_PROXY=socks5h://(?P=endpoint)(?:\n|$)"
    )
    content = legacy_pattern.sub("", content)
    # Also cover older HTTP-only output when a previous config is available.
    if old_config and old_config.get("proxy_host") and old_config.get("proxy_protocol") == "http":
        endpoint = f"{old_config['proxy_host']}:{int(old_config.get('proxy_port') or DEFAULT_PORT)}"
        http_pattern = re.compile(
            rf"(?m)^export HTTP_PROXY=http://{re.escape(endpoint)}\n"
            rf"export HTTPS_PROXY=http://{re.escape(endpoint)}\n"
            rf"export ALL_PROXY=http://{re.escape(endpoint)}(?:\n|$)"
        )
        content = http_pattern.sub("", content)
    return content


def managed_shell_block(config: dict[str, Any]) -> str:
    host, port = config["proxy_host"], int(config["proxy_port"])
    http_url = f"http://{host}:{port}"
    all_url = f"socks5h://{host}:{port}" if config["proxy_protocol"] == "socks5" else http_url
    return (
        f"{SHELL_BLOCK_BEGIN}\n"
        f"export HTTP_PROXY={http_url}\n"
        f"export HTTPS_PROXY={http_url}\n"
        f"export ALL_PROXY={all_url}\n"
        f"export NO_PROXY={SHELL_NO_PROXY}\n"
        f"{SHELL_BLOCK_END}\n"
    )


def stale_proxy_processes(
    config: dict[str, Any], uid: int, proc_root: Path = Path("/proc")
) -> list[dict[str, Any]]:
    """Find long-running VS Code processes that inherited a different proxy."""
    expected_http = f"http://{config['proxy_host']}:{int(config['proxy_port'])}"
    expected_all = (
        f"socks5h://{config['proxy_host']}:{int(config['proxy_port'])}"
        if config.get("proxy_protocol") == "socks5"
        else expected_http
    )
    expected = {"HTTP_PROXY": expected_http, "HTTPS_PROXY": expected_http, "ALL_PROXY": expected_all}
    stale: list[dict[str, Any]] = []
    for directory in proc_root.iterdir() if proc_root.exists() else []:
        if not directory.name.isdigit():
            continue
        try:
            if directory.stat().st_uid != uid:
                continue
            command = directory.joinpath("cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
            if "vscode-server" not in command and ".vscode-server" not in command:
                continue
            environ = directory.joinpath("environ").read_bytes().split(b"\0")
            values = {}
            for item in environ:
                key, separator, value = item.partition(b"=")
                name = key.decode(errors="ignore")
                if separator and name in expected:
                    values[name] = value.decode(errors="replace")
            mismatches = {name: value for name, value in values.items() if value and value != expected[name]}
            if mismatches:
                stale.append({"pid": int(directory.name), "command": command, "proxy": mismatches})
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
    return stale


def terminate_stale_proxy_processes(processes: list[dict[str, Any]]) -> list[int]:
    restarted: list[int] = []
    for process in processes:
        pid = int(process["pid"])
        try:
            os.kill(pid, signal.SIGTERM)
            restarted.append(pid)
        except (ProcessLookupError, PermissionError):
            continue
    return restarted


def reconcile_shell_proxy(
    home: Path | None, config: dict[str, Any] | None, old_config: dict[str, Any] | None = None
) -> bool:
    """Idempotently update/remove only gateway-owned settings in ~/.profile."""
    if home is None:
        return False
    profile = home / ".profile"
    original = profile.read_text(encoding="utf-8", errors="ignore") if profile.exists() else ""
    content = _strip_legacy_shell_proxy(_strip_managed_shell_block(original), old_config).rstrip("\n")
    if config is not None:
        content = (content + "\n\n" if content else "") + managed_shell_block(config).rstrip("\n")
    updated = content + ("\n" if content else "")
    if updated == original:
        return False
    profile.parent.mkdir(parents=True, exist_ok=True)
    mode = profile.stat().st_mode & 0o777 if profile.exists() else 0o644
    owner = profile.stat() if profile.exists() else home.stat()
    fd, tmp_name = tempfile.mkstemp(prefix=".profile.", dir=profile.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(updated)
        os.chmod(tmp_name, mode)
        if is_root():
            os.chown(tmp_name, owner.st_uid, owner.st_gid)
        os.replace(tmp_name, profile)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return True


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


def resolve_proxy_addresses(host: str, port: int) -> list[str]:
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(host.strip("[]"), port, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise GatewayError(f"Could not resolve proxy host {host}: {exc}") from exc
    return sorted(addresses, key=lambda value: (ipaddress.ip_address(value).version, value))


def build_proxy_traffic_nft_script(addresses: list[str], port: int) -> str:
    lines = [
        f"delete table {TRAFFIC_TABLE_FAMILY} {TRAFFIC_TABLE_NAME}",
        f"table {TRAFFIC_TABLE_FAMILY} {TRAFFIC_TABLE_NAME} {{",
        " chain input { type filter hook input priority filter; policy accept;",
    ]
    for address in addresses:
        family = "ip6" if ipaddress.ip_address(address).version == 6 else "ip"
        for protocol in ("tcp", "udp"):
            lines.append(
                f'  {family} saddr {address} {protocol} sport {port} counter comment "download"'
            )
    lines.extend([" }", " chain output { type filter hook output priority filter; policy accept;"])
    for address in addresses:
        family = "ip6" if ipaddress.ip_address(address).version == 6 else "ip"
        for protocol in ("tcp", "udp"):
            lines.append(
                f'  {family} daddr {address} {protocol} dport {port} counter comment "upload"'
            )
    lines.extend([" }", "}"])
    return "\n".join(lines) + "\n"


def configure_proxy_traffic_accounting(host: str, port: int) -> None:
    require_root()
    if not shutil.which("nft"):
        raise GatewayError("nft is required for complete proxy traffic monitoring.")
    addresses = resolve_proxy_addresses(host, port)
    script = build_proxy_traffic_nft_script(addresses, port)
    # `destroy` is atomic with the replacement but fails when the table does
    # not exist, so ensure an empty table exists first.
    run(["nft", "add", "table", TRAFFIC_TABLE_FAMILY, TRAFFIC_TABLE_NAME], check=False)
    result = subprocess.run(
        ["nft", "-f", "-"], input=script, text=True, capture_output=True
    )
    if result.returncode != 0:
        raise GatewayError(result.stderr.strip() or "Could not configure proxy traffic monitoring.")


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


def cleanup_traffic_accounting() -> None:
    try:
        run(["nft", "delete", "table", TRAFFIC_TABLE_FAMILY, TRAFFIC_TABLE_NAME], check=False)
    except FileNotFoundError:
        pass


def cleanup_managed_shell_for_all_users() -> int:
    """Remove only owned blocks during uninstall, including direct-root runs."""
    cleaned = 0
    seen: set[Path] = set()
    preferred = user_home_for_config(default_user_config_path())
    homes = [preferred] if preferred else []
    homes.extend(Path(entry.pw_dir) for entry in pwd.getpwall() if entry.pw_uid >= 1000 and entry.pw_dir)
    for home in homes:
        if home is None or home in seen or not home.is_dir():
            continue
        seen.add(home)
        try:
            if reconcile_shell_proxy(home, None):
                cleaned += 1
        except OSError:
            continue
    return cleaned


def is_service_active() -> bool:
    result = run(["systemctl", "is-active", "vm-proxy-gateway.service"], check=False)
    return result.stdout.strip() == "active"


def apply_config(config_path: Path, restart_active: bool = False) -> None:
    require_root()
    raw = read_json(config_path)
    config = normalize_config(raw)
    old_config = read_json(SYSTEM_CONFIG) if SYSTEM_CONFIG.exists() else None
    was_active = is_service_active()
    SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
    write_json(SYSTEM_CONFIG, config)
    write_json(SING_BOX_CONFIG, build_sing_box_config(config))
    configure_proxy_traffic_accounting(config["proxy_host"], int(config["proxy_port"]))
    write_systemd_unit()
    run(["systemctl", "daemon-reload"])
    # Login startup is managed by the GUI so startup failures can be shown to
    # the user. Keep the system service from starting silently before login.
    run(["systemctl", "disable", "vm-proxy-gateway.service"])
    if restart_active and was_active:
        cleanup_runtime_network_state()
        run(["systemctl", "restart", "vm-proxy-gateway.service"])
        reconcile_shell_proxy(user_home_for_config(config_path), config, old_config)


def apply_and_start(config_path: Path) -> None:
    old_config = read_json(SYSTEM_CONFIG) if SYSTEM_CONFIG.exists() else None
    apply_config(config_path)
    service_action("restart" if is_service_active() else "start", refresh_config=False)
    reconcile_shell_proxy(user_home_for_config(config_path), read_json(SYSTEM_CONFIG), old_config)


def service_action(action: str, refresh_config: bool = True) -> None:
    require_root()
    if action not in {"start", "stop", "restart"}:
        raise GatewayError(f"Unsupported action: {action}")
    if action in {"start", "restart"}:
        cleanup_runtime_network_state()
    user_config = default_user_config_path() if refresh_config and action in {"start", "restart"} else None
    if user_config:
        apply_config(user_config)
    result = run(["systemctl", action, "vm-proxy-gateway.service"], check=False)
    if result.returncode == 0:
        if action == "stop":
            cleanup_runtime_network_state()
            cleanup_traffic_accounting()
            reconcile_shell_proxy(user_home_for_config(), None)
        elif action in {"start", "restart"}:
            config = read_json(SYSTEM_CONFIG) if SYSTEM_CONFIG.exists() else None
            reconcile_shell_proxy(user_home_for_config(user_config if refresh_config else None), config)
        return
    missing_unit = result.returncode == 5 or "not loaded" in result.stderr.lower() or "could not be found" in result.stderr.lower()
    if action == "stop" and (missing_unit or not SYSTEMD_UNIT.exists()):
        cleanup_runtime_network_state()
        cleanup_traffic_accounting()
        reconcile_shell_proxy(user_home_for_config(), None)
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
    """Return all VM traffic exchanged with the configured proxy endpoint."""
    require_root()
    result = run(["nft", "list", "table", TRAFFIC_TABLE_FAMILY, TRAFFIC_TABLE_NAME], check=False)
    if result.returncode != 0:
        return {"available": False, "upload_bytes": 0, "download_bytes": 0}
    totals = {"upload": 0, "download": 0}
    pattern = re.compile(r'counter packets \d+ bytes (?P<bytes>\d+) comment "(?P<direction>upload|download)"')
    for match in pattern.finditer(result.stdout):
        totals[match.group("direction")] += int(match.group("bytes"))
    config = read_json(SYSTEM_CONFIG) if SYSTEM_CONFIG.exists() else {}
    return {
        "available": True,
        "source": "proxy_endpoint",
        "proxy_host": config.get("proxy_host"),
        "proxy_port": config.get("proxy_port"),
        "upload_bytes": totals["upload"],
        "download_bytes": totals["download"],
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


def diagnose(config_path: Path | None = None, repair: bool = False) -> dict[str, Any]:
    raw = read_json(config_path) if config_path and config_path.exists() else {}
    host = str(raw.get("proxy_host") or "").strip()
    try:
        port = int(raw.get("proxy_port") or DEFAULT_PORT)
        port_valid = 0 < port <= 65535
    except (TypeError, ValueError):
        port = DEFAULT_PORT
        port_valid = False
    gateway = get_default_gateway()
    target = host or gateway
    protocol = str(raw.get("proxy_protocol") or "socks5").lower()
    if protocol not in {"socks5", "http"}:
        protocol = "socks5"
    proxy_config = {"proxy_host": host, "proxy_port": port, "proxy_protocol": protocol} if host else None
    home = user_home_for_config(config_path)
    active = is_service_active()

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
        "repair_requested": repair,
        "repairs": [],
        "diagnostic_checks": [],
    }

    diagnostic_checks: list[dict[str, Any]] = checks["diagnostic_checks"]
    chinese = str(raw.get("language") or "").lower().startswith("zh")

    def human(en: str, zh: str) -> str:
        return zh if chinese else en

    check_names = {
        "user_config": human("User settings", "用户配置文件"),
        "proxy_host": human("Proxy server address", "代理服务器地址"),
        "proxy_port": human("Proxy server port", "代理服务器端口"),
        "default_gateway": human("VM default gateway", "虚拟机默认网关"),
        "local_dns": human("DNS server", "DNS 服务器"),
        "sing_box_binary": human("sing-box program", "sing-box 核心程序"),
        "curl_binary": human("Network test tool", "网络测试工具 curl"),
        "system_config": human("System proxy configuration", "系统代理配置"),
        "sing_box_config": human("sing-box runtime configuration", "sing-box 运行配置"),
        "systemd_unit": human("Proxy system service", "代理系统服务"),
        "service_state": human("Proxy service state", "代理服务状态"),
        "shell_proxy": human("Persistent Shell proxy", "Shell 持久化代理"),
        "vscode_process_environment": human("VS Code Remote proxy environment", "VS Code Remote 代理环境"),
        "proxy_tcp": human("Connection to the proxy port", "代理端口连接"),
        "generated_configuration": human("Configuration consistency", "配置一致性"),
        "tun_interface": human("Transparent-proxy network interface", "透明代理网络接口"),
        "traffic_accounting": human("Traffic accounting rules", "流量统计规则"),
        "runtime_dns": human("Temporary proxy DNS state", "临时代理 DNS 状态"),
        "proxy_http_request": human("Internet request through proxy", "通过代理访问互联网"),
    }

    solutions = {
        "user_config": "Save the settings once, then run diagnosis again.",
        "proxy_host": "Enter the Windows host IP. In NAT mode it is commonly the VM default gateway.",
        "proxy_port": "Set a numeric proxy port between 1 and 65535 and make it match the Windows proxy.",
        "default_gateway": "Restore the VM network adapter/DHCP lease, then verify `ip route` has a default route.",
        "local_dns": "Restore systemd-resolved or set a reachable DNS server in the VM network settings.",
        "sing_box_binary": "Run install.sh again to download and install the supported sing-box binary.",
        "curl_binary": "Install curl with `sudo apt install curl`; it is required for end-to-end diagnosis.",
        "system_config": "Run diagnosis with repair privileges or click Apply to regenerate the system configuration.",
        "sing_box_config": "Run privileged diagnosis to regenerate sing-box.json from the user configuration.",
        "systemd_unit": "Run privileged diagnosis or reinstall the application to recreate the systemd unit.",
        "shell_proxy": "Run privileged diagnosis, then restart login sessions that inherited the old environment.",
        "vscode_process_environment": "Reconnect VS Code Remote so its server starts with the corrected environment.",
        "proxy_tcp": f"Enable LAN access on the Windows proxy, listen on 0.0.0.0:{port}, and allow TCP {port} in Windows Firewall.",
        "generated_configuration": "Run privileged diagnosis or click Apply to rebuild all generated configuration.",
        "tun_interface": f"Stop the service and delete stale interface {TUN_INTERFACE}, or run privileged diagnosis.",
        "traffic_accounting": "Run privileged diagnosis to recreate the nftables accounting table; reinstall nftables if missing.",
        "runtime_dns": f"Run privileged diagnosis or `sudo resolvectl revert {TUN_INTERFACE}` to remove the stale per-interface DNS state.",
        "proxy_http_request": "Verify the configured protocol, Windows proxy outbound connectivity, DNS, and authentication settings.",
    }
    if chinese:
        solutions.update({
            "user_config": "先点击“应用”保存设置，然后重新运行诊断。",
            "proxy_host": "填写 Windows 宿主机地址；NAT 网络中通常可先尝试上方显示的虚拟机默认网关。",
            "proxy_port": "填写 1 到 65535 之间的数字，并确保与 Windows 代理软件的监听端口一致。",
            "default_gateway": "检查虚拟机网卡是否已连接并启用 DHCP，然后运行 ip route，确认存在 default via 路由。",
            "local_dns": "恢复 systemd-resolved，或在虚拟机网络设置中填写一个从虚拟机可达的 DNS 服务器。",
            "sing_box_binary": "在项目目录重新运行 sudo ./install.sh，重新安装 sing-box 核心。",
            "curl_binary": "运行 sudo apt install curl，安装用于实际联网验证的工具。",
            "system_config": "使用管理员权限重新诊断，或点击“应用”，让程序重新生成系统配置。",
            "sing_box_config": "使用管理员权限重新诊断，自动从用户配置重新生成 sing-box 配置。",
            "systemd_unit": "使用管理员权限重新诊断；仍失败时重新运行 sudo ./install.sh。",
            "shell_proxy": "使用管理员权限重新诊断清理配置；随后重新登录 Shell，使新进程不再继承旧代理。",
            "vscode_process_environment": "断开并重新连接 VS Code Remote；诊断修复模式会自动终止仍持有旧地址的 Server 进程。",
            "proxy_tcp": f"在 Windows 代理软件中启用“允许局域网连接”，监听 0.0.0.0:{port}，并在 Windows 防火墙放行 TCP {port}。",
            "generated_configuration": "点击“应用”或运行管理员诊断，重新生成系统配置、sing-box 配置和 systemd 服务。",
            "tun_interface": f"运行管理员诊断自动删除残留接口；也可在服务停止后执行 sudo ip link delete {TUN_INTERFACE}。",
            "traffic_accounting": "运行管理员诊断重建 nftables 规则；若 nft 命令缺失，运行 sudo apt install nftables。",
            "runtime_dns": f"运行管理员诊断自动清理；也可执行 sudo resolvectl revert {TUN_INTERFACE} 删除残留的接口 DNS 状态。",
            "proxy_http_request": "确认代理协议选择正确，并检查 Windows 代理自身能否联网、DNS 是否正常以及代理是否要求认证。",
        })

    def record(check_id: str, ok: bool, detail: str, repairable: bool = False, repaired: bool = False) -> None:
        diagnostic_checks.append({
            "id": check_id,
            "name": check_names.get(check_id, check_id),
            "ok": ok or repaired,
            "detected": not ok,
            "repairable": repairable,
            "repaired": repaired,
            "detail": detail,
            "solution": None if ok or repaired else solutions.get(check_id, "Review the application logs and correct this item manually."),
        })

    user_config_ok = bool(config_path and config_path.exists())
    record("user_config", user_config_ok, human("The user settings file is readable.", "用户配置文件存在且可以读取。") if user_config_ok else human("The user settings file does not exist, so there is no reliable configuration to repair from.", "找不到用户配置文件，程序没有可用于自动修复的可靠配置来源。"))
    record("proxy_host", bool(host), human(f"Configured proxy server: {host}.", f"当前代理服务器：{host}。") if host else human("No proxy server address is configured.", "代理服务器地址为空，程序不知道应连接哪台主机。"))
    record("proxy_port", port_valid, human(f"Configured proxy port: {port}.", f"当前代理端口：{port}。") if port_valid else human(f"The configured port is not a valid number from 1 to 65535; diagnosis used fallback {port}.", f"填写的端口不是 1 到 65535 之间的有效数字；本次诊断临时使用了 {port}。"))
    record("default_gateway", bool(gateway), human(f"Detected default gateway: {gateway}.", f"检测到默认网关：{gateway}。") if gateway else human("No default route was found; the VM may not have a working network connection.", "没有检测到默认路由，虚拟机网卡可能未连接或 DHCP 配置异常。"))
    local_dns = checks["local_dns"]
    record("local_dns", bool(local_dns), human(f"Detected DNS server: {local_dns}.", f"检测到 DNS 服务器：{local_dns}。") if local_dns else human("No usable DNS server was detected.", "没有检测到可用的 DNS 服务器，域名请求可能失败。"))
    sing_ok = Path(SING_BOX_BIN).is_file() and os.access(SING_BOX_BIN, os.X_OK)
    record("sing_box_binary", sing_ok, human(f"sing-box is installed at {SING_BOX_BIN}.", f"sing-box 已安装：{SING_BOX_BIN}。") if sing_ok else human(f"{SING_BOX_BIN} is missing or not executable; the proxy service cannot start.", f"{SING_BOX_BIN} 不存在或不可执行，透明代理服务无法启动。"))
    curl_ok = bool(shutil.which("curl"))
    record("curl_binary", curl_ok, human("curl is available.", "curl 网络测试工具可用。") if curl_ok else human("curl is not installed, so diagnosis cannot verify a real HTTPS request.", "系统未安装 curl，因此无法验证真实 HTTPS 请求。"))
    record("system_config", SYSTEM_CONFIG.exists(), human("The system configuration exists.", "系统代理配置存在。") if SYSTEM_CONFIG.exists() else human(f"{SYSTEM_CONFIG} is missing.", f"缺少系统配置文件 {SYSTEM_CONFIG}。"), repairable=bool(config_path))
    record("sing_box_config", SING_BOX_CONFIG.exists(), human("The sing-box runtime configuration exists.", "sing-box 运行配置存在。") if SING_BOX_CONFIG.exists() else human(f"{SING_BOX_CONFIG} is missing.", f"缺少 sing-box 运行配置 {SING_BOX_CONFIG}。"), repairable=bool(config_path))
    record("systemd_unit", SYSTEMD_UNIT.exists(), human("The systemd service unit exists.", "systemd 服务单元存在。") if SYSTEMD_UNIT.exists() else human(f"{SYSTEMD_UNIT} is missing; systemd cannot manage the proxy.", f"缺少 {SYSTEMD_UNIT}，systemd 无法管理代理服务。"), repairable=bool(config_path))
    record("service_state", True, human(f"The proxy service is {'running' if active else 'stopped'}.", f"代理服务当前{'正在运行' if active else '已停止'}。"))

    if proxy_config and home:
        try:
            uid = home.stat().st_uid
            stale = stale_proxy_processes(proxy_config, uid)
        except OSError:
            stale = []
        checks["stale_proxy_processes"] = stale
        profile = home / ".profile"
        profile_content = profile.read_text(encoding="utf-8", errors="ignore") if profile.exists() else ""
        expected_block = managed_shell_block(proxy_config).strip()
        shell_ok = expected_block in profile_content if active else SHELL_BLOCK_BEGIN not in profile_content
        shell_repaired = False
        if repair:
            changed = reconcile_shell_proxy(home, proxy_config if active else None, read_json(SYSTEM_CONFIG) if SYSTEM_CONFIG.exists() else None)
            if changed:
                checks["repairs"].append("shell_proxy_updated" if active else "shell_proxy_removed")
                shell_repaired = True
            restarted = terminate_stale_proxy_processes(stale)
            checks["restarted_process_ids"] = restarted
            if restarted:
                checks["repairs"].append("stale_vscode_server_restarted")
        shell_detail = human("The persistent Shell proxy was corrected to match the service state.", "已修正 Shell 持久化代理，使其与当前服务状态一致。") if shell_repaired else (human("Persistent Shell proxy matches the service state.", "Shell 持久化代理与当前服务状态一致。") if shell_ok else human("~/.profile contains a missing, stale, or conflicting managed proxy block.", "~/.profile 中的托管代理块缺失、过期或与当前服务状态冲突。"))
        vscode_restarted = bool(checks.get("restarted_process_ids"))
        vscode_detail = human(f"Restarted {len(checks.get('restarted_process_ids') or [])} stale VS Code Server process(es).", f"已重启 {len(checks.get('restarted_process_ids') or [])} 个仍使用旧代理的 VS Code Server 进程。") if vscode_restarted else (human("VS Code Server processes use the current proxy.", "VS Code Server 进程使用的是当前代理。") if not stale else human(f"Found {len(stale)} VS Code Server process(es) still using another proxy address.", f"发现 {len(stale)} 个 VS Code Server 进程仍在使用其他代理地址。"))
        record("shell_proxy", shell_ok, shell_detail, True, shell_repaired)
        record("vscode_process_environment", not stale, vscode_detail, True, vscode_restarted)
    else:
        record("shell_proxy", not active, "Shell proxy ownership could not be resolved.", False)
        record("vscode_process_environment", True, "No stale VS Code Server proxy was detected.")

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
    configured_reachable = next((item["reachable"] for item in tcp_checks if item["label"] == "configured_proxy"), False)
    tcp_error = next((item.get("error") for item in tcp_checks if item["label"] == "configured_proxy"), None)
    record("proxy_tcp", bool(configured_reachable), human(f"Connected to {host}:{port}.", f"已连接代理端口 {host}:{port}。") if configured_reachable else human(f"Cannot connect to {host or '(not configured)'}:{port}: {tcp_error or 'no proxy address'}.", f"无法连接代理端口 {host or '（未配置地址）'}:{port}：{tcp_error or '没有代理地址'}。"))

    # Rebuild derived state only when the upstream is reachable; this repairs
    # config drift, missing sing-box JSON, the unit file, and nft accounting.
    artifacts_ok = False
    if proxy_config and SYSTEM_CONFIG.exists():
        try:
            system_raw = read_json(SYSTEM_CONFIG)
            artifacts_ok = (
                str(system_raw.get("proxy_host")) == host
                and int(system_raw.get("proxy_port") or DEFAULT_PORT) == port
                and str(system_raw.get("proxy_protocol")) == protocol
                and SING_BOX_CONFIG.exists()
                and SYSTEMD_UNIT.exists()
            )
        except (OSError, ValueError, json.JSONDecodeError):
            artifacts_ok = False
    artifacts_repaired = False
    if repair and not artifacts_ok and configured_reachable and config_path:
        apply_config(config_path, restart_active=active)
        artifacts_repaired = True
        checks["repairs"].append("generated_configuration_rebuilt")
        for item in diagnostic_checks:
            if item["id"] in {"system_config", "sing_box_config", "systemd_unit"} and not item["ok"]:
                item.update({
                    "ok": True,
                    "repaired": True,
                    "solution": None,
                    "detail": human("The missing generated file was recreated and synchronized.", "缺失的生成文件已重新创建，并与当前用户配置同步。"),
                })
    record("generated_configuration", artifacts_ok, human("User, system, sing-box, and systemd configurations agree.", "用户配置、系统配置、sing-box 配置和 systemd 服务一致。") if artifacts_ok else human("Generated configuration is missing or does not match the current user settings.", "生成配置缺失，或系统配置、sing-box 配置与当前用户设置不一致。"), True, artifacts_repaired)

    tun_exists = Path(f"/sys/class/net/{TUN_INTERFACE}").exists()
    tun_ok = active or not tun_exists
    tun_repaired = False
    if repair and not tun_ok:
        cleanup_runtime_network_state()
        tun_repaired = True
        checks["repairs"].append("stale_tun_removed")
    record("tun_interface", tun_ok, human("The transparent-proxy interface state is correct.", "透明代理网络接口状态正确。") if tun_ok else human(f"Interface {TUN_INTERFACE} still exists although the service is stopped.", f"代理服务已停止，但网络接口 {TUN_INTERFACE} 仍然存在。"), True, tun_repaired)

    nft = run(["nft", "list", "table", TRAFFIC_TABLE_FAMILY, TRAFFIC_TABLE_NAME], check=False) if shutil.which("nft") else None
    nft_exists = bool(nft and nft.returncode == 0)
    nft_ok = nft_exists if active else not nft_exists
    nft_repaired = artifacts_repaired and active
    if repair and not active and nft_exists:
        cleanup_traffic_accounting()
        nft_repaired = True
        checks["repairs"].append("stale_traffic_accounting_removed")
    nft_failure = human(f"The service is running but nftables table {TRAFFIC_TABLE_NAME} is missing.", f"代理服务正在运行，但 nftables 表 {TRAFFIC_TABLE_NAME} 不存在，流量统计将不可用。") if active else human(f"The service is stopped but nftables table {TRAFFIC_TABLE_NAME} still exists.", f"代理服务已停止，但 nftables 表 {TRAFFIC_TABLE_NAME} 仍然存在，属于运行状态残留。")
    record("traffic_accounting", nft_ok, human("Traffic accounting state matches the service state.", "流量统计规则与服务状态一致。") if nft_ok else nft_failure, bool(proxy_config), nft_repaired)

    dns_status = run(["resolvectl", "status", TUN_INTERFACE], check=False) if shutil.which("resolvectl") else None
    stale_dns = not active and bool(dns_status and dns_status.returncode == 0)
    dns_repaired = False
    if repair and stale_dns:
        try:
            run(["resolvectl", "revert", TUN_INTERFACE], check=False)
            dns_repaired = True
            checks["repairs"].append("stale_runtime_dns_removed")
        except FileNotFoundError:
            pass
    record("runtime_dns", not stale_dns, human("No stale per-interface DNS state was found.", "没有发现接口级 DNS 残留。") if not stale_dns else human(f"The service is stopped but systemd-resolved still has DNS state for {TUN_INTERFACE}.", f"代理服务已停止，但 systemd-resolved 中仍保留 {TUN_INTERFACE} 的 DNS 状态。"), True, dns_repaired)

    web_ok = False
    web_error = None
    if configured_reachable and shutil.which("curl") and proxy_config:
        curl_proxy = f"socks5h://{host}:{port}" if protocol == "socks5" else f"http://{host}:{port}"
        web = run(["curl", "-fsSL", "--max-time", "8", "--proxy", curl_proxy, "https://api.ipify.org"], check=False)
        web_ok = web.returncode == 0
        web_error = web.stderr.strip() if not web_ok else None
    checks["proxy_http_test"] = "ok" if web_ok else "failed"
    checks["proxy_http_error"] = web_error
    record("proxy_http_request", web_ok, human("A real HTTPS request succeeded through the proxy.", "已通过代理成功完成真实 HTTPS 请求。") if web_ok else human(f"The proxy port check was not enough: the HTTPS request failed. {web_error or 'TCP connection was unavailable.'}", f"仅端口检测不足：通过代理发起 HTTPS 请求失败。{web_error or '代理 TCP 连接不可用。'}"))

    if not target:
        checks["advice"].append("No proxy host is configured and no default gateway was detected.")
    elif host and not configured_reachable:
        checks["advice"].extend([
            f"Make sure the Windows proxy listens on {target}:{port}, not only on 127.0.0.1:{port}.",
            "If you use Clash/mihomo/v2rayN, enable LAN access / allow LAN / bind 0.0.0.0.",
            f"Allow inbound TCP {port} in Windows Defender Firewall for the private network.",
            "Do not use ping as the final test; Windows commonly blocks ICMP while TCP still works.",
        ])
    elif configured_reachable:
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
    cleanup_runtime_network_state()
    cleanup_traffic_accounting()
    if SYSTEMD_UNIT.exists():
        SYSTEMD_UNIT.unlink()
    run(["systemctl", "daemon-reload"], check=False)
    cleanup_managed_shell_for_all_users()
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
    p_diagnose.add_argument("--repair", action="store_true")
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
            print(json.dumps(diagnose(args.config, repair=args.repair), indent=2, sort_keys=True))
        elif args.command == "discover":
            print(json.dumps(discover(), indent=2, sort_keys=True))
        elif args.command == "uninstall":
            uninstall()
            print("Service and managed runtime state were cleaned.")
        return 0
    except (GatewayError, subprocess.CalledProcessError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
