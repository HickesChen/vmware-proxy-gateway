# 贡献指南

[English](CONTRIBUTING.md)

感谢你帮助改进 VM Proxy Gateway。

## 开发检查

提交 Pull Request 前请运行：

```bash
python3 -m py_compile app/vm_proxy_gateway.py app/vm_proxy_gateway_gui.py tools/validate_scenarios.py
bash -n install.sh
bash -n uninstall.sh
python3 tools/validate_scenarios.py
```

如果 `/usr/local/bin/sing-box` 存在，场景验证还会检查生成的 sing-box 配置结构。

## 变更原则

- 控制器必须能在没有 GUI 的情况下通过 CLI 使用。
- GUI 相关文本需要同时维护 English、简体中文和繁體中文。
- 网络相关修改要谨慎。新增路由、DNS、包源或服务管理行为时，优先补充场景验证。
- 不要扩大 sudoers 规则范围，除非明确记录安全影响。
