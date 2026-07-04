# 安全策略

[English](SECURITY.md)

VM Proxy Gateway 会管理 systemd 服务，并写入 `/etc` 下的系统配置，因此涉及权限的变更需要谨慎审查。

## 特权操作

安装器可以添加一个可选 sudoers 规则，让本机 `sudo` 组成员不必反复输入密码即可运行以下 VM Proxy Gateway 控制命令：

- `apply --config /home/*/.config/vm-proxy-gateway/config.json`
- `apply-start --config /home/*/.config/vm-proxy-gateway/config.json`
- `start`
- `stop`
- `restart`
- `uninstall`

如果不希望安装这个便利规则，请使用：

```bash
sudo ./install.sh --no-sudoers
```

## 报告安全问题

如果你发现安全问题，请不要先在公开 issue 中发布利用细节。请在 GitHub 上开启私有安全公告，或通过仓库安全联系人联系维护者。
