# LOG · Red Blue CP · 项目演进日志

> **自古红蓝出 CP —— B 站小红书 Content Pipeline**

本文档分三条线：**决策纲要 / 开发纲要 / 经验沉淀**。
每行是索引，详情文档放在 `docs/devlog/` 目录下，按 `YYYY-MM-DD-{slug}.md` 命名。
模板见 [docs/devlog/TEMPLATE.md](docs/devlog/TEMPLATE.md)。

---

## 设计源对话

| 日期 | 阶段 | 渠道 | 链接 |
|---|---|---|---|
| 2026-05-08 | 早期需求探索 | ChatGPT | <（私有对话，未公开）> |
| 2026-05-09 | 需求收敛 + 文档冻结 v3.1 | Claude.ai | _(填本次对话链接)_ |
| 2026-05-09 | CEO review + 文档同步 | Claude Code | /plan-ceo-review |
| 2026-05-09 | Eng review + 架构决议 | Claude Code | /plan-eng-review |

---

## 决策纲要

倒序排列（最新在上）。优先级：🔴 高 / 🟡 中 / 🟢 低。

类别：架构 / 安全 / 业务 / 部署 / 工程 / 范围

| 日期 | 优先级 | 类别 | 决策 | 详情 |
|---|---|---|---|---|
| 2026-05-09 | 🔴 高 | 架构 | Eng review：extractor 拆分、to_thread、restart 清理、配置发现链、输出路径可配 | PLAN.md §Eng Review 决议 |
| 2026-05-09 | 🟡 中 | 业务 | 多图笔记全量处理（去掉 max_images 限制），VLM 并发调用 | — |
| 2026-05-09 | 🟡 中 | 业务 | ASR 走音频 URL 优先直发云端，失败回退 ffmpeg 下载 | — |
| 2026-05-09 | 🔴 高 | 架构 | CEO review：参考移植取代 fork，P0 加 ModelProvider，Queue/status/auth 推 P1 | [CEO plan](docs/gstack/ceo-plans/2026-05-09-p0-from-scratch.md) |
| 2026-05-09 | 🔴 高 | 架构 | 目录结构 ~/knowledge-vault/ → ~/transcript/ 扁平结构 | — |
| 2026-05-09 | 🔴 高 | 部署 | uvicorn 绑定 0.0.0.0，兼容 WSL2 mirrored networking | — |
| 2026-05-09 | 🔴 高 | 安全 | cookie 与 API Key 同存 .env，.gitignore 保护；P0 WebUI 无认证（已知限制） | — |
| 2026-05-09 | 🔴 高 | 命名 | 项目命名为 Red Blue CP（红蓝CP），CLI 命令 rbcp | [详情](docs/devlog/2026-05-09-naming-red-blue-cp.md) |
| 2026-05-09 | 🔴 高 | 架构 | P0 只允许 ModelProvider 抽象，其余（Pipeline/Queue/Adapter）P1 再引入 | [详情](docs/devlog/2026-05-09-p0-keep-it-simple.md) |
| 2026-05-09 | 🔴 高 | 架构 | ~~不删 MCP 入口~~（已废除：参考移植无 MCP 入口） | — |
| 2026-05-09 | 🔴 高 | 安全 | 文件接口走 job_id 不暴露 path | — |
| 2026-05-09 | 🔴 高 | 部署 | MVP 强制单进程 uvicorn，禁 --workers | — |
| 2026-05-09 | 🔴 高 | 业务 | 小红书图文走 VLM，不依赖 desc 字段 | — |
| 2026-05-09 | 🔴 高 | 工程 | 失败任务必须持久化（含 error_message + log_excerpt） | — |
| 2026-05-09 | 🔴 高 | 范围 | 形态从 CLI+skill 演变到 WebUI+CLI 双入口；MCP 砍掉 | — |
| 2026-05-09 | 🟡 中 | 架构 | 模型抽象推到 P1e，与 P1a-d 串行不并行 | — |
| 2026-05-09 | 🟡 中 | 业务 | VLM 图片走 URL 优先 + tempfile 兜底双轨（防盗链） | — |
| 2026-05-09 | 🟡 中 | 范围 | bilibili-cli / xiaohongshu-cli 推到 P1，不阻塞 P0 | — |
| 2026-05-09 | 🟡 中 | 工程 | 文件名 sanitize 规则严格定义（emoji/特殊字符/超长） | — |
| 2026-05-09 | 🟡 中 | 工程 | tempfile 跑完即删，不进 ~/transcript/ | — |
| 2026-05-09 | 🟡 中 | 架构 | 选 HTMX + Jinja2 服务端渲染，不上 React | — |
| 2026-05-09 | 🟡 中 | 架构 | asyncio.Queue 进程内队列，不上 celery/redis | — |
| 2026-05-09 | 🟢 低 | 部署 | 部署到本地服务器（国内 IP，避免小红书海外风控） | — |
| 2026-05-09 | 🟢 低 | 部署 | 远程访问首选 tailscale，frp 备选 | — |
| 2026-05-09 | 🟢 低 | 工程 | 文档命名约定：PRD/SPEC/PLAN/CLAUDE/REFERENCES/LOG | — |

---

## 开发纲要

按时间正序（最新在下）。

| 日期 | 阶段 | 状态 | 备注 |
|---|---|---|---|
| 2026-05-08 | 早期需求探索 | done | ChatGPT 多轮，得出"开源工具链 vs Get 笔记"的对比 |
| 2026-05-09 | 仓库选型完成 | done | 主体确定 social-post-extractor-mcp，P1 接 bilibili-cli/xiaohongshu-cli |
| 2026-05-09 | 文档冻结 v3.1 | done | PRD / SPEC / PLAN / CLAUDE / REFERENCES / LOG 创建 |
| 2026-05-09 | 项目命名 v3.2 | done | 定名 Red Blue CP（红蓝CP），CLI 命令 rbcp，文档批量更新 |
| 2026-05-09 | CEO review 完成 | done | 参考移植方案确定，P0 scope 精简（+ModelProvider -Queue/status/auth），文档同步 22 处 |
| 2026-05-09 | Eng review 完成 | done | 9 条架构决议（extractor 拆分、to_thread、config 发现等），Codex 审查通过 |
| 2026-05-09 | M0 完成 | done | 研读上游代码 + 云端模型调研完成，确认自实现可行。[详情](docs/devlog/2026-05-09-m0-upstream-analysis.md) |
| 待定 | M1a 完成 | pending | CLI 极简闭环：rbcp run \<url\> 出 MD |
| 待定 | M1b 完成 | pending | WebUI 最小页 |
| 待定 | P0 收尾 | pending | 三类链接均能稳定出 Markdown |
| 待定 | P1 启动（M2） | pending | 下阶段后再说 |

---

## 经验沉淀

值得复用的工程经验。开发过程中遇到值得复用的 lesson 时在这里加索引。

| 日期 | 优先级 | 主题 | 详情 |
|---|---|---|---|
| — | — | _(空)_ | — |

---

## 维护规则

### 何时新增决策行

- 形态/架构变化（影响多个文件）
- 安全约束新增或修订
- 上游依赖切换
- 时间盘 / 优先级调整
- 范围变化（加新功能 / 砍功能）

### 何时新增详情文档

不是所有决策都需要写详情。判断标准：
- **高优先级决策**：建议写详情，未来回看时省时间
- **中优先级决策**：值得写但不强求
- **低优先级决策**：通常只在 LOG.md 留索引

### 何时新增经验沉淀

实际开发遇到这些情况时：
- 踩了一个意料之外的坑（如小红书风控触发条件）
- 某个工具/库的非显然行为（如 dashscope SDK 的某个怪癖）
- 验证了某个怀疑（如"VLM 直接吃 URL 失败率多高"）
- 完成一个里程碑后值得复盘的事

### 链接源对话

每次产品/需求级别的网页讨论（Claude.ai / ChatGPT）后，在"设计源对话"表格里新增一行。这样未来排查"这个决定是怎么来的"时可以追溯。
