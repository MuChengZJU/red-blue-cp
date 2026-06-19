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
| 2026-06-15 | 🔴 高 | 形态/范围/架构 | **0.6 调头做「给人的速览」产品**（引擎仍开源）：Pipeline = Extract→Digest→Render，两壳 RBCP CLI / RBCP Desktop（原门控 P2 桌面 GUI 启动）+ 将来 Mobile；速览=高亮/卡片/脉络三形态同屏；砍本地模型、defer 收藏夹/知识库；商业（托管+手机+按实际使用计费）走私有 RBCP Cloud，不进开源。exp/agent-interface-demo(MCP demo) 存档 parked | [0.6 速览产品](docs/devlog/2026-06-15-0.6-speed-read-product.md) / PLAN §v0.6 |
| 2026-06-05 | 🔴 高 | 范围/架构 | 博主全量抓清单 pydoll→浏览器插件(MV3)，pydoll 降不稳定可选项（红线#9 改）；下载加代理（应对固定共享出口 IP）；立项 **M4 博主安全批量 + 错误地基**（M4a 地基串行→M4b‖M4c 并行） | [博主安全批量](docs/blogger-safe-batch-feature.md) / [Codex review](docs/devlog/2026-06-05-codex-review-blogger-batch.md) |
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
| 2026-06-06 | M4 阶段1 完成 | done | 博主安全批量+错误地基。波1 并行写计划+token过期 spike，波2 串行 M4a 锁契约(PR#16)→M4b‖M4c 并行(PR#17/#18)，三 PR 各过 Codex 独立 review（修 1 真 bug + 5 UX/安全项）。MV3 插件抓清单 + `rbcp batch` 走代理断点续传。真链路：真实 xhs URL 端到端出 Markdown + 断点续传 live 验证；插件↔batch 契约跨语言验证。367 单测全过。WebUI 导入入口推迟。[波1契约+spike](docs/devlog/2026-06-05-m4-wave1-contracts-and-token-spike.md) |
| 2026-06-06 | 0.4.0 发布 + UX 迭代 | done | M4 全合 + bump 0.4.0 + CHANGELOG。用户实测反馈一轮：能并行的派 agent(popup/剪贴板/重试/URL-CJK/调研)、耦合的自己做(URL清理接入/重试原地/traceback脱敏/输入框放行)。406 单测。[M4 交付+UX迭代](docs/devlog/2026-06-06-m4-ship-and-ux-iteration.md) |
| 2026-06-07 | M5a 完成 + 0.4.1 发布 | done | 流式修长文超时（根因=非流式+180s read 超时撞 ~300s 生成）+ 任务用量/费用统计 P1h（ASR 秒数/token/耗时/目录价估算，jobs.usage JSON 列+旧库迁移+`/api/stats`）。范围调整：provider env 化（Gemini 入口）因无真实需求移出、进 PLAN 待办。全程 TDD 449 单测；spike 实证 include_usage 与 ASR usage.duration；真链路 B 站视频账单落库+页面渲染；Codex review 修 3 项（重试残留账单/流式连接泄漏/详情页跨重试残留）。PR#35，tag 自动发 PyPI。[M5a 详情](docs/devlog/2026-06-07-m5a-streaming-and-usage.md) |
| 2026-06-07 | M5b 完成 + 0.5.0 发布 | done | WebUI v2：主页单条/批量两标签（去独立 /batches 页）+ 批次卡片进任务列表（取名/进度/前5条可滚/展开/条目进详情）+ **批量逐条建 job**（batch_item.job_id，详情/账单/重试复用任务体系，重跑原地重置）+ 去重检测（dedup_key 归一，单条 409 弹窗确认/批量跳过报数）+ serve --port。Eval E1-E12 先行逐条验收；TDD 475 单测；浏览器真链路核验；Codex review 修 2（P1 批量 job 重试绕过代理 / P2 重跑孤儿 job）。PR#37。[M5b 详情](docs/devlog/2026-06-07-m5b-webui-v2.md) |
| 2026-06-16 | 0.6 M6 全部建成+验证（已并入 0.6.0） | done | 速览产品 Extract→Digest→Render + 两壳。service→extract 改名 + §A/§B/§C 契约锁定(4-lens 对抗审查) + M6a 配置发现(platformdirs 修「~/.config/rbcp/.env 从未被读」硬伤+PR#46) + M6b Extract 迁冻结契约(canonical+readable+segments，真链路44段对齐/毫秒) + M6c Digest+确定性服务端锚定(exact→normalized，3-lens 对抗验证修2 major，真链路100% exact) + M6f CLI(rbcp digest/ls+门面动词) + M6e+d Desktop(Tauri v2+PyInstaller sidecar spike: onefile 9MB/365ms·onedir 30ms + 三形态渲染)。design/verify/fan-out 全程 dynamic workflow 编排。全链路 rbcp digest 真实测过(URL→extract→digest→契约 JSON，时间戳映射)。566 测试。feat/0.6-extract-digest-render。欠账：desktop vendored 引擎拷贝、未打包发布。[实现计划](docs/devlog/2026-06-15-0.6-implementation-plan.md) / [digest-json 契约](docs/contracts/0.6-digest-json-contract.md) |
| 2026-06-07 | 0.5.1/0.5.2 实测连环修 + 插件油猴分发 | done | 用户真机连续暴露问题逐轮修：0.5.1 旧批次回填 job+标题（升级前条目点不进详情根因=「逐条建job」迁移没覆盖存量）；0.5.2 标题去渣+批次费用汇总。插件 0.3.1：根因（首屏 SSR 不发翻页请求→读 `__INITIAL_STATE__.user.notes.value`，探针实证 Vue ref+驼峰字段）；分发改**油猴脚本**（一键装+`@updateURL`自动更新，否决上商店）；面板折叠成小方块。484 单测。[详情](docs/devlog/2026-06-07-plugin-userscript-and-followup-fixes.md) |
| 2026-06-17 | 0.6 桌面端全功能建成（已并入 0.6.0） | done | 桌面端从「速览查看器 spike」改造成**常驻 rbcp serve + 原生红蓝前端**的全功能端。Phase1 后端8任务（产物持久化/APIRouter+token/serve桌面模式/digest端点/批量artifacts/禁pydoll/单篇删除/by_stage账单 + CORS + readable_text 贯通）· Phase3 前端地基+6屏（**6 个 codex 真并行**）· Phase2 Tauri 壳（我直接写 Rust：spawn 常驻 serve / 读 port+token / get_api_config / 单实例 / 退出 watchdog 清理）。该阶段 17 个线性提交。真链路：591 测试 + serve 后端（port/token/401/200/CORS/by_stage 真数据）+ frozen sidecar 起服务 + cargo tauri dev 启动 + spawn serve + 关窗 0 残留。**未验：webview 6 屏真实渲染（待后续 e2e）**。[详情](docs/devlog/2026-06-17-0.6-desktop-built-and-running.md) |
| 2026-06-18 | 0.6 桌面端实测连环修 + 四项补强（已并入 0.6.0） | done | 用户真机连续暴露问题逐轮修：①转录 HTTP 400 根因=设置页存空串把 `RBCP_*_MODEL` 清空（`getenv(k,default)` 空串≠未设）→ 读侧 `or 默认` + 写侧空串跳过 + `config.resolve_output_dir()` 替 9 处；②导出 401「Not authenticated」根因=`<a href>` 跳转不带 token 还把 webview 导航走 → fetch 带头取 blob 保存；③桌面跑的是**冻结 PyInstaller sidecar**，改源码必须 `desktop/sidecar/build.sh` 重打+重启（光清 .env 会被旧二进制再存设置重写空）；④sidecar 漏打 `app/extract/templates`（note.md.j2）→ build.sh 补 `--add-data`。**四项对齐 WebUI 补强**（understand→implement→review 三段 workflow 编排）：任务页状态筛选 chip / reader 整篇 markdown 视图(marked+DOMPurify 懒加载) / 文件库封面缩略图(后端捕获B站封面+小红书首图→缓存端点，红线#5/#11/无新依赖；前端 token blob) / 输入区 form+回车+平台检测+spinner+空态+批次进度费用。对抗审查(5维×验证)修 16 项(批次/筛选可见性同步、markdown 加载竞态、缩略图并发去重+objectURL 释放、`.placeholder`/compose 表单缺 CSS、防重复提交)。渐进加载(digest LLM 同步阻塞→先显示 .md 全文)。桌面 app 图标换 WebUI 红蓝双方块。612 测试。[详情](docs/devlog/2026-06-18-0.6-desktop-parity-and-release.md) |
| 2026-06-18 | **0.6.0 发布** | done | 首个速览产品版本。PyPI（引擎/CLI/WebUI 全平台）+ GitHub Release（含桌面 .app，macOS arm64 未签名）。Pipeline=Extract→Digest→Render；版本 0.5.2→0.6.0；文档全套刷新（README 四形态/AGENTS.md 新建/CLAUDE 当前阶段/CHANGELOG）。合 main 打 tag v0.6.0。612 测试 + leak 检查过。 |
| 待定 | M2a/d/e/f | pending | 批量限流 / B站手动ASR / 模型抽象 / 远程访问 |

---

## 经验沉淀

值得复用的工程经验。开发过程中遇到值得复用的 lesson 时在这里加索引。

| 日期 | 优先级 | 主题 | 详情 |
|---|---|---|---|
| 2026-06-19 | 🔴 高 | Codex(mimo) 并行 vs DynamicWorkflow(Opus) 并行复盘：不是 mimo 代码弱，主因是运行时/工具带不匹配——apply_patch 按 model-slug 查内置 catalog 决定是否注入，mimo 不在 catalog→没给工具，叠 CJK panic+自设预算静默停；甜区(独立/新建/无特殊字符)质量过关。DW 顺=同运行时(同 Edit 工具/同规则书/Opus/结果回流即验)。下一步=3 实验(mimo×codex 协议 spike / 同任务端到端对照 / 不信 exit0 的验证 wrapper) | [Codex vs DW 编排复盘](docs/devlog/2026-06-19-codex-vs-dynamicworkflow-orchestration.md) |
| 2026-06-18 | 🟡 中 | 0.6 周期短反思：引擎稳、痛点全在桌面端新形态（Tauri + 冻结 sidecar）；做对了契约先行+分层隔离+workflow编排+真链路实测；踩了桌面端被低估、冻结 sidecar 调试盲点、getenv 空串雷、靠用户真机逐轮暴露。给下阶段：新形态别压成 spike、计费/云契约更早锁、别开第三份前端 | [短反思](docs/devlog/2026-06-18-0.6-retro-short.md)（详细版后补） |
| 2026-06-17 | 🔴 高 | 「无法转录 llm_clean HTTP 400」根因=设置页存空串把 `RBCP_LLM_MODEL`/`VLM`/`OUTPUT_DIR` 清成 `""`，而读侧全用 `os.getenv(key, default)`——**空串≠未设，默认值不生效**，于是 `model=""` 发给 DashScope 报 400（ASR 模型没被清所以转写能跑、卡在 llm_clean）。同根因解释了仓库里冒出的 `_index.sqlite`（`Path("")`→cwd）。修法=读侧改 `getenv(key) or default`（pipeline 模型 + 新 `config.resolve_output_dir()` 替 9 处内联，立即自愈不用重存）+写侧 `set_config` 把模型字段也加进「空串跳过」。配套观测：API 错误体（DashScope 的 JSON 真因）之前只进服务器日志、GUI 看不到（=用户说的「没日志」）→ `_safe_error_detail` 把 `payload_excerpt` 也带上（服务商 JSON 不含本机路径，安全）。教训①=`getenv(k, default)` 配「能存空串的设置 UI」是反复踩的雷；外部 API 报错体必须可见。教训②（这次真正的卡点）=**桌面端跑的是冻结的 PyInstaller sidecar**（`src-tauri/binaries/rbcp-serve-<triple>`），改 Python 源码**必须 `desktop/sidecar/build.sh` 重打 + 重启 app** 才生效；光清用户 `.env` 会被「旧二进制 + 再存一次设置」重新写空。DashScope 真因 body=`"you must provide a model parameter."`（dev 模式 `cargo tauri dev` 的 stderr 转发了 sidecar 日志才看到）。`build.sh` 用 `uv pip install -e` + `--paths repo`，重打即取当前源码 | 本次会话 |
| 2026-06-17 | 🟡 中 | 桌面端 review 抓到 4 个集成契约 bug（单测全绿没兜住）：①vendored 前端漂移——`/api/batches` 后端包 `{batches:[...]}` 但 desktop 当数组用 + 读不存在的扁平 `done_count`（实际是 `counts` 字典）→ 批次卡片空白；WebUI 早就解包了，desktop 复制时漏。②2s 轮询无条件全量重渲染 `innerHTML` → 把用户手动展开的失败「详情」冲掉（加 signature-diff，对齐 WebUI）。③`output_dir` 空串被持久化 → `Path("")` 落 cwd（后端按 key 同款跳过空串）。④`delete_job` 不解绑 `batch_item.job_id` → 批次悬挂+重跑捞失效 job_id。教训=后端单测覆盖不到 JS 消费端，契约改了要两边一起测 | 本次会话 / code-review-feat-0.6 报告 |
| 2026-06-17 | 🔴 高 | codex@本地高速模型（MiMo-UltraSpeed 1000TPS）并行编排：①稳定做对「实现+定向测试」但常在「全量验证+commit」前停 → codex 写、主控验+提交；②跨多文件常漏 HTTP 路由那一环（库/存储层做对、路由忘了）；③禁 sed（改乱文件 / 全角字符让 apply_patch 失败）→ 整文件覆盖；④**并行解法 = codex 不 commit → 同主仓库并发跑「碰不相交文件」的 N 个 codex、主控统一提交**（避 worktree venv 漂移 + 并发 git 锁）；⑤接缝先锁（api.js 契约+屏模块接口）再 fan out；⑥喂前主控先 grep 核实签名/字段/类型坑；⑦Rust/Tauri 等没联网+版本敏感的主控直接写 | [桌面端建成+并行编排](docs/devlog/2026-06-17-0.6-desktop-built-and-running.md) |
| 2026-06-16 | 🔴 高 | 用户最在意、能看见的那一面（GUI）不该在 fan-out 里被压成最薄 spike：一下午 rigor 全压在看不见但承重的引擎（多 workflow/对抗审查/真链路），Desktop 只给了"速览查看器"渲染 spike、缺 WebUI 全部交互能力 → 用户视角=残废。scoping 按"用户价值可见度"分配投入，不只按技术难度。配套：没 DESIGN.md → fan-out agent 自起暗色 UI 跑偏品牌（已补 DESIGN.md） | [0.6 M6 建成+桌面端缺口](docs/devlog/2026-06-16-0.6-m6-build-and-desktop-gap.md) |
| 2026-06-06 | 🔴 高 | 单测绿但真用崩（再证"完工=真链路"）：①分享文案粘贴报错根因在前端——`<input type=url>` 浏览器提交前就拦下非纯 URL，后端 clean_url 早能抽；改 type=text。②traceback 把 `/home/用户名`/.venv 路径泄漏给用户——log_excerpt 改脱敏异常链摘要、完整 tb 只进服务器日志。③长文 llm_clean 超时根因=非流式+180s read 超时撞 ~300s 生成（不是网络/额度）→ 流式是正解 | [M4 交付+UX迭代](docs/devlog/2026-06-06-m4-ship-and-ux-iteration.md) |
| 2026-06-07 | 🔴 高 | 爬虫目标结构必须探针实证再写代码：修小红书插件时凭记忆赌字段两次都错（notes 是 Vue ref 不是 object；item 字段驼峰不是下划线）→ 用户控制台跑探针拿真实结构才写对。配套：「逐条建job」类把旧数据接新模型的改动迁移要覆盖存量（旧批次成死条目）；补不出的账/无法确认的「是否到底」如实标"部分/估算"不造数据 | [插件油猴+连环修](docs/devlog/2026-06-07-plugin-userscript-and-followup-fixes.md) |
| 2026-06-08 | 🟡 中 | 模型成本调研：阿里云免费额度「轮换白嫖」基本不成立（每月循环的只有 paraformer，其余 ASR+全部 VLM 是一次性90天）；全球比价 paraformer-v2(ASR 0.29元/h)+qwen3-vl-flash(VLM 0.0012元/张)已是最便宜档。结论=现状最优不换；唯一每天循环白嫖是 Gemini 免费层但 ASR 丢说话人分离。立项「模型横评实验」入 PLAN 待办，平台化才触发 | [全球模型比价](docs/devlog/2026-06-08-global-model-pricing-and-benchmark-plan.md) |
| 2026-06-06 | 🔴 高 | 挂机一夜自主完成 M4 复盘：波次法(串行锁契约→并行填充)多 agent 下成立；Codex review 当合并门抓到 mock 盲区(probe_exit_ip 用 requests.get(trust_env=) 真跑 TypeError，单测 mock 吞了)；后台长跑 agent 遇 ECONNRESET 半途死(M4c 只留 RED 测试)→salvage+主会话接手比重派稳；遇不可验证 scope(WebUI 浏览器 QA)主动停+写清楚。后台无人值守期间完成/4 PR/367 测试/9 Codex 修 | [挂机自主 M4 复盘](docs/devlog/2026-06-06-overnight-autonomous-m4-retro.md) |
| 2026-06-05 | 🔴 高 | M4 波1 契约交叉核对 + token 过期 spike：①`proxy` 契约穿不过原文件边界→M4a 扩到 extractor/fetcher 显式 `proxies=` 穿透；②小红书过期 token 可靠信号=`response.url` 跳 `/404`+`error_code=300031`（**非** title 空，避 Codex 误伤坑），须在解析前查；③proxy 口径=主站走代理、CDN 媒体字节默认不走 | [M4 波1 契约+spike](docs/devlog/2026-06-05-m4-wave1-contracts-and-token-spike.md) |
| 2026-06-05 | 🔴 高 | Codex 独立 review 博主批量方案：实锤 `model.py` `trust_env=False` 致视频/ASR 下载绕过代理；并行相交面被低估（storage 隐藏耦合 / 批量必依赖 service 异常）→ **先串行锁地基（errors.py+抽_fetch_single+storage模型+修代理）再并行**；异常契约改少类+结构化字段；阶段1降范围只 CLI batch | [Codex review](docs/devlog/2026-06-05-codex-review-blogger-batch.md) |
| 2026-06-05 | 🔴 高 | 小红书博主批量全链路验通（探索，未立项）：插件 MV3 抓列表 + CLI 下载转录。换详情需 xsec_token（门票非用户身份，已在导出JSON）、不需 cookie，不带 token 返空壳；下载是 IP 风险非账号风险，海外代理可行（30条8并发1.5s零封）、CDN 下字节12并发零失败；固定共享出口 IP（多人共用出口）必须走代理 | [插件抓列表+批量下载 spike](docs/devlog/2026-06-05-xhs-blogger-batch-spike.md) |
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
