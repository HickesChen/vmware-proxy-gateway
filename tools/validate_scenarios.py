#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "app" / "vm_proxy_gateway.py"
GUI = ROOT / "app" / "vm_proxy_gateway_gui.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ctl = load_module("vm_proxy_gateway", CONTROLLER)
gui = load_module("vm_proxy_gateway_gui", GUI)


class FakeResult:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.args = []


def check(name: str, func) -> None:
    func()
    print(f"PASS {name}")


def test_dns_from_resolvectl() -> None:
    def runner(cmd, check=True):
        return FakeResult("Global:\nLink 2 (ens33): 192.168.0.1 2001:4860:4860::8888\n")

    with tempfile.TemporaryDirectory() as tmp:
        resolv = Path(tmp) / "resolv.conf"
        resolv.write_text("nameserver 127.0.0.53\n", encoding="utf-8")
        assert ctl.get_system_dns_server(resolv_conf=resolv, runner=runner) == "192.168.0.1"


def test_dns_from_resolv_conf() -> None:
    def missing_runner(cmd, check=True):
        raise FileNotFoundError

    with tempfile.TemporaryDirectory() as tmp:
        resolv = Path(tmp) / "resolv.conf"
        resolv.write_text("nameserver 127.0.0.53\nnameserver 10.0.2.3\n", encoding="utf-8")
        assert ctl.get_system_dns_server(resolv_conf=resolv, runner=missing_runner) == "10.0.2.3"


def test_dns_falls_back_to_gateway() -> None:
    def missing_runner(cmd, check=True):
        raise FileNotFoundError

    old_gateway = ctl.get_default_gateway
    ctl.get_default_gateway = lambda: "172.16.1.1"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            resolv = Path(tmp) / "resolv.conf"
            resolv.write_text("nameserver 127.0.0.53\n", encoding="utf-8")
            assert ctl.get_system_dns_server(resolv_conf=resolv, runner=missing_runner) == "172.16.1.1"
    finally:
        ctl.get_default_gateway = old_gateway


def test_apt_sources_deb822_and_list() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        apt = Path(tmp)
        apt.joinpath("sources.list").write_text(
            "deb [arch=amd64 signed-by=/x.gpg] https://mirrors.aliyun.com/ubuntu noble main\n"
            "# deb https://ignored.example/ubuntu noble main\n",
            encoding="utf-8",
        )
        d = apt / "sources.list.d"
        d.mkdir()
        d.joinpath("ubuntu.sources").write_text(
            "Types: deb\n"
            "URIs: http://cn.archive.ubuntu.com/ubuntu/ https://mirror.internal.example/repo\n"
            "Suites: noble noble-updates\n",
            encoding="utf-8",
        )
        domains = set(ctl.get_apt_source_domains(apt))
        assert ".mirrors.aliyun.com" in domains
        assert ".cn.archive.ubuntu.com" in domains
        assert ".mirror.internal.example" in domains
        assert ".ignored.example" not in domains


def test_normalize_uses_dynamic_apt_sources_and_defaults() -> None:
    old_tcp = ctl.tcp_connect
    old_gateway = ctl.get_default_gateway
    old_local = ctl.get_local_ipv4_cidrs
    old_dns = ctl.get_system_dns_server
    old_apt = ctl.get_apt_source_domains
    ctl.tcp_connect = lambda host, port: (True, "ok")
    ctl.get_default_gateway = lambda: "192.168.56.1"
    ctl.get_local_ipv4_cidrs = lambda: ["192.168.56.0/24"]
    ctl.get_system_dns_server = lambda: "192.168.56.1"
    ctl.get_apt_source_domains = lambda: [".mirror.internal.example"]
    try:
        config = ctl.normalize_config({"proxy_host": "192.168.56.2", "proxy_protocol": "socks5"})
        assert config["bypass_system_packages"] is True
        assert config["bypass_container_registries"] is False
        assert config["dns_strategy"] == "ipv4_only"
        assert ".mirror.internal.example" in config["bypass_domains"]
        assert ".docker.io" not in config["bypass_domains"]
        assert "apt-get" in config["bypass_processes"]
        enabled = ctl.normalize_config({"proxy_host": "192.168.56.2", "proxy_protocol": "socks5", "bypass_container_registries": True})
        assert ".docker.io" in enabled["bypass_domains"]
        disabled = ctl.normalize_config({"proxy_host": "192.168.56.2", "proxy_protocol": "socks5", "bypass_system_packages": False})
        assert "apt-get" not in disabled["bypass_processes"]
        domain_host = ctl.normalize_config({"proxy_host": "proxy.vmware.local", "proxy_protocol": "socks5"})
        assert not any("proxy.vmware.local" in cidr for cidr in domain_host["bypass_cidrs"])
        custom = ctl.normalize_config({
            "proxy_host": "192.168.56.2",
            "proxy_protocol": "socks5",
            "bypass_domains": ["HTTPS://Example.COM/path", "*.Corp.Local.", ".LAN."],
        })
        assert "example.com" in custom["bypass_domains"]
        assert ".corp.local" in custom["bypass_domains"]
        assert ".lan" in custom["bypass_domains"]
        try:
            ctl.normalize_config({"proxy_host": "192.168.56.2", "proxy_protocol": "socks5", "proxy_port": "bad"})
        except ctl.GatewayError as exc:
            assert "proxy_port" in str(exc)
        else:
            raise AssertionError("invalid proxy_port should fail")
    finally:
        ctl.tcp_connect = old_tcp
        ctl.get_default_gateway = old_gateway
        ctl.get_local_ipv4_cidrs = old_local
        ctl.get_system_dns_server = old_dns
        ctl.get_apt_source_domains = old_apt


def test_stop_missing_unit_is_safe() -> None:
    old_run = ctl.run
    old_is_root = ctl.is_root
    old_unit = ctl.SYSTEMD_UNIT
    ctl.is_root = lambda: True
    ctl.SYSTEMD_UNIT = Path("/tmp/vm-proxy-gateway-unit-that-does-not-exist.service")
    ctl.run = lambda cmd, check=True: FakeResult(stderr="Unit vm-proxy-gateway.service could not be found.\n", returncode=5)
    try:
        ctl.service_action("stop")
    finally:
        ctl.run = old_run
        ctl.is_root = old_is_root
        ctl.SYSTEMD_UNIT = old_unit


def test_apply_restarts_active_service() -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, check=True):
        calls.append(cmd)
        if cmd[:2] == ["systemctl", "is-active"]:
            return FakeResult("active\n")
        return FakeResult()

    old_run = ctl.run
    old_is_root = ctl.is_root
    old_normalize = ctl.normalize_config
    old_system_dir = ctl.SYSTEM_DIR
    old_system_config = ctl.SYSTEM_CONFIG
    old_sing_box_config = ctl.SING_BOX_CONFIG
    old_unit = ctl.SYSTEMD_UNIT
    ctl.run = fake_run
    ctl.is_root = lambda: True
    ctl.normalize_config = lambda raw: {
        "proxy_host": "192.168.56.2",
        "proxy_port": 10086,
        "proxy_protocol": "socks5",
        "local_dns": "192.168.56.1",
        "dns_strategy": "ipv4_only",
        "bypass_cidrs": ["127.0.0.0/8"],
        "bypass_domains": ["localhost"],
        "bypass_processes": [],
        "block_udp_when_unsupported": False,
        "bypass_system_packages": True,
        "bypass_container_registries": False,
        "apt_source_domains": [],
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ctl.SYSTEM_DIR = root / "etc"
        ctl.SYSTEM_CONFIG = ctl.SYSTEM_DIR / "config.json"
        ctl.SING_BOX_CONFIG = ctl.SYSTEM_DIR / "sing-box.json"
        ctl.SYSTEMD_UNIT = root / "vm-proxy-gateway.service"
        config_path = root / "user.json"
        config_path.write_text("{}", encoding="utf-8")
        try:
            ctl.apply_config(config_path, restart_active=True)
            assert ["systemctl", "restart", "vm-proxy-gateway.service"] in calls
        finally:
            ctl.run = old_run
            ctl.is_root = old_is_root
            ctl.normalize_config = old_normalize
            ctl.SYSTEM_DIR = old_system_dir
            ctl.SYSTEM_CONFIG = old_system_config
            ctl.SING_BOX_CONFIG = old_sing_box_config
            ctl.SYSTEMD_UNIT = old_unit


def test_single_instance_lock() -> None:
    old_lock_file = gui.LOCK_FILE
    with tempfile.TemporaryDirectory() as tmp:
        gui.LOCK_FILE = Path(tmp) / "gui.lock"
        lock = gui.acquire_single_instance()
        try:
            assert lock is not None
            assert gui.acquire_single_instance() is None
        finally:
            if lock:
                lock.close()
            gui.LOCK_FILE = old_lock_file


def test_active_tray_icon_tint() -> None:
    assert gui.Image is not None
    image = gui.Image.new("RGBA", (2, 2), (20, 40, 80, 255))
    image.putpixel((0, 0), (0, 0, 0, 0))
    tinted = gui.make_active_tray_image(image)
    transparent = tinted.getpixel((0, 0))
    colored = tinted.getpixel((1, 1))
    assert transparent[3] == 0
    assert colored[0] > colored[1] > colored[2]
    assert colored[0] >= 151
    assert colored[1] >= 84


def test_sing_box_config_shape() -> None:
    config = {
        "proxy_host": "192.168.56.2",
        "proxy_port": 10086,
        "proxy_protocol": "socks5",
        "local_dns": "192.168.56.1",
        "dns_strategy": "ipv4_only",
        "bypass_cidrs": ["127.0.0.0/8", "192.168.56.0/24"],
        "bypass_domains": ["localhost", ".ubuntu.com", ".mirror.internal.example"],
        "bypass_processes": ["apt", "apt-get", "http", "https"],
        "block_udp_when_unsupported": True,
    }
    sing = ctl.build_sing_box_config(config)
    assert sing["dns"]["strategy"] == "ipv4_only"
    assert sing["dns"]["servers"][1]["address"] == "192.168.56.1"
    assert sing["dns"]["servers"][1]["detour"] == "direct"
    assert sing["route"]["rules"][0]["protocol"] == "dns"
    assert sing["route"]["rules"][0]["outbound"] == "dns-out"
    assert any(rule.get("network") == "udp" and rule.get("outbound") == "block" for rule in sing["route"]["rules"])
    assert any("apt-get" in rule.get("process_name", []) for rule in sing["route"]["rules"])
    assert any("ubuntu.com" in rule.get("domain_suffix", []) for rule in sing["route"]["rules"])
    assert any(outbound["tag"] == "dns-out" and outbound["type"] == "dns" for outbound in sing["outbounds"])
    sing_box = Path("/usr/local/bin/sing-box")
    if sing_box.exists():
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(sing, f)
            tmp = Path(f.name)
        try:
            result = subprocess.run([str(sing_box), "check", "-c", str(tmp)], text=True, capture_output=True)
            assert result.returncode == 0, result.stderr or result.stdout
        finally:
            tmp.unlink(missing_ok=True)


def main() -> int:
    checks = [
        ("dns_from_resolvectl", test_dns_from_resolvectl),
        ("dns_from_resolv_conf", test_dns_from_resolv_conf),
        ("dns_falls_back_to_gateway", test_dns_falls_back_to_gateway),
        ("apt_sources_deb822_and_list", test_apt_sources_deb822_and_list),
        ("normalize_uses_dynamic_apt_sources_and_defaults", test_normalize_uses_dynamic_apt_sources_and_defaults),
        ("stop_missing_unit_is_safe", test_stop_missing_unit_is_safe),
        ("apply_restarts_active_service", test_apply_restarts_active_service),
        ("single_instance_lock", test_single_instance_lock),
        ("active_tray_icon_tint", test_active_tray_icon_tint),
        ("sing_box_config_shape", test_sing_box_config_shape),
    ]
    for name, func in checks:
        check(name, func)
    print(f"PASS all {len(checks)} scenario checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
