# LOG · Red Blue CP · 项目演进日志

> **自古红蓝出 CP —— B 站小红书 Content Pipeline**

本文档分三条线：**决策纲要 / 开发纲要 / 经验沉淀**。
每行是索引，详情文档放在 `docs/devlog/` 目录下，按 `YYYY-MM-DD-{slug}.md` 命名。
模板见 [docs/devlog/TEMPLATE.md](docs/devlog/TEMPLATE.md)。

---

## 设计源对话

> 设计阶段的产品/需求讨论发生在 ChatGPT 与 Claude.ai 的网页对话里（私有，未公开）。
> 关键决策已沉淀到下方"决策纲要"和 `docs/devlog/`，可独立追溯，无需原始对话。

| 日期 | 阶段 | 渠道 |
|---|---|---|
| 2026-05-08 | 早期需求探索 | ChatGPT（私有对话） |
| 2026-05-09 | 需求收敛 + 文档冻结 v3.1 | Claude.ai（私有对话） |
| 2026-05-09 | CEO review + 文档同步 | Claude Code · /plan-ceo-review |
| 2026-05-09 | Eng review + 架构决议 | Claude Code · /plan-eng-review |
| 2026-05-09 | M1a + M1b + QA 实施 | Claude Code | TDD + Codex 并行 |

---

## 决策纲要

倒序排列（最新在上）。优先级：🔴 高 / 🟡 中 / 🟢 低。

类别：架构 / 安全 / 业务 / 部署 / 工程 / 范围

| 日期 | 优先级 | 类别 | 决策 | 详情 |
|---|---|---|---|---|
| 2026-06-03 | 🔴 高 | 范围 | Q1 形态定案：不收敛单一入口。现在做＝自部署 WebUI 手机可达（Tailscale）+ 发 PyPI（pipx/uv tool）；Tauri 桌面 GUI 门控 P2（真实非技术用户 + API Key 上手路径）。架构守 service 前端无关给 GUI 留门；公网暴露前必须加鉴权 | [形态定案与 V3 范围](docs/devlog/2026-06-03-product-form-and-v3-scope.md) |
| 2026-06-03 | 🟡 中 | 工程 | WebUI 视觉从零重做为「红蓝品牌」设计系统；详情页 Markdown 渲染/源码切换（marked+DOMPurify，CDN 非 Python 依赖） | [详情](docs/devlog/2026-06-03-webui-redesign-and-qa.md) |
| 2026-06-01 | 🟡 中 | 业务 | ASR 加说话人分离（paraformer-v2 diarization）：多人对谈标「说话人N：」，单人降级纯文本，一人多角色交 LLM 后处理 | SPEC §8.3 / PLAN §M1c |
| 2026-05-09 | 🟡 中 | 业务 | 失败任务加"重试"按钮提前到 P0（成本极低，POST 同 url 复用即可），不等 M2d | [P0 交付](docs/devlog/2026-05-09-p0-delivery.md) |
| 2026-05-09 | 🔴 高 | 架构 | Eng review R2：ASR 统一异步/去 SDK/加 dotenv/配置简化，Codex 20 findings | PLAN.md §Eng Review 决议（第二轮） |
| 2026-05-09 | 🔴 高 | 架构 | Eng review R1：extractor 拆分、to_thread、restart 清理、配置发现链、输出路径可配 | PLAN.md §Eng Review 决议 |
| 2026-05-09 | 🟡 中 | 业务 | 多图笔记全量处理（去掉 max_images 限制），VLM 并发调用 | — |
| 2026-05-09 | 🟡 中 | 业务 | ~~ASR 走音频 URL 优先直发云端~~ → R2 修正：统一走 OSS 流式中转 + 异步文件转写 | — |
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
| 2026-05-09 | Eng review R2 完成 | done | M0 后修正：ASR 统一异步转写、去 dashscope SDK、加 python-dotenv、依赖 7 个 |
| 2026-05-09 | M1a 完成 | done | TDD + Codex 并行：7 轮调度，106 单测全过。[详情](docs/devlog/2026-05-09-p0-delivery.md) |
| 2026-05-09 | M1b 完成 | done | FastAPI + 5 API + HTMX 模板，路径穿越防御，135 单测全过。[详情](docs/devlog/2026-05-09-p0-delivery.md) |
| 2026-05-09 | QA + 接线 bug 修复 | done | 真链接跑通 3/3，修了 5 个接线层 bug（serve/job_id/metadata/timeout/file_urls）。137 单测全过。[详情](docs/devlog/2026-05-09-p0-delivery.md) |
| 2026-05-09 | P0 收尾 | done | 三类链接均能稳定出 Markdown：xhs 图文 / B 站视频 / xhs 视频笔记 |
| 2026-06-02 | M2 文档定稿 | done | 博主全量+评论设计/PRD/SPEC/PLAN/CLAUDE 改完，3 轮 Codex 审 |
| 2026-06-03 | M2b/M2c 完成 | done | 博主全量+评论：并行 SubAgent 写解析层，pydoll 原生捕获写浏览器壳，加 rbcp login。真链路实测：清单 90 笔记 / 评论含楼中楼嵌套渲染。[详情](docs/devlog/2026-06-03-pydoll-native-capture-and-login.md) |
| 2026-06-03 | WebUI 重做（红蓝品牌）+ QA | done | 从零重做 WebUI 设计系统（方案3红蓝品牌）+ 详情页 Markdown 渲染/源码切换（marked+DOMPurify），gstack 浏览器自动化 QA 修 4 个 bug，264 单测全过。[详情](docs/devlog/2026-06-03-webui-redesign-and-qa.md) |
| 2026-06-03 | v0.3.0 发布 | done | 形态落地版发布到 PyPI（`red-blue-cp` 0.3.0）：自部署 WebUI 手机可达 + CI/CD（Trusted Publishing 打 tag 自动发）+ WSL 部署指南 + WebUI 重做。`pipx`/`uv tool` 一行装。真链路验证：从 PyPI 装后 `rbcp --help` 正常。[形态定案与 V3 范围](docs/devlog/2026-06-03-product-form-and-v3-scope.md) |
| 待定 | M2a/d/e/f | pending | 批量限流 / B站手动ASR / 模型抽象 / 远程访问 |

---

## 经验沉淀

值得复用的工程经验。开发过程中遇到值得复用的 lesson 时在这里加索引。

| 日期 | 优先级 | 主题 | 详情 |
|---|---|---|---|
| 2026-06-05 | 🔴 高 | 小红书博主批量全链路验通（探索，未立项）：插件 MV3 抓列表 + CLI 下载转录。换详情需 xsec_token（门票非用户身份，已在导出JSON）、不需 cookie，不带 token 返空壳；下载是 IP 风险非账号风险，海外代理可行（30条8并发1.5s零封）、CDN 下字节12并发零失败；固定共享IP（校园网）必须走代理 | [插件抓列表+批量下载 spike](docs/devlog/2026-06-05-xhs-blogger-batch-spike.md) |
| 2026-06-03 | 🔴 高 | 合成/seed 测试数据丢了真实数据关键特征(frontmatter/脏URL)就给假"通过"，比没测更危险；"做了 e2e"≠"验证有效"，要追问喂的数据像不像真的 | [WebUI 假测复盘](docs/devlog/2026-06-03-retro-webui-fake-test-data.md) |
| 2026-06-03 | 🟡 中 | 自测数据缺真实数据的关键特征就测不出真实 bug（手写无 frontmatter 的 md 掩盖了 marked 把 frontmatter 渲成巨大 setext 标题）；`[hidden]` 会被 `display:flex` 静默盖掉；改 routes.py 须重启 uvicorn（模板热重载 / Python 模块不重载） | [WebUI 重做+QA](docs/devlog/2026-06-03-webui-redesign-and-qa.md) |
| 2026-06-03 | 🔴 高 | 何时能并行=接缝锁定没（锁定=决策敲定+写成代码，不是PRD全不全）；依赖链型串行真不能并行；调研分功能层(锁哪儿)+技术层(锁得住吗)，技术调研要在 fan out 前做 spike | [并行判断+调研分层](docs/devlog/2026-06-03-when-to-parallelize-and-research-layering.md) |
| 2026-06-03 | 🔴 高 | P1 复盘（五段×三问，对标业界 agent 编码方法论）：赢在规划阶段把契约定成可执行的；输在执行/评审对"并行隔离"和"提交=所测"没设硬门 | [P1 复盘](docs/devlog/2026-06-03-retro-p1-claude-code.md) |
| 2026-06-03 | 🔴 高 | pydoll 抓接口别用 JS 注入拦截器（页面早抓走原始 fetch 引用，覆盖钩不到，抓 0）→ 用原生 get_network_logs+get_network_response_body；扫码登录别用 web_session 判成功（游客也有），改按回车确认 | [Phase 2 实测复盘](docs/devlog/2026-06-03-pydoll-native-capture-and-login.md) |
| 2026-06-02 | 🔴 高 | 并行 SubAgent TDD：成本在"合"不在"写"；worktree 可能从旧基线切致 agent 看不到契约而各自重建（接口分叉）；可执行契约(dataclass 桩)+把契约嵌进 prompt 才能收住 | [并行 SubAgent TDD 收获与教训](docs/devlog/2026-06-02-parallel-subagent-tdd-lessons.md) |
| 2026-06-02 | 🔴 高 | 抓博主全量笔记别滚 DOM（触发风控+虚拟滚动丢数据），注入 XHR 拦截器抓 user_posted 接口 JSON，翻页收割；博主编号会乱（跳号/重复），核对按内容不按文件名 | [博主全量·XHR 拦截器](docs/devlog/2026-06-02-xhs-blogger-full-fetch-via-interceptor.md) |
| 2026-05-09 | 🔴 高 | 架构审阅 + 单测都抓不到"接线层"bug，必须靠端到端实测 | [接线层 bug 复盘](docs/devlog/2026-05-09-integration-layer-bugs.md) |
| 2026-05-09 | 🔴 高 | 外部 API 字段名查官方文档，不能信引用代码（`_reference/` 也是错的） | [接线层 bug 复盘](docs/devlog/2026-05-09-integration-layer-bugs.md) |
| 2026-05-09 | 🟡 中 | smoke test 必须跑到外部 API 那一步，否则等于零（YouTube 假 URL 在 detect_platform 第一步就 ValueError） | [接线层 bug 复盘](docs/devlog/2026-05-09-integration-layer-bugs.md) |
| 2026-05-09 | 🟡 中 | 配置加载（load_dotenv 等横切关注点）放进程入口，别埋进业务函数体内 | [接线层 bug 复盘](docs/devlog/2026-05-09-integration-layer-bugs.md) |
| 2026-05-09 | 🟡 中 | TDD + Codex 并行：CC 写测试定接口契约 + Codex 写实现，10+ 轮调度只 1 次返工 | [P0 交付](docs/devlog/2026-05-09-p0-delivery.md) |

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
- 某个工具/库的非显然行为（如百炼 API 的某个怪癖）
- 验证了某个怀疑（如"VLM 直接吃 URL 失败率多高"）
- 完成一个里程碑后值得复盘的事

### 链接源对话

每次产品/需求级别的网页讨论（Claude.ai / ChatGPT）后，在"设计源对话"表格里新增一行（只记日期+渠道，不贴私有对话链接）。这样未来排查"这个决定是怎么来的"时可以追溯。
