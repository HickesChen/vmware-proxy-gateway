# Release Checklist

[简体中文](RELEASE.zh-CN.md)

1. Update `VERSION`.
2. Update `CHANGELOG.md`.
3. Run validation:

   ```bash
   python3 -m py_compile app/vm_proxy_gateway.py app/vm_proxy_gateway_gui.py tools/validate_scenarios.py
   bash -n install.sh
   bash -n uninstall.sh
   python3 tools/validate_scenarios.py
   ```

4. Or use the release helper:

   ```bash
   tools/release.sh        # patch, for example 0.1.3 -> 0.1.4
   tools/release.sh minor  # 0.1.3 -> 0.2.0
   tools/release.sh major  # 0.1.3 -> 1.0.0
   tools/release.sh --version 1.2.3
   ```

   The helper updates `VERSION`, validates, commits, tags, pushes `main`, and
   pushes the tag. GitHub Actions then builds the release zip and attaches it to
   the GitHub Release automatically.

5. Install on a fresh Ubuntu VM and verify:

   ```bash
   sudo ./install.sh
   vm-proxy-gateway-gui
   vm-proxy-gateway status
   ```

6. Confirm uninstall cleanup:

   ```bash
   sudo ./uninstall.sh
   ```
