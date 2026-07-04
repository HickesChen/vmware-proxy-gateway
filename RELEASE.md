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

4. Commit the changes and push `main`.
5. Create and push a version tag:

   ```bash
   git tag -a v$(cat VERSION) -m "Release v$(cat VERSION)"
   git push origin v$(cat VERSION)
   ```

   GitHub Actions will build the release zip and attach it to the GitHub
   Release automatically.

6. Install on a fresh Ubuntu VM and verify:

   ```bash
   sudo ./install.sh
   vm-proxy-gateway-gui
   vm-proxy-gateway status
   ```

7. Confirm uninstall cleanup:

   ```bash
   sudo ./uninstall.sh
   ```
