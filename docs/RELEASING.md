# 发布流程（RELEASING）

本仓库的发布**自动化**：打 tag `v*` → GitHub Actions（[`.github/workflows/publish.yml`](../.github/workflows/publish.yml)）跑测试 → `uv build` → **PyPI Trusted Publishing（OIDC）自动发布**。**不需要、也不要手动 `uv publish` 或 PyPI token。**

PyPI 是「打 tag 自动发」，**不是**命令行手动发。桌面端 `.dmg` 走单独的 GitHub Release（手动 `gh release create` 附二进制）。

## 一次性前置（已配好，新人参考）

- **PyPI Trusted Publishing**：在 PyPI 项目设置加 publisher（owner=`MuChengZJU`、repo=`red-blue-cp`、workflow=`publish.yml`、environment=`pypi`），GitHub 仓库 Settings → Environments 建 `pypi`。详见 publish.yml 顶部注释。
- **gh CLI 已登录**（`gh auth status` 确认），用于建 GitHub Release。

## 发布一个版本（vX.Y.Z）

### 1. 准备（在特性分支上）

```bash
# 版本号：两处都要改，保持一致
#   pyproject.toml         project.version
#   desktop/src-tauri/tauri.conf.json  version
# 更新 CHANGELOG.md（写主题 + 新增/修复/说明）
# 刷新 README / CLAUDE(=AGENTS) / LOG / devlog
./.venv/bin/pytest -q tests        # 全绿
bash scripts/check-leaks.sh        # 无泄漏（公开仓库）
git commit ...                     # 按粒度提交，别自动 push
```

### 2. 合并到 main —— **走 PR，不直推**

```bash
git push origin <feature-branch>
gh pr create --base main --title "..." --body "..."
# review 后合并（仓库用 merge commit；保持线性可 rebase merge）
gh pr merge --merge   # 或在网页上点 Merge
```

### 3. 打 tag → 自动发 PyPI

```bash
git checkout main && git pull origin main      # 拿到合并后的 main
git tag -a vX.Y.Z -m "vX.Y.Z — 一句话主题"
git push origin vX.Y.Z                          # ← 这一步触发 publish.yml，自动发 PyPI
```

去 Actions 看 `Publish to PyPI` 跑绿；几分钟后 https://pypi.org/project/red-blue-cp/ 出现新版本。验证：`pipx install red-blue-cp==X.Y.Z`。

### 4. GitHub Release（附桌面 .dmg，手动）

CI 只发 PyPI，不建 Release。桌面端二进制单独发。`tauri.conf.json` 的 `bundle.targets` 已设 `["app", "dmg"]`，构建即出 DMG：

```bash
# 构建桌面 .dmg（macOS arm64）
cd desktop/sidecar && bash build.sh             # 先重打 sidecar（含最新 Python 源码）
cd .. && cargo tauri build --bundles dmg         # 出 src-tauri/target/release/bundle/dmg/RBCP Desktop_X.Y.Z_aarch64.dmg
# 重命名成无空格资产名
cp "src-tauri/target/release/bundle/dmg/RBCP Desktop_X.Y.Z_aarch64.dmg" \
   "RBCP-Desktop-X.Y.Z-macos-arm64.dmg"
# 建 Release，附 dmg
gh release create vX.Y.Z \
  --title "vX.Y.Z — 主题" \
  --notes-file <release-notes.md> \
  "RBCP-Desktop-X.Y.Z-macos-arm64.dmg"
```

桌面端**未签名**，Release 正文要写明：打开 DMG → 拖进「应用程序」→ 首次「右键 → 打开」过 Gatekeeper。

> **Windows / Intel Mac 待办**：当前只出 macOS arm64。Windows `.exe`/`.msi` 无法在 mac 上交叉构建——PyInstaller sidecar 必须在目标平台上打、Tauri 的 Windows 包也需 Windows 工具链。要做得搭一条 GitHub Actions 跨平台 release 工作流（`windows-latest` 跑 sidecar 打包 + `cargo tauri build` 出 NSIS/WiX 包，矩阵化上传到 Release）；且 Windows 引擎本身（ffmpeg / 路径 / `%APPDATA%` 配置发现）尚未在 Windows 上验证过。属独立工程，未排期。

## 想反悔（tag 推出去之前）

```bash
git tag -d vX.Y.Z                  # 删本地 tag
git branch -f main origin/main     # 本地 main 回退到远端
```

tag 一旦 push 触发 CI 发了 PyPI，**同版本号不可覆盖重发**——只能发 X.Y.(Z+1)。所以 tag push 前务必确认。

## 易踩的坑

- **sdist 体积**：`pyproject.toml` 的 `[tool.hatch.build.targets.sdist].include` 显式限定只装 `app/` + 元数据，防把 `desktop/`（Rust target、.venv、PyInstaller 产物）扫进 sdist（曾在脏工作区打出 ~1GB，PyPI 会拒）。
- **dist/ 别上 PyPI 错文件**：本地若手动 build，dist/ 可能同时有 wheel/sdist 和 .app.zip——但正常流程 PyPI 由 CI 在干净检出里 build，不用本地 dist/。
- **两处版本号**：pyproject 和 tauri.conf 容易漏一个。
