# Red Blue CP · 红蓝CP

> **自古红蓝出 CP —— B 站小红书 Content Pipeline**

把 B 站和小红书的视频/图文内容转成纯文本，沉淀成本地 Markdown 知识库。

## 状态

P0 实施中。基于 [JNHFlow21/social-post-extractor-mcp](https://github.com/JNHFlow21/social-post-extractor-mcp) fork 改造。

仓库名：`red-blue-cp` ｜ PyPI 包名：`red-blue-cp` ｜ CLI 命令：`rbcp` ｜ 内部代号：`rbcp`

## 文档导航

| 文档 | 用途 |
|---|---|
| [PRD.md](./PRD.md) | 产品需求：项目定位、五层功能架构、优先级排期 |
| [SPEC.md](./SPEC.md) | 技术规格：架构、API、数据模型、决策记录 |
| [PLAN.md](./PLAN.md) | 开发计划：里程碑、P0 Checklist、风险 |
| [CLAUDE.md](./CLAUDE.md) | Claude Code 工作规则、项目不变量、红线 |
| [REFERENCES.md](./REFERENCES.md) | 外部仓库选型记录 |
| [LOG.md](./LOG.md) | 项目演进日志：决策纲要 + 开发纲要 + 经验沉淀（详情在 [logs/](./logs/)） |

## 形态

- **WebUI**：手机 + 电脑浏览器
- **CLI**：AI Agent + 脚本调用

两者共享同一组业务函数。

## 目录结构（预期）

```
.
├── app/
│   ├── service/
│   │   ├── extractor.py        # 包装上游 extract 函数
│   │   ├── markdown.py         # frontmatter + sanitize + 原子写入
│   │   └── storage.py          # SQLite jobs CRUD
│   ├── web/
│   │   └── routes.py           # WebUI + REST API
│   └── cli.py                  # rbcp 命令
├── config/
│   └── social-post-extractor.env  # 百炼 API Key（gitignored）
├── PRD.md
├── SPEC.md
├── PLAN.md
├── CLAUDE.md
├── REFERENCES.md
├── LOG.md
├── logs/
│   ├── TEMPLATE.md
│   └── YYYY-MM-DD-{slug}.md     # 决策/里程碑/经验详情
└── README.md
```

知识库默认输出位置：`~/knowledge-vault/`

## 快速开始（占位，P0 完成后填）

```bash
# 1. 克隆
git clone <repo-url>
cd social-post-extractor

# 2. 装依赖
uv sync

# 3. 配 API Key
cp .env.example config/social-post-extractor.env
# 编辑填入 BAILIAN_API_KEY

# 4. 启 WebUI
uv run uvicorn app.web.routes:app

# 或 CLI
uv run rbcp run <url>
```

## 技术栈

FastAPI + Jinja2 + HTMX + typer + SQLite + asyncio + dashscope SDK

## 部署位置

本地服务器（国内 IP，避免小红书海外风控）。手机访问走 tailscale 私有网络或 frp 中转。

## 范围外

- 抖音平台
- MCP server（fork 后保留入口但不维护）
- Get 笔记历史数据迁移（独立项目）
- 远期 LLM Wiki 主题索引（本项目只产 Markdown 原料）

## License

继承上游 Apache-2.0。
