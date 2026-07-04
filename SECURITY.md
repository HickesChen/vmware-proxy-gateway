# Security Policy

[简体中文](SECURITY.zh-CN.md)

VM Proxy Gateway manages a systemd service and writes files under `/etc`, so
security-sensitive changes should be reviewed carefully.

## Privileged Operations

The installer can add an optional sudoers rule that allows members of the local
`sudo` group to run only these VM Proxy Gateway controller commands without
repeated password prompts:

- `apply --config /home/*/.config/vm-proxy-gateway/config.json`
- `apply-start --config /home/*/.config/vm-proxy-gateway/config.json`
- `start`
- `stop`
- `restart`
- `uninstall`

Install with `--no-sudoers` if you do not want this convenience rule:

```bash
sudo ./install.sh --no-sudoers
```

## Reporting Security Issues

If you find a security issue, please do not publish exploit details in a public
issue first. Open a private security advisory on GitHub, or contact the
maintainer through the repository's security contact.
