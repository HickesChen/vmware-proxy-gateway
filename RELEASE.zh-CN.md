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

4. 也可以直接使用发布脚本：

   ```bash
   tools/release.sh        # patch，例如 0.1.3 -> 0.1.4
   tools/release.sh minor  # 0.1.3 -> 0.2.0
   tools/release.sh major  # 0.1.3 -> 1.0.0
   tools/release.sh --version 1.2.3
   ```

   脚本会更新 `VERSION`、运行验证、提交、打 tag、推送 `main` 和 tag。
   GitHub Actions 随后会自动构建发布 zip，并把它挂到 GitHub Release。

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
