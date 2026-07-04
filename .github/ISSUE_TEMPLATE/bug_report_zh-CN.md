---
name: 问题反馈
about: 反馈 VM Proxy Gateway 的问题
title: ""
labels: bug
assignees: ""
---

## 环境

- Ubuntu 版本：
- 虚拟机平台：VMware / VirtualBox / WSL / Hyper-V / 其他
- 桌面环境：
- Windows 代理软件和端口：
- 远程开发工具：VS Code Remote / Cursor / Codex / 其他
- 失败的流量类型：插件安装 / Marketplace / Git / npm / pip / AI 请求 / 其他

## 发生了什么

请描述你遇到的问题，以及你原本预期的行为。

## 诊断信息

请尽量附上：

```bash
vm-proxy-gateway status
vm-proxy-gateway diagnose --config ~/.config/vm-proxy-gateway/config.json
systemctl status vm-proxy-gateway.service --no-pager
journalctl -u vm-proxy-gateway.service -n 120 --no-pager
```
