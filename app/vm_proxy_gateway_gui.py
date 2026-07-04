#!/usr/bin/env python3
"""
Tkinter GUI for vm-proxy-gateway.
"""

from __future__ import annotations

import json
import fcntl
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

try:
    import pystray
    from PIL import Image
except Exception:
    pystray = None
    Image = None


APP_NAME = "VM Proxy Gateway"
USER_CONFIG = Path.home() / ".config" / "vm-proxy-gateway" / "config.json"
LOCK_FILE = Path.home() / ".config" / "vm-proxy-gateway" / "gui.lock"
CONTROLLER = Path("/opt/vm-proxy-gateway/vm_proxy_gateway.py")
ICON_NAME = "vm-proxy-gateway.png"
DEFAULT_CONFIG = {
    "proxy_host": "",
    "proxy_port": 10086,
    "proxy_protocol": "auto",
    "bypass_cidrs": [],
    "bypass_domains": [],
    "block_udp_when_unsupported": False,
    "bypass_system_packages": True,
    "bypass_container_registries": False,
    "language": "zh_CN",
}
LANGUAGES = {
    "en": "English",
    "zh_CN": "简体中文",
    "zh_TW": "繁體中文",
}
TEXT = {
    "en": {
        "language": "Language",
        "proxy_host": "Proxy host",
        "proxy_port": "Proxy port",
        "protocol": "Protocol",
        "discover": "Discover",
        "block_udp": "Block UDP when upstream support is unknown",
        "save": "Save",
        "apply": "Apply",
        "turn_on": "Turn On",
        "turn_off": "Turn Off",
        "test": "Test",
        "diagnose": "Diagnose",
        "refresh": "Refresh",
        "bypass_cidrs": "Bypass CIDRs / IPs",
        "bypass_domains": "Bypass domains / suffixes",
        "bypass_system_packages": "Bypass system package downloads (APT / Snap / Flatpak)",
        "bypass_container_registries": "Bypass container image registries (Docker / Podman)",
        "status_not_checked": "Status: not checked",
        "status_saved": "Status: saved to {path}",
        "status_not_installed": "Status: not installed under /opt/vm-proxy-gateway",
        "status_missing_controller": "Missing controller: {path}\nRun install.sh inside the Ubuntu VM.",
        "status_summary": "Status: {active} | enabled: {enabled} | proxy: {host}:{port}",
        "status_non_json": "Status: command returned non-JSON output",
        "status_failed": "Status: failed to query service",
        "status_discovered": "Status: discovered candidate {candidate}",
        "port_number": "Proxy port must be a number.",
        "port_range": "Proxy port must be between 1 and 65535.",
        "apply_failed": "Apply failed. See output for details.",
        "log_apply": "Apply",
        "log_turn_on": "Turn On",
        "log_turn_off": "Turn Off",
        "log_test": "Test",
        "log_diagnose": "Diagnose",
        "log_status": "Status",
        "log_discover": "Discover",
        "exit_code": "Exit code: {code}",
        "yes": "yes",
        "no": "no",
        "unknown": "unknown",
        "enabled_yes": "yes",
        "enabled_no": "no",
        "service_active": "The proxy service is running.",
        "service_inactive": "The proxy service is not running.",
        "service_enabled": "It will start automatically after reboot: {enabled}.",
        "service_config": "Installed config: {config}; proxy engine config: {engine}.",
        "proxy_target": "Proxy address: {host}:{port}.",
        "proxy_missing": "No proxy address has been applied yet. Enter the Windows host IP, then click Apply.",
        "proxy_reachable": "The Ubuntu VM can connect to the proxy port.",
        "proxy_unreachable": "The Ubuntu VM cannot connect to the proxy port. {error}",
        "local_network": "Detected VM network: gateway {gateway}; local ranges {cidrs}.",
        "local_dns": "Direct DNS server: {dns}.",
        "apt_sources": "Detected APT source domains: {domains}.",
        "test_tcp_ok": "Step 1 passed: the proxy port accepts connections.",
        "test_tcp_bad": "Step 1 failed: the proxy port cannot be reached. {error}",
        "test_web_ok": "Step 2 passed: internet traffic can go through the proxy. Public IP: {ip}.",
        "test_web_bad": "Step 2 failed: the proxy port was reached, but web traffic did not work. {error}",
        "test_proxy": "Testing proxy: {proxy}.",
        "diagnose_configured": "Configured proxy: {host}:{port}.",
        "diagnose_no_host": "No proxy host is configured yet.",
        "diagnose_gateway": "VM default gateway: {gateway}.",
        "diagnose_tcp_ok": "Can connect to {target}.",
        "diagnose_tcp_bad": "Cannot connect to {target}. {error}",
        "diagnose_advice": "Suggestions:",
        "discover_found": "Suggested proxy host: {candidate}. This is usually the Windows host address for NAT mode.",
        "discover_none": "No candidate proxy host was found automatically. Enter the Windows host IP manually.",
        "discover_gateway": "Detected VM default gateway: {gateway}.",
        "operation_ok": "Done.",
        "operation_failed": "This operation failed. {error}",
        "apply_ok": "Settings have been applied. You can now turn the proxy service on.",
        "apply_start_ok": "Settings have been applied and the proxy service is running.",
        "start_ok": "Proxy service has been turned on.",
        "stop_ok": "Proxy service has been turned off.",
        "advice_no_proxy": "No proxy host is configured and no default gateway was detected. Enter the Windows host IP manually.",
        "advice_listen": "Make sure the Windows proxy listens on {target}, not only on 127.0.0.1.",
        "advice_lan": "In your Windows proxy app, enable LAN access, allow LAN, or bind to 0.0.0.0.",
        "advice_firewall": "Allow inbound TCP {port} in Windows Defender Firewall on the private network.",
        "advice_ping": "Do not use ping as the final test. Windows often blocks ping even when the proxy port works.",
        "advice_reachable": "The proxy TCP port is reachable from the Ubuntu VM.",
        "tray_show": "Open Window",
        "tray_exit": "Exit",
        "tray_tooltip": "VM Proxy Gateway",
        "tray_minimized": "The app is still running in the system tray. Use the tray icon to open it or exit safely.",
        "tray_unavailable": "System tray support is not available. Install pystray and Pillow, then restart the app.",
        "exit_stopping": "Closing proxy service before exit...",
        "exit_stop_failed": "The app could not turn off the proxy before exit. See output for details.",
        "tray_action_failed": "Action failed",
        "already_running": "VM Proxy Gateway is already running. Use the existing window or tray icon.",
    },
    "zh_CN": {
        "language": "语言",
        "proxy_host": "代理主机",
        "proxy_port": "代理端口",
        "protocol": "协议",
        "discover": "发现",
        "block_udp": "上游支持未知时阻止 UDP",
        "save": "保存",
        "apply": "应用",
        "turn_on": "开启",
        "turn_off": "关闭",
        "test": "测试",
        "diagnose": "诊断",
        "refresh": "刷新",
        "bypass_cidrs": "绕过 CIDR / IP",
        "bypass_domains": "绕过域名 / 后缀",
        "bypass_system_packages": "绕过系统包下载（APT / Snap / Flatpak）",
        "bypass_container_registries": "绕过容器镜像仓库（Docker / Podman）",
        "status_not_checked": "状态：未检查",
        "status_saved": "状态：已保存到 {path}",
        "status_not_installed": "状态：未安装到 /opt/vm-proxy-gateway",
        "status_missing_controller": "缺少控制器：{path}\n请在 Ubuntu 虚拟机中运行 install.sh。",
        "status_summary": "状态：{active} | 已启用：{enabled} | 代理：{host}:{port}",
        "status_non_json": "状态：命令返回了非 JSON 输出",
        "status_failed": "状态：查询服务失败",
        "status_discovered": "状态：已发现候选地址 {candidate}",
        "port_number": "代理端口必须是数字。",
        "port_range": "代理端口必须在 1 到 65535 之间。",
        "apply_failed": "应用失败。请查看输出详情。",
        "log_apply": "应用",
        "log_turn_on": "开启",
        "log_turn_off": "关闭",
        "log_test": "测试",
        "log_diagnose": "诊断",
        "log_status": "状态",
        "log_discover": "发现",
        "exit_code": "退出码：{code}",
        "yes": "是",
        "no": "否",
        "unknown": "未知",
        "enabled_yes": "是",
        "enabled_no": "否",
        "service_active": "代理服务正在运行。",
        "service_inactive": "代理服务没有运行。",
        "service_enabled": "开机自动启动：{enabled}。",
        "service_config": "已安装配置：{config}；代理引擎配置：{engine}。",
        "proxy_target": "代理地址：{host}:{port}。",
        "proxy_missing": "还没有应用代理地址。请先填写 Windows 主机 IP，然后点击“应用”。",
        "proxy_reachable": "Ubuntu 虚拟机可以连接到代理端口。",
        "proxy_unreachable": "Ubuntu 虚拟机连不上代理端口。{error}",
        "local_network": "检测到的虚拟机网络：网关 {gateway}；本机网段 {cidrs}。",
        "local_dns": "直连 DNS 服务器：{dns}。",
        "apt_sources": "检测到的 APT 源域名：{domains}。",
        "test_tcp_ok": "第 1 步通过：代理端口可以连接。",
        "test_tcp_bad": "第 1 步失败：代理端口连不上。{error}",
        "test_web_ok": "第 2 步通过：网络流量可以通过代理访问互联网。出口 IP：{ip}。",
        "test_web_bad": "第 2 步失败：代理端口已连上，但网页访问没有成功。{error}",
        "test_proxy": "正在测试代理：{proxy}。",
        "diagnose_configured": "当前填写的代理：{host}:{port}。",
        "diagnose_no_host": "还没有填写代理主机。",
        "diagnose_gateway": "虚拟机默认网关：{gateway}。",
        "diagnose_tcp_ok": "可以连接到 {target}。",
        "diagnose_tcp_bad": "无法连接到 {target}。{error}",
        "diagnose_advice": "建议：",
        "discover_found": "建议的代理主机：{candidate}。NAT 模式下这通常就是 Windows 主机地址。",
        "discover_none": "没有自动发现候选代理主机。请手动填写 Windows 主机 IP。",
        "discover_gateway": "检测到的虚拟机默认网关：{gateway}。",
        "operation_ok": "操作已完成。",
        "operation_failed": "操作失败。{error}",
        "apply_ok": "设置已应用。接下来可以点击“开启”启动代理服务。",
        "apply_start_ok": "设置已应用，代理服务已开启。",
        "start_ok": "代理服务已开启。",
        "stop_ok": "代理服务已关闭。",
        "advice_no_proxy": "没有填写代理主机，也没有检测到默认网关。请手动填写 Windows 主机 IP。",
        "advice_listen": "确认 Windows 上的代理正在监听 {target}，不要只监听 127.0.0.1。",
        "advice_lan": "在 Windows 代理软件里开启 LAN 访问 / 允许局域网 / 绑定到 0.0.0.0。",
        "advice_firewall": "在 Windows Defender 防火墙里允许专用网络入站 TCP {port}。",
        "advice_ping": "不要用 ping 作为最终判断。Windows 经常会拦截 ping，但代理端口仍然可用。",
        "advice_reachable": "Ubuntu 虚拟机可以连接到代理 TCP 端口。",
        "tray_show": "打开窗口",
        "tray_exit": "退出",
        "tray_tooltip": "VM Proxy Gateway",
        "tray_minimized": "程序仍在系统托盘运行。可以通过托盘图标重新打开，或安全退出。",
        "tray_unavailable": "系统托盘支持不可用。请安装 pystray 和 Pillow 后重启程序。",
        "exit_stopping": "正在退出前关闭代理服务...",
        "exit_stop_failed": "退出前未能关闭代理服务。请查看输出详情。",
        "tray_action_failed": "操作失败",
        "already_running": "VM Proxy Gateway 已经在运行。请使用已有窗口或托盘图标。",
    },
    "zh_TW": {
        "language": "語言",
        "proxy_host": "代理主機",
        "proxy_port": "代理連接埠",
        "protocol": "通訊協定",
        "discover": "偵測",
        "block_udp": "上游支援未知時阻擋 UDP",
        "save": "儲存",
        "apply": "套用",
        "turn_on": "開啟",
        "turn_off": "關閉",
        "test": "測試",
        "diagnose": "診斷",
        "refresh": "重新整理",
        "bypass_cidrs": "略過 CIDR / IP",
        "bypass_domains": "略過網域 / 後綴",
        "bypass_system_packages": "略過系統套件下載（APT / Snap / Flatpak）",
        "bypass_container_registries": "略過容器映像倉庫（Docker / Podman）",
        "status_not_checked": "狀態：尚未檢查",
        "status_saved": "狀態：已儲存到 {path}",
        "status_not_installed": "狀態：尚未安裝到 /opt/vm-proxy-gateway",
        "status_missing_controller": "缺少控制器：{path}\n請在 Ubuntu 虛擬機中執行 install.sh。",
        "status_summary": "狀態：{active} | 已啟用：{enabled} | 代理：{host}:{port}",
        "status_non_json": "狀態：命令回傳了非 JSON 輸出",
        "status_failed": "狀態：查詢服務失敗",
        "status_discovered": "狀態：已偵測到候選位址 {candidate}",
        "port_number": "代理連接埠必須是數字。",
        "port_range": "代理連接埠必須介於 1 到 65535 之間。",
        "apply_failed": "套用失敗。請查看輸出詳情。",
        "log_apply": "套用",
        "log_turn_on": "開啟",
        "log_turn_off": "關閉",
        "log_test": "測試",
        "log_diagnose": "診斷",
        "log_status": "狀態",
        "log_discover": "偵測",
        "exit_code": "結束碼：{code}",
        "yes": "是",
        "no": "否",
        "unknown": "未知",
        "enabled_yes": "是",
        "enabled_no": "否",
        "service_active": "代理服務正在執行。",
        "service_inactive": "代理服務沒有執行。",
        "service_enabled": "開機自動啟動：{enabled}。",
        "service_config": "已安裝設定：{config}；代理引擎設定：{engine}。",
        "proxy_target": "代理位址：{host}:{port}。",
        "proxy_missing": "尚未套用代理位址。請先填寫 Windows 主機 IP，然後點選「套用」。",
        "proxy_reachable": "Ubuntu 虛擬機可以連線到代理連接埠。",
        "proxy_unreachable": "Ubuntu 虛擬機無法連線到代理連接埠。{error}",
        "local_network": "偵測到的虛擬機網路：閘道 {gateway}；本機網段 {cidrs}。",
        "local_dns": "直連 DNS 伺服器：{dns}。",
        "apt_sources": "偵測到的 APT 來源網域：{domains}。",
        "test_tcp_ok": "第 1 步通過：代理連接埠可以連線。",
        "test_tcp_bad": "第 1 步失敗：代理連接埠無法連線。{error}",
        "test_web_ok": "第 2 步通過：網路流量可以透過代理連上網際網路。出口 IP：{ip}。",
        "test_web_bad": "第 2 步失敗：代理連接埠已連上，但網頁存取沒有成功。{error}",
        "test_proxy": "正在測試代理：{proxy}。",
        "diagnose_configured": "目前填寫的代理：{host}:{port}。",
        "diagnose_no_host": "尚未填寫代理主機。",
        "diagnose_gateway": "虛擬機預設閘道：{gateway}。",
        "diagnose_tcp_ok": "可以連線到 {target}。",
        "diagnose_tcp_bad": "無法連線到 {target}。{error}",
        "diagnose_advice": "建議：",
        "discover_found": "建議的代理主機：{candidate}。NAT 模式下這通常就是 Windows 主機位址。",
        "discover_none": "沒有自動偵測到候選代理主機。請手動填寫 Windows 主機 IP。",
        "discover_gateway": "偵測到的虛擬機預設閘道：{gateway}。",
        "operation_ok": "操作已完成。",
        "operation_failed": "操作失敗。{error}",
        "apply_ok": "設定已套用。接下來可以點選「開啟」啟動代理服務。",
        "apply_start_ok": "設定已套用，代理服務已開啟。",
        "start_ok": "代理服務已開啟。",
        "stop_ok": "代理服務已關閉。",
        "advice_no_proxy": "沒有填寫代理主機，也沒有偵測到預設閘道。請手動填寫 Windows 主機 IP。",
        "advice_listen": "確認 Windows 上的代理正在監聽 {target}，不要只監聽 127.0.0.1。",
        "advice_lan": "在 Windows 代理軟體中開啟 LAN 存取 / 允許區域網路 / 綁定到 0.0.0.0。",
        "advice_firewall": "在 Windows Defender 防火牆中允許私人網路入站 TCP {port}。",
        "advice_ping": "不要用 ping 作為最終判斷。Windows 經常會阻擋 ping，但代理連接埠仍然可用。",
        "advice_reachable": "Ubuntu 虛擬機可以連線到代理 TCP 連接埠。",
        "tray_show": "開啟視窗",
        "tray_exit": "退出",
        "tray_tooltip": "VM Proxy Gateway",
        "tray_minimized": "程式仍在系統匣執行。可以透過系統匣圖示重新開啟，或安全退出。",
        "tray_unavailable": "系統匣支援不可用。請安裝 pystray 和 Pillow 後重新啟動程式。",
        "exit_stopping": "正在退出前關閉代理服務...",
        "exit_stop_failed": "退出前未能關閉代理服務。請查看輸出詳情。",
        "tray_action_failed": "操作失敗",
        "already_running": "VM Proxy Gateway 已經在執行。請使用既有視窗或系統匣圖示。",
    },
}


def load_config() -> dict:
    if not USER_CONFIG.exists():
        return dict(DEFAULT_CONFIG)
    with USER_CONFIG.open("r", encoding="utf-8") as f:
        config = json.load(f)
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    return merged


def save_config(config: dict) -> None:
    USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = USER_CONFIG.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    tmp.replace(USER_CONFIG)


def find_asset(name: str) -> Path | None:
    base = Path(__file__).resolve().parent
    for path in [base / "assets" / name, base.parent / "assets" / name]:
        if path.exists():
            return path
    return None


def run_user_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True)


def run_privileged(args: list[str]) -> subprocess.CompletedProcess[str]:
    if shutil.which("sudo"):
        sudo = subprocess.run(["sudo", "-n"] + args, text=True, capture_output=True)
        if sudo.returncode == 0 or "a password is required" not in sudo.stderr.lower():
            return sudo
    if shutil.which("pkexec"):
        return subprocess.run(["pkexec"] + args, text=True, capture_output=True)
    return subprocess.run(["sudo"] + args, text=True, capture_output=True)


def run_controller(command: str, privileged: bool = False, extra: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(CONTROLLER), command]
    if extra:
        args.extend(extra)
    if privileged:
        return run_privileged(args)
    return run_user_command(args)


def acquire_single_instance():
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock = LOCK_FILE.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    lock.write(str(os.getpid()))
    lock.flush()
    return lock


def show_already_running_message() -> None:
    config = load_config()
    language = str(config.get("language") or "zh_CN")
    if language not in TEXT:
        language = "zh_CN"
    root = tk.Tk(className="VmProxyGateway")
    root.withdraw()
    messagebox.showinfo(APP_NAME, TEXT[language]["already_running"])
    root.destroy()


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__(className="VmProxyGateway")
        self.title(APP_NAME)
        self.geometry("820x640")
        self.minsize(760, 580)
        self.config_data = load_config()

        self.proxy_host = tk.StringVar(value=str(self.config_data.get("proxy_host", "")))
        self.proxy_port = tk.StringVar(value=str(self.config_data.get("proxy_port", 10086)))
        self.proxy_protocol = tk.StringVar(value=str(self.config_data.get("proxy_protocol", "auto")))
        self.block_udp = tk.BooleanVar(value=bool(self.config_data.get("block_udp_when_unsupported", False)))
        self.bypass_system_packages = tk.BooleanVar(value=bool(self.config_data.get("bypass_system_packages", True)))
        self.bypass_container_registries = tk.BooleanVar(value=bool(self.config_data.get("bypass_container_registries", False)))
        language = str(self.config_data.get("language") or "zh_CN")
        if language not in LANGUAGES:
            language = "zh_CN"
        self.language_code = language
        self.language = tk.StringVar(value=LANGUAGES[language])
        self.status_text = tk.StringVar(value=self.tr("status_not_checked"))
        self._labels: dict[str, ttk.Label] = {}
        self._buttons: dict[str, ttk.Button] = {}
        self._checks: dict[str, ttk.Checkbutton] = {}
        self._last_status_key = "status_not_checked"
        self._last_status_kwargs: dict[str, object] = {}
        self._last_log_title = APP_NAME
        self._last_log_content = ""
        self._tray_action_title: str | None = None
        self._exiting = False
        self._tray_icon = None
        self._tray_thread: threading.Thread | None = None

        self._build()
        self._set_window_icon()
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.start_tray()
        self.refresh_status()

    def tr(self, key: str, **kwargs: object) -> str:
        text = TEXT[self.language_code][key]
        return text.format(**kwargs) if kwargs else text

    def _build(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        top = ttk.Frame(root)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        self._label(top, "language").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        language = ttk.Combobox(top, textvariable=self.language, values=list(LANGUAGES.values()), state="readonly", width=12)
        language.grid(row=0, column=1, sticky="w", pady=4)
        language.bind("<<ComboboxSelected>>", self.change_language)

        self._label(top, "proxy_host").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(top, textvariable=self.proxy_host).grid(row=1, column=1, sticky="ew", pady=4)
        self._button(top, "discover", self.discover).grid(row=1, column=2, padx=(8, 0), pady=4)

        self._label(top, "proxy_port").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(top, textvariable=self.proxy_port, width=12).grid(row=2, column=1, sticky="w", pady=4)

        self._label(top, "protocol").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        protocol = ttk.Combobox(top, textvariable=self.proxy_protocol, values=["auto", "socks5", "http"], state="readonly", width=12)
        protocol.grid(row=3, column=1, sticky="w", pady=4)

        self._check(top, "block_udp", self.block_udp).grid(row=4, column=1, sticky="w", pady=4)
        self._check(top, "bypass_system_packages", self.bypass_system_packages).grid(row=5, column=1, sticky="w", pady=4)
        self._check(top, "bypass_container_registries", self.bypass_container_registries).grid(row=6, column=1, sticky="w", pady=4)

        actions = ttk.Frame(root)
        actions.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        self._button(actions, "save", self.save).pack(side="left", padx=(0, 8))
        self._button(actions, "apply", self.apply).pack(side="left", padx=(0, 8))
        self._button(actions, "turn_on", self.turn_on).pack(side="left", padx=(0, 8))
        self._button(actions, "turn_off", self.turn_off).pack(side="left", padx=(0, 8))
        self._button(actions, "test", self.test).pack(side="left", padx=(0, 8))
        self._button(actions, "diagnose", self.diagnose).pack(side="left", padx=(0, 8))
        self._button(actions, "refresh", self.refresh_status).pack(side="left")

        panes = ttk.PanedWindow(root, orient="vertical")
        panes.grid(row=2, column=0, sticky="nsew")

        rules = ttk.Frame(panes, padding=(0, 4))
        rules.columnconfigure(0, weight=1)
        rules.columnconfigure(1, weight=1)
        rules.rowconfigure(1, weight=1)
        panes.add(rules, weight=3)

        self._label(rules, "bypass_cidrs").grid(row=0, column=0, sticky="w")
        self._label(rules, "bypass_domains").grid(row=0, column=1, sticky="w")
        self.cidr_text = tk.Text(rules, height=10, wrap="none")
        self.domain_text = tk.Text(rules, height=10, wrap="none")
        self.cidr_text.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(4, 0))
        self.domain_text.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(4, 0))
        self.cidr_text.insert("1.0", "\n".join(self.config_data.get("bypass_cidrs", [])))
        self.domain_text.insert("1.0", "\n".join(self.config_data.get("bypass_domains", [])))

        bottom = ttk.Frame(panes)
        bottom.columnconfigure(0, weight=1)
        bottom.rowconfigure(1, weight=1)
        panes.add(bottom, weight=2)

        ttk.Label(bottom, textvariable=self.status_text).grid(row=0, column=0, sticky="w", pady=(8, 4))
        self.output = tk.Text(bottom, height=9, wrap="word", state="disabled")
        self.output.grid(row=1, column=0, sticky="nsew")

    def _set_window_icon(self) -> None:
        path = find_asset(ICON_NAME)
        if not path:
            return
        try:
            self._window_icon = tk.PhotoImage(file=str(path))
            self.iconphoto(True, self._window_icon)
        except tk.TclError:
            pass

    def _tray_image(self):
        path = find_asset(ICON_NAME)
        if not path or Image is None:
            return None
        return Image.open(path)

    def _call_from_tray(self, callback: Callable[[], None], title: str | None = None) -> None:
        if not self._exiting:
            self.after(0, lambda: self._run_tray_action(callback, title))

    def _run_tray_action(self, callback: Callable[[], None], title: str | None) -> None:
        self._tray_action_title = title
        try:
            callback()
        finally:
            self._tray_action_title = None

    def notify_user(self, title: str, message: str, error: bool = False) -> None:
        if error:
            messagebox.showerror(title, message)
        else:
            messagebox.showinfo(title, message)

    def _tray_menu(self):
        if pystray is None:
            return None
        return pystray.Menu(
            pystray.MenuItem(self.tr("tray_show"), lambda _icon, _item: self._call_from_tray(self.show_window), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self.tr("apply"), lambda _icon, _item: self._call_from_tray(self.apply, self.tr("log_apply"))),
            pystray.MenuItem(self.tr("turn_on"), lambda _icon, _item: self._call_from_tray(self.turn_on, self.tr("log_turn_on"))),
            pystray.MenuItem(self.tr("turn_off"), lambda _icon, _item: self._call_from_tray(self.turn_off, self.tr("log_turn_off"))),
            pystray.MenuItem(self.tr("test"), lambda _icon, _item: self._call_from_tray(self.test, self.tr("log_test"))),
            pystray.MenuItem(self.tr("diagnose"), lambda _icon, _item: self._call_from_tray(self.diagnose, self.tr("log_diagnose"))),
            pystray.MenuItem(self.tr("refresh"), lambda _icon, _item: self._call_from_tray(self.refresh_status, self.tr("log_status"))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self.tr("tray_exit"), lambda _icon, _item: self._call_from_tray(self.safe_exit)),
        )

    def start_tray(self) -> None:
        if pystray is None:
            return
        image = self._tray_image()
        if image is None:
            return
        self._tray_icon = pystray.Icon("vm-proxy-gateway", image, self.tr("tray_tooltip"), self._tray_menu())
        self._tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True)
        self._tray_thread.start()

    def refresh_tray_menu(self) -> None:
        if self._tray_icon is not None:
            self._tray_icon.title = self.tr("tray_tooltip")
            self._tray_icon.menu = self._tray_menu()
            self._tray_icon.update_menu()

    def show_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide_to_tray(self) -> None:
        if self._tray_icon is None:
            messagebox.showinfo(APP_NAME, self.tr("tray_unavailable"))
            self.iconify()
            return
        self.withdraw()
        self.log(APP_NAME, self.tr("tray_minimized"))

    def safe_exit(self) -> None:
        if self._exiting:
            return
        self._exiting = True
        if not CONTROLLER.exists():
            if self._tray_icon is not None:
                self._tray_icon.stop()
                self._tray_icon = None
            self.destroy()
            return
        self.deiconify()
        self.log(self.tr("tray_exit"), self.tr("exit_stopping"))
        result = run_controller("stop", privileged=True)
        self.log(self.tr("log_turn_off"), result, kind="stop")
        if result.returncode != 0:
            messagebox.showerror(APP_NAME, self.tr("exit_stop_failed"))
            self._exiting = False
            return
        if self._tray_icon is not None:
            self._tray_icon.stop()
            self._tray_icon = None
        self.destroy()

    def _label(self, parent: tk.Widget, key: str) -> ttk.Label:
        label = ttk.Label(parent, text=self.tr(key))
        self._labels[key] = label
        return label

    def _button(self, parent: tk.Widget, key: str, command: Callable) -> ttk.Button:
        button = ttk.Button(parent, text=self.tr(key), command=command)
        self._buttons[key] = button
        return button

    def _check(self, parent: tk.Widget, key: str, variable: tk.BooleanVar) -> ttk.Checkbutton:
        check = ttk.Checkbutton(parent, text=self.tr(key), variable=variable)
        self._checks[key] = check
        return check

    def change_language(self, _event: tk.Event | None = None) -> None:
        selected = self.language.get()
        for code, name in LANGUAGES.items():
            if name == selected:
                self.language_code = code
                break
        self.refresh_text()
        self.refresh_tray_menu()
        config = load_config()
        config["language"] = self.language_code
        save_config(config)

    def refresh_text(self) -> None:
        for key, label in self._labels.items():
            label.configure(text=self.tr(key))
        for key, button in self._buttons.items():
            button.configure(text=self.tr(key))
        for key, check in self._checks.items():
            check.configure(text=self.tr(key))
        self._set_status(self._last_status_key, **self._last_status_kwargs)

    def _set_status(self, key: str, **kwargs: object) -> None:
        self._last_status_key = key
        self._last_status_kwargs = kwargs
        self.status_text.set(self.tr(key, **kwargs))

    def _yes_no(self, value: object) -> str:
        if value is True:
            return self.tr("yes")
        if value is False:
            return self.tr("no")
        return self.tr("unknown")

    def _enabled_text(self, value: object) -> str:
        if value == "enabled":
            return self.tr("enabled_yes")
        if value == "disabled":
            return self.tr("enabled_no")
        return str(value or self.tr("unknown"))

    def _join_items(self, items: object) -> str:
        if isinstance(items, list) and items:
            return ", ".join(str(item) for item in items)
        return self.tr("unknown")

    def _json_from_result(self, result: subprocess.CompletedProcess[str]) -> dict | None:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

    def _friendly_advice(self, advice: str) -> str:
        if advice.startswith("No proxy host is configured"):
            return self.tr("advice_no_proxy")
        if advice.startswith("Make sure the Windows proxy listens on "):
            target = advice.split(" listens on ", 1)[1].split(", not only", 1)[0]
            return self.tr("advice_listen", target=target)
        if advice.startswith("If you use Clash"):
            return self.tr("advice_lan")
        if advice.startswith("Allow inbound TCP "):
            port = advice.split("Allow inbound TCP ", 1)[1].split(" ", 1)[0]
            return self.tr("advice_firewall", port=port)
        if advice.startswith("Do not use ping"):
            return self.tr("advice_ping")
        if advice.startswith("The proxy TCP port is reachable"):
            return self.tr("advice_reachable")
        return advice

    def format_result(self, kind: str, result: subprocess.CompletedProcess[str] | str) -> str:
        if isinstance(result, str):
            return result

        error = result.stderr.strip()
        if result.returncode != 0:
            return self.tr("operation_failed", error=error or self.tr("exit_code", code=result.returncode))

        if kind == "apply":
            return self.tr("apply_ok")
        if kind == "apply-start":
            return self.tr("apply_start_ok")
        if kind == "start":
            return self.tr("start_ok")
        if kind == "stop":
            return self.tr("stop_ok")

        data = self._json_from_result(result)
        if kind == "status" and data:
            lines = [
                self.tr("service_active") if data.get("active") == "active" else self.tr("service_inactive"),
                self.tr("service_enabled", enabled=self._enabled_text(data.get("enabled"))),
                self.tr(
                    "service_config",
                    config=self._yes_no(data.get("system_config_exists")),
                    engine=self._yes_no(data.get("sing_box_config_exists")),
                ),
            ]
            if data.get("proxy_host"):
                lines.append(self.tr("proxy_target", host=data.get("proxy_host"), port=data.get("proxy_port")))
                if data.get("proxy_reachable") is True:
                    lines.append(self.tr("proxy_reachable"))
                elif data.get("proxy_reachable") is False:
                    lines.append(self.tr("proxy_unreachable", error=data.get("proxy_error") or ""))
            else:
                lines.append(self.tr("proxy_missing"))
            lines.append(
                self.tr(
                    "local_network",
                    gateway=data.get("default_gateway") or self.tr("unknown"),
                    cidrs=self._join_items(data.get("local_cidrs")),
                )
            )
            lines.append(self.tr("local_dns", dns=data.get("local_dns") or self.tr("unknown")))
            lines.append(self.tr("apt_sources", domains=self._join_items(data.get("apt_source_domains"))))
            return "\n".join(lines)

        if kind == "test" and data:
            lines = [self.tr("test_proxy", proxy=data.get("proxy") or self.tr("unknown"))]
            if data.get("proxy_reachable"):
                lines.append(self.tr("test_tcp_ok"))
            else:
                lines.append(self.tr("test_tcp_bad", error=data.get("proxy_error") or ""))
            if data.get("proxy_http_test") == "ok":
                lines.append(self.tr("test_web_ok", ip=data.get("proxy_public_ip") or self.tr("unknown")))
            else:
                lines.append(self.tr("test_web_bad", error=data.get("proxy_http_error") or ""))
            return "\n".join(lines)

        if kind == "diagnose" and data:
            lines = []
            if data.get("configured_proxy_host"):
                lines.append(
                    self.tr(
                        "diagnose_configured",
                        host=data.get("configured_proxy_host"),
                        port=data.get("configured_proxy_port"),
                    )
                )
            else:
                lines.append(self.tr("diagnose_no_host"))
            lines.append(self.tr("diagnose_gateway", gateway=data.get("default_gateway") or self.tr("unknown")))
            lines.append(self.tr("local_dns", dns=data.get("local_dns") or self.tr("unknown")))
            lines.append(self.tr("apt_sources", domains=self._join_items(data.get("apt_source_domains"))))
            for item in data.get("tcp_checks") or []:
                if item.get("reachable"):
                    lines.append(self.tr("diagnose_tcp_ok", target=item.get("target")))
                else:
                    lines.append(self.tr("diagnose_tcp_bad", target=item.get("target"), error=item.get("error") or ""))
            advice = data.get("advice") or []
            if advice:
                lines.append("")
                lines.append(self.tr("diagnose_advice"))
                lines.extend(f"- {self._friendly_advice(str(item))}" for item in advice)
            return "\n".join(lines)

        if kind == "discover" and data:
            lines = [self.tr("discover_gateway", gateway=data.get("default_gateway") or self.tr("unknown"))]
            candidates = data.get("proxy_candidates") or []
            if candidates:
                lines.append(self.tr("discover_found", candidate=candidates[0]))
            else:
                lines.append(self.tr("discover_none"))
            lines.append(
                self.tr(
                    "local_network",
                    gateway=data.get("default_gateway") or self.tr("unknown"),
                    cidrs=self._join_items(data.get("local_cidrs")),
                )
            )
            return "\n".join(lines)

        content = result.stdout.strip()
        if error:
            content += ("\n" if content else "") + error
        return content or self.tr("operation_ok")

    def current_config(self) -> dict:
        try:
            port = int(self.proxy_port.get())
        except ValueError as exc:
            raise ValueError(self.tr("port_number")) from exc
        if port <= 0 or port > 65535:
            raise ValueError(self.tr("port_range"))
        return {
            "proxy_host": self.proxy_host.get().strip(),
            "proxy_port": port,
            "proxy_protocol": self.proxy_protocol.get(),
            "bypass_cidrs": self._lines(self.cidr_text),
            "bypass_domains": self._lines(self.domain_text),
            "block_udp_when_unsupported": self.block_udp.get(),
            "bypass_system_packages": self.bypass_system_packages.get(),
            "bypass_container_registries": self.bypass_container_registries.get(),
            "language": self.language_code,
        }

    def _lines(self, text: tk.Text) -> list[str]:
        return [x.strip() for x in text.get("1.0", "end").splitlines() if x.strip() and not x.strip().startswith("#")]

    def log(self, title: str, result: subprocess.CompletedProcess[str] | str, kind: str = "plain") -> None:
        content = self.format_result(kind, result)
        self._last_log_title = title
        self._last_log_content = content
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", f"{title}\n\n{content}\n")
        self.output.configure(state="disabled")

    def maybe_notify_tray_action(self, ok: bool = True) -> None:
        if not self._tray_action_title:
            return
        title = self._tray_action_title if ok else self.tr("tray_action_failed")
        self.notify_user(title, self._last_log_content or self.tr("operation_ok"), error=not ok)

    def save(self, silent: bool = False) -> bool:
        try:
            save_config(self.current_config())
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return False
        if not silent:
            self._set_status("status_saved", path=USER_CONFIG)
        return True

    def apply(self) -> bool:
        if not self.save():
            return False
        result = run_controller("apply", privileged=True, extra=["--config", str(USER_CONFIG)])
        self.log(self.tr("log_apply"), result, kind="apply")
        if result.returncode != 0:
            messagebox.showerror(APP_NAME, self.tr("apply_failed"))
            self.maybe_notify_tray_action(ok=False)
            return False
        self.maybe_notify_tray_action()
        self.refresh_status(notify=False)
        return True

    def turn_on(self) -> None:
        if not self.save():
            return
        result = run_controller("apply-start", privileged=True, extra=["--config", str(USER_CONFIG)])
        self.log(self.tr("log_turn_on"), result, kind="apply-start")
        if result.returncode != 0:
            self.maybe_notify_tray_action(ok=False)
            if not self._tray_action_title:
                messagebox.showerror(APP_NAME, self._last_log_content)
            return
        self.maybe_notify_tray_action()
        self.refresh_status(notify=False)

    def turn_off(self) -> None:
        result = run_controller("stop", privileged=True)
        self.log(self.tr("log_turn_off"), result, kind="stop")
        self.maybe_notify_tray_action(ok=result.returncode == 0)
        self.refresh_status(notify=False)

    def test(self) -> None:
        if not self.save():
            return
        result = run_controller("test", extra=["--config", str(USER_CONFIG)])
        self.log(self.tr("log_test"), result, kind="test")
        self.maybe_notify_tray_action(ok=result.returncode == 0)

    def diagnose(self) -> None:
        if not self.save():
            return
        result = run_controller("diagnose", extra=["--config", str(USER_CONFIG)])
        self.log(self.tr("log_diagnose"), result, kind="diagnose")
        self.maybe_notify_tray_action(ok=result.returncode == 0)

    def refresh_status(self, notify: bool = True) -> None:
        if not CONTROLLER.exists():
            self._set_status("status_not_installed")
            self.log(self.tr("log_status"), self.tr("status_missing_controller", path=CONTROLLER))
            return
        result = run_controller("status")
        self.log(self.tr("log_status"), result, kind="status")
        if notify:
            self.maybe_notify_tray_action(ok=result.returncode == 0)
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                self._set_status(
                    "status_summary",
                    active=data.get("active"),
                    enabled=data.get("enabled"),
                    host=data.get("proxy_host"),
                    port=data.get("proxy_port"),
                )
            except json.JSONDecodeError:
                self._set_status("status_non_json")
        else:
            self._set_status("status_failed")

    def discover(self) -> None:
        result = run_controller("discover")
        self.log(self.tr("log_discover"), result, kind="discover")
        self.maybe_notify_tray_action(ok=result.returncode == 0)
        if result.returncode != 0:
            return
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return
        candidates = data.get("proxy_candidates") or []
        if candidates and not self.proxy_host.get().strip():
            self.proxy_host.set(candidates[0])
            self._set_status("status_discovered", candidate=candidates[0])


def main() -> int:
    lock = acquire_single_instance()
    if lock is None:
        show_already_running_message()
        return 0
    app = App()
    app._single_instance_lock = lock
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
