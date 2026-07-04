# GitHub 上传指南

建议把项目整理成一个固定的仓库目录 `vm-proxy-gateway`，并把这个目录里的
内容作为仓库根目录上传。不要把 `vm-proxy-gateway-0.1.0`、
`vm-proxy-gateway-0.1.2`、`vm-proxy-gateway-0.1.3` 这些版本目录一起提交到
仓库，也不要把外层 zip 文件提交到仓库。

GitHub 仓库应该只有一个，例如 `vm-proxy-gateway`。以后每个版本都在这个
仓库里继续修改、提交，并用 Git tag 和 GitHub Release 标记版本，不需要为
每个版本创建一个新文件夹。

## 推荐仓库名

```text
vm-proxy-gateway
```

## 首次上传

第一次上传时，在固定仓库目录 `vm-proxy-gateway` 里运行：

```bash
git init
git add .
git commit -m "Initial release"
git branch -M main
git remote add origin https://github.com/<your-name>/vm-proxy-gateway.git
git push -u origin main
```

首次上传后，为当前版本打 tag：

```bash
git tag -a v0.1.3 -m "Release v0.1.3"
git push origin v0.1.3
```

推送 tag 后，GitHub Actions 会自动创建 GitHub Release，并上传
`vmware-proxy-gateway-0.1.3.zip`。zip 是发布附件，不是仓库源码。

## 以后发布新版本

以后不要复制出一个新的项目文件夹继续开发。推荐流程是：

1. 继续在同一个 Git 仓库里修改代码。
2. 更新 `CHANGELOG.md` 和 `CHANGELOG.zh-CN.md`。
3. 运行发布脚本。
4. 等待 GitHub Actions 自动创建 Release 和 zip 附件。

示例：

```bash
tools/release.sh        # patch，例如 0.1.3 -> 0.1.4
tools/release.sh minor  # 0.1.3 -> 0.2.0
tools/release.sh major  # 0.1.3 -> 1.0.0
tools/release.sh --version 1.2.3
tools/release.sh --dry-run
```

脚本会自动更新 `VERSION`、运行验证、提交、打 tag、推送 `main` 和 tag。
如果只想在本地生成提交和 tag，不立刻推送，可以使用 `--no-push`。

如果需要在本地临时生成 zip 测试包，可以在父目录运行：

```bash
zip -r vmware-proxy-gateway-0.1.4.zip vm-proxy-gateway -x '*/.git/*' '*/__pycache__/*'
```

注意：仓库目录名可以一直叫 `vm-proxy-gateway`，不需要叫
`vm-proxy-gateway-0.1.4`。版本号由 `VERSION`、Git tag 和 GitHub Release
共同记录。

## 上传前检查

```bash
python3 -m py_compile app/vm_proxy_gateway.py app/vm_proxy_gateway_gui.py tools/validate_scenarios.py
bash -n install.sh
bash -n uninstall.sh
python3 tools/validate_scenarios.py
find . -type d -name __pycache__ -o -type f -name '*.pyc'
```

最后一条命令应当没有输出。

## 不建议提交

- `*.zip`
- `__pycache__/`
- `*.pyc`
- 本地日志或临时文件

这些内容已经在 `.gitignore` 中排除。
