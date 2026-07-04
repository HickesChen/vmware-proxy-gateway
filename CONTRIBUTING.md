# Contributing

[简体中文](CONTRIBUTING.zh-CN.md)

Thanks for helping improve VM Proxy Gateway.

## Development Checks

Run these before opening a pull request:

```bash
python3 -m py_compile app/vm_proxy_gateway.py app/vm_proxy_gateway_gui.py tools/validate_scenarios.py
bash -n install.sh
bash -n uninstall.sh
python3 tools/validate_scenarios.py
```

If `sing-box` is installed at `/usr/local/bin/sing-box`, the scenario validation
also checks the generated sing-box config shape.

## Change Guidelines

- Keep the controller usable from the CLI without the GUI.
- Keep GUI changes localized and translated in English, Simplified Chinese, and
  Traditional Chinese.
- Treat networking changes carefully. Prefer adding scenario checks for new
  routing, DNS, package source, or service-management behavior.
- Do not broaden the sudoers rule unless the security impact is documented.
