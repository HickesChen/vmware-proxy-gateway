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

4. 提交修改并推送 `main`。
5. 创建并推送版本 tag：

   ```bash
   git tag -a v$(cat VERSION) -m "Release v$(cat VERSION)"
   git push origin v$(cat VERSION)
   ```

   GitHub Actions 会自动构建发布 zip，并把它挂到 GitHub Release。

6. 在全新 Ubuntu 虚拟机安装并验证：

   ```bash
   sudo ./install.sh
   vm-proxy-gateway-gui
   vm-proxy-gateway status
   ```

7. 确认卸载清理：

   ```bash
   sudo ./uninstall.sh
   ```
