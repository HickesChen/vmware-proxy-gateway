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


class FakeGetVar:
    def __init__(self, value: str):
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


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
        wildcard = ctl.normalize_config({
            "proxy_host": "192.168.56.2",
            "proxy_protocol": "socks5",
            "bypass_cidrs": ["192.168.10.*", "10.*.*.*"],
        })
        assert "192.168.10.0/24" in wildcard["bypass_cidrs"]
        assert "10.0.0.0/8" in wildcard["bypass_cidrs"]
        structured = ctl.normalize_config({
            "proxy_host": "192.168.56.2",
            "proxy_protocol": "socks5",
            "bypass_rules": [
                {"type": "domain_keyword", "value": "GitHub", "invert": False},
                {"type": "domain_prefix", "value": "mirror-", "invert": False},
                {"type": "ip_cidr", "value": "172.20.*.*", "invert": True},
            ],
        })
        assert structured["bypass_rules"][0]["value"] == "github"
        assert structured["bypass_rules"][2] == {
            "type": "ip_cidr",
            "value": "172.20.0.0/16",
            "invert": True,
        }
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


def test_wildcard_cidr_validation() -> None:
    assert ctl.normalize_bypass_cidr("192.168.*.*") == "192.168.0.0/16"
    assert ctl.normalize_bypass_cidr("*") == "0.0.0.0/0"
    try:
        ctl.normalize_bypass_cidr("192.*.1.*")
    except ValueError as exc:
        assert "trailing" in str(exc)
    else:
        raise AssertionError("non-trailing wildcard should fail")


def test_traffic_log_parser() -> None:
    raw = (
        "+0800 2026-07-10 09:24:37 INFO [2967477805 9ms] "
        "outbound/socks[proxy]: outbound connection to chatgpt.com:443\n"
        "+0800 2026-07-10 09:24:38 INFO [330599505 8ms] "
        "outbound/direct[direct]: outbound packet connection to 185.125.190.58:123\n"
    )
    entries = ctl.parse_traffic_logs(raw, "192.168.56.1:10086")
    assert len(entries) == 2
    assert entries[1]["destination"] == "chatgpt.com"
    assert entries[1]["port"] == 443
    assert entries[1]["via"] == "192.168.56.1:10086"
    assert entries[0]["route"] == "direct"
    assert entries[0]["network"] == "udp"


def test_traffic_stats_and_speed_format() -> None:
    old_run = ctl.run
    old_root = ctl.is_root
    old_config = ctl.SYSTEM_CONFIG
    ctl.is_root = lambda: True
    ctl.SYSTEM_CONFIG = Path("/tmp/nonexistent-vm-proxy-config")
    ctl.run = lambda cmd, check=True: FakeResult(
        'counter packets 4 bytes 4096 comment "upload"\n'
        'counter packets 8 bytes 8192 comment "download"\n'
    )
    try:
        stats = ctl.traffic_stats()
    finally:
        ctl.run = old_run
        ctl.is_root = old_root
        ctl.SYSTEM_CONFIG = old_config
    assert stats["available"] is True
    assert stats["upload_bytes"] == 4096
    assert stats["download_bytes"] == 8192
    assert gui.App._format_speed(0) == "0 B/s"
    assert gui.App._format_speed(1536) == "1.5 KB/s"

    script = ctl.build_proxy_traffic_nft_script(["192.0.2.10", "2001:db8::10"], 10086)
    assert "ip daddr 192.0.2.10 tcp dport 10086" in script
    assert "ip6 saddr 2001:db8::10 udp sport 10086" in script
    assert script.count('comment "upload"') == 4
    assert script.count('comment "download"') == 4


def test_app_autostart_desktop_entry() -> None:
    old_autostart = gui.AUTOSTART_FILE
    with tempfile.TemporaryDirectory() as tmp:
        gui.AUTOSTART_FILE = Path(tmp) / "autostart" / "vm-proxy-gateway.desktop"
        try:
            gui.configure_app_autostart(True)
            content = gui.AUTOSTART_FILE.read_text(encoding="utf-8")
            assert "--autostart" in content
            assert "X-GNOME-Autostart-enabled=true" in content
            gui.configure_app_autostart(False)
            assert not gui.AUTOSTART_FILE.exists()
        finally:
            gui.AUTOSTART_FILE = old_autostart


def test_gui_log_keeps_popup_content() -> None:
    app = object.__new__(gui.App)
    app.language_code = "zh_CN"
    app._last_log_title = ""
    app._last_log_content = ""
    result = FakeResult(
        stdout=json.dumps({
            "proxy": "socks5://192.168.31.203:10086",
            "proxy_reachable": True,
            "proxy_http_test": "ok",
            "proxy_public_ip": "203.0.113.8",
        })
    )
    gui.App.log(app, "测试", result, kind="test")
    assert "正在检查代理连通性" in app._last_log_content
    assert "出口 IP：203.0.113.8" in app._last_log_content


def test_gui_effective_rules_include_protection() -> None:
    app = object.__new__(gui.App)
    app.proxy_host = FakeGetVar("192.168.31.203")
    app.bypass_rules = [{"type": "domain_keyword", "value": "mirror", "invert": False}]
    app._effective_cidrs = set(gui.PROTECTIVE_BYPASS_CIDRS)
    app._effective_domains = set(gui.PROTECTIVE_BYPASS_DOMAINS)
    app._local_cidrs = {"192.168.31.0/24", "192.168.31.88/32"}
    app._default_gateway = "192.168.31.1"
    rows = gui.App._effective_rule_rows(app)
    values = {row["value"] for row in rows}
    for expected in {
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "localhost",
        "192.168.31.0/24",
        "192.168.31.88/32",
        "192.168.31.1/32",
        "192.168.31.203/32",
        "mirror",
    }:
        assert expected in values
    assert all(not row["editable"] for row in rows if row["value"] != "mirror")


def test_gui_traffic_block_filter_and_sort() -> None:
    app = object.__new__(gui.App)
    app.traffic_search = FakeGetVar("")
    app.traffic_route = FakeGetVar("block")
    app._traffic_sort_column = "port"
    app._traffic_sort_reverse = False
    app._traffic_entries = [
        {"destination": "dns.example", "port": 53, "route": "block", "network": "udp"},
        {"destination": "ntp.example", "port": 123, "route": "block", "network": "udp"},
        {"destination": "web.example", "port": 443, "route": "proxy", "network": "tcp"},
    ]
    visible = gui.App._sorted_visible_traffic_entries(app)
    assert [entry["port"] for entry in visible] == [53, 123]


def test_gui_discover_populates_and_shows_result() -> None:
    app = object.__new__(gui.App)
    app.language_code = "zh_CN"
    app.proxy_host = FakeGetVar("")
    app._last_log_title = ""
    app._last_log_content = ""
    calls = []
    app._set_button_busy = lambda key, text_key: calls.append(("busy", key, text_key))
    app._restore_button = lambda key: calls.append(("restore", key))
    app._update_effective_rule_context = lambda data: calls.append(("rules", data["default_gateway"]))
    app._set_status = lambda key, **kwargs: calls.append(("status", key, kwargs))
    app._show_result = lambda title, ok, warning=False: calls.append(("popup", title, ok, warning))
    app.maybe_notify_tray_action = lambda ok=True: None
    old_controller = gui.run_controller
    gui.run_controller = lambda command: FakeResult(json.dumps({
        "default_gateway": "192.168.31.1",
        "local_cidrs": ["192.168.31.0/24"],
        "proxy_candidates": ["192.168.31.1"],
    }))
    try:
        gui.App.discover(app)
    finally:
        gui.run_controller = old_controller
    assert app.proxy_host.get() == "192.168.31.1"
    assert ("busy", "discover", "discovering") in calls
    assert ("popup", "发现", True, False) in calls


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
    old_accounting = ctl.configure_proxy_traffic_accounting
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
    ctl.configure_proxy_traffic_accounting = lambda host, port: calls.append(["accounting", host, str(port)])
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
            assert ["systemctl", "disable", "vm-proxy-gateway.service"] in calls
        finally:
            ctl.run = old_run
            ctl.is_root = old_is_root
            ctl.normalize_config = old_normalize
            ctl.SYSTEM_DIR = old_system_dir
            ctl.SYSTEM_CONFIG = old_system_config
            ctl.SING_BOX_CONFIG = old_sing_box_config
            ctl.SYSTEMD_UNIT = old_unit
            ctl.configure_proxy_traffic_accounting = old_accounting


def test_shell_proxy_reconciliation() -> None:
    new = {"proxy_host": "10.211.181.216", "proxy_port": 10086, "proxy_protocol": "socks5"}
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        profile = home / ".profile"
        profile.write_text(
            "export USER_PROXY=http://manual.example:8080\n"
            "export HTTP_PROXY=http://192.168.0.6:10086\n"
            "export HTTPS_PROXY=http://192.168.0.6:10086\n"
            "export ALL_PROXY=socks5h://192.168.0.6:10086\n",
            encoding="utf-8",
        )
        # Migration must work even if config.json has already moved to the new endpoint.
        assert ctl.reconcile_shell_proxy(home, new, new) is True
        content = profile.read_text(encoding="utf-8")
        assert "192.168.0.6" not in content
        assert content.count(ctl.SHELL_BLOCK_BEGIN) == 1
        assert "HTTP_PROXY=http://10.211.181.216:10086" in content
        assert "export USER_PROXY=http://manual.example:8080" in content
        assert ctl.reconcile_shell_proxy(home, new, new) is False
        assert profile.read_text(encoding="utf-8") == content
        assert ctl.reconcile_shell_proxy(home, None) is True
        cleaned = profile.read_text(encoding="utf-8")
        assert ctl.SHELL_BLOCK_BEGIN not in cleaned
        assert "export USER_PROXY=http://manual.example:8080" in cleaned


def test_shell_proxy_preserves_unmanaged_exports() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        profile = home / ".profile"
        manual = "export HTTP_PROXY=http://manual.example:3128\n"
        profile.write_text(manual, encoding="utf-8")
        assert ctl.reconcile_shell_proxy(home, None) is False
        assert profile.read_text(encoding="utf-8") == manual


def test_stale_vscode_proxy_process_detection() -> None:
    config = {"proxy_host": "10.211.181.216", "proxy_port": 10086, "proxy_protocol": "socks5"}
    with tempfile.TemporaryDirectory() as tmp:
        proc = Path(tmp)
        stale = proc / "12345"
        stale.mkdir()
        stale.joinpath("cmdline").write_bytes(b"/home/user/.vscode-server/bin/code-server\0--start-server\0")
        stale.joinpath("environ").write_bytes(
            b"HTTP_PROXY=http://192.168.0.6:10086\0"
            b"HTTPS_PROXY=http://192.168.0.6:10086\0"
            b"ALL_PROXY=socks5h://192.168.0.6:10086\0"
        )
        current = proc / "12346"
        current.mkdir()
        current.joinpath("cmdline").write_bytes(b"/home/user/.vscode-server/bin/code-server\0")
        current.joinpath("environ").write_bytes(
            b"HTTP_PROXY=http://10.211.181.216:10086\0"
            b"ALL_PROXY=socks5h://10.211.181.216:10086\0"
        )
        found = ctl.stale_proxy_processes(config, stale.stat().st_uid, proc)
        assert [item["pid"] for item in found] == [12345]
        assert found[0]["proxy"]["HTTP_PROXY"] == "http://192.168.0.6:10086"


def test_diagnose_reports_common_checks_and_solutions() -> None:
    names = [
        "get_default_gateway", "get_system_dns_server", "get_apt_source_domains",
        "get_local_ipv4_cidrs", "is_service_active", "tcp_connect",
        "user_home_for_config", "stale_proxy_processes", "run",
    ]
    originals = {name: getattr(ctl, name) for name in names}
    old_paths = (ctl.SYSTEM_CONFIG, ctl.SING_BOX_CONFIG, ctl.SYSTEMD_UNIT)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = root / "config.json"
        config.write_text(json.dumps({
            "proxy_host": "192.0.2.10", "proxy_port": 10086, "proxy_protocol": "socks5",
        }), encoding="utf-8")
        ctl.SYSTEM_CONFIG = root / "missing-system.json"
        ctl.SING_BOX_CONFIG = root / "missing-sing.json"
        ctl.SYSTEMD_UNIT = root / "missing.service"
        ctl.get_default_gateway = lambda: "192.0.2.1"
        ctl.get_system_dns_server = lambda: "192.0.2.53"
        ctl.get_apt_source_domains = lambda: []
        ctl.get_local_ipv4_cidrs = lambda: ["192.0.2.0/24"]
        ctl.is_service_active = lambda: False
        ctl.tcp_connect = lambda host, port: (False, "connection refused")
        ctl.user_home_for_config = lambda path=None: root
        ctl.stale_proxy_processes = lambda config, uid: []
        ctl.run = lambda cmd, check=True: FakeResult(returncode=1, stderr="unavailable")
        try:
            result = ctl.diagnose(config, repair=False)
        finally:
            for name, value in originals.items():
                setattr(ctl, name, value)
            ctl.SYSTEM_CONFIG, ctl.SING_BOX_CONFIG, ctl.SYSTEMD_UNIT = old_paths
    checks = result["diagnostic_checks"]
    assert len(checks) >= 10
    assert len({item["id"] for item in checks}) == len(checks)
    assert all(item.get("solution") for item in checks if not item["ok"])


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
        "bypass_rules": [
            {"type": "domain_keyword", "value": "github", "invert": False},
            {"type": "domain_prefix", "value": "mirror-", "invert": False},
            {"type": "domain_regex", "value": r"^api[0-9]+\\.example\\.com$", "invert": True},
        ],
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
    assert any("github" in rule.get("domain_keyword", []) for rule in sing["route"]["rules"])
    assert any("^mirror\\-" in rule.get("domain_regex", []) for rule in sing["route"]["rules"])
    assert any(rule.get("invert") is True for rule in sing["route"]["rules"])
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
        ("wildcard_cidr_validation", test_wildcard_cidr_validation),
        ("traffic_log_parser", test_traffic_log_parser),
        ("traffic_stats_and_speed_format", test_traffic_stats_and_speed_format),
        ("app_autostart_desktop_entry", test_app_autostart_desktop_entry),
        ("gui_log_keeps_popup_content", test_gui_log_keeps_popup_content),
        ("gui_effective_rules_include_protection", test_gui_effective_rules_include_protection),
        ("gui_traffic_block_filter_and_sort", test_gui_traffic_block_filter_and_sort),
        ("gui_discover_populates_and_shows_result", test_gui_discover_populates_and_shows_result),
        ("stop_missing_unit_is_safe", test_stop_missing_unit_is_safe),
        ("apply_restarts_active_service", test_apply_restarts_active_service),
        ("shell_proxy_reconciliation", test_shell_proxy_reconciliation),
        ("shell_proxy_preserves_unmanaged_exports", test_shell_proxy_preserves_unmanaged_exports),
        ("stale_vscode_proxy_process_detection", test_stale_vscode_proxy_process_detection),
        ("diagnose_reports_common_checks_and_solutions", test_diagnose_reports_common_checks_and_solutions),
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
