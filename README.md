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

<!-- <p align="center">
  <a href="./README.en.md">English</a>
</p> -->

<p align="center">
  <img src="docs/assets/webui-home.png" alt="WebUI 主界面" width="720">
</p>

粘一个链接，得到一篇 Markdown。支持 B 站视频、小红书视频、小红书图文，自动转录/识别文字，多人对谈标注说话人。还能批量下载整个博主、连评论一起存。

## 快速开始

**前置**：Python ≥ 3.11，[百炼 API Key](https://bailian.console.aliyun.com/)（ASR / VLM 用）。

### 1. 安装

```bash
# 推荐：从 PyPI 装，命令直接是 rbcp
pipx install red-blue-cp

# 或源码安装（开发用）
git clone https://github.com/MuChengZJU/red-blue-cp.git
cd red-blue-cp && uv sync
```

### 2. 配置

```bash
# PyPI 安装：配置文件放 ~/.config/rbcp/.env
mkdir -p ~/.config/rbcp && cp .env.example ~/.config/rbcp/.env

# 源码安装：配置文件放仓库根目录
cp .env.example .env
```

编辑 `.env`，填入 `DASHSCOPE_API_KEY`。单篇公开内容只需这一个 key。

### 3. 使用

```bash
# 打开网页界面（推荐）
rbcp serve                     # 浏览器访问 http://localhost:8000

# 或命令行直接转
rbcp run "B站或小红书链接"
```

> 源码安装的命令前加 `uv run`，如 `uv run rbcp serve`。

## 功能

- **视频转录** — B 站视频优先取字幕，无字幕走 ASR（百炼 Paraformer）
- **图文识别** — 小红书图文用 VLM（百炼 Qwen-VL）识别图片内容
- **说话人分离** — 多人对谈自动标注「说话人 1 / 2 / ...」
- **博主批量下载** — `rbcp fetch "<博主主页>" --all`，先预览再确认
- **评论提取** — `rbcp fetch "<笔记链接>" --comments`，含楼中楼
- **扫码登录** — `rbcp login` 弹浏览器扫码，cookie 本地复用

博主批量和评论功能需要登录态 + 系统安装 Chrome/Edge。

## 给 AI Agent 用

rbcp 把 B 站和小红书统一成了结构化接口。AI Agent 可以直接调 CLI 做内容调研——拿博主清单、按规则筛选、逐条下载、读取 Markdown 结果，整个流程无需人工介入。

```bash
# Agent 典型工作流：
rbcp list "<博主主页>" --json          # 1. 拿到博主全部笔记清单（结构化 JSON）
rbcp fetch "<笔记链接>" --json         # 2. 逐条下载，拿到 Markdown 路径
rbcp fetch "<博主主页>" --all --json --yes  # 或直接整个博主批量下
```

所有命令加 `--json` 即输出机器可读的 JSON。字段契约和完整性标记（`complete: true/false`，区分"拉全了"还是"被风控截断"）见 [SPEC.md](./SPEC.md)。

## WebUI

网页界面支持桌面和移动端。粘贴链接提交后可实时查看任务状态，完成后直接预览渲染好的 Markdown。

<p align="center">
  <img src="docs/assets/webui-detail.png" alt="WebUI 详情页（移动端）" width="360">
</p>

## 开发

```bash
uv sync                    # 安装依赖
uv run pytest              # 跑测试
uv run rbcp serve          # 本地起服务
```

技术栈：FastAPI + Jinja2 + HTMX + Typer + SQLite + asyncio。博主批量/评论用 [pydoll](https://github.com/pydoll-project/pydoll)（CDP 连系统 Chrome）。

```
app/
├── service/          # 核心逻辑：抓取、转录、Markdown 生成、存储
├── web/              # WebUI + REST API
└── cli.py            # CLI 入口
```

## 文档

| 文档 | 内容 |
|---|---|
| [PRD.md](./PRD.md) | 产品需求、定位、排期 |
| [SPEC.md](./SPEC.md) | 技术规格、API、数据模型 |
| [PLAN.md](./PLAN.md) | 里程碑进度 |
| [LOG.md](./LOG.md) | 演进日志（决策 / 开发 / 经验） |

## License

[MIT](./LICENSE)
