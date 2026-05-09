# Red Blue CP · 红蓝CP

> **自古红蓝出 CP —— B 站小红书 Content Pipeline**

把 B 站和小红书的视频/图文内容转成纯文本，沉淀成本地 Markdown 知识库。

## 状态

P0 实施中。参考 [JNHFlow21/social-post-extractor-mcp](https://github.com/JNHFlow21/social-post-extractor-mcp) 逻辑，自主架构实现。

仓库名：`red-blue-cp` ｜ PyPI 包名：`red-blue-cp` ｜ CLI 命令：`rbcp` ｜ 内部代号：`rbcp`

## 文档导航

| 文档 | 用途 |
|---|---|
| [PRD.md](./PRD.md) | 产品需求：项目定位、五层功能架构、优先级排期 |
| [SPEC.md](./SPEC.md) | 技术规格：架构、API、数据模型、决策记录 |
| [PLAN.md](./PLAN.md) | 开发计划：里程碑、P0 Checklist、风险 |
| [CLAUDE.md](./CLAUDE.md) | Claude Code 工作规则、项目不变量、红线 |
| [REFERENCES.md](./REFERENCES.md) | 外部仓库选型记录 |
| [LOG.md](./LOG.md) | 项目演进日志：决策纲要 + 开发纲要 + 经验沉淀（详情在 [docs/devlog/](./docs/devlog/)） |

## 形态

- **WebUI**：手机 + 电脑浏览器
- **CLI**：AI Agent + 脚本调用

两者共享同一组业务函数。

## 目录结构（预期）

```
.
├── app/
│   ├── service/
│   │   ├── model.py            # ModelProvider Protocol + DashscopeProvider
│   │   ├── extractor.py        # 编排：调 fetcher + model
│   │   ├── fetcher.py          # HTTP 爬取 B站/小红书 API + 解析
│   │   ├── markdown.py         # frontmatter + sanitize + 原子写入
│   │   └── storage.py          # SQLite jobs CRUD
│   ├── web/
│   │   └── routes.py           # WebUI + REST API
│   └── cli.py                  # rbcp 命令
├── .env                        # 百炼 API Key + 小红书 cookie（gitignored）
├── PRD.md
├── SPEC.md
├── PLAN.md
├── CLAUDE.md
├── REFERENCES.md
├── LOG.md
├── docs/
│   ├── devlog/
│   │   ├── TEMPLATE.md
│   │   └── YYYY-MM-DD-{slug}.md  # 决策/里程碑/经验详情
│   └── gstack/                    # gstack skill 产出物
└── README.md
```

知识库默认输出位置：`~/transcript/`

## 快速开始（占位，P0 完成后填）

```bash
# 1. 克隆
git clone <repo-url>
cd red-blue-cp

# 2. 装依赖
uv sync

# 3. 配 API Key
cp .env.example .env
# 编辑填入 DASHSCOPE_API_KEY

# 4. 启 WebUI
rbcp serve

# 或 CLI
rbcp run <url>
```

## 技术栈

FastAPI + Jinja2 + HTMX + typer + SQLite + asyncio + requests（REST/OpenAI 兼容 HTTP 直调百炼）

## 部署位置

自部署工具。推荐部署在国内 IP 机器（避免小红书海外风控）。支持 WSL2 mirrored networking。手机访问走 tailscale 私有网络或 frp 中转。

## 范围外

- 抖音平台
- MCP server（P0 不含，P2 按需新建）
- Get 笔记历史数据迁移（独立项目）
- 远期 LLM Wiki 主题索引（本项目只产 Markdown 原料）

## License

MIT 或 Apache-2.0（待定）。
