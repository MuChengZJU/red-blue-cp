<p align="center">
  <img src="docs/assets/banner.png" alt="Red Blue CP · 红蓝CP" width="100%">
</p>

<p align="center">
  <strong>自古红蓝出 CP —— 把 B 站和小红书内容转成本地 Markdown 知识库</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/red-blue-cp/"><img src="https://img.shields.io/pypi/v/red-blue-cp?color=blue" alt="PyPI"></a>
  <a href="https://pypi.org/project/red-blue-cp/"><img src="https://img.shields.io/pypi/pyversions/red-blue-cp" alt="Python"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/github/license/MuChengZJU/red-blue-cp" alt="License"></a>
</p>

<p align="center">
  <img src="docs/assets/webui-home.png" alt="WebUI 主界面" width="720">
</p>

粘一个链接，得到一篇 Markdown。把 B 站和小红书的视频/图文沉淀成**你自己的本地知识库**——文件落在你指定的目录，拿 Obsidian 管、群晖同步，都随你。

---

## 主要功能

- **速览（0.6 新）** — 忠实原文之上加一层"快速读懂"：**重点高亮**跳读 / **金句卡片** / **脉络大纲**，一竖屏抓重点，随时切回原文。高亮/卡片/大纲由服务端锚定回原文坐标，不编造原文没有的内容
- **视频转录** — B 站视频优先取字幕，无字幕走 ASR；小红书视频同理
- **图文识别** — 小红书图文用视觉模型识别图片里的文字与画面
- **说话人分离** — 多人对谈自动标注「说话人 1 / 2 / …」
- **博主安全批量** — 浏览器插件在你登录态抓清单 → 命令行走代理批量下载（断点续传、失败不中断、过期跳过）
- **评论提取** — 连楼中楼一起存
- **用量与费用** — 每条任务记录 token / 音频时长 / 各阶段耗时，按官方目录价估算费用
- **粘贴即用** — 直接粘整段分享文案（带标题、emoji、中文尾巴都行），自动抽干净 URL

---

## 四种形态

同一套核心逻辑，四种用法，按场景挑：

| 形态 | 是什么 | 干什么 | 给谁 |
|---|---|---|---|
| **① 油猴脚本** | 浏览器里的用户脚本（Tampermonkey） | 在你登录态的小红书博主主页抓清单，导出 `notes.json` | 要批量整个博主的人 |
| **② 命令行工具** | 本地 CLI（`rbcp`） | 链接/清单 → 本地 Markdown + 速览 JSON，可脚本化、给 AI Agent 编排 | 命令行党、自动化 |
| **③ 本地服务 + 网页端** | `rbcp serve` 起的本地网页 | 浏览器（含手机）点点点：提交、看进度、读 Markdown、看用量费用 | 想要图形界面的人 |
| **④ 桌面客户端（0.6 新）** | RBCP Desktop（Tauri 原生 app，内置 serve） | 装好即用的原生界面 + **速览阅读器**（高亮/卡片/脉络） | 不想碰命令行的人（当前 macOS arm64） |

> 为什么抓清单单独做成油猴：下载和落知识库**必须**本地进程（浏览器写不了本地目录、跑不了 ffmpeg），而抓清单**只有浏览器**能在你登录态里安全做（避风控）。所以 ① 负责浏览器才能干的那段，②③④ 是同一套本地核心的几层皮。配合用，不是几选一。

---

## 路线图（Roadmap）

> **0.6 已发布**：重心从"链接 → 忠实原文"扩到**帮人快速读懂**。

- **0.6 · 速览产品（已发布）**：忠实原文之上加一层"速览"——重点**高亮跳读** / **卡片金句** / **脉络梳理**，一竖屏抓住重点（随时可切回看原文）。架构按 **Extract**（采集转录→忠实原文，无损）→ **Digest**（提炼高亮/金句/脉络，确定性服务端锚定）→ **Render**（呈现）分层；引擎保持开源。新增 **RBCP Desktop** 桌面客户端（当前 macOS arm64）。
- **下一步**：托管版 RBCP Cloud（按实际使用计费）、手机端、桌面端跨平台（Windows）。这些走私有云，引擎层继续开源。
- 详见 [0.6 速览产品 devlog](docs/devlog/2026-06-15-0.6-speed-read-product.md) 与 [PLAN.md](docs/PLAN.md) §v0.6。

---

## 快速入门

### 1. 装命令行工具

```bash
pipx install red-blue-cp        # 或 uv tool install red-blue-cp
```

> 想读源码 / 改代码：`git clone https://github.com/MuChengZJU/red-blue-cp.git && cd red-blue-cp && uv sync`，命令前加 `uv run`。

### 2. 配一个 Key

```bash
rbcp config        # 打印你本机的配置目录 + 写 Key 的确切命令（跨平台路径自动对）
```

按它末尾提示写入即可（配置目录因系统而异——mac 在 `~/Library/Application Support/rbcp`、Linux 在 `~/.config/rbcp`、Windows 在 `%APPDATA%\rbcp`，`rbcp config` 会告诉你确切路径）：

```bash
echo 'DASHSCOPE_API_KEY=sk-你的key' >> "<rbcp config 打印的路径>/.env"
```

单篇公开内容只需这一个 Key。[百炼 API Key →](https://bailian.console.aliyun.com/)（桌面客户端则直接在「设置」里填，无需碰命令行）

### 3. 跑起来

```bash
rbcp serve                      # 网页界面，浏览器开 http://localhost:8000
rbcp run "B站或小红书链接"        # 或命令行直接转一条（忠实原文）
rbcp digest "B站或小红书链接"     # 转录 + 生成速览（高亮/卡片/脉络）
```

### 不想碰命令行？用桌面客户端（RBCP Desktop）

0.6 起提供原生桌面 app（内置 serve，装好打开即用，界面里就能配 Key / 看任务 / 读速览）：

1. 去 [Releases](https://github.com/MuChengZJU/red-blue-cp/releases) 下载 `RBCP-Desktop-*.app`（当前 **macOS arm64**）。
2. 首次打开：直接双击会被 macOS 拦（提示「无法打开」，因为本版未做代码签名）——**右键 app → 打开**，在弹窗里再点「打开」确认一次即可，之后正常双击。
3. 在「设置」里填百炼 API Key，回到「任务列表」粘链接即可。

> 当前仅 macOS arm64，且未签名（开源项目暂无签名证书）。Windows / Intel Mac 待后续；想自己构建见 [desktop/README.md](desktop/README.md) 或下方"技术"。

### 4. 要批量整个博主？再装浏览器插件（油猴）

下载整个博主需要先抓清单——这步**只有浏览器能在你登录态里安全做**（避风控），所以拆给插件：

1. 装 [Tampermonkey](https://www.tampermonkey.net/)（应用商店搜，本身可信）
2. 点 [**安装脚本**](https://raw.githubusercontent.com/MuChengZJU/red-blue-cp/main/extension/rbcp-xhs.user.js)，油猴弹确认即装好（以后自动更新）
3. 打开小红书博主主页，右下角面板「导出 notes.json」
4. 交给命令行下载：`rbcp batch notes.json --proxy http://127.0.0.1:7897`（代理填你自己的 http 代理地址；或用网页端「批量」标签导入）

> 也提供 MV3 扩展版（开发/调试用），装法见 [extension/README.md](extension/README.md)。

---

## 全面功能

| 能力 | 命令 / 入口 | 说明 |
|---|---|---|
| 单条转 Markdown | `rbcp run <url>` / 网页端单条 | B站视频 / 小红书视频 / 小红书图文 |
| 速览（高亮/卡片/脉络） | `rbcp digest <url>` / 桌面端阅读器 | 原文之上提炼重点，服务端锚定回原文坐标 |
| 列已转录 | `rbcp ls` | 列本地知识库已有内容 |
| 网页端 | `rbcp serve` | 桌面+移动端，任务列表、实时状态、Markdown 预览、用量费用 |
| 博主批量 | 插件导出 → `rbcp batch notes.json --proxy …` | 断点续传、过期跳过、失败留痕、批次进任务列表 |
| 评论 | `rbcp fetch "<笔记>" --comments` | 含楼中楼，需登录态 + 系统 Chrome/Edge |
| 扫码登录 | `rbcp login` | 弹浏览器扫码，cookie 本地复用 |
| 去重 | 自动 | 已成功下过的链接再提交会提示，可选强制重下 |
| 给 Agent 用 | 所有命令加 `--json` | 输出机器可读 JSON + 完整性标记，供 AI 编排内容调研 |

字段契约、完整性标记（区分"拉全了"还是"被风控截断"）见 [SPEC.md](docs/SPEC.md)。

---

## 技术

**核心 + 多薄壳**：抓取/转录/落库逻辑在 `app/extract/`，**与前端完全无关**（不依赖任何 Web/CLI 框架）。命令行、网页端、桌面客户端都只是调用它的薄壳。0.6 起在引擎之上加一层**与 extract 物理隔离**的 `app/digest/`（原文 → 速览，LLM 有损但确定性锚定回原文坐标）。

```
app/
├── extract/          # 引擎：采集 / 转录 / Markdown / 存储 / 批量 / 用量 / 错误（无损，原 service/）
├── digest/           # 速览：原文 → 高亮 / 卡片 / 脉络（LLM 有损，确定性服务端锚定，与 extract 隔离）
├── web/              # 网页端 + REST API（薄壳）
├── config.py         # 跨平台配置发现（platformdirs）
└── cli.py            # 命令行入口（薄壳）
desktop/              # RBCP Desktop：Tauri v2 壳 + PyInstaller sidecar（内置 rbcp serve）
extension/            # 浏览器插件：油猴脚本 + MV3 扩展，抓博主清单导出 notes.json
```

技术栈：FastAPI + Jinja2 + Typer + SQLite + asyncio；速览的呈现在桌面端是原生 HTML/CSS/JS（Tauri v2）；模型走 DashScope（ASR `paraformer-v2` / 视觉 `qwen3-vl-flash` / 文本 `qwen-plus`，OpenAI 兼容端点流式调用）；下载走代理（`requests` 显式 proxies）。插件抓清单优先读页面初始状态、补以网络拦截，不驱动自动化浏览器。

```bash
uv sync && uv run pytest        # 612 测试
uv run rbcp serve               # 本地起服务
uv run rbcp digest "<链接>"      # 转录 + 生成速览（高亮/卡片/脉络）
# 桌面端构建：见 desktop/README.md；本 release 仅提供 macOS arm64 产物，其它平台改 cargo target 自构建
```

---

## 📖 开发日志开源 —— 一个 AI 协作开发的真实样本

这个项目把**全过程的设计与开发日志一并开源**。不只是代码能看，**怎么想的、踩了什么坑、怎么和 AI 协作**都摊开记着，供学习参考：

- **软件设计与架构决策** —— 为什么是"核心 + 多薄壳"、产品形态怎么定、范围怎么砍
  - [产品形态定案（插件 / 客户端 / 服务+网页）](docs/devlog/2026-06-03-product-form-and-v3-scope.md)
  - [何时并行 + 调研分层](docs/devlog/2026-06-03-when-to-parallelize-and-research-layering.md)
- **开发踩坑实录** —— 单测全绿却真用崩、爬虫结构靠探针实证而非猜
  - [集成层 bug：完工 = 真链路跑通](docs/devlog/2026-05-09-integration-layer-bugs.md)
  - [插件根因 + 油猴分发决策](docs/devlog/2026-06-07-plugin-userscript-and-followup-fixes.md)
- **人机协作经验** —— 多 agent 并行、契约先行、挂机自主开发一夜的复盘
  - [挂机自主完成一个里程碑的复盘](docs/devlog/2026-06-06-overnight-autonomous-m4-retro.md)
  - [并行契约 + spike 先行](docs/devlog/2026-06-05-m4-wave1-contracts-and-token-spike.md)

完整索引（决策 / 开发 / 经验三条线）在 [LOG.md](docs/LOG.md)，全部详情在 [docs/devlog/](docs/devlog/)。

---

## 文档

| 文档 | 内容 |
|---|---|
| [PRD.md](docs/PRD.md) | 产品需求、定位、排期 |
| [SPEC.md](docs/SPEC.md) | 技术规格、API、数据模型 |
| [PLAN.md](docs/PLAN.md) | 里程碑进度 |
| [LOG.md](docs/LOG.md) | 演进日志索引（决策 / 开发 / 经验） |
| [CHANGELOG.md](./CHANGELOG.md) | 版本变更 |
| [AGENTS.md](./AGENTS.md) | AI agent / 贡献者规则书（CLAUDE.md `@import` 它） |
| [RELEASING.md](docs/RELEASING.md) | 发布流程（打 tag → CI 自动发 PyPI + 桌面 Release） |
| [extension/README.md](extension/README.md) | 浏览器插件安装与使用 |
| [desktop/README.md](desktop/README.md) | 桌面客户端构建与运行 |

## License

[MIT](./LICENSE)
