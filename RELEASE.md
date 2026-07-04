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

4. Build the release archive from the parent directory:

   ```bash
   zip -r vm-proxy-gateway-$(cat vm-proxy-gateway/VERSION).zip vm-proxy-gateway -x '*/.git/*' '*/__pycache__/*'
   ```

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
