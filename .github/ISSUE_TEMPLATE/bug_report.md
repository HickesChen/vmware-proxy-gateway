---
name: Bug report
about: Report a problem with VM Proxy Gateway
title: ""
labels: bug
assignees: ""
---

## Environment

- Ubuntu version:
- VM platform: VMware / VirtualBox / WSL / Hyper-V / other
- Desktop environment:
- Windows proxy app and port:
- Remote development tool: VS Code Remote / Cursor / Codex / other
- Failing traffic: extension install / marketplace / Git / npm / pip / AI request / other

## What Happened

Describe the problem and what you expected instead.

## Diagnostics

Please include:

```bash
vm-proxy-gateway status
vm-proxy-gateway diagnose --config ~/.config/vm-proxy-gateway/config.json
systemctl status vm-proxy-gateway.service --no-pager
journalctl -u vm-proxy-gateway.service -n 120 --no-pager
```
