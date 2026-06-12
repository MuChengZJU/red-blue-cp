---
date: 2026-06-12
type: experiment
priority: medium
related: [app/mcp/CONTRACT.md, 2026-06-10-deep-diagnosis-report.md, 2026-06-10-product-tech-diagnosis.md, 2026-06-12-mcp-protocol-spec-notes.md]
status: active
---

# Agent 接口 demo：4 动词 MCP server（实验，未立项）

> 把 rbcp 的 service 层包成本地 stdio MCP server，让 Claude Code 直接"读"B站/小红书内容和本地语料库；零新增依赖、零修改现有文件。

## 背景

[深度诊断报告](2026-06-10-deep-diagnosis-report.md)（§五）和[方向盘点](2026-06-10-product-tech-diagnosis.md)之后，方向讨论里反复出现的判断是：rbcp 的差异化在**可读化层**，而这一层的**第一读者越来越是 Agent 而不是人**——与其先做给人看的浏览页，不如先验证 Agent 能不能把这个库当工具用。本实验在 `exp/agent-interface-demo` 分支上落一个最小 demo：用纯标准库实现 JSON-RPC stdio 循环（不装 `mcp` 包），把已有 service 接口暴露成 4 个 Agent 动词。契约唯一事实源是 [app/mcp/CONTRACT.md](../../app/mcp/CONTRACT.md)，协议细节依据[MCP 协议笔记](2026-06-12-mcp-protocol-spec-notes.md)（已对官方规范核实）。

## 动词契约摘要（详见 CONTRACT.md）

| 动词 | 干什么 | 入参 | 返回 |
|---|---|---|---|
| `read` | 读一条 B站/小红书内容的完整转录；缓存优先，未命中触发转录（约 1-5 分钟、花少量 API 费） | `url`（必填，接受分享文案）、`force`（默认 false） | 命中：元数据 JSON + Markdown 全文两个 block；进行中/新启动：状态 JSON（含 job_id + 下一步提示） |
| `search` | 在本地知识库全文检索；多词空格分隔、全部命中（AND，不分大小写） | `query`（必填）、`limit`（默认 8） | 单 block JSON：query / total_matched / results（标题、作者、原链接、文件路径、上下文摘录、得分，按得分降序） |
| `list_recent` | 列出最近的转录任务，盘点库里有什么、进展如何 | `limit`（默认 10） | 单 block JSON：jobs（job_id、状态、标题、作者、平台、链接、时间）+ 全库累计费用 |
| `get_status` | 按 job_id 查任务进度 | `job_id`（必填） | 单 block JSON：状态、标题、链接、错误信息；done 时提示再调 `read` 取全文 |

## 怎么试用（Claude Code）

在**仓库根目录**注册（`uv run python -m app.mcp` 依赖当前目录）：

```bash
claude mcp add rbcp-demo -- uv run python -m app.mcp
claude mcp list   # 验证：应看到 rbcp-demo 且状态 connected
```

知识库目录由 `RBCP_OUTPUT_DIR` 控制（默认 `~/transcript`）；`read` 转录新内容需要 `.env` 里的 `DASHSCOPE_API_KEY`，只读动词不需要。

注册后直接对 Claude Code 说，3 个示例提示词：

1. **搜库出金句跳读版**：「用 rbcp-demo 搜一下库里讲"专注"的内容，从命中的几篇里各挑两三句金句，整理成一份跳读版」
2. **read 一条新链接**（会触发转录、花少量 API 费）：「帮我读这条 `https://www.bilibili.com/video/BV1xxxxxxxxx`，没转录过就先启动转录，做完给我核心观点」
3. **盘点最近任务**：「看看库里最近 10 条转录任务，有没有失败的，失败原因是什么」

## 冒烟脚本

[scripts/mcp_demo_smoke.py](../../scripts/mcp_demo_smoke.py)，纯标准库，起子进程按 NDJSON 走一遍 `initialize → initialized → tools/list → search → list_recent`：

```bash
uv run python scripts/mcp_demo_smoke.py                                  # 用现有环境的知识库
uv run python scripts/mcp_demo_smoke.py --output-dir ~/transcript --query 关键词
```

断言：initialize 带 serverInfo、tools/list 恰好 4 个工具、两次 tools/call 都有 content。全过打 `SMOKE OK` 退出码 0。**只走只读动词、绝不调 read——冒烟不花钱**；单条响应超 10 秒判挂死失败。

## 实验声明与转正清单

**声明**：本分支是实验 demo，**未立项**。拍板转正前不改 PRD / PLAN / SPEC / README / LOG 主干，不动 `service/`、`web/`、`cli.py`、`pyproject.toml`——全部产物是新增文件，随时可整体丢弃。

转正要做的事（照 [CONTRACT.md](../../app/mcp/CONTRACT.md) 末节，拍板后才动）：

- [ ] PRD「第一层·形态」加 MCP 入口
- [ ] PLAN 立项（M6?）
- [ ] `rbcp mcp` CLI 子命令
- [ ] `_run_job` / `_safe_error_detail` 上提进 `service/`（demo 里是从 web 层复制的约 40 行）
- [ ] research / comments 动词
- [ ] LOG.md 索引补行
- [ ] pyproject 打包含 `app/mcp`

## 影响

| 文件/模块 | 影响 |
|---|---|
| 现有代码与文档主干 | **零修改**（demo 红线） |
| 新增 | `app/mcp/`（4 文件）、`tests/test_mcp_demo.py`、`scripts/mcp_demo_smoke.py`、本文 |
