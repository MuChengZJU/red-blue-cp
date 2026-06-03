<p align="center">
  <img src="docs/assets/banner.png" alt="Red Blue CP · 红蓝CP —— B 站小红书 Content Pipeline" width="100%">
</p>

# Red Blue CP · 红蓝CP

> **自古红蓝出 CP —— B 站小红书 Content Pipeline**

把 B 站和小红书的视频/图文内容转成纯文本，沉淀成本地 Markdown 知识库。

**状态**：`v0.3.0`，MIT 开源，已上 [PyPI](https://pypi.org/project/red-blue-cp/)。P0 单篇闭环（B站/小红书 视频+图文 → Markdown，多人对谈自动说话人分离）+ P1 小红书博主全量下载 / 评论提取 / 扫码登录。**v0.3 形态落地**：`pipx`/`uv tool` 一行装、WebUI 重做（红蓝品牌 + Markdown 渲染）、自部署远程可达（见 [部署指南](docs/deploy-wsl.md)）、CI/CD 打 tag 自动发布。
仓库 `red-blue-cp` ｜ CLI `rbcp` ｜ 输出默认 `~/transcript/`

---

## 一、给用户（人）

把一个链接变成桌面上的一个 Markdown 文件。视频转文字、图文做识别、多人对谈分说话人。新版还能扫码登录后**整个博主批量下**、**连评论一起存**。

### 装 + 配

前置：Python ≥3.11；ffmpeg（音频抽流兜底用，按需）；Chrome/Edge（仅评论/批量用）。

```bash
# A. 从 PyPI 装（推荐，命令直接是 rbcp）
pipx install red-blue-cp        # 或 uv tool install red-blue-cp

# B. 从源码装（开发用，命令前加 uv run）
git clone <repo-url> && cd red-blue-cp && uv sync
```

配置（填百炼 `DASHSCOPE_API_KEY`，单篇公开笔记不需 cookie）：

```bash
cp .env.example .env            # 源码方式：放仓库根目录
# PyPI 方式：放 ~/.config/rbcp/.env（发现顺序：环境变量 > ~/.config/rbcp/.env > 当前目录 .env）
```

### 用

> PyPI 装的直接用 `rbcp ...`；源码装的命令前加 `uv run`（下面示例按源码写）。

```bash
# 网页版：浏览器粘链接
uv run rbcp serve                              # http://0.0.0.0:8000

# 单篇（主要给人用）
uv run rbcp run "<B站 或 小红书 链接>"          # 转录成 Markdown
uv run rbcp fetch "<小红书笔记链接>" --comments  # 附带评论（含楼中楼）

# 博主全量 / 评论：先扫码登录一次（cookie 存本地复用）
uv run rbcp login                              # 弹浏览器→手机扫码→回终端按回车
uv run rbcp fetch "<博主主页链接>" --all        # 先预览 X 篇，确认后逐条下
```

可选开关：`--comments`（带评论）/ `--save-media`（留原始媒体）/ `--text-only`（跳过转录只取正文）。
带评论 / 博主全量走浏览器抓接口，温和限频（实测清单 ~14、评论 ~4 请求·分钟⁻¹），不易触发风控。

---

## 二、给开发者

**技术栈**：FastAPI + Jinja2 + HTMX + typer + SQLite + asyncio + requests（REST/OpenAI 兼容 HTTP 直调百炼）；博主全量/评论用 pydoll（CDP 连系统 Chrome 抓接口）。

**结构**：
```
app/
├── service/
│   ├── model.py       # ModelProvider + DashscopeProvider（ASR/VLM/LLM）
│   ├── extractor.py   # 编排：fetcher + model（含 --text-only/--save-media）
│   ├── fetcher.py     # requests 爬 B站/小红书 API + 解析
│   ├── discover.py    # P1 唯一碰浏览器处：pydoll 抓博主清单/评论 + rbcp login
│   ├── comments.py    # 评论 → {note_id}.comments.md（楼中楼嵌套）
│   ├── markdown.py    # frontmatter + sanitize + 原子写
│   └── storage.py     # SQLite jobs
├── web/routes.py      # WebUI + REST API
└── cli.py             # rbcp 命令
```

**开发**：
```bash
uv run pytest          # 全量测试
uv run rbcp serve      # 本地起服务（单进程 uvicorn，禁 --workers）
```

**部署**：自部署工具，推荐国内 IP 机器（避海外风控）；手机访问走 tailscale 或 frp。

**文档导航**：

| 文档 | 用途 |
|---|---|
| [PRD.md](./PRD.md) | 产品需求：定位、五层架构、排期 |
| [SPEC.md](./SPEC.md) | 技术规格：架构、API、数据模型、决策 |
| [PLAN.md](./PLAN.md) | 里程碑、Checklist、风险、开放问题 |
| [CLAUDE.md](./CLAUDE.md) | 项目不变量、红线、协作规则 |
| [LOG.md](./LOG.md) | 演进日志（决策/开发/经验，详情在 [docs/devlog/](./docs/devlog/)） |
| [docs/reference/xhs-api-notes.md](./docs/reference/xhs-api-notes.md) | 小红书接口速查（字段/风控/cookie） |

---

## 三、给 Agent

**定位**：单篇给人用，**博主批量为 Agent 设计**——工具只列清单，按什么规则筛由 Agent 决定。

**列清单（机器可读）**：
```bash
uv run rbcp list "<博主主页链接>" --json
```
返回固定结构（[SPEC §4.3](./SPEC.md)），关键是 **`complete` 硬字段**：

- `complete: true` → 拉全了，`notes[]` 是全量
- `complete: false` → 被风控/cookie 过期/网络中断截断，是**半份**，**不得当全量**，且退出码非 0

每条 note 给 `note_id / title / type / liked_count / xsec_token`（token 一次性会过期，拿到尽快用）。

**典型工作流**：`list --json` 拿清单 → 自己按关键词/类型筛出要的 → 对每条 `fetch`。或直接 `fetch <博主url> --all --json --yes` 整博主下，返回 `{captured, downloaded, failed, results[]}`。

```bash
uv run rbcp fetch "<笔记链接>" --comments --json   # 单篇，结构化输出
uv run rbcp fetch "<博主url>" --all --json --yes    # 整博主，逐条结果
```

**注意**：评论/博主全量需登录态（`rbcp login` 或 `.env` 配 `XHS_COOKIE`/`RBCP_XHS_COOKIE_FILE`）；浏览器任务全局串行、温和限频；解析层契约与字段见 [SPEC §4.4](./SPEC.md) 和 [小红书接口速查](./docs/reference/xhs-api-notes.md)。

---

## 范围外

抖音 ｜ MCP server（P2 按需）｜ Get 笔记历史迁移（独立项目）｜ 远期 LLM Wiki（本项目只产 Markdown 原料）。

## License

[MIT](./LICENSE)
