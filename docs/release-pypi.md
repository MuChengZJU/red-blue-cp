# 发布到 PyPI

> 把 RBCP 发到 PyPI，用户即可 `pipx install red-blue-cp` 或 `uv tool install red-blue-cp` 一行装上。
> 包名 `red-blue-cp` 在 PyPI 上**尚未被占用**（首次发布即占名）。

打包配置（`pyproject.toml`）已就绪并验证过：`uv build` 成功、模板进了 wheel、干净环境装后 `rbcp --help` 正常、`twine check` 通过。剩下的只是"怎么把产物推上去"。

有两条路。**推荐 A（CI 自动发，免存 token）**；想先手动试一把用 B。

---

## 路径 A：CI 自动发布（Trusted Publishing，推荐）

仓库已带 `.github/workflows/publish.yml`：打 `v*` tag → 跑测试 → build → 发 PyPI。用 PyPI 的 OIDC Trusted Publishing，**不在仓库存任何 token**。

### 一次性配置

1. **PyPI 侧**：登录 https://pypi.org → 账号设置 → Publishing → 加一个 **pending publisher**（项目还没发布过时用 pending）：
   - PyPI Project Name: `red-blue-cp`
   - Owner: `MuChengZJU`
   - Repository name: `red-blue-cp`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
2. **GitHub 侧**：仓库 Settings → Environments → 新建一个名为 `pypi` 的 environment（名字必须和上面一致）。

### 每次发版

```bash
# 1. 改版本号（发 v0.3 时）
#    pyproject.toml: version = "0.3.0"
# 2. 提交 + 打 tag + 推
git add pyproject.toml
git commit -m "chore: 版本号 0.2.0 → 0.3.0"
git tag v0.3.0
git push origin main --tags
```

推 tag 后去仓库 Actions 看 `Publish to PyPI` 跑完即发布成功。

---

## 路径 B：手动发布（uv publish）

先在 **TestPyPI** 演练一遍（强烈建议，避免正式库发错无法覆盖）：

```bash
# 1. 在 https://test.pypi.org 注册并建 API token
# 2. 构建
uv build
# 3. 发到 TestPyPI
uv publish --publish-url https://test.pypi.org/legacy/ --token pypi-<你的TestPyPI-token>
# 4. 从 TestPyPI 装来验证（依赖仍从正式 PyPI 拉）
uv tool install --index https://test.pypi.org/simple/ \
  --index-strategy unsafe-best-match red-blue-cp
rbcp --help
```

正式发布：

```bash
# 在 https://pypi.org 建 API token
uv build
uv publish --token pypi-<你的PyPI-token>
```

> token 别写进任何文件 / 别进 git。临时放环境变量 `UV_PUBLISH_TOKEN` 也行：
> `export UV_PUBLISH_TOKEN=pypi-... && uv publish`

---

## 发布后验证

```bash
# 换个干净环境装来跑
pipx install red-blue-cp     # 或 uv tool install red-blue-cp
rbcp --help                  # 应列出 run / serve / login / list / fetch
```

PyPI 页面：https://pypi.org/project/red-blue-cp/

> 注意：README 顶部的 banner 图是相对路径，PyPI 上不渲染（GitHub 正常）。要让 PyPI 页面也显示，
> 把 README 里 `docs/assets/banner.png` 换成 `https://raw.githubusercontent.com/MuChengZJU/red-blue-cp/main/docs/assets/banner.png` 绝对链接即可。

## 注意事项

- **同一版本号只能发一次**，发错了不能覆盖，只能 bump 版本号重发（所以先 TestPyPI 演练）。
- 路径 A 和 B 二选一即可。配好 A 之后，日常只需打 tag，最省事也最规范。
