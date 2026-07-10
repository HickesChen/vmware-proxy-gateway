# VM Proxy Gateway

[简体中文文档](README.zh-CN.md)

VM Proxy Gateway is a small Ubuntu desktop tool for developers who run VS Code,
Cursor, Codex, or similar tools on a Windows host, then connect to an Ubuntu
virtual machine over SSH/Remote Development while the usable proxy also runs on
the Windows host.

The main problem it solves: after VS Code or Cursor connects from the Windows
host into the VM, extension installation, remote server downloads, marketplace
access, language services, AI/Codex requests, Git, npm, pip, and other tool
traffic may be launched by processes running inside the Ubuntu VM. That traffic
often does not follow Windows proxy settings, desktop proxy settings, browser
proxy settings, or simple host-port forwarding rules. As a result, plugin
installation or remote development features can hang or fail even though the
Windows host itself can access the network.

VM Proxy Gateway creates a transparent TUN proxy on the Ubuntu side and sends
normal VM TCP/DNS traffic to the Windows-hosted proxy, for example:

```text
Windows host proxy: <host-ip>:<port>
Ubuntu VM traffic:  transparent TUN proxy through sing-box
```

In short, it gives the VM a practical way to "borrow" the Windows host proxy for
development traffic that ordinary proxy configuration cannot reliably catch.

## What it does

- Runs a `sing-box` TUN service on Ubuntu.
- Captures normal TCP traffic and DNS from the VM.
- Sends traffic to the Windows host proxy.
- Helps traffic launched inside the VM by VS Code Remote/Cursor sessions,
  extension/plugin installation, remote development tooling, Git, npm, pip, and
  AI/Codex-style tools reach the network through the Windows proxy.
- Keeps localhost, the VM local IP, the host proxy IP, and private LAN ranges
  direct by default.
- Provides a Tkinter GUI to configure language, host, port, protocol, on/off
  state, and custom bypass rules. The GUI supports English, Simplified Chinese,
  and Traditional Chinese.
- Includes a desktop/tray icon. Closing the window keeps the app in the system
  tray; use the tray menu for quick actions or safe exit.
- Provides preset bypass switches for traffic that is often better left direct,
  such as APT/Snap/Flatpak system package downloads and optional container image
  registries.
- Provides a dedicated traffic log page with destination, port, and proxy/direct
  filtering from real sing-box forwarding events.
- Persists GUI settings under:

```text
~/.config/vm-proxy-gateway/config.json
```

System service configuration is generated under:

```text
/etc/vm-proxy-gateway/
```

## Install on Ubuntu VM

Copy this folder to the Ubuntu VM, then run:

```bash
chmod +x install.sh uninstall.sh
sudo ./install.sh
```

The installer automatically cleans older VM Proxy Gateway application files,
systemd unit files, desktop entries, symlinks, and generated sing-box runtime
configuration before installing the new version. It keeps user preferences under
`~/.config/vm-proxy-gateway/`.

Then start the GUI:

```bash
vm-proxy-gateway-gui
```

You can also launch **VM Proxy Gateway** from the application menu.

The installer adds the application icon and installs the tray dependencies used
by the GUI. It also installs a narrow sudoers rule for VM Proxy Gateway commands
so the GUI does not ask for a password every time you apply, turn on, turn off,
or safely exit. You still need `sudo` for installation and uninstallation.

Installer options for constrained environments:

```bash
sudo ./install.sh --skip-deps
sudo ./install.sh --skip-sing-box
sudo ./install.sh --no-sudoers
```

These are useful when dependencies are already installed, sing-box is managed
separately, or your organization does not allow NOPASSWD sudoers rules. The
installer tries dependency installation first and only refreshes APT metadata if
that fails.

## First run

1. Choose **English**, **简体中文**, or **繁體中文** from the language selector.
2. Enter the Windows host proxy IP and a port that matches your Windows proxy setup.
3. Leave protocol as `auto` unless you know it is HTTP only.
4. Click **Save** / **保存** / **儲存**.
5. Click **Apply** / **应用** / **套用**.
6. Click **Turn On** / **开启** / **開啟**.
7. Click **Test** / **测试** / **測試**.

If `apt update` or package downloads appear stuck, keep **Bypass system package
downloads (APT / Snap / Flatpak)** enabled. This sends Ubuntu/Debian package
mirrors and common app-store downloads directly instead of through the
transparent proxy. This is a runtime setting in the GUI, not an installer
option.

Closing the window minimizes the app to the system tray instead of quitting it.
Right-click the tray icon to open the window, apply settings, turn the proxy on
or off, run tests, diagnose problems, refresh status, or exit. The tray **Exit**
action turns the proxy service off before the app closes.

Tray menu actions show a pop-up with the operation result, so you can tell
whether turning the proxy on/off, testing, or diagnosis succeeded without
reopening the main window.

The **Test** action checks two things:

- whether `<host-ip>:<port>` accepts TCP connections;
- whether HTTPS traffic can reach the internet through the proxy.

For SOCKS5, the test uses `socks5h`, so DNS resolution happens through the
proxy instead of the Ubuntu VM's current DNS resolver.

If your VM uses VMware NAT, the auto-discovered candidate is often the default
gateway. If you use bridged networking, the Windows host may be on the same LAN
as the VM, for example `192.168.0.6` and `192.168.0.9`.

Do not use `ping` as the final proxy test. Windows Defender Firewall often
blocks ICMP, so `ping <host-ip>` can fail even when the proxy TCP port works.
Test the proxy port instead:

```bash
nc -vz <host-ip> <port>
```

Or use the built-in diagnosis:

```bash
vm-proxy-gateway diagnose --config ~/.config/vm-proxy-gateway/config.json
```

For public websites, prefer TCP/HTTPS checks over ICMP checks:

```bash
curl -4 -I https://www.google.com
```

The generated DNS configuration uses IPv4-only answers by default because many
Ubuntu VMs have no usable IPv6 route even when DNS returns IPv6 records. A
failed `ping -6` usually means IPv6 is unavailable in the VM, not that the
Windows proxy is broken.

If the configured TCP port is unreachable from Ubuntu, check the Windows proxy app:

- Enable LAN access / allow LAN.
- Bind the proxy to `0.0.0.0` or the Windows LAN/VMware IP, not only `127.0.0.1`.
- Allow inbound TCP on the configured port in Windows Defender Firewall on the private network.

## Bypass rules

The tool always adds protective bypass rules for:

- `127.0.0.0/8`
- `localhost`
- VM local IPs and local subnets
- the default gateway
- the configured proxy host
- common private LAN ranges:
  - `10.0.0.0/8`
  - `172.16.0.0/12`
  - `192.168.0.0/16`

The GUI keeps custom bypass rules in one table. Use **Add rule** to choose IP / CIDR,
exact domain, domain prefix, domain suffix, keyword, or regular-expression matching.
Rules can also be inverted. Existing CIDR and domain entries from older versions are
merged into this table automatically.
The table also shows read-only system protection, current proxy, default gateway,
VM-local address/subnet, and applied preset rules alongside editable custom rules.

IP / CIDR rules accept values such as:

```text
192.168.88.0/24
192.168.88.20/32
192.168.10.*
10.*.*.*
```

IPv4 wildcards must cover complete trailing octets. For example,
`192.168.*.*` is equivalent to `192.168.0.0/16`; a discontinuous pattern such
as `192.*.1.*` is rejected.

Domain rules accept values such as:

```text
nas.local
.corp
.lan
```

Preset bypass switches:

- **System package downloads**: enabled by default. Covers Ubuntu/Debian package
  mirrors, Canonical/Snap, Launchpad, Flathub-style downloads, and common
  Ubuntu mirror providers such as Aliyun, Tsinghua, USTC, Huawei Cloud, Tencent
  Cloud, Nanjing University, Shanghai Jiao Tong University, and NetEase. It also
  bypasses common package-manager processes such as `apt`, `apt-get`,
  `apt-helper`, `dpkg`, `snapd`, and `flatpak`, so package downloads do not
  depend only on domain sniffing.
- **Container image registries**: disabled by default. Enable it only if Docker,
  Podman, or Kubernetes image pulls behave better direct than through the
  Windows proxy.

Other traffic that may deserve a separate bypass switch later:

- OS vendor updates or app stores beyond Ubuntu/Snap/Flatpak, if you use them.
- Container registries used by your company or lab, if they are LAN/private
  endpoints.
- Internal corporate domains, NAS, router, printer, database, and development
  lab hosts. For these, custom bypass domains/CIDRs are usually better than a
  broad built-in preset.

Git, npm, pip, VS Code, Codex, Cursor, and browser traffic are intentionally not
bypassed by default because they are the main traffic classes this tool is meant
to help route through the Windows proxy.

## CLI

```bash
vm-proxy-gateway discover
vm-proxy-gateway status
vm-proxy-gateway logs --limit 300
vm-proxy-gateway diagnose --config ~/.config/vm-proxy-gateway/config.json
vm-proxy-gateway test --config ~/.config/vm-proxy-gateway/config.json
sudo vm-proxy-gateway apply --config ~/.config/vm-proxy-gateway/config.json
sudo vm-proxy-gateway start
sudo vm-proxy-gateway stop
sudo vm-proxy-gateway restart
sudo vm-proxy-gateway uninstall
```

## Scenario validation

Before installing or after changing the package, you can run the built-in
scenario checks from the source folder:

```bash
python3 tools/validate_scenarios.py
```

The checks simulate different DNS setups, systemd-resolved stub DNS, Deb822 and
legacy APT source formats, custom mirror domains, domain proxy hosts, invalid
proxy ports, container registry defaults, safe stop behavior when the service
unit is missing, active-service config restarts, single-instance GUI locking,
active tray icon tinting, UDP blocking, and generated sing-box config shape.

## GitHub Project Hygiene

This repository includes:

- MIT license. This is a permissive free and open-source license; it grants
  usage, copy, modification, and distribution rights while clarifying warranty
  limits.
- GitHub Actions CI for syntax and scenario validation.
- Bug report issue template.
- Security policy describing privileged operations.
- Contributing guide and changelog.
- English and Simplified Chinese documentation.

## Important limits

- This first version targets Ubuntu VMs and assumes `systemd`.
- TCP and DNS are the main supported traffic classes.
- UDP support depends on the upstream proxy at `host:<port>`.
- If your Windows proxy only listens on `127.0.0.1`, the Ubuntu VM cannot use it.
  Configure the Windows proxy to listen on a VM-reachable host IP.

## Emergency recovery

If networking behaves badly, run in the Ubuntu VM:

```bash
sudo systemctl stop vm-proxy-gateway.service
sudo systemctl disable vm-proxy-gateway.service
```

To remove the application:

```bash
sudo ./uninstall.sh
```

The uninstall script removes the application files, command symlinks, desktop
entry, installed icons, systemd unit, sudoers rule, and `/etc/vm-proxy-gateway`.
It leaves `~/.config/vm-proxy-gateway/` in your home directory so your personal
GUI preferences are not deleted unexpectedly.
