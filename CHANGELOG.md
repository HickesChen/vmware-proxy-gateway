# Changelog

[简体中文](CHANGELOG.zh-CN.md)

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
