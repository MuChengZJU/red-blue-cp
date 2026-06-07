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

- **视频转录** — B 站视频优先取字幕，无字幕走 ASR；小红书视频同理
- **图文识别** — 小红书图文用视觉模型识别图片里的文字与画面
- **说话人分离** — 多人对谈自动标注「说话人 1 / 2 / …」
- **博主安全批量** — 浏览器插件在你登录态抓清单 → 命令行走代理批量下载（断点续传、失败不中断、过期跳过）
- **评论提取** — 连楼中楼一起存
- **用量与费用** — 每条任务记录 token / 音频时长 / 各阶段耗时，按官方目录价估算费用
- **粘贴即用** — 直接粘整段分享文案（带标题、emoji、中文尾巴都行），自动抽干净 URL

三种用法同一套核心：**命令行** / **本地网页端**（`rbcp serve`，手机也能用）/ **浏览器插件**（抓博主清单）。

---

## 快速入门

### 1. 装命令行工具

```bash
pipx install red-blue-cp        # 或 uv tool install red-blue-cp
```

> 想读源码 / 改代码：`git clone https://github.com/MuChengZJU/red-blue-cp.git && cd red-blue-cp && uv sync`，命令前加 `uv run`。

### 2. 配一个 Key

```bash
mkdir -p ~/.config/rbcp && cp .env.example ~/.config/rbcp/.env
# 编辑 ~/.config/rbcp/.env，填入 DASHSCOPE_API_KEY（百炼控制台拿）
```

单篇公开内容只需这一个 Key。[百炼 API Key →](https://bailian.console.aliyun.com/)

### 3. 跑起来

```bash
rbcp serve                      # 网页界面，浏览器开 http://localhost:8000
rbcp run "B站或小红书链接"        # 或命令行直接转一条
```

### 4. 要批量整个博主？再装浏览器插件（油猴）

下载整个博主需要先抓清单——这步**只有浏览器能在你登录态里安全做**（避风控），所以拆给插件：

1. 装 [Tampermonkey](https://www.tampermonkey.net/)（应用商店搜，本身可信）
2. 点 [**安装脚本**](https://raw.githubusercontent.com/MuChengZJU/red-blue-cp/main/extension/rbcp-xhs.user.js)，油猴弹确认即装好（以后自动更新）
3. 打开小红书博主主页，右下角面板「导出 notes.json」
4. 交给命令行下载：`rbcp batch notes.json --proxy <你的代理>`（或网页端「批量」标签导入）

> 也提供 MV3 扩展版（开发/调试用），装法见 [extension/README.md](extension/README.md)。

---

## 全面功能

| 能力 | 命令 / 入口 | 说明 |
|---|---|---|
| 单条转 Markdown | `rbcp run <url>` / 网页端单条 | B站视频 / 小红书视频 / 小红书图文 |
| 网页端 | `rbcp serve` | 桌面+移动端，任务列表、实时状态、Markdown 预览、用量费用 |
| 博主批量 | 插件导出 → `rbcp batch notes.json --proxy …` | 断点续传、过期跳过、失败留痕、批次进任务列表 |
| 评论 | `rbcp fetch "<笔记>" --comments` | 含楼中楼，需登录态 + 系统 Chrome/Edge |
| 扫码登录 | `rbcp login` | 弹浏览器扫码，cookie 本地复用 |
| 去重 | 自动 | 已成功下过的链接再提交会提示，可选强制重下 |
| 给 Agent 用 | 所有命令加 `--json` | 输出机器可读 JSON + 完整性标记，供 AI 编排内容调研 |

字段契约、完整性标记（区分"拉全了"还是"被风控截断"）见 [SPEC.md](./SPEC.md)。

---

## 技术

**核心 + 多薄壳**：所有抓取/转录/落库逻辑在 `app/service/`，**与前端完全无关**（不依赖任何 Web/CLI 框架）。命令行、网页端、未来的桌面客户端都只是调用它的薄壳。

```
app/
├── service/          # 核心：抓取 / 转录 / Markdown / 存储 / 批量 / 用量 / 错误
├── web/              # 网页端 + REST API（薄壳）
└── cli.py            # 命令行入口（薄壳）
extension/            # 浏览器插件：油猴脚本 + MV3 扩展，抓博主清单导出 notes.json
```

技术栈：FastAPI + Jinja2 + HTMX + Typer + SQLite + asyncio；模型走 DashScope（ASR `paraformer-v2` / 视觉 `qwen3-vl-flash` / 文本 `qwen-plus`，OpenAI 兼容端点流式调用）；下载走代理（`requests` 显式 proxies）。插件抓清单优先读页面初始状态、补以网络拦截，不驱动自动化浏览器。

```bash
uv sync && uv run pytest        # 484 测试
uv run rbcp serve               # 本地起服务
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

完整索引（决策 / 开发 / 经验三条线）在 [LOG.md](./LOG.md)，全部详情在 [docs/devlog/](docs/devlog/)。

---

## 文档

| 文档 | 内容 |
|---|---|
| [PRD.md](./PRD.md) | 产品需求、定位、排期 |
| [SPEC.md](./SPEC.md) | 技术规格、API、数据模型 |
| [PLAN.md](./PLAN.md) | 里程碑进度 |
| [LOG.md](./LOG.md) | 演进日志索引（决策 / 开发 / 经验） |
| [CHANGELOG.md](./CHANGELOG.md) | 版本变更 |
| [extension/README.md](extension/README.md) | 浏览器插件安装与使用 |

## License

[MIT](./LICENSE)
