# VM Proxy Gateway

[English documentation](README.md)

VM Proxy Gateway 是一个面向开发者的 Ubuntu 虚拟机桌面工具，适合在 Windows 主机上运行 VS Code、Cursor、Codex 或类似工具，然后通过 SSH/Remote Development 连接到 Ubuntu 虚拟机，而可用代理也运行在 Windows 主机上的场景。

它主要解决的问题是：当 VS Code 或 Cursor 从 Windows 主机远程连接到虚拟机后，插件安装、远程 server 下载、Marketplace 访问、语言服务、AI/Codex 请求、Git、npm、pip 等流量可能由 Ubuntu 虚拟机内部的进程发起。这些流量不一定遵循 Windows 代理设置、Ubuntu 桌面代理设置、浏览器代理设置，也经常不是简单端口转发规则能覆盖的。结果就是：Windows 主机本身能联网，但 VS Code/Cursor 远程开发里的插件安装、远程功能或开发工具仍然卡住或失败。

VM Proxy Gateway 在 Ubuntu 侧创建一个透明 TUN 代理，把虚拟机里的常规 TCP/DNS 流量发送到 Windows 主机代理，例如：

```text
Windows 主机代理：<host-ip>:10086
Ubuntu 虚拟机流量：通过 sing-box TUN 透明代理
```

简单说，它是给虚拟机准备的一条“借用 Windows 主机代理”的通道，用来接住普通代理配置和端口转发接不住的开发流量。

## 功能

- 在 Ubuntu 上运行 `sing-box` TUN 服务。
- 捕获虚拟机里的常规 TCP 流量和 DNS。
- 将流量发送到 Windows 主机代理。
- 帮助 VS Code Remote/Cursor 会话在虚拟机内部发起的流量、插件/扩展安装、远程开发工具、Git、npm、pip 和 AI/Codex 类工具通过 Windows 代理联网。
- 默认直连 localhost、虚拟机本地 IP、Windows 主机代理 IP、默认网关和常见私有网段。
- 提供 Tkinter GUI，可配置语言、代理主机、端口、协议、开启/关闭状态和自定义绕过规则。
- GUI 支持 English、简体中文、繁體中文。
- 提供桌面图标和系统托盘图标。关闭窗口会最小化到托盘，托盘菜单可执行快捷操作和安全退出。
- 提供预设绕过开关，例如 APT/Snap/Flatpak 系统包下载，以及可选的 Docker/Podman 容器镜像仓库。

GUI 用户配置保存于：

```text
~/.config/vm-proxy-gateway/config.json
```

系统服务配置生成于：

```text
/etc/vm-proxy-gateway/
```

## 安装

把这个目录复制到 Ubuntu 虚拟机，然后运行：

```bash
chmod +x install.sh uninstall.sh
sudo ./install.sh
```

安装器会清理旧版本应用文件、systemd unit、桌面入口、符号链接和旧的 sing-box 运行配置。用户偏好会保留在 `~/.config/vm-proxy-gateway/`。

启动 GUI：

```bash
vm-proxy-gateway-gui
```

也可以从应用菜单启动 **VM Proxy Gateway**。

安装器会安装图标和托盘依赖。默认还会安装一个范围很窄的 sudoers 规则，让 GUI 执行应用、开启、关闭、安全退出时不用每次重复输入密码。安装和卸载本身仍然需要 `sudo`。

受限或离线环境可使用：

```bash
sudo ./install.sh --skip-deps
sudo ./install.sh --skip-sing-box
sudo ./install.sh --no-sudoers
```

这些选项适合依赖已安装、sing-box 由你自己管理，或组织不允许 NOPASSWD sudoers 规则的场景。安装器会先直接安装依赖，只有依赖安装失败时才刷新一次 APT 元数据并重试。

## 首次使用

1. 在语言选择中选择 **English**、**简体中文** 或 **繁體中文**。
2. 填写 Windows 主机代理 IP 和端口，默认端口是 `10086`。
3. 协议保持 `auto`，除非你明确知道代理只支持 HTTP。
4. 点击 **保存**。
5. 点击 **应用**。
6. 点击 **开启**。
7. 点击 **测试**。

如果 `apt update` 或系统包下载卡住，请保持 **绕过系统包下载（APT / Snap / Flatpak）** 开启。它会让 Ubuntu/Debian 包源和常见应用商店下载直连，而不是走透明代理。这个开关是 GUI 里的运行时设置，不是安装参数。

关闭窗口不会退出程序，而是最小化到系统托盘。右键托盘图标可以打开窗口、应用设置、开启/关闭代理、测试、诊断、刷新状态或退出。托盘 **退出** 会先关闭代理服务，再退出程序。

托盘菜单操作会弹出结果提示，因此不打开主窗口也能知道开启、关闭、测试或诊断是否成功。

## 代理测试

**测试** 会检查两件事：

- `<host-ip>:10086` 是否能建立 TCP 连接；
- HTTPS 流量是否能通过代理访问互联网。

SOCKS5 测试使用 `socks5h`，因此 DNS 会通过代理解析，而不是由 Ubuntu 当前 DNS 解析。

VMware NAT 模式下，自动发现的候选地址通常是默认网关。桥接模式下，Windows 主机可能是同一局域网里的另一个 IP，例如 `192.168.0.6` 和 `192.168.0.9`。

不要把 `ping` 作为最终判断。Windows Defender 防火墙经常拦截 ICMP，所以 `ping <host-ip>` 失败并不代表代理端口不可用。请测试代理 TCP 端口：

```bash
nc -vz <host-ip> 10086
```

也可以使用内置诊断：

```bash
vm-proxy-gateway diagnose --config ~/.config/vm-proxy-gateway/config.json
```

如果 Ubuntu 无法连接 TCP `10086`，请检查 Windows 代理软件：

- 开启 LAN access / allow LAN。
- 绑定到 `0.0.0.0` 或 Windows 的 LAN/VMware IP，不要只监听 `127.0.0.1`。
- 在 Windows Defender 防火墙里允许专用网络入站 TCP `10086`。

## 绕过规则

工具总会添加保护性绕过规则：

- `127.0.0.0/8`
- `localhost`
- 虚拟机本地 IP 和本地子网
- 默认网关
- 配置的代理主机
- 常见私有网段：
  - `10.0.0.0/8`
  - `172.16.0.0/12`
  - `192.168.0.0/16`

可在 GUI 中添加自定义 CIDR 或 IP，每行一个：

```text
192.168.88.0/24
192.168.88.20/32
```

也可以添加域名或后缀，每行一个：

```text
nas.local
.corp
.lan
```

预设绕过开关：

- **系统包下载**：默认开启。覆盖 Ubuntu/Debian 包源、Canonical/Snap、Launchpad、Flathub，以及阿里、清华、中科大、华为云、腾讯云、南大、上交、网易等常见 Ubuntu 镜像。它还会让 `apt`、`apt-get`、`apt-helper`、`dpkg`、`snapd`、`flatpak` 等常见包管理进程直连，避免系统包下载完全依赖域名识别。
- **容器镜像仓库**：默认关闭。只有当 Docker、Podman 或 Kubernetes 拉镜像直连比走 Windows 代理更稳定时再开启。

Git、npm、pip、VS Code、Codex、Cursor 和浏览器流量默认不绕过，因为它们正是这个工具希望帮助走 Windows 代理的主要流量。

## CLI

```bash
vm-proxy-gateway discover
vm-proxy-gateway status
vm-proxy-gateway diagnose --config ~/.config/vm-proxy-gateway/config.json
vm-proxy-gateway test --config ~/.config/vm-proxy-gateway/config.json
sudo vm-proxy-gateway apply --config ~/.config/vm-proxy-gateway/config.json
sudo vm-proxy-gateway start
sudo vm-proxy-gateway stop
sudo vm-proxy-gateway restart
sudo vm-proxy-gateway uninstall
```

## 场景验证

安装前或修改代码后，可以在源码目录运行：

```bash
python3 tools/validate_scenarios.py
```

验证内容包括不同 DNS 设置、systemd-resolved stub DNS、Deb822 和传统 APT 源格式、自定义镜像域名、容器仓库默认值、服务 unit 缺失时的安全停止、GUI 单实例锁，以及生成的 sing-box 配置结构。

## GitHub 仓库内容

本仓库包含：

- MIT License。这是宽松的免费开源许可，用来明确允许使用、复制、修改和分发，同时说明免责声明。
- GitHub Actions CI。
- Bug report issue template。
- 安全策略。
- 贡献指南和变更日志。
- 英文和中文文档。

## 重要限制

- 当前版本主要面向使用 `systemd` 的 Ubuntu 虚拟机。
- 主要支持 TCP 和 DNS。
- UDP 支持取决于上游代理 `host:10086`。
- 如果 Windows 代理只监听 `127.0.0.1`，Ubuntu 虚拟机无法使用它。请改为监听虚拟机可访问的 Windows 主机 IP。

## 紧急恢复

如果网络异常，在 Ubuntu 虚拟机中运行：

```bash
sudo systemctl stop vm-proxy-gateway.service
sudo systemctl disable vm-proxy-gateway.service
```

卸载应用：

```bash
sudo ./uninstall.sh
```

卸载脚本会删除应用文件、命令符号链接、桌面入口、图标、systemd unit、sudoers 规则和 `/etc/vm-proxy-gateway`。它会保留 `~/.config/vm-proxy-gateway/`，避免意外删除你的个人 GUI 偏好。
