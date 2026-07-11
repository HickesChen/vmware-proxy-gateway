#!/usr/bin/env python3
"""
Tkinter GUI for vm-proxy-gateway.
"""

from __future__ import annotations

import csv
import ipaddress
import json
import fcntl
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

try:
    import pystray
except Exception:
    pystray = None

try:
    from PIL import Image
except Exception:
    Image = None


APP_NAME = "VM Proxy Gateway"
USER_CONFIG = Path.home() / ".config" / "vm-proxy-gateway" / "config.json"
LOCK_FILE = Path.home() / ".config" / "vm-proxy-gateway" / "gui.lock"
CONTROLLER = Path("/opt/vm-proxy-gateway/vm_proxy_gateway.py")
ICON_NAME = "vm-proxy-gateway.png"
TRAY_ACTIVE_COLOR_DARK = (151, 84, 0)
TRAY_ACTIVE_COLOR_LIGHT = (255, 186, 59)
DEFAULT_CONFIG = {
    "proxy_host": "",
    "proxy_port": 10086,
    "proxy_protocol": "auto",
    "bypass_cidrs": [],
    "bypass_domains": [],
    "bypass_rules": [],
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
RULE_TYPES = (
    "ip_cidr",
    "domain",
    "domain_prefix",
    "domain_suffix",
    "domain_keyword",
    "domain_regex",
)
PROTECTIVE_BYPASS_CIDRS = (
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
)
PROTECTIVE_BYPASS_DOMAINS = ("localhost", ".local", ".lan", ".home")


def make_active_tray_image(image):
    if Image is None:
        return image
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    luminance = rgba.convert("L")
    dark = Image.new("RGBA", rgba.size, TRAY_ACTIVE_COLOR_DARK + (255,))
    light = Image.new("RGBA", rgba.size, TRAY_ACTIVE_COLOR_LIGHT + (255,))
    tinted = Image.composite(light, dark, luminance)
    tinted.putalpha(alpha)
    return tinted


TEXT = {
    "en": {
        "language": "Language",
        "app_subtitle": "Transparent proxy control for Ubuntu virtual machines",
        "section_connection": "Connection",
        "section_options": "Runtime options",
        "section_rules": "Custom bypass rules",
        "add_rule": "Add rule",
        "edit_rule": "Edit",
        "delete_rule": "Delete",
        "rule_match": "Match type",
        "rule_value": "Value",
        "rule_invert": "Not",
        "rule_source": "Source",
        "rule_search": "Search rules",
        "rule_source_system": "System protection",
        "rule_source_preset": "Applied preset",
        "rule_source_custom": "Custom",
        "rule_count": "{visible} shown · {system} protected/preset · {custom} custom",
        "rule_duplicate": "An identical rule already exists.",
        "rule_protected": "System and preset rules are read-only.",
        "rule_invert_option": "Invert match (all traffic except this value)",
        "rule_type_ip_cidr": "IP / CIDR",
        "rule_type_domain": "Exact domain",
        "rule_type_domain_prefix": "Domain prefix",
        "rule_type_domain_suffix": "Domain suffix",
        "rule_type_domain_keyword": "Contains keyword",
        "rule_type_domain_regex": "Regular expression",
        "rule_value_required": "Enter a rule value.",
        "rule_value_invalid": "The rule value is invalid: {error}",
        "rule_select_first": "Select a rule first.",
        "rule_delete_confirm": "Delete the selected rule?",
        "confirm": "Confirm",
        "cancel": "Cancel",
        "section_output": "Status and output",
        "section_speed": "Proxy traffic speed",
        "upload_speed": "Upload",
        "download_speed": "Download",
        "tab_control": "Control",
        "tab_rules": "Custom bypass rules",
        "tab_logs": "Traffic logs",
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
        "bypass_cidrs_placeholder": "192.168.56.0/24\n10.0.0.*\n192.168.*.*",
        "bypass_domains_placeholder": "example.com\n.corp.local\n*.internal.lan",
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
        "apt_sources": "APT source domains to bypass directly: {domains}. These are source hostnames, not proxy endpoints.",
        "test_tcp_ok": "Step 1 passed: the proxy port accepts connections.",
        "test_tcp_bad": "Step 1 failed: the proxy port cannot be reached. {error}",
        "test_web_ok": "Step 2 passed: internet traffic can go through the proxy. Public IP: {ip}.",
        "test_web_bad": "Step 2 failed: the proxy port was reached, but web traffic did not work. {error}",
        "test_proxy": "Checking proxy reachability: {proxy}.",
        "diagnose_configured": "Configured proxy: {host}:{port}.",
        "diagnose_no_host": "No proxy host is configured yet.",
        "diagnose_gateway": "VM default gateway: {gateway}.",
        "diagnose_tcp_ok": "{label}: connected to {target}.",
        "diagnose_tcp_bad": "{label}: cannot connect to {target}. {error}",
        "tcp_label_configured_proxy": "Configured proxy",
        "tcp_label_default_gateway": "Default gateway probe",
        "diagnose_advice": "Suggestions:",
        "discover_found": "Suggested proxy host: {candidate}. This is usually the Windows host address for NAT mode.",
        "discover_none": "No candidate proxy host was found automatically. Enter the Windows host IP manually.",
        "discover_gateway": "Detected VM default gateway: {gateway}.",
        "operation_ok": "Done.",
        "operation_failed": "This operation failed. {error}",
        "applying": "Applying...",
        "starting": "Starting...",
        "stopping": "Stopping...",
        "testing": "Testing...",
        "diagnosing": "Diagnosing...",
        "discovering": "Discovering...",
        "service_running_button": "Running",
        "service_stopped_button": "Stopped",
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
        "traffic_search": "Search destination",
        "filter_all": "All",
        "filter_proxy": "Proxied",
        "filter_direct": "Direct",
        "filter_block": "Blocked",
        "auto_refresh": "Auto refresh",
        "refresh_logs": "Refresh logs",
        "export_logs": "Export CSV",
        "export_empty": "There are no matching traffic records to export.",
        "export_success": "Exported {count} traffic records to:\n{path}",
        "traffic_time": "Time",
        "traffic_destination": "Destination",
        "traffic_port": "Port",
        "traffic_network": "Network",
        "traffic_route": "Route",
        "traffic_via": "Via",
        "traffic_id": "Connection ID",
        "traffic_count": "{visible} shown · {total} captured",
        "traffic_empty": "No matching traffic records",
        "traffic_unavailable": "Traffic logs are unavailable. Reinstall this version to update the controller.",
        "route_proxy": "Proxy",
        "route_direct": "Direct",
        "route_block": "Blocked",
    },
    "zh_CN": {
        "language": "语言",
        "app_subtitle": "Ubuntu 虚拟机透明代理控制器",
        "section_connection": "连接设置",
        "section_options": "运行选项",
        "section_rules": "自定义绕过规则",
        "add_rule": "添加规则",
        "edit_rule": "编辑",
        "delete_rule": "删除",
        "rule_match": "匹配方式",
        "rule_value": "匹配内容",
        "rule_invert": "非",
        "rule_source": "来源",
        "rule_search": "搜索规则",
        "rule_source_system": "系统保护",
        "rule_source_preset": "已应用预设",
        "rule_source_custom": "自定义",
        "rule_count": "显示 {visible} 条 · 系统/预设 {system} 条 · 自定义 {custom} 条",
        "rule_duplicate": "已经存在完全相同的规则。",
        "rule_protected": "系统保护规则和预设规则为只读，不能编辑或删除。",
        "rule_invert_option": "取反（匹配上述内容以外的所有流量）",
        "rule_type_ip_cidr": "IP / CIDR",
        "rule_type_domain": "完全匹配域名",
        "rule_type_domain_prefix": "域名前缀",
        "rule_type_domain_suffix": "域名后缀",
        "rule_type_domain_keyword": "包含关键词",
        "rule_type_domain_regex": "正则表达式",
        "rule_value_required": "请输入规则内容。",
        "rule_value_invalid": "规则内容无效：{error}",
        "rule_select_first": "请先选择一条规则。",
        "rule_delete_confirm": "确定删除选中的规则吗？",
        "confirm": "确定",
        "cancel": "取消",
        "section_output": "状态与输出",
        "section_speed": "代理实时速度",
        "upload_speed": "上传",
        "download_speed": "下载",
        "tab_control": "代理控制",
        "tab_rules": "自定义绕过规则",
        "tab_logs": "流量日志",
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
        "bypass_cidrs_placeholder": "192.168.56.0/24\n10.0.0.*\n192.168.*.*",
        "bypass_domains_placeholder": "example.com\n.corp.local\n*.internal.lan",
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
        "apt_sources": "APT 源域名（仅用于直连绕过规则，不是代理地址）：{domains}。",
        "test_tcp_ok": "第 1 步通过：代理端口可以连接。",
        "test_tcp_bad": "第 1 步失败：代理端口连不上。{error}",
        "test_web_ok": "第 2 步通过：网络流量可以通过代理访问互联网。出口 IP：{ip}。",
        "test_web_bad": "第 2 步失败：代理端口已连上，但网页访问没有成功。{error}",
        "test_proxy": "正在检查代理连通性：{proxy}。",
        "diagnose_configured": "当前填写的代理：{host}:{port}。",
        "diagnose_no_host": "还没有填写代理主机。",
        "diagnose_gateway": "虚拟机默认网关：{gateway}。",
        "diagnose_tcp_ok": "{label}：已连接到 {target}。",
        "diagnose_tcp_bad": "{label}：无法连接到 {target}。{error}",
        "tcp_label_configured_proxy": "当前填写的代理",
        "tcp_label_default_gateway": "默认网关探测",
        "diagnose_advice": "建议：",
        "discover_found": "建议的代理主机：{candidate}。NAT 模式下这通常就是 Windows 主机地址。",
        "discover_none": "没有自动发现候选代理主机。请手动填写 Windows 主机 IP。",
        "discover_gateway": "检测到的虚拟机默认网关：{gateway}。",
        "operation_ok": "操作已完成。",
        "operation_failed": "操作失败。{error}",
        "applying": "应用中...",
        "starting": "开启中...",
        "stopping": "关闭中...",
        "testing": "测试中...",
        "diagnosing": "诊断中...",
        "discovering": "发现中...",
        "service_running_button": "已开启",
        "service_stopped_button": "已关闭",
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
        "traffic_search": "搜索目标地址",
        "filter_all": "全部",
        "filter_proxy": "已代理",
        "filter_direct": "直连",
        "filter_block": "已阻止",
        "auto_refresh": "自动刷新",
        "refresh_logs": "刷新日志",
        "export_logs": "导出 CSV",
        "export_empty": "当前没有可导出的匹配流量记录。",
        "export_success": "已导出 {count} 条流量记录：\n{path}",
        "traffic_time": "时间",
        "traffic_destination": "目标地址",
        "traffic_port": "端口",
        "traffic_network": "网络",
        "traffic_route": "路由",
        "traffic_via": "转发至",
        "traffic_id": "连接 ID",
        "traffic_count": "显示 {visible} 条 · 共捕获 {total} 条",
        "traffic_empty": "没有匹配的流量记录",
        "traffic_unavailable": "流量日志暂不可用，请重新安装此版本以更新控制器。",
        "route_proxy": "代理",
        "route_direct": "直连",
        "route_block": "阻止",
    },
    "zh_TW": {
        "language": "語言",
        "app_subtitle": "Ubuntu 虛擬機透明代理控制器",
        "section_connection": "連線設定",
        "section_options": "執行選項",
        "section_rules": "自訂略過規則",
        "add_rule": "新增規則",
        "edit_rule": "編輯",
        "delete_rule": "刪除",
        "rule_match": "比對方式",
        "rule_value": "比對內容",
        "rule_invert": "非",
        "rule_source": "來源",
        "rule_search": "搜尋規則",
        "rule_source_system": "系統保護",
        "rule_source_preset": "已套用預設",
        "rule_source_custom": "自訂",
        "rule_count": "顯示 {visible} 筆 · 系統/預設 {system} 筆 · 自訂 {custom} 筆",
        "rule_duplicate": "已經存在完全相同的規則。",
        "rule_protected": "系統保護規則和預設規則為唯讀，無法編輯或刪除。",
        "rule_invert_option": "反向比對（上述內容以外的所有流量）",
        "rule_type_ip_cidr": "IP / CIDR",
        "rule_type_domain": "完全比對網域",
        "rule_type_domain_prefix": "網域前綴",
        "rule_type_domain_suffix": "網域後綴",
        "rule_type_domain_keyword": "包含關鍵字",
        "rule_type_domain_regex": "正規表示式",
        "rule_value_required": "請輸入規則內容。",
        "rule_value_invalid": "規則內容無效：{error}",
        "rule_select_first": "請先選取一筆規則。",
        "rule_delete_confirm": "確定刪除選取的規則嗎？",
        "confirm": "確定",
        "cancel": "取消",
        "section_output": "狀態與輸出",
        "section_speed": "代理即時速度",
        "upload_speed": "上傳",
        "download_speed": "下載",
        "tab_control": "代理控制",
        "tab_rules": "自訂略過規則",
        "tab_logs": "流量日誌",
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
        "bypass_cidrs_placeholder": "192.168.56.0/24\n10.0.0.*\n192.168.*.*",
        "bypass_domains_placeholder": "example.com\n.corp.local\n*.internal.lan",
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
        "apt_sources": "APT 來源網域（僅用於直連繞過規則，不是代理位址）：{domains}。",
        "test_tcp_ok": "第 1 步通過：代理連接埠可以連線。",
        "test_tcp_bad": "第 1 步失敗：代理連接埠無法連線。{error}",
        "test_web_ok": "第 2 步通過：網路流量可以透過代理連上網際網路。出口 IP：{ip}。",
        "test_web_bad": "第 2 步失敗：代理連接埠已連上，但網頁存取沒有成功。{error}",
        "test_proxy": "正在檢查代理連通性：{proxy}。",
        "diagnose_configured": "目前填寫的代理：{host}:{port}。",
        "diagnose_no_host": "尚未填寫代理主機。",
        "diagnose_gateway": "虛擬機預設閘道：{gateway}。",
        "diagnose_tcp_ok": "{label}：已連線到 {target}。",
        "diagnose_tcp_bad": "{label}：無法連線到 {target}。{error}",
        "tcp_label_configured_proxy": "目前填寫的代理",
        "tcp_label_default_gateway": "預設閘道探測",
        "diagnose_advice": "建議：",
        "discover_found": "建議的代理主機：{candidate}。NAT 模式下這通常就是 Windows 主機位址。",
        "discover_none": "沒有自動偵測到候選代理主機。請手動填寫 Windows 主機 IP。",
        "discover_gateway": "偵測到的虛擬機預設閘道：{gateway}。",
        "operation_ok": "操作已完成。",
        "operation_failed": "操作失敗。{error}",
        "applying": "套用中...",
        "starting": "開啟中...",
        "stopping": "關閉中...",
        "testing": "測試中...",
        "diagnosing": "診斷中...",
        "discovering": "偵測中...",
        "service_running_button": "已開啟",
        "service_stopped_button": "已關閉",
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
        "traffic_search": "搜尋目標位址",
        "filter_all": "全部",
        "filter_proxy": "已代理",
        "filter_direct": "直連",
        "filter_block": "已阻擋",
        "auto_refresh": "自動重新整理",
        "refresh_logs": "重新整理日誌",
        "export_logs": "匯出 CSV",
        "export_empty": "目前沒有可匯出的符合流量記錄。",
        "export_success": "已匯出 {count} 筆流量記錄：\n{path}",
        "traffic_time": "時間",
        "traffic_destination": "目標位址",
        "traffic_port": "連接埠",
        "traffic_network": "網路",
        "traffic_route": "路由",
        "traffic_via": "轉送至",
        "traffic_id": "連線 ID",
        "traffic_count": "顯示 {visible} 筆 · 共擷取 {total} 筆",
        "traffic_empty": "沒有符合的流量記錄",
        "traffic_unavailable": "流量日誌暫時無法使用，請重新安裝此版本以更新控制器。",
        "route_proxy": "代理",
        "route_direct": "直連",
        "route_block": "阻擋",
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
    root.title(APP_NAME)
    root.geometry("480x210")
    root.resizable(False, False)
    root.configure(bg="#eef1f4")
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("DialogHeader.TFrame", background="#ffffff")
    style.configure("DialogBody.TFrame", background="#f7f8fa")
    style.configure("DialogTitle.TLabel", background="#ffffff", foreground="#101828", font=("TkDefaultFont", 15, "bold"))
    style.configure("DialogText.TLabel", background="#f7f8fa", foreground="#344054")
    style.configure("DialogPrimary.TButton", background="#0f766e", foreground="#ffffff", padding=(16, 8), borderwidth=0)
    style.map("DialogPrimary.TButton", background=[("active", "#0b625c"), ("pressed", "#084c47")])

    icon_path = find_asset(ICON_NAME)
    if icon_path:
        try:
            root._window_icon = tk.PhotoImage(file=str(icon_path))
            root.iconphoto(True, root._window_icon)
        except tk.TclError:
            pass

    header = ttk.Frame(root, padding=(22, 16), style="DialogHeader.TFrame")
    header.pack(fill="x")
    ttk.Label(header, text=APP_NAME, style="DialogTitle.TLabel").pack(anchor="w")
    body = ttk.Frame(root, padding=(22, 20), style="DialogBody.TFrame")
    body.pack(fill="both", expand=True)
    ttk.Label(
        body,
        text=TEXT[language]["already_running"],
        style="DialogText.TLabel",
        wraplength=430,
        justify="left",
    ).pack(anchor="w")
    ttk.Button(body, text=TEXT[language]["confirm"], command=root.destroy, style="DialogPrimary.TButton").pack(
        anchor="e", pady=(22, 0)
    )
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.update_idletasks()
    x = max(0, (root.winfo_screenwidth() - root.winfo_width()) // 2)
    y = max(0, (root.winfo_screenheight() - root.winfo_height()) // 2)
    root.geometry(f"+{x}+{y}")
    root.focus_force()
    root.mainloop()


class HistoryEntry(ttk.Entry):
    """ttk.Entry with predictable desktop editing shortcuts and local undo history."""

    def __init__(self, master=None, **kwargs: object) -> None:
        super().__init__(master, **kwargs)
        self._undo_stack: list[tuple[str, int, tuple[int, int] | None]] = []
        self._redo_stack: list[tuple[str, int, tuple[int, int] | None]] = []
        self.bind("<KeyPress>", self._remember_keyboard_edit, add=True)
        self.bind("<Control-z>", self._undo)
        self.bind("<Control-y>", self._redo)
        self.bind("<Control-Shift-Z>", self._redo)
        self.bind("<Control-a>", self._select_all)
        self.bind("<Control-x>", self._cut)
        self.bind("<Control-c>", self._copy)
        self.bind("<Control-v>", self._paste)
        self.bind("<Control-Insert>", self._copy)
        self.bind("<Shift-Insert>", self._paste)

    def _snapshot(self) -> tuple[str, int, tuple[int, int] | None]:
        selection = None
        try:
            if self.selection_present():
                selection = (self.index("sel.first"), self.index("sel.last"))
        except tk.TclError:
            pass
        return self.get(), self.index("insert"), selection

    def _restore(self, snapshot: tuple[str, int, tuple[int, int] | None]) -> None:
        value, cursor, selection = snapshot
        self.delete(0, "end")
        self.insert(0, value)
        self.icursor(min(cursor, len(value)))
        self.selection_clear()
        if selection:
            self.selection_range(*selection)

    def _remember_edit(self) -> None:
        snapshot = self._snapshot()
        if not self._undo_stack or self._undo_stack[-1] != snapshot:
            self._undo_stack.append(snapshot)
            del self._undo_stack[:-200]
        self._redo_stack.clear()

    def _remember_keyboard_edit(self, event: tk.Event) -> None:
        if event.state & 0x4:
            return
        if event.keysym in {"BackSpace", "Delete"} or event.char:
            self._remember_edit()

    def _undo(self, _event: tk.Event | None = None) -> str:
        if self._undo_stack:
            self._redo_stack.append(self._snapshot())
            self._restore(self._undo_stack.pop())
        return "break"

    def _redo(self, _event: tk.Event | None = None) -> str:
        if self._redo_stack:
            self._undo_stack.append(self._snapshot())
            self._restore(self._redo_stack.pop())
        return "break"

    def _select_all(self, _event: tk.Event | None = None) -> str:
        self.selection_range(0, "end")
        self.icursor("end")
        return "break"

    def _copy(self, _event: tk.Event | None = None) -> str:
        if self.selection_present():
            self.clipboard_clear()
            self.clipboard_append(self.get()[self.index("sel.first"):self.index("sel.last")])
        return "break"

    def _cut(self, _event: tk.Event | None = None) -> str:
        if self.selection_present():
            self._remember_edit()
            self._copy()
            self.delete("sel.first", "sel.last")
        return "break"

    def _paste(self, _event: tk.Event | None = None) -> str:
        try:
            value = self.clipboard_get()
        except tk.TclError:
            return "break"
        self._remember_edit()
        if self.selection_present():
            self.delete("sel.first", "sel.last")
        self.insert("insert", value)
        return "break"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__(className="VmProxyGateway")
        self.title(APP_NAME)
        self.geometry("1080x760")
        self.minsize(1000, 660)
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
        self.upload_speed = tk.StringVar(value="0 B/s")
        self.download_speed = tk.StringVar(value="0 B/s")
        self.traffic_search = tk.StringVar(value="")
        self.traffic_route = tk.StringVar(value="all")
        self.auto_refresh_logs = tk.BooleanVar(value=True)
        self.rule_search = tk.StringVar(value="")
        self.bypass_rules = self._load_bypass_rules(self.config_data)
        self._effective_cidrs = set(PROTECTIVE_BYPASS_CIDRS)
        self._effective_domains = set(PROTECTIVE_BYPASS_DOMAINS)
        self._local_cidrs: set[str] = set()
        self._default_gateway = ""
        self._labels: dict[str, ttk.Label] = {}
        self._buttons: dict[str, ttk.Button] = {}
        self._checks: dict[str, ttk.Checkbutton] = {}
        self._frames: dict[str, ttk.LabelFrame] = {}
        self._tabs: dict[str, ttk.Frame] = {}
        self._radios: dict[str, ttk.Radiobutton] = {}
        self._tree_headings: dict[str, str] = {}
        self._traffic_entries: list[dict] = []
        self._rule_rows_by_iid: dict[str, dict] = {}
        self._traffic_sort_column = "time"
        self._traffic_sort_reverse = True
        self._log_refresh_job: str | None = None
        self._speed_refresh_job: str | None = None
        self._last_traffic_sample: tuple[float, int, int] | None = None
        self._last_status_key = "status_not_checked"
        self._last_status_kwargs: dict[str, object] = {}
        self._last_log_title = APP_NAME
        self._last_log_content = ""
        self._tray_action_title: str | None = None
        self._exiting = False
        self._tray_icon = None
        self._tray_thread: threading.Thread | None = None
        self._tray_images: dict[str, object] = {}
        self._tray_active = False
        self._service_active: bool | None = None
        self.proxy_host.trace_add("write", lambda *_args: self._render_bypass_rules())

        self._build()
        self._set_window_icon()
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.start_tray()
        self.refresh_status()
        self._schedule_speed_refresh(immediate=True)

    def tr(self, key: str, **kwargs: object) -> str:
        text = TEXT[self.language_code][key]
        return text.format(**kwargs) if kwargs else text

    def _build(self) -> None:
        self._configure_style()

        root = ttk.Frame(self, style="App.TFrame")
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root, padding=(24, 18), style="Header.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title_area = ttk.Frame(header, style="Header.TFrame")
        title_area.grid(row=0, column=0, sticky="w")
        ttk.Label(title_area, text=APP_NAME, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self._label(title_area, "app_subtitle", style="Subtitle.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))

        language_area = ttk.Frame(header, style="Header.TFrame")
        language_area.grid(row=0, column=1, sticky="e")
        ttk.Label(
            language_area,
            textvariable=self.status_text,
            style="HeaderStatus.TLabel",
            wraplength=460,
            justify="right",
        ).grid(
            row=0, column=0, columnspan=2, sticky="e", pady=(0, 8)
        )
        self._label(language_area, "language", style="HeaderField.TLabel").grid(row=1, column=0, sticky="e", padx=(0, 8))
        language = ttk.Combobox(language_area, textvariable=self.language, values=list(LANGUAGES.values()), state="readonly", width=12)
        language.grid(row=1, column=1, sticky="e")
        language.bind("<<ComboboxSelected>>", self.change_language)

        self.notebook = ttk.Notebook(root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=20, pady=(16, 20))
        control_page = ttk.Frame(self.notebook, padding=16, style="Page.TFrame")
        rules_page = ttk.Frame(self.notebook, padding=16, style="Page.TFrame")
        logs_page = ttk.Frame(self.notebook, padding=16, style="Page.TFrame")
        self._tabs = {"tab_control": control_page, "tab_rules": rules_page, "tab_logs": logs_page}
        self.notebook.add(control_page, text=self.tr("tab_control"))
        self.notebook.add(rules_page, text=self.tr("tab_rules"))
        self.notebook.add(logs_page, text=self.tr("tab_logs"))
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        control_page.columnconfigure(0, weight=1)
        settings = ttk.Frame(control_page, style="Page.TFrame")
        settings.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        settings.columnconfigure(0, weight=3)
        settings.columnconfigure(1, weight=2)

        connection = self._section(settings, "section_connection")
        connection.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        connection.columnconfigure(0, weight=1)
        connection.columnconfigure(1, weight=0)
        connection.columnconfigure(2, weight=0)

        self._label(connection, "proxy_host", style="Field.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        HistoryEntry(connection, textvariable=self.proxy_host).grid(row=1, column=0, sticky="ew", pady=(4, 12))
        self._button(connection, "discover", self.discover).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(4, 12))

        self._label(connection, "proxy_port", style="Field.TLabel").grid(row=2, column=0, sticky="w")
        self._label(connection, "protocol", style="Field.TLabel").grid(row=2, column=1, columnspan=2, sticky="w", padx=(12, 0))
        HistoryEntry(connection, textvariable=self.proxy_port, width=14).grid(row=3, column=0, sticky="w", pady=(4, 0))
        protocol = ttk.Combobox(connection, textvariable=self.proxy_protocol, values=["auto", "socks5", "http"], state="readonly", width=14)
        protocol.grid(row=3, column=1, columnspan=2, sticky="w", padx=(12, 0), pady=(4, 0))

        options = self._section(settings, "section_options")
        options.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        options.columnconfigure(0, weight=1)
        self._check(options, "block_udp", self.block_udp).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self._check(options, "bypass_system_packages", self.bypass_system_packages).grid(row=1, column=0, sticky="w", pady=8)
        self._check(options, "bypass_container_registries", self.bypass_container_registries).grid(row=2, column=0, sticky="w", pady=8)

        actions = ttk.Frame(control_page, style="Page.TFrame")
        actions.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self._button(actions, "save", self.save, width=8).pack(side="left", padx=(0, 8))
        self._button(actions, "apply", self.apply, style="Primary.TButton", width=8).pack(side="left", padx=(0, 8))
        self._button(actions, "turn_on", self.turn_on, style="Primary.TButton", width=8).pack(side="left", padx=(0, 8))
        self._button(actions, "turn_off", self.turn_off, width=8).pack(side="left", padx=(0, 8))
        self._button(actions, "test", self.test, width=8).pack(side="left", padx=(0, 8))
        self._button(actions, "diagnose", self.diagnose, width=8).pack(side="left", padx=(0, 8))
        self._button(actions, "refresh", self.refresh_status, width=8).pack(side="left")

        speed = self._section(control_page, "section_speed")
        speed.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        speed.columnconfigure(1, weight=1)
        speed.columnconfigure(3, weight=1)
        self._label(speed, "upload_speed", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(speed, textvariable=self.upload_speed, style="Field.TLabel").grid(
            row=0, column=1, sticky="w", padx=(10, 32)
        )
        self._label(speed, "download_speed", style="Field.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Label(speed, textvariable=self.download_speed, style="Field.TLabel").grid(
            row=0, column=3, sticky="w", padx=(10, 0)
        )

        self._build_rules_page(rules_page)
        self._build_logs_page(logs_page)

    def _build_rules_page(self, page: ttk.Frame) -> None:
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        rule_actions = ttk.Frame(page, style="Page.TFrame")
        rule_actions.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        rule_actions.columnconfigure(1, weight=1)
        self._label(rule_actions, "rule_search", style="PageField.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        rule_search = HistoryEntry(rule_actions, textvariable=self.rule_search, width=30)
        rule_search.grid(row=0, column=1, sticky="ew", padx=(0, 16))
        self.rule_search.trace_add("write", lambda *_args: self._render_bypass_rules())
        self._button(rule_actions, "add_rule", self.add_rule, style="Primary.TButton").grid(row=0, column=2)
        self._button(rule_actions, "edit_rule", self.edit_rule).grid(row=0, column=3, padx=(8, 0))
        self._button(rule_actions, "delete_rule", self.delete_rule).grid(row=0, column=4, padx=(8, 0))

        rule_table = ttk.Frame(page, style="Table.TFrame", padding=1)
        rule_table.grid(row=1, column=0, sticky="nsew")
        rule_table.columnconfigure(0, weight=1)
        rule_table.rowconfigure(0, weight=1)
        self.rule_tree = ttk.Treeview(
            rule_table,
            columns=("source", "match", "value", "invert"),
            show="headings",
            selectmode="browse",
        )
        self.rule_tree.heading("source", text=self.tr("rule_source"))
        self.rule_tree.heading("match", text=self.tr("rule_match"))
        self.rule_tree.heading("value", text=self.tr("rule_value"))
        self.rule_tree.heading("invert", text=self.tr("rule_invert"))
        self.rule_tree.column("source", width=145, minwidth=110, stretch=False)
        self.rule_tree.column("match", width=175, minwidth=130, stretch=False)
        self.rule_tree.column("value", width=500, minwidth=220, stretch=True)
        self.rule_tree.column("invert", width=70, minwidth=55, stretch=False, anchor="center")
        self.rule_tree.tag_configure("protected", foreground="#667085", background="#f8fafc")
        rule_scrollbar = ttk.Scrollbar(rule_table, orient="vertical", command=self.rule_tree.yview)
        self.rule_tree.configure(yscrollcommand=rule_scrollbar.set)
        self.rule_tree.grid(row=0, column=0, sticky="nsew")
        rule_scrollbar.grid(row=0, column=1, sticky="ns")
        self.rule_tree.bind("<Double-1>", lambda _event: self.edit_rule())
        self.rule_tree.bind("<Delete>", lambda _event: self.delete_rule())
        self.rule_tree.bind("<<TreeviewSelect>>", lambda _event: self._update_rule_controls())
        self.rule_summary = tk.StringVar(value="")
        ttk.Label(page, textvariable=self.rule_summary, style="TableSummary.TLabel").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )
        self._render_bypass_rules()

    def _build_logs_page(self, page: ttk.Frame) -> None:
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(page, style="Page.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        toolbar.columnconfigure(1, weight=1)
        self._label(toolbar, "traffic_search", style="PageField.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        search = HistoryEntry(toolbar, textvariable=self.traffic_search, width=30)
        search.grid(row=0, column=1, sticky="ew", padx=(0, 16))
        self.traffic_search.trace_add("write", lambda *_args: self._render_traffic_logs())

        self._button(toolbar, "refresh_logs", self.refresh_traffic_logs, style="Primary.TButton").grid(
            row=0, column=2, padx=(0, 8)
        )
        self._button(toolbar, "export_logs", self.export_traffic_logs).grid(row=0, column=3)

        for column, (key, value) in enumerate(
            [
                ("filter_all", "all"),
                ("filter_proxy", "proxy"),
                ("filter_direct", "direct"),
                ("filter_block", "block"),
            ]
        ):
            radio = ttk.Radiobutton(
                toolbar,
                text=self.tr(key),
                variable=self.traffic_route,
                value=value,
                command=self._render_traffic_logs,
                style="Filter.TRadiobutton",
            )
            radio.grid(row=1, column=column, padx=(0, 4), pady=(10, 0), sticky="w")
            self._radios[key] = radio
        self._check(toolbar, "auto_refresh", self.auto_refresh_logs, command=self._schedule_log_refresh).grid(
            row=1, column=4, padx=(12, 0), pady=(10, 0), sticky="e"
        )

        table_frame = ttk.Frame(page, style="Table.TFrame", padding=1)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = ("time", "destination", "port", "network", "route", "via", "connection_id")
        self.traffic_tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        heading_keys = {
            "time": "traffic_time",
            "destination": "traffic_destination",
            "port": "traffic_port",
            "network": "traffic_network",
            "route": "traffic_route",
            "via": "traffic_via",
            "connection_id": "traffic_id",
        }
        self._tree_headings = heading_keys
        widths = {"time": 150, "destination": 260, "port": 70, "network": 75, "route": 85, "via": 170, "connection_id": 115}
        for column in columns:
            self.traffic_tree.heading(
                column,
                text=self.tr(heading_keys[column]),
                command=lambda selected_column=column: self._sort_traffic_logs(selected_column),
            )
            self.traffic_tree.column(column, width=widths[column], minwidth=60, stretch=column in {"destination", "via"})
        self._update_traffic_headings()
        self.traffic_tree.tag_configure("proxy", foreground="#0f766e")
        self.traffic_tree.tag_configure("direct", foreground="#475467")
        self.traffic_tree.tag_configure("block", foreground="#b42318")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.traffic_tree.yview)
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=self.traffic_tree.xview)
        self.traffic_tree.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        self.traffic_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.traffic_tree.bind("<Control-c>", self._copy_selected_traffic)

        self.traffic_summary = tk.StringVar(value=self.tr("traffic_empty"))
        ttk.Label(page, textvariable=self.traffic_summary, style="TableSummary.TLabel").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self.configure(bg="#eef1f4")
        style.configure("App.TFrame", background="#eef1f4")
        style.configure("Header.TFrame", background="#ffffff")
        style.configure("Page.TFrame", background="#f7f8fa")
        style.configure("Table.TFrame", background="#d0d5dd")
        style.configure("Card.TLabelframe", background="#ffffff", bordercolor="#d0d5dd", relief="solid")
        style.configure(
            "Card.TLabelframe.Label",
            background="#ffffff",
            foreground="#1d2939",
            font=("TkDefaultFont", 10, "bold"),
        )
        style.configure("Title.TLabel", background="#ffffff", foreground="#101828", font=("TkDefaultFont", 18, "bold"))
        style.configure("Subtitle.TLabel", background="#ffffff", foreground="#667085")
        style.configure("HeaderField.TLabel", background="#ffffff", foreground="#475467")
        style.configure("HeaderStatus.TLabel", background="#ffffff", foreground="#0f766e", font=("TkDefaultFont", 9, "bold"))
        style.configure("Field.TLabel", background="#ffffff", foreground="#344054")
        style.configure("PageField.TLabel", background="#f7f8fa", foreground="#344054")
        style.configure("TableSummary.TLabel", background="#f7f8fa", foreground="#667085")
        style.configure("TCheckbutton", background="#ffffff", foreground="#344054")
        style.configure("Filter.TRadiobutton", background="#f7f8fa", foreground="#344054", padding=(7, 5))
        style.map("Filter.TRadiobutton", foreground=[("selected", "#0f766e")])
        style.configure("TButton", padding=(12, 7), borderwidth=1)
        style.map(
            "TButton",
            background=[("pressed", "#d0d5dd"), ("active", "#e4e7ec")],
            relief=[("pressed", "sunken"), ("!pressed", "raised")],
        )
        style.configure("Primary.TButton", background="#0f766e", foreground="#ffffff", padding=(14, 7), borderwidth=0)
        style.map(
            "Primary.TButton",
            background=[("active", "#0b625c"), ("pressed", "#084c47"), ("disabled", "#98a2b3")],
            foreground=[("disabled", "#ffffff")],
            relief=[("pressed", "sunken"), ("!pressed", "flat")],
        )
        style.configure("Active.TButton", background="#15803d", foreground="#ffffff", padding=(14, 7), borderwidth=0)
        style.map("Active.TButton", background=[("disabled", "#15803d")], foreground=[("disabled", "#ffffff")])
        style.configure("Danger.TButton", background="#b42318", foreground="#ffffff", padding=(14, 7), borderwidth=0)
        style.map(
            "Danger.TButton",
            background=[("active", "#912018"), ("pressed", "#7a271a")],
            relief=[("pressed", "sunken"), ("!pressed", "flat")],
        )
        style.configure("Inactive.TButton", background="#e4e7ec", foreground="#667085", padding=(14, 7))
        style.map("Inactive.TButton", background=[("disabled", "#e4e7ec")], foreground=[("disabled", "#667085")])
        style.configure("Busy.TButton", background="#f79009", foreground="#ffffff", padding=(14, 7), borderwidth=0)
        style.map("Busy.TButton", background=[("disabled", "#f79009")], foreground=[("disabled", "#ffffff")])
        style.configure("TNotebook", background="#eef1f4", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 9), background="#e4e7ec", foreground="#475467")
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#f7f8fa"), ("active", "#eaecf0")],
            foreground=[("selected", "#0f766e")],
        )
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground="#1d2939", rowheight=32, borderwidth=0)
        style.configure("Treeview.Heading", background="#f2f4f7", foreground="#344054", font=("TkDefaultFont", 9, "bold"), padding=(8, 8))
        style.map("Treeview", background=[("selected", "#dff3f0")], foreground=[("selected", "#134e4a")])
        style.configure("TEntry", padding=6)
        style.configure("TCombobox", padding=5)

    def _section(self, parent: tk.Widget, key: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=self.tr(key), padding=14, style="Card.TLabelframe")
        self._frames[key] = frame
        return frame

    @staticmethod
    def _load_bypass_rules(config: dict) -> list[dict]:
        rules: list[dict] = []
        for item in config.get("bypass_rules", []):
            if not isinstance(item, dict):
                continue
            rule_type = str(item.get("type") or "")
            value = str(item.get("value") or "").strip()
            if rule_type in RULE_TYPES and value:
                rules.append({"type": rule_type, "value": value, "invert": bool(item.get("invert", False))})

        for value in config.get("bypass_cidrs", []):
            value = str(value).strip()
            if value:
                rules.append({"type": "ip_cidr", "value": value, "invert": False})
        for value in config.get("bypass_domains", []):
            value = str(value).strip()
            if not value:
                continue
            if value.startswith("*."):
                value = value[2:]
                rule_type = "domain_suffix"
            elif value.startswith("."):
                value = value[1:]
                rule_type = "domain_suffix"
            else:
                rule_type = "domain"
            rules.append({"type": rule_type, "value": value, "invert": False})

        unique = []
        seen = set()
        for rule in rules:
            key = (rule["type"], rule["value"], rule["invert"])
            if key not in seen:
                unique.append(rule)
                seen.add(key)
        return unique

    def _rule_type_text(self, rule_type: str) -> str:
        return self.tr(f"rule_type_{rule_type}")

    def _normalize_rule_value(self, rule_type: str, value: str) -> str:
        value = value.strip()
        if rule_type == "ip_cidr":
            if "*" not in value:
                return str(ipaddress.ip_network(value, strict=False))
            if value == "*":
                return "0.0.0.0/0"
            parts = value.split(".")
            first_wildcard = next((i for i, part in enumerate(parts) if part == "*"), None)
            if (
                len(parts) != 4
                or first_wildcard is None
                or any(part != "*" for part in parts[first_wildcard:])
                or any(not part.isdigit() or not 0 <= int(part) <= 255 for part in parts[:first_wildcard])
            ):
                raise ValueError("IPv4 wildcard must use trailing octets, for example 192.168.*.*")
            octets = [int(part) for part in parts[:first_wildcard]] + [0] * (4 - first_wildcard)
            return str(ipaddress.ip_network(f"{'.'.join(str(part) for part in octets)}/{first_wildcard * 8}"))
        if rule_type == "domain_regex":
            re.compile(value)
            return value
        if any(character.isspace() for character in value):
            raise ValueError("domain rules cannot contain spaces")
        value = value.lower().rstrip(".")
        if rule_type == "domain_suffix":
            value = value.removeprefix("*.").lstrip(".")
        elif rule_type == "domain":
            value = value.lstrip(".")
        if not value:
            raise ValueError("rule value cannot be empty")
        return value

    def _canonical_rule_key(self, rule: dict) -> tuple[str, str, bool]:
        rule_type = str(rule["type"])
        try:
            value = self._normalize_rule_value(rule_type, str(rule["value"]))
        except (ValueError, re.error):
            value = str(rule["value"]).strip().lower()
        return rule_type, value, bool(rule.get("invert", False))

    def _effective_rule_rows(self) -> list[dict]:
        rows: list[dict] = []
        custom_keys = {self._canonical_rule_key(rule) for rule in self.bypass_rules}
        cidrs = set(self._effective_cidrs) | set(PROTECTIVE_BYPASS_CIDRS) | self._local_cidrs
        domains = set(self._effective_domains) | set(PROTECTIVE_BYPASS_DOMAINS)

        gateway_cidr = ""
        if self._default_gateway:
            try:
                gateway_cidr = f"{ipaddress.ip_address(self._default_gateway)}/32"
                cidrs.add(gateway_cidr)
            except ValueError:
                pass
        proxy_value = self.proxy_host.get().strip()
        proxy_cidr = ""
        proxy_domain = ""
        if proxy_value:
            try:
                proxy_ip = ipaddress.ip_address(proxy_value.strip("[]"))
                proxy_cidr = f"{proxy_ip}/{proxy_ip.max_prefixlen}"
                cidrs.add(proxy_cidr)
            except ValueError:
                proxy_domain = proxy_value.lower().rstrip(".")
                domains.add(proxy_domain)

        for value in sorted(cidrs):
            rule = {"type": "ip_cidr", "value": value, "invert": False}
            if self._canonical_rule_key(rule) in custom_keys:
                continue
            protected = value in PROTECTIVE_BYPASS_CIDRS or value in self._local_cidrs or value in {gateway_cidr, proxy_cidr}
            rows.append({**rule, "source": "system" if protected else "preset", "editable": False})
        for value in sorted(domains):
            rule_type = "domain_suffix" if value.startswith(".") else "domain"
            rule = {"type": rule_type, "value": value.lstrip("."), "invert": False}
            if self._canonical_rule_key(rule) in custom_keys:
                continue
            protected = value in PROTECTIVE_BYPASS_DOMAINS or value == proxy_domain
            rows.append({**rule, "source": "system" if protected else "preset", "editable": False})
        rows.extend({**rule, "source": "custom", "editable": True, "custom_index": index} for index, rule in enumerate(self.bypass_rules))
        return rows

    def _render_bypass_rules(self, selected: int | None = None) -> None:
        if not hasattr(self, "rule_tree"):
            return
        selected_iid = f"custom:{selected}" if selected is not None else None
        if selected_iid is None and self.rule_tree.selection():
            selected_iid = self.rule_tree.selection()[0]
        self.rule_tree.delete(*self.rule_tree.get_children())
        self._rule_rows_by_iid.clear()
        search = self.rule_search.get().strip().lower()
        rows = self._effective_rule_rows()
        visible_count = 0
        system_count = sum(not row["editable"] for row in rows)
        custom_count = sum(row["editable"] for row in rows)
        for row_index, rule in enumerate(rows):
            source_text = self.tr(f"rule_source_{rule['source']}")
            match_text = self._rule_type_text(str(rule["type"]))
            haystack = f"{source_text} {match_text} {rule['value']}".lower()
            if search and search not in haystack:
                continue
            iid = f"custom:{rule['custom_index']}" if rule["editable"] else f"system:{row_index}"
            self._rule_rows_by_iid[iid] = rule
            self.rule_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    source_text,
                    match_text,
                    rule["value"],
                    self.tr("yes") if rule.get("invert") else self.tr("no"),
                ),
                tags=() if rule["editable"] else ("protected",),
            )
            visible_count += 1
        if selected_iid in self._rule_rows_by_iid:
            self.rule_tree.selection_set(selected_iid)
            self.rule_tree.focus(selected_iid)
            self.rule_tree.see(selected_iid)
        self.rule_summary.set(
            self.tr("rule_count", visible=visible_count, system=system_count, custom=custom_count)
        )
        self._update_rule_controls()

    def _selected_rule_index(self) -> int | None:
        selection = self.rule_tree.selection()
        if not selection:
            messagebox.showwarning(self.tr("section_rules"), self.tr("rule_select_first"), parent=self)
            return None
        row = self._rule_rows_by_iid.get(selection[0])
        if not row or not row["editable"]:
            messagebox.showinfo(self.tr("section_rules"), self.tr("rule_protected"), parent=self)
            return None
        return int(row["custom_index"])

    def _update_rule_controls(self) -> None:
        if "edit_rule" not in self._buttons:
            return
        selection = self.rule_tree.selection()
        row = self._rule_rows_by_iid.get(selection[0]) if selection else None
        state = "normal" if row and row["editable"] else "disabled"
        self._buttons["edit_rule"].configure(state=state)
        self._buttons["delete_rule"].configure(state=state)

    def add_rule(self) -> None:
        self._open_rule_dialog()

    def edit_rule(self) -> None:
        index = self._selected_rule_index()
        if index is not None:
            self._open_rule_dialog(index)

    def delete_rule(self) -> None:
        index = self._selected_rule_index()
        if index is None:
            return
        if not messagebox.askyesno(
            self.tr("delete_rule"),
            self.tr("rule_delete_confirm"),
            parent=self,
        ):
            return
        del self.bypass_rules[index]
        self._render_bypass_rules(min(index, len(self.bypass_rules) - 1))

    def _open_rule_dialog(self, index: int | None = None) -> None:
        editing = index is not None
        existing = self.bypass_rules[index] if editing else {"type": "domain_suffix", "value": "", "invert": False}
        window = tk.Toplevel(self)
        window.title(self.tr("edit_rule") if editing else self.tr("add_rule"))
        window.configure(bg="#f7f8fa")
        window.transient(self)
        window.resizable(False, False)
        window.grab_set()

        content = ttk.Frame(window, padding=20, style="Page.TFrame")
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)

        type_names = {self._rule_type_text(rule_type): rule_type for rule_type in RULE_TYPES}
        selected_type = tk.StringVar(value=self._rule_type_text(str(existing["type"])))
        value_var = tk.StringVar(value=str(existing["value"]))
        invert_var = tk.BooleanVar(value=bool(existing.get("invert", False)))

        ttk.Label(content, text=self.tr("rule_match"), style="PageField.TLabel").grid(row=0, column=0, sticky="w")
        type_box = ttk.Combobox(
            content,
            textvariable=selected_type,
            values=list(type_names),
            state="readonly",
            width=42,
        )
        type_box.grid(row=1, column=0, sticky="ew", pady=(5, 14))
        ttk.Label(content, text=self.tr("rule_value"), style="PageField.TLabel").grid(row=2, column=0, sticky="w")
        value_entry = HistoryEntry(content, textvariable=value_var, width=48)
        value_entry.grid(row=3, column=0, sticky="ew", pady=(5, 14))
        ttk.Checkbutton(content, text=self.tr("rule_invert_option"), variable=invert_var).grid(
            row=4, column=0, sticky="w"
        )

        buttons = ttk.Frame(content, style="Page.TFrame")
        buttons.grid(row=5, column=0, sticky="e", pady=(20, 0))

        def confirm() -> None:
            value = value_var.get().strip()
            rule_type = type_names[selected_type.get()]
            if not value:
                messagebox.showwarning(self.tr("section_rules"), self.tr("rule_value_required"), parent=window)
                return
            try:
                value = self._normalize_rule_value(rule_type, value)
            except (ValueError, re.error) as exc:
                messagebox.showerror(
                    self.tr("section_rules"),
                    self.tr("rule_value_invalid", error=str(exc)),
                    parent=window,
                )
                return
            rule = {"type": rule_type, "value": value, "invert": invert_var.get()}
            candidate_key = self._canonical_rule_key(rule)
            duplicate_custom = any(
                other_index != index and self._canonical_rule_key(other) == candidate_key
                for other_index, other in enumerate(self.bypass_rules)
            )
            duplicate_system = any(
                not row["editable"] and self._canonical_rule_key(row) == candidate_key
                for row in self._effective_rule_rows()
            )
            if duplicate_custom or duplicate_system:
                messagebox.showwarning(self.tr("section_rules"), self.tr("rule_duplicate"), parent=window)
                return
            if editing:
                self.bypass_rules[index] = rule
                selected = index
            else:
                self.bypass_rules.append(rule)
                selected = len(self.bypass_rules) - 1
            self._render_bypass_rules(selected)
            window.destroy()

        ttk.Button(buttons, text=self.tr("cancel"), command=window.destroy).pack(side="left")
        ttk.Button(buttons, text=self.tr("confirm"), command=confirm, style="Primary.TButton").pack(
            side="left", padx=(8, 0)
        )
        window.bind("<Escape>", lambda _event: window.destroy())
        window.bind("<Return>", lambda _event: confirm())
        value_entry.focus_set()
        window.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - window.winfo_reqwidth()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - window.winfo_reqheight()) // 2)
        window.geometry(f"+{x}+{y}")

    def _set_window_icon(self) -> None:
        path = find_asset(ICON_NAME)
        if not path:
            return
        try:
            self._window_icon = tk.PhotoImage(file=str(path))
            self.iconphoto(True, self._window_icon)
        except tk.TclError:
            pass

    def _tray_image(self, active: bool = False):
        cache_key = "active" if active else "inactive"
        if cache_key in self._tray_images:
            return self._tray_images[cache_key]
        path = find_asset(ICON_NAME)
        if not path or Image is None:
            return None
        base = Image.open(path).convert("RGBA")
        image = make_active_tray_image(base) if active else base
        self._tray_images[cache_key] = image
        return image

    def set_tray_active(self, active: bool) -> None:
        self._tray_active = active
        if self._tray_icon is None:
            return
        image = self._tray_image(active)
        if image is None:
            return
        self._tray_icon.icon = image

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
        image = self._tray_image(self._tray_active)
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

    def _label(self, parent: tk.Widget, key: str, **kwargs: object) -> ttk.Label:
        label = ttk.Label(parent, text=self.tr(key), **kwargs)
        self._labels[key] = label
        return label

    def _button(self, parent: tk.Widget, key: str, command: Callable, **kwargs: object) -> ttk.Button:
        button = ttk.Button(parent, text=self.tr(key), command=command, **kwargs)
        self._buttons[key] = button
        return button

    def _check(
        self,
        parent: tk.Widget,
        key: str,
        variable: tk.BooleanVar,
        command: Callable | None = None,
    ) -> ttk.Checkbutton:
        check = ttk.Checkbutton(parent, text=self.tr(key), variable=variable, command=command)
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
        for key, frame in self._frames.items():
            frame.configure(text=self.tr(key))
        for key, page in self._tabs.items():
            self.notebook.tab(page, text=self.tr(key))
        for key, radio in self._radios.items():
            radio.configure(text=self.tr(key))
        if hasattr(self, "traffic_tree"):
            self._update_traffic_headings()
            self._render_traffic_logs()
        if hasattr(self, "rule_tree"):
            self.rule_tree.heading("source", text=self.tr("rule_source"))
            self.rule_tree.heading("match", text=self.tr("rule_match"))
            self.rule_tree.heading("value", text=self.tr("rule_value"))
            self.rule_tree.heading("invert", text=self.tr("rule_invert"))
            self._render_bypass_rules()
        self._set_status(self._last_status_key, **self._last_status_kwargs)
        self._update_service_controls()

    def _on_tab_changed(self, _event: tk.Event | None = None) -> None:
        if self.notebook.select() == str(self._tabs["tab_logs"]):
            self.refresh_traffic_logs()
        else:
            self._cancel_log_refresh()

    def _cancel_log_refresh(self) -> None:
        if self._log_refresh_job is not None:
            self.after_cancel(self._log_refresh_job)
            self._log_refresh_job = None

    def _schedule_log_refresh(self) -> None:
        self._cancel_log_refresh()
        if self.auto_refresh_logs.get() and self.notebook.select() == str(self._tabs["tab_logs"]):
            self._log_refresh_job = self.after(3000, self.refresh_traffic_logs)

    def refresh_traffic_logs(self) -> None:
        self._cancel_log_refresh()
        if not CONTROLLER.exists():
            self.traffic_summary.set(self.tr("status_missing_controller", path=CONTROLLER))
            return
        result = run_controller("logs", extra=["--limit", "500"])
        data = self._json_from_result(result)
        if result.returncode != 0 or not data:
            self.traffic_summary.set(self.tr("traffic_unavailable"))
            self._schedule_log_refresh()
            return
        self._traffic_entries = list(data.get("entries") or [])
        self._render_traffic_logs()
        self._schedule_log_refresh()

    def _route_text(self, route: str) -> str:
        key = {"proxy": "route_proxy", "direct": "route_direct", "block": "route_block"}.get(route)
        return self.tr(key) if key else route

    def _visible_traffic_entries(self) -> list[dict]:
        search = self.traffic_search.get().strip().lower()
        route_filter = self.traffic_route.get()
        visible = []
        for entry in self._traffic_entries:
            if route_filter != "all" and entry.get("route") != route_filter:
                continue
            haystack = " ".join(
                str(entry.get(key) or "") for key in ("destination", "port", "network", "route", "via", "connection_id")
            ).lower()
            if search and search not in haystack:
                continue
            visible.append(entry)
        return visible

    def _update_traffic_headings(self) -> None:
        for column, key in self._tree_headings.items():
            marker = ""
            if column == self._traffic_sort_column:
                marker = " v" if self._traffic_sort_reverse else " ^"
            self.traffic_tree.heading(column, text=self.tr(key) + marker)

    def _sort_traffic_logs(self, column: str) -> None:
        if self._traffic_sort_column == column:
            self._traffic_sort_reverse = not self._traffic_sort_reverse
        else:
            self._traffic_sort_column = column
            self._traffic_sort_reverse = False
        self._update_traffic_headings()
        self._render_traffic_logs()

    def _traffic_sort_value(self, entry: dict) -> object:
        value = entry.get(self._traffic_sort_column)
        if self._traffic_sort_column in {"port", "connection_id"}:
            try:
                return int(value)
            except (TypeError, ValueError):
                return -1
        return str(value or "").lower()

    def _sorted_visible_traffic_entries(self) -> list[dict]:
        return sorted(
            self._visible_traffic_entries(),
            key=self._traffic_sort_value,
            reverse=self._traffic_sort_reverse,
        )

    def _copy_selected_traffic(self, _event: tk.Event | None = None) -> str:
        selection = self.traffic_tree.selection()
        if selection:
            values = self.traffic_tree.item(selection[0], "values")
            self.clipboard_clear()
            self.clipboard_append("\t".join(str(value) for value in values))
        return "break"

    def export_traffic_logs(self) -> None:
        visible = self._sorted_visible_traffic_entries()
        if not visible:
            messagebox.showwarning(self.tr("export_logs"), self.tr("export_empty"))
            return
        path = filedialog.asksaveasfilename(
            title=self.tr("export_logs"),
            defaultextension=".csv",
            initialfile=f"traffic-logs-{datetime.now():%Y%m%d-%H%M%S}.csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*")],
        )
        if not path:
            return
        columns = ("time", "destination", "port", "network", "route", "via", "connection_id")
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(self.tr(self._tree_headings[column]) for column in columns)
                for entry in visible:
                    writer.writerow(
                        (
                            entry.get("time") or "",
                            entry.get("destination") or "",
                            entry.get("port") or "",
                            str(entry.get("network") or "").upper(),
                            self._route_text(str(entry.get("route") or "")),
                            entry.get("via") or "",
                            entry.get("connection_id") or "",
                        )
                    )
        except OSError as exc:
            messagebox.showerror(self.tr("export_logs"), str(exc))
            return
        messagebox.showinfo(self.tr("export_logs"), self.tr("export_success", count=len(visible), path=path))

    def _render_traffic_logs(self) -> None:
        if not hasattr(self, "traffic_tree"):
            return
        visible = self._sorted_visible_traffic_entries()

        self.traffic_tree.delete(*self.traffic_tree.get_children())
        for entry in visible:
            route = str(entry.get("route") or "")
            self.traffic_tree.insert(
                "",
                "end",
                values=(
                    entry.get("time") or "",
                    entry.get("destination") or "",
                    entry.get("port") or "",
                    str(entry.get("network") or "").upper(),
                    self._route_text(route),
                    entry.get("via") or "",
                    entry.get("connection_id") or "",
                ),
                tags=(route,),
            )
        if visible:
            self.traffic_summary.set(self.tr("traffic_count", visible=len(visible), total=len(self._traffic_entries)))
        else:
            self.traffic_summary.set(self.tr("traffic_empty"))

    def _set_status(self, key: str, **kwargs: object) -> None:
        self._last_status_key = key
        self._last_status_kwargs = kwargs
        self.status_text.set(self.tr(key, **kwargs))

    @staticmethod
    def _format_speed(bytes_per_second: float) -> str:
        value = max(0.0, bytes_per_second)
        for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
            if value < 1024.0 or unit == "GB/s":
                return f"{value:.0f} {unit}" if unit == "B/s" else f"{value:.1f} {unit}"
            value /= 1024.0
        return "0 B/s"

    def _schedule_speed_refresh(self, immediate: bool = False) -> None:
        if self._speed_refresh_job is not None:
            self.after_cancel(self._speed_refresh_job)
            self._speed_refresh_job = None
        if immediate:
            self._refresh_speed()
        else:
            self._speed_refresh_job = self.after(1000, self._refresh_speed)

    def _refresh_speed(self) -> None:
        self._speed_refresh_job = None
        result = run_controller("traffic-stats")
        data = self._json_from_result(result) if result.returncode == 0 else None
        now = time.monotonic()
        if not data or not data.get("available"):
            self._last_traffic_sample = None
            self.upload_speed.set("0 B/s")
            self.download_speed.set("0 B/s")
        else:
            upload = int(data.get("upload_bytes") or 0)
            download = int(data.get("download_bytes") or 0)
            if self._last_traffic_sample is not None:
                previous_time, previous_upload, previous_download = self._last_traffic_sample
                elapsed = max(now - previous_time, 0.001)
                self.upload_speed.set(self._format_speed((upload - previous_upload) / elapsed))
                self.download_speed.set(self._format_speed((download - previous_download) / elapsed))
            self._last_traffic_sample = (now, upload, download)
        self._schedule_speed_refresh()

    def _update_effective_rule_context(self, data: dict) -> None:
        if "bypass_cidrs" in data:
            self._effective_cidrs = set(PROTECTIVE_BYPASS_CIDRS)
            self._effective_cidrs.update(str(value) for value in data.get("bypass_cidrs") or [] if value)
        if "bypass_domains" in data:
            self._effective_domains = set(PROTECTIVE_BYPASS_DOMAINS)
            self._effective_domains.update(str(value) for value in data.get("bypass_domains") or [] if value)
        if "local_cidrs" in data:
            self._local_cidrs = {str(value) for value in data.get("local_cidrs") or [] if value}
        if "default_gateway" in data:
            self._default_gateway = str(data.get("default_gateway") or "")
        self._render_bypass_rules()

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
                label = self.tr(f"tcp_label_{item.get('label')}") if item.get("label") else self.tr("unknown")
                if item.get("reachable"):
                    lines.append(self.tr("diagnose_tcp_ok", label=label, target=item.get("target")))
                else:
                    lines.append(self.tr("diagnose_tcp_bad", label=label, target=item.get("target"), error=item.get("error") or ""))
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
            "bypass_cidrs": [],
            "bypass_domains": [],
            "bypass_rules": [dict(rule) for rule in self.bypass_rules],
            "block_udp_when_unsupported": self.block_udp.get(),
            "bypass_system_packages": self.bypass_system_packages.get(),
            "bypass_container_registries": self.bypass_container_registries.get(),
            "language": self.language_code,
        }

    def log(self, title: str, result: subprocess.CompletedProcess[str] | str, kind: str = "plain") -> None:
        content = self.format_result(kind, result)
        self._last_log_title = title
        self._last_log_content = content

    def _set_button_busy(self, key: str, text_key: str) -> None:
        button = self._buttons[key]
        button.configure(text=self.tr(text_key), style="Busy.TButton", state="disabled")
        self.update_idletasks()

    def _restore_button(self, key: str) -> None:
        base_style = "Primary.TButton" if key == "apply" else "TButton"
        self._buttons[key].configure(text=self.tr(key), style=base_style, state="normal")
        self._update_service_controls()

    def _update_service_controls(self) -> None:
        if "turn_on" not in self._buttons or "turn_off" not in self._buttons:
            return
        turn_on = self._buttons["turn_on"]
        turn_off = self._buttons["turn_off"]
        if self._service_active is True:
            turn_on.configure(text=self.tr("service_running_button"), style="Active.TButton", state="disabled")
            turn_off.configure(text=self.tr("turn_off"), style="Danger.TButton", state="normal")
        elif self._service_active is False:
            turn_on.configure(text=self.tr("turn_on"), style="Primary.TButton", state="normal")
            turn_off.configure(text=self.tr("service_stopped_button"), style="Inactive.TButton", state="disabled")
        else:
            turn_on.configure(text=self.tr("turn_on"), style="Primary.TButton", state="normal")
            turn_off.configure(text=self.tr("turn_off"), style="TButton", state="normal")

    def _show_result(self, title: str, ok: bool, warning: bool = False) -> bool:
        if self._tray_action_title:
            return False
        content = self._last_log_content or self.tr("operation_ok")
        if not ok:
            messagebox.showerror(title, content)
        elif warning:
            messagebox.showwarning(title, content)
        else:
            messagebox.showinfo(title, content)
        return True

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
        self._set_button_busy("apply", "applying")
        try:
            result = run_controller("apply", privileged=True, extra=["--config", str(USER_CONFIG)])
        finally:
            self._restore_button("apply")
        self.log(self.tr("log_apply"), result, kind="apply")
        if result.returncode != 0:
            messagebox.showerror(APP_NAME, self._last_log_content or self.tr("apply_failed"))
            self.maybe_notify_tray_action(ok=False)
            return False
        self.maybe_notify_tray_action()
        self.refresh_status(notify=False)
        return True

    def turn_on(self) -> None:
        if not self.save():
            return
        self._set_button_busy("turn_on", "starting")
        try:
            result = run_controller("apply-start", privileged=True, extra=["--config", str(USER_CONFIG)])
        finally:
            self._restore_button("turn_on")
        self.log(self.tr("log_turn_on"), result, kind="apply-start")
        if result.returncode != 0:
            self.maybe_notify_tray_action(ok=False)
            if not self._tray_action_title:
                messagebox.showerror(APP_NAME, self._last_log_content)
            return
        self.maybe_notify_tray_action()
        self.refresh_status(notify=False)

    def turn_off(self) -> None:
        self._set_button_busy("turn_off", "stopping")
        try:
            result = run_controller("stop", privileged=True)
        finally:
            self._restore_button("turn_off")
        self.log(self.tr("log_turn_off"), result, kind="stop")
        self.maybe_notify_tray_action(ok=result.returncode == 0)
        self.refresh_status(notify=False)

    def test(self) -> None:
        if not self.save():
            return
        self._set_button_busy("test", "testing")
        try:
            result = run_controller("test", extra=["--config", str(USER_CONFIG)])
        finally:
            self._restore_button("test")
        self.log(self.tr("log_test"), result, kind="test")
        data = self._json_from_result(result) or {}
        command_ok = result.returncode == 0
        test_ok = command_ok and data.get("proxy_reachable") is True and data.get("proxy_http_test") == "ok"
        self._show_result(self.tr("log_test"), command_ok, warning=command_ok and not test_ok)
        self.maybe_notify_tray_action(ok=test_ok)

    def diagnose(self) -> None:
        if not self.save():
            return
        self._set_button_busy("diagnose", "diagnosing")
        try:
            result = run_controller("diagnose", extra=["--config", str(USER_CONFIG)])
        finally:
            self._restore_button("diagnose")
        self.log(self.tr("log_diagnose"), result, kind="diagnose")
        data = self._json_from_result(result) or {}
        self._update_effective_rule_context(data)
        checks = data.get("tcp_checks") or []
        command_ok = result.returncode == 0
        reachable = any(item.get("reachable") for item in checks)
        self._show_result(self.tr("log_diagnose"), command_ok, warning=command_ok and not reachable)
        self.maybe_notify_tray_action(ok=command_ok and reachable)

    def refresh_status(self, notify: bool = True) -> None:
        if not CONTROLLER.exists():
            self.set_tray_active(False)
            self._service_active = None
            self._update_service_controls()
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
                self._update_effective_rule_context(data)
                self._service_active = data.get("active") == "active"
                self.set_tray_active(self._service_active)
                self._update_service_controls()
                self._set_status(
                    "status_summary",
                    active=data.get("active"),
                    enabled=data.get("enabled"),
                    host=data.get("proxy_host"),
                    port=data.get("proxy_port"),
                )
            except json.JSONDecodeError:
                self.set_tray_active(False)
                self._service_active = None
                self._update_service_controls()
                self._set_status("status_non_json")
        else:
            self.set_tray_active(False)
            self._service_active = None
            self._update_service_controls()
            self._set_status("status_failed")

    def discover(self) -> None:
        self._set_button_busy("discover", "discovering")
        try:
            result = run_controller("discover")
        finally:
            self._restore_button("discover")
        self.log(self.tr("log_discover"), result, kind="discover")
        data = self._json_from_result(result) or {}
        if data:
            self._update_effective_rule_context(data)
        candidates = data.get("proxy_candidates") or []
        if candidates and not self.proxy_host.get().strip():
            self.proxy_host.set(candidates[0])
            self._set_status("status_discovered", candidate=candidates[0])
        command_ok = result.returncode == 0
        self._show_result(self.tr("log_discover"), command_ok, warning=command_ok and not candidates)
        self.maybe_notify_tray_action(ok=command_ok)


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
