# AGENTS.md · Red Blue CP

给在本仓库工作的 AI 编码 agent（Codex / Claude / 其它）的上手指南。
**规则书的单一真相源是 [CLAUDE.md](./CLAUDE.md)** —— 本文件是精简索引，冲突以 CLAUDE.md 为准。

## 一句话

Red Blue CP（红蓝CP）：把 B 站 / 小红书的视频·图文转成本地 Markdown 知识库，并在原文之上生成"速览"（高亮/卡片/脉络）。Pipeline = **Extract**（采集转录→忠实原文，无损）→ **Digest**（原文→速览，LLM 有损但确定性锚定）→ **Render**（CLI / WebUI / 桌面三形态呈现）。

## 目录结构

```
app/
├── extract/   引擎：采集/转录/Markdown/存储/批量/用量/错误（无损；原 service/）
├── digest/    速览：原文→高亮/卡片/脉络（LLM 有损，确定性服务端锚定，与 extract 物理隔离）
├── web/       FastAPI 网页端 + REST API（薄壳）
├── config.py  跨平台配置发现（platformdirs）
└── cli.py     CLI 入口（薄壳）
desktop/        RBCP Desktop：Tauri v2 壳 + PyInstaller sidecar（内置 rbcp serve）
extension/      浏览器插件：油猴脚本 + MV3，抓博主清单导出 notes.json
docs/devlog/    分日开发详情；索引在 LOG.md
```
`app/service/` 是弃用转发 shim（0.7 删），新代码别往里写。

## 构建 / 测试 / 验证（命令可直接复制）

```bash
uv sync                                   # 建环境
./.venv/bin/pytest -q tests               # 跑测试（当前 612）
./.venv/bin/python -m compileall app/     # 至少能编译
bash scripts/check-leaks.sh               # 提交前必跑：查个人/环境信息泄漏
uv run rbcp serve                         # 起本地服务（默认 :8000）
# 桌面端 sidecar 重打（改了 Python 源码必须重打 + 重启 app 才生效）：
cd desktop/sidecar && bash build.sh
```

前端是纯 JS（`desktop/frontend/`、`app/web/templates/`），无构建步骤；改完用 `node --check <file>` 过一遍语法。

## 红线（违反即 bug，详见 CLAUDE.md §不变量）

1. 文件下载/读取走 `job_id`，不接受任意路径（防穿越）。
2. 敏感配置（API Key / cookie）进 `.env`，必须被 `.gitignore`；**绝不进 Git**。
3. MVP 单进程 uvicorn，禁 `--workers > 1`。
4. 知识库目录（`~/transcript`）只放 Markdown + `_index.sqlite`；**媒体/缓存/DB 绝不混入**（缩略图等用 platformdirs 缓存目录）。
5. Markdown 原子写（`.tmp` + `os.replace`）。
6. 小红书图片走 VLM URL 优先 + tempfile 兜底（带 `referer` 防盗链）。
7. 不做抖音；不引入 bilibili-cli / xiaohongshu-cli；不在文档泄漏作者/环境个人信息。

## 工程纪律（高频）

- **改完跑验证**，不只改不测；不注释报错让代码"通过"，找根因。
- **不擅自加依赖**：核心仅 requests/ffmpeg-python/python-dotenv/fastapi/uvicorn/jinja2/typer + 标准库 sqlite3；platformdirs（配置/缓存）；pydoll（可选）。要加先在对话里说。
- **外部 API（DashScope/B站/小红书）查官方文档**，别信引用代码的字段名；调用失败打 response body，别让 HTTPError 吞细节。
- **完工 = 真链路跑通**，不是"测试全绿 + 审阅通过"。里程碑收尾必须端到端实测打到外部 API。
- 提交粒度小，commit message 中文意图 + 英文类型前缀（`feat:`/`fix:`/`docs:`/`refactor:`），**不自动 push**。
- 多 session 并行用 git worktree，按目录切割范围（见 CLAUDE.md §多 session 并行协作）。

## 文档体系

两层日志（硬纪律）：纲要索引 [LOG.md](./LOG.md)（决策/开发/经验三线）+ 详情 `docs/devlog/YYYY-MM-DD-{slug}.md`。完成里程碑/做架构-安全-范围决策/踩坑总结时主动加索引。改 PRD/SPEC/PLAN 前先在对话里说一句。
