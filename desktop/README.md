# RBCP Desktop（M6e+d spike）

最小可用的 Red Blue CP 桌面壳：Tauri v2 + PyInstaller sidecar + 三形态同屏渲染。
目标是"能跑通 + spike 出结论"，不追求精致。

```
desktop/
  sidecar/          PyInstaller spike：文本 → app.digest → 契约 JSON
    rbcp_sidecar.py   入口（读 stdin/arg，FakeProvider 离线跑引擎）；用仓库真实 app/ 引擎
    build.sh          打二进制（onefile / onedir）；--paths 指仓库根打真 app/，不再 vendored
  frontend/         三形态渲染（纯 HTML/JS，无框架）
    index.html  styles.css  app.js  render.js
    sample.json       = docs/contracts/0.6-digest-json-sample.json
    test_cpslice.mjs  codepoint 切片正确性自检
  src-tauri/        Tauri v2 壳：run_digest 命令 spawn sidecar
```

## 跑起来

```bash
# 1. 打 sidecar 二进制
bash sidecar/build.sh            # → sidecar/dist/rbcp-sidecar

# 2. 放到 Tauri 期望的位置（带 target-triple 后缀）
cp sidecar/dist/rbcp-sidecar \
   src-tauri/binaries/rbcp-sidecar-$(rustc -vV | sed -n 's/host: //p')

# 3. 编译 / 打包（本机若有代理需 CARGO_HTTP_PROXY="" 绕过）
cd src-tauri && cargo build              # 验证编译
cargo tauri build --config '{"build":{"beforeBuildCommand":""}}'  # 出 .app
```

开发期只看渲染（不装 Tauri）：起个静态服务器，浏览器开 `frontend/index.html`，
读内联/`sample.json` 渲染三形态。

## 三形态（M6d）

同屏三块，"一竖屏读懂"：
- ① 全文 + 重点高亮：点高亮跳读，可"只看高亮"（其余变淡）。
- ② 卡片 / 金句：`source==null` 的金句展示但不可跳转。
- ③ 脉络大纲：递归树，有 source 的节点可点跳到原文。

点卡片 / 大纲 → 滚到全文对应高亮并闪烁。有 `seconds` 的显示时间戳。

### ⚠️ 高亮按 codepoint 切，不是 UTF-16

契约的 `span_start/span_end` 是 Python codepoint 下标。JS `string.slice` 对 emoji /
罕用字（astral）会错位。`render.js` 用 `Array.from(text).slice(s,e).join("")`。
`test_cpslice.mjs` 锁这条不变量（`node test_cpslice.mjs`）。

## 接缝

sidecar stdout = `docs/contracts/0.6-digest-json-contract.md` 的信封。
联调期 `run_digest` 把它换成真实 `rbcp digest --json`（M6f CLI 那侧产出，形状一致）。

sidecar 直接用仓库真实 `app/` 引擎（`build.sh` 的 `--paths` 指仓库根、`--hidden-import` 补
digest 的 lazy import；digest 纯标准库依赖，闭包小、不拉 fastapi/pydoll）。**不再 vendored 拷贝**。
LLM 部分用 `FakeProvider` 离线确定性替代、`_build_extract` 是桩，不需要真 API key——
联调真链路时把 `run_digest` 换成调 `rbcp digest <url> --json`（M6f 那侧，形状一致）。

## Spike 结论（PyInstaller 体积 / 冷启动，macOS arm64）

| 模式 | 体积 | 冷启动（10 次均值） | 适用 |
|---|---|---|---|
| onefile | 9.05 MB 单文件 | ~365 ms | 分发简单，但每次自解压到 temp |
| onedir | 20 MB 文件夹 | ~30 ms | 每次请求 spawn 首选（快 12x） |

对照：裸 Python 跑同脚本约 20 ms。

结论：引擎依赖极轻（纯标准库 + digest/extract.contracts），打包很小。Tauri 作为
sidecar 每次请求 spawn 时，**用 onedir**——onefile 的 365ms 是每次自解压开销，
交互体验差。最终 .app 含 onedir sidecar 约 20MB 量级。
若改成常驻进程（一次启动多次喂文本），onefile 的启动开销只付一次，体积优势可取。
