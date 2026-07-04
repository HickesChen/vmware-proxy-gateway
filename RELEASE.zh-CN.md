# 发布清单

[English](RELEASE.md)

1. 更新 `VERSION`。
2. 更新 `CHANGELOG.md` 和 `CHANGELOG.zh-CN.md`。
3. 运行验证：

   ```bash
   python3 -m py_compile app/vm_proxy_gateway.py app/vm_proxy_gateway_gui.py tools/validate_scenarios.py
   bash -n install.sh
   bash -n uninstall.sh
   python3 tools/validate_scenarios.py
   ```

4. 在父目录构建发布压缩包：

   ```bash
   zip -r vm-proxy-gateway-$(cat vm-proxy-gateway/VERSION).zip vm-proxy-gateway -x '*/.git/*' '*/__pycache__/*'
   ```

5. 在全新 Ubuntu 虚拟机安装并验证：

   ```bash
   sudo ./install.sh
   vm-proxy-gateway-gui
   vm-proxy-gateway status
   ```

6. 确认卸载清理：

   ```bash
   sudo ./uninstall.sh
   ```
