# Changelog

[简体中文](CHANGELOG.zh-CN.md)

## 0.1.5

- Hardened runtime configuration for domain proxy hosts, invalid proxy ports,
  custom bypass domain normalization, active-service restarts, stale TUN/DNS
  cleanup, UDP blocking, and IPv4-only DNS behavior.
- Hardened installation when sing-box already exists outside `/usr/local/bin`
  and added sing-box verification.
- Hardened release automation for dirty release worktrees, remote divergence,
  release asset replacement, and explicit release workflow dependencies.
- Expanded scenario validation from 9 to 10 checks.

## 0.1.4

- Added an orange-yellow active tray icon so users can distinguish proxy on/off
  state from the system tray.
- Added validation coverage for active tray icon tinting.

## 0.1.3

- Added English, Simplified Chinese, and Traditional Chinese GUI language selection.
- Added desktop and system tray icons.
- Added tray actions for open, apply, turn on, turn off, test, diagnose, refresh, and safe exit.
- Added safe exit that stops the proxy service before the GUI exits.
- Added single-instance locking for the GUI.
- Added preset bypass switches for system package downloads and container registries.
- Added dynamic APT source domain detection for official, mirror, and private package sources.
- Added process-level bypass for common package managers so APT/Snap/Flatpak
  downloads do not depend only on domain sniffing.
- Refreshes generated service configuration before start/restart when a user
  config is available.
- Added robust local DNS detection instead of assuming `127.0.0.1:53`.
- Added scenario validation checks.
- Added installer options for constrained or offline environments.
