# PLAN · Red Blue CP

> **自古红蓝出 CP —— B 站小红书 Content Pipeline**

## 里程碑总览

| 阶段 | 天数 | 目标 | 状态 |
|---|---|---|---|
| M0 | 0.5-1 | 研读上游 + 评估复杂度（参考移植） | ✅ 完成 |
| M1a | 1 | CLI 极简闭环 + ModelProvider | ✅ 完成 |
| M1b | 0.5 | WebUI 最小页 | ✅ 完成 |
| M1c | — | 说话人分离增强（P0 转录保真） | ✅ 完成 |
| M2 | 3-5 | P1 规模化（按子优先级串行） | 🔄 进行中：M2b/M2c ✅ |
| M3 | 按需 | P2 完善 | 未启动 |
| M4 | 3-4 | 博主安全批量 + 错误地基（插件抓清单 + 代理批量下载，补 M2b 残次品） | ✅ 阶段1完成 2026-06-06（WebUI 导入入口推迟） |
| M6 | 并行 | **v0.6 速览产品**：Pipeline = Extract→Digest→Render + 两壳 RBCP Desktop/CLI（地基 M6a 先行，后 fan out） | ✅ 建成+验证 2026-06-16（feat/0.6，566 测试，未发布；详见 §v0.6） |

P0 = M0 + M1a + M1b（+ M1c 增强）≈ 2-2.5 天（CC 辅助开发）→ **已完成，首个可用版本 v0.1.0**
P1 = M2 ≈ 3-5 天（M2b/M2c ✅，M2a/d/e/f 未启动）
P2 = M3，按需（未启动）
M4 = P1 范畴的演进（博主全量从 pydoll 串行 → 插件 + 代理安全批量）+ 横切的错误处理地基；不严格对应单一 P 层。

> **编码说明（维持现状，别造新套）**：本项目两套阶段编码并存——**P0/P1/P2**（PRD 用，优先级/范围）与 **M0/M1/M2…**（PLAN 用，开发里程碑，子任务用小写字母如 M2a/M2b）。两者靠上面映射挂钩，注意**编号错位**：P0↔M1、P1↔M2、P2↔M3。新里程碑一律沿用 `M+数字+小写字母`，不另造第三套编码（曾出现过的 G/Lane 临时编码已废，统一为 M4a/b/c）。

---

## v0.3 · 形态落地（发布里程碑）

> Q1 形态决策（见下方开放问题 §Q1 / [devlog](docs/devlog/2026-06-03-product-form-and-v3-scope.md)）的首个落地版本：**可分发 + 可自部署 + WebUI 打磨**。

| 工作流 | 内容 | 状态 |
|---|---|---|
| PyPI 上架 | 包元数据 + wheel 可发布（`pipx`/`uv tool` 装） | ✅ 打包配置就绪；发布待 PyPI pending publisher + tag |
| CI/CD | ci.yml（PR/push 跑测试）+ publish.yml（tag 自动发，Trusted Publishing） | ✅ |
| WSL 自部署 | 远程可达自部署指南（mirrored 网络 + Tailscale + 群晖同步） | ✅ 指南 [docs/deploy-wsl.md](docs/deploy-wsl.md)；作者实测跑通待验 |
| WebUI 优化 | 红蓝品牌设计系统 + Markdown 渲染/源码切换 + QA | ✅ |

**发布判据**：四块进 main → pyproject `version=0.3.0`（已 bump）→ 打 `v0.3.0` tag → CI 自动发 PyPI。
**不在 v0.3**：Tauri 桌面 GUI（P2 门控）、知识库浏览页（Q2 待定）。

---

## v0.6 · 速览产品（Extract → Digest → Render；RBCP CLI / RBCP Desktop）

> 方向调头（2026-06-15 定，详见 [LOG 决策纲要](LOG.md) / [devlog](docs/devlog/2026-06-15-0.6-speed-read-product.md)）：从"开源管道层"演进为**给人的速览产品**——引擎仍开源，在其上加产品层。
> 产品 = **RBCP**，一条 Pipeline：**Extract**（采集转录→忠实原文，开源库 `rbcp-extract`，原 Core）→ **Digest**（高亮/卡片/脉络，有损 LLM，`rbcp-digest`，与 Extract 隔离）→ **Render**。两壳 **RBCP CLI**（`rbcp`）/ **RBCP Desktop**（Tauri；原门控 P2 桌面 GUI 在此启动）；将来 **RBCP Mobile**。**RBCP Cloud（私有）** 托管+计费，单独私有仓库，不在开源范围。
> 命名消歧：单说 RBCP=整个产品；指明用 RBCP CLI / RBCP Desktop / RBCP Mobile。

### 节奏：已设计的并行干，没想清的串行

**M6 并行批 ✅ 全部建成 + 验证（2026-06-16，`feat/0.6-extract-digest-render`，566 测试，两条真链路实测，未发布）**

| 子里程碑 | 内容 | 状态 |
|---|---|---|
| M6-pre 改名 | `service/`→`extract/`（机械改名 + 弃用 shim） | ✅ |
| 契约锁定 §A/§B/§C | dataclass 桩 + import-lint（4-lens 对抗审查补强，关键不变量自执行） | ✅ |
| M6a 配置清零（地基） | platformdirs 配置发现（修 `~/.config/rbcp/.env` 硬伤）+ PR#46 | ✅ |
| M6b Extract 清接口 | extract 迁冻结契约（canonical+readable+segments+sha256）+ build_canonical | ✅ 真链路（44段对齐/毫秒） |
| M6c Digest | LLM 三形态 + 确定性服务端锚定（exact→normalized，低置信进 diagnostics）；3-lens 对抗验证修 2 major | ✅ 真链路（100% exact） |
| M6f RBCP CLI | `rbcp digest/ls` + 门面动词；run/fetch/list 留别名（get/blogger/search 待补） | ✅ |
| M6e Desktop 壳 | Tauri v2 + PyInstaller sidecar（spike：onefile 9MB/365ms、onedir 20MB/30ms） | ✅ build 过、端到端 |
| M6d 速览三形态 + Render | desktop 前端同屏渲染 高亮跳读/卡片金句/脉络（codepoint 切片） | ✅ headless 验证 |

**收尾欠账**：desktop 用 vendored 引擎拷贝（待接真 app/ 或 `rbcp digest --json`）；未打包/发布；CLI `get/blogger/search` 别名/全文检索待补。
**串行往后（没设计透）**：RBCP Cloud 后端 · 计费 · RBCP Mobile · 精读跨篇 · 可追溯速览。

### 砍 / defer

- **砍**：本地模型 / 本地引擎（伪需求）。
- **defer**：收藏夹自动同步（隐私死穴：平台收藏夹需公开可见才抓得到）；知识库管理（另一个产品 + 不熟，先做起来再说）。保留**最小 Library**（历史/搜索/状态/原链接，现 WebUI 已有雏形）。

### 不在 v0.6（明确）

RBCP Cloud / 计费 / RBCP Mobile / 精读跨篇 / 可追溯速览（设计未透，串行往后）。**商业相关（计费/定价/收款）属私有，不进开源文档。**

---

## M0 · 研读上游 + 评估复杂度（0.5-1 天）

> **参考移植**：研读上游 social-post-extractor-mcp 的代码，理解 SDK 调用和爬取逻辑，评估自实现复杂度。

### 任务清单

- [ ] clone [JNHFlow21/social-post-extractor-mcp](https://github.com/JNHFlow21/social-post-extractor-mcp)（只读参考，不 fork）
- [ ] 研读上游代码，重点理解三件事：
  - [x] ~~dashscope SDK 调用方式~~ → M0 确认：ASR 走 REST 异步，VLM/LLM 走 OpenAI 兼容 HTTP，不用 SDK
  - [x] 小红书爬取签名逻辑（cookie、headers、防盗链）
  - [x] B 站视频字幕/音频获取逻辑
- [ ] 评估自实现复杂度：
  - 某单项预估超过 2 天 → 退回方案 A（fork + 旁路包装）
  - 可控 → 继续参考移植
- [ ] 配置百炼 API Key 到 `.env`，验证 API 调用通路

### 不做的事

- [ ] ~~fork 上游~~（只读参考）
- [ ] ~~装 bilibili-cli / xiaohongshu-cli~~（P1 才用）
- [ ] ~~抽 PlatformAdapter / Pipeline~~（M1 不需要）

### 出口

理解上游核心逻辑，确认自实现可行性。决定是继续参考移植还是退回 fork。

---

## M1a · CLI 极简闭环（1 天）✅ 完成 2026-05-09

> 目标：终端跑 `rbcp run <url>`，桌面多一个 Markdown 文件。
>
> 实施详情见 [docs/devlog/2026-05-09-p0-delivery.md](docs/devlog/2026-05-09-p0-delivery.md)。

### 执行策略：TDD + Codex 并行

先写测试定接口契约，再派 Codex 并行写实现。顺序：

```
第一批（并行）：
  CC 写 test_sanitize.py  →  Codex 实现 service/markdown.py
  CC 写 test_storage.py   →  Codex 实现 service/storage.py

第二批（并行）：
  CC 写 test_model.py     →  Codex 实现 service/model.py（OSS + REST + OpenAI HTTP）

第三批（串行，依赖前面）：
  CC 写 test_extractor.py + service/extractor.py + service/fetcher.py

最后：
  cli.py + pyproject.toml + .env.example + 端到端验收
```

每个模块完成后独立 commit。Codex 产出需要人工 review 后才合入。

### 任务清单

- [ ] **service/model.py**
  - [ ] `ModelProvider` Protocol（asr / vlm / llm_clean 三个方法）
  - [ ] `DashscopeProvider` 实现：
    - [ ] ASR：OSS 流式中转 → REST 异步提交+轮询（不用 dashscope SDK）
    - [ ] VLM：OpenAI 兼容 HTTP `/chat/completions`（URL 直传 + base64 兜底）
    - [ ] LLM 清洗：OpenAI 兼容 HTTP `/chat/completions`
- [ ] **service/extractor.py**
  - [ ] 新增 `extract_url(url, provider) -> ExtractResult`
  - [ ] `ExtractResult` dataclass 包含：platform / content_type / title / author / author_id / published_at / url / text / metadata / raw_info
  - [ ] 内部 if/elif 分发 B 站视频 / 小红书视频 / 小红书图文（不抽 Pipeline）
  - [ ] 自实现内容提取逻辑（参考上游，用 requests 调 REST/OpenAI 兼容 HTTP）
- [ ] **service/markdown.py**
  - [ ] `sanitize_filename(title, author, date, suffix_id) -> str`（按 SPEC §6.2）
  - [ ] Jinja2 模板渲染 frontmatter + 正文（按 SPEC §6.4）
  - [ ] `render_and_write(result) -> Path`，写 .tmp + os.replace 原子替换
- [ ] **service/storage.py**
  - [ ] SQLite schema 初始化（按 SPEC §5.1，P0 完整版）
  - [ ] `create_job / mark_running / mark_done / mark_failed / get_job / list_jobs`
  - [ ] 失败时持久化 error_message + log_excerpt
- [ ] **cli.py**
  - [ ] `rbcp run <url>` 同步阻塞
  - [ ] 跑完输出 `Done: ~/transcript/...`
  - [ ] 失败输出 `Failed: <error_message>`，并把 traceback 写进 SQLite
- [ ] **pyproject.toml**
  - [ ] `[project.scripts]` entry point：`rbcp = "app.cli:app"`
  - [ ] 依赖列表：requests / ffmpeg-python / python-dotenv / fastapi / uvicorn / jinja2 / typer（不含 dashscope SDK / mcp）
- [ ] **启动检测**
  - [ ] 检测 DASHSCOPE_API_KEY + ffmpeg，缺失给清晰提示
- [ ] **URL 自动检测**
  - [ ] 正则匹配 bilibili.com / b23.tv / xiaohongshu.com / xhslink.com

### 验收

- [ ] B 站视频链接 → 正确路径下的 .md，frontmatter 完整
- [ ] 小红书视频链接 → 同上
- [ ] 小红书图文链接 → 同上
- [ ] 失败链接（故意造）→ SQLite 留下 failed 记录
- [ ] tempfile 跑完已清理（任务后 `ls /tmp` 看一眼）

---

## M1b · WebUI 最小页（0.5 天）✅ 完成 2026-05-09

> 目标：浏览器粘 URL，看到结果。
>
> 实施详情见 [docs/devlog/2026-05-09-p0-delivery.md](docs/devlog/2026-05-09-p0-delivery.md)。
> QA 实战 + 接线 bug 复盘见 [docs/devlog/2026-05-09-integration-layer-bugs.md](docs/devlog/2026-05-09-integration-layer-bugs.md)。

### 任务清单

- [ ] **web/routes.py**
  - [ ] `POST /api/jobs` 提交单 URL，返回 job_id；后端 `asyncio.create_task` 跑
  - [ ] `GET /api/jobs?limit=20&offset=0` 任务列表
  - [ ] `GET /api/jobs/{id}` 任务详情
  - [ ] `GET /api/jobs/{id}/markdown` MD 内容
  - [ ] `GET /api/jobs/{id}/download` MD 下载（带 Content-Disposition）
  - [ ] **不暴露 file path**，所有文件接口走 job_id
- [ ] **templates/**
  - [ ] index.html：输入框 + 任务列表（轮询 2s 一次）
  - [ ] detail.html：标题 + frontmatter 摘要 + 正文渲染 + 复制按钮 + 下载按钮
- [ ] 启动命令：`rbcp serve`（内部 `uvicorn --host 0.0.0.0`，**不用 --workers**）

### 验收

- [ ] 浏览器粘 URL → 任务列表出现 → 几分钟后 status=done
- [ ] 点击进详情 → MD 正确渲染
- [ ] 复制按钮工作（三粒度可后期再做，P0 只要"复制全文"）
- [ ] 下载按钮拿到正确文件
- [ ] 失败任务列表显示 error_message
- [ ] 路径穿越测试：`GET /api/jobs/abc/../../etc/passwd` 返回 404

### 不做的事

- [ ] ~~SSE 实时进度~~（轮询够用）
- [ ] ~~批量提交~~
- [ ] ~~博主拉取~~
- [ ] ~~评论提取~~
- [ ] ~~移动端深度适配~~（响应式基础布局即可）

---

## M1c · 说话人分离增强（P0 转录保真，✅ 完成 2026-06-01）

> 目标：多人对谈视频的转录正文能区分说话人，而不是糊成一段。
> 不是新平台/新范围，是 ASR 转录保真度的增强。复用既有 paraformer-v2，加参数即可。

### 任务清单

- [x] **model.py**：提交转写任务带 `diarization_enabled` + 可选 `speaker_count`；
      转写结果按 `transcripts[].sentences[].speaker_id` 分组，输出「说话人N：」；
      ≤1 个说话人时降级纯文本（拆出纯函数 `_format_transcription` 便于单测）
- [x] **extractor.py**：统计说话人数写入 `metadata["speaker_count"]`（≥2 才写）
- [x] **markdown.py + 模板**：frontmatter 透传 `speaker_count`
- [x] **cli.py**：读 `RBCP_ASR_DIARIZATION` / `RBCP_ASR_SPEAKER_COUNT` 环境变量
- [x] **LLM 清洗 prompt**：保留「说话人N：」前缀，不要清洗掉

### 验收

- [x] 单测覆盖 `_format_transcription`：多人 / 单人降级 / 无 speaker_id 字段三种
- [x] 真链路实测一条双人对谈视频，正文真出「说话人N：」、frontmatter 真写 speaker_count

### 不做的事

- [ ] ~~一人多角色靠 ASR 声纹拆分~~（声纹分不出，交给后续 LLM 后处理）
- [ ] ~~句级时间戳 / 词级时间戳落盘~~（P2 再议）

---

## M2 · P1 规模化（3-5 天，子任务串行不并行）

### M2a · 批量 + 限流（1 天）

- [ ] `service/queue.py`：asyncio.Queue + N worker
- [ ] 启动时从 SQLite 重建（pending/running 任务回到 pending）
- [ ] 限流配置：
  - 小红书 worker = 1，间隔 ≥ 2s
  - B 站 worker = 2-4
- [ ] `POST /api/jobs/batch` 接受 URL 数组
- [ ] CLI `rbcp batch <file>`

### M2b · 博主全量（✅ 完成 2026-06-03；抓清单主路径已演进为插件，见 M4，pydoll 转不稳定可选项）

> 实现方式重定为 pydoll **原生网络捕获**（`enable_network_events` + `get_network_logs` + `get_network_response_body`）。设计见 [博主全量+评论设计](docs/devlog/2026-06-02-blogger-full-and-comments-design.md)，实现踩坑见 [Phase 2 实测复盘](docs/devlog/2026-06-03-pydoll-native-capture-and-login.md)。只做小红书；B 站另一套机制本期不做。
> 真链路实测：清单抓 90 笔记（真标题/token/点赞），频率 ~14 请求/分钟。**新增 `rbcp login` 扫码登录命令**作为最终用户拿 cookie 的入口。

- [ ] 加依赖 `pydoll`（CDP 连系统 Chrome，不打包 chromium）；宿主需装 Chrome/Edge
- [ ] `service/discover.py`：pydoll 驱动 Chrome，拦截 `user_posted` 接口；纯函数 `parse_user_posted(json)->list[Note]` 单独可测
  - async 原生，**不走 to_thread**；浏览器任务串行化 + try/finally 关闭
  - 风控/验证码中途触发 → 返回部分清单 + 明确告警，**绝不静默截断**
- [ ] `POST /api/uploaders/posts`（body: user_url）→ 列清单 + 总数/类型拆分/预估
- [ ] CLI `rbcp list <博主url> [--json]`（不下载）
- [ ] CLI `rbcp fetch <url> --all`：整博主下载，默认先预览+确认（`--yes` 跳过），按 note_id 跳过已下载（续传）
- [ ] 子集下载由 Agent 编排（list → 筛 → 逐条 fetch），不在工具里写过滤维度
- [ ] WebUI 列表页 + 勾选下载（人用路径）

### M2c · 评论提取（✅ 完成 2026-06-03）

> 同 M2b 的 pydoll 原生捕获。真链路实测：抓到含楼中楼的评论，嵌套渲染正确（"X 回复 Y" + @提及 + 属地/点赞/时间），频率 ~4 请求/分钟。

- [ ] `service/discover.py` 加 `discover_comments(url)`：拦截 `comment/page` + `comment/sub/page`；纯函数 `parse_comments(json)->list[Comment]` 单独可测
- [ ] `service/comments.py`：评论数据 → `{note_id}.comments.md`（一级 + 二级嵌套）
- [ ] `POST /api/comments`（body: url, sub?）单笔记
- [ ] CLI：`rbcp fetch <url> --comments [--no-sub]`（叠加在单篇下载上）
- [ ] 评论逐篇量大（160+）是最大风控未验证点 → 单篇按需为主 + 可断点续 + 逐篇失败留痕 + 限流

### M2c+ · 媒体落盘 / 纯文本开关（含在 M2b/c）

- [ ] `extractor.py` 加 `--save-media`：原始媒体移出 tempfile → `RBCP_MEDIA_DIR`（独立于知识库，守不变量 #5 新措辞）；视频要存完整视频（比 ASR 多下一步）
- [ ] `extractor.py` 加 `--text-only`：跳过 VLM/ASR；**加回归测试**守住原有全量转写不破

### M2d · B 站手动 ASR 切换（0.5 天）

- [ ] `POST /api/jobs/{id}/rerun?force_asr=true` 强制走 ASR 路径
- [ ] WebUI 详情页加"重抽 ASR"按钮
- [ ] frontmatter status 改为 `asr_force` 标记

### M2e · 模型抽象层（1.5 天，单独排足时间）

- [ ] 抽 `IModelProvider` 接口：
  ```
  asr(audio) -> text
  vlm(images) -> text
  llm_clean(text) -> text
  ```
- [ ] `DashscopeProvider` 实现（MVP 现状）
- [ ] `OpenAICompatProvider` 实现（base_url + api_key + model 三件套）
- [ ] 配置切换：`config/social-post-extractor.env` 加 `MODEL_PROVIDER` 字段

**重点**：不要与 M2a-d 并行。三种调用形态差异大，会拆乱代码。

### M2f · 远程访问（0.5 天，运维任务）

- [ ] tailscale 部署：本地服务器 + 手机加入同一 tailnet
- [ ] 文档化访问方式
- [ ] 备选方案：frp 中转阿里云日本（如果已有）

---

## M3 · P2 完善（按需）

| 子任务 | 触发条件 |
|---|---|
| 飞书多维表格同步 | 手机查看真实痛了 |
| 移动端响应式深度适配 + Web Share API | 手机用得多了 |
| PaddleOCR 备选通路 | VLM 出问题或成本太高 |
| SQLite FTS5 全文检索 + WebUI 搜索框 | 文档量过百 |
| 任务失败重试 / 断点续抓 / cooldown 自动调整 | 风控经常踩坑了 |

不进时间盘。

---

## M4 · 博主安全批量 + 错误地基（✅ 阶段1完成 2026-06-06）

> 完整设计见 [博主安全批量功能文档](docs/blogger-safe-batch-feature.md)。把博主全量从 M2b 的 pydoll 串行（"能跑的残次品"：自动化痕迹 + 串行裸 IP）补成**安全可用**：抓清单改浏览器插件、下载走代理。同时补全项目错误处理（见 [错误审计](docs/error-handling-audit.md)）。
> 执行：先串行 **M4a** 打地基（PR #16），再 **M4b（PR #17）‖ M4c（PR #18）** 并行。三个 PR 各过 Codex 独立 review。
> 真链路验收：真实小红书 URL 跑 `rbcp batch --text-only` 端到端出 Markdown + 断点续传 live 验证；插件↔batch 数据契约跨语言验证通过。
> **未做（留后续）**：WebUI 导入清单入口（需浏览器 QA，自主夜间未验，明确推迟）；完整 §十二 验收（插件真抓 326 + 代理出口 + ≥5 含视频）需用户登录态浏览器 + 配好代理。

> 波1（并行写计划 + 契约交叉核对 + token 过期 spike）已完成，见 [M4 波1 契约 + spike](docs/devlog/2026-06-05-m4-wave1-contracts-and-token-spike.md)。下方任务已据此细化。

### M4a · 错误地基（串行，锁公共接缝）— 独占 `errors.py`(新)/`pipeline.py`(新)/`model.py`/`storage.py`/`extractor.py`+`fetcher.py`(仅 proxy 穿透)
- [ ] `service/errors.py`：异常最小集（RbcpError/UnsupportedUrlError/ConfigError/NetworkError/ApiError/RiskControlError/AuthError(含 `reason`)/ParseError）+ 结构化字段 + `format_error_for_user()`
- [ ] 抽 `_fetch_single` → `service/pipeline.py: fetch_single(url, *, api_key, output_dir, comments, sub, save_media, text_only, proxy=None)`（cli/batch 共用）+ `build_proxies()` + `probe_exit_ip()`
- [ ] **proxy 穿透**（边界扩到 extractor/fetcher）：显式 `proxies=` 一路传到下载层；`model.py` 保持 `trust_env=False` 防环境变量漏代理。**主站走代理，CDN 媒体字节默认不走**（音频/图片，可配置开）。阶段 1 只支持 http/https（socks5 拒）
- [ ] storage 扩展：`batch`/`batch_item` 表 + CRUD 方法 + 迁移（锁定 schema，IF NOT EXISTS）
- [ ] 迁移 `test_p2_wiring.py` 的 mock 目标（`cli._fetch_single`→`pipeline.fetch_single`）

### M4b · 错误流填充（M4a 后，‖ M4c）
- [ ] 各 service 把裸异常 / `raise_for_status` 换成 errors 类 + logging + 打 response body（重点 fetcher/model，audit #1）
- [ ] **token 过期判定**：`fetch_xiaohongshu` 请求后查 `response.url` 含 `/404` 或 `error_code=300031` → 抛 `AuthError(reason="token_expired")`（spike 实证信号，**非** title 空判，须在解析前查）
- [ ] `detail.html` 失败展示分层（人话 + 折叠 traceback）+ 重试按钮；前端轻量 JS 错误映射（audit #2）
- [ ] `cli.py` `run` 退出码 bug 修复（`return`→`raise typer.Exit(1)`）+ 错误文案翻人话（audit #3）
- [ ] `routes.py` `create_job` 平台早校验（audit #4，与 M4c 改同文件不同函数）

### M4c · 博主批量流（M4a 后，‖ M4b）
- [ ] 浏览器插件（MV3）：抓 `user_posted` 清单 → 导出 `notes.json`（带 `schema_version: 1` + 贪婪字段）。阶段 1 只导出 JSON，无 popup
- [ ] `service/batch.py` + CLI `rbcp batch <notes.json>`：schema_version 校验 → 单 URL 代理（开跑前 `probe_exit_ip` 出口探测，未生效报错）→ 逐条 `pipeline.fetch_single(proxy=)` → 断点（查 batch_item status）→ 汇总 ok/failed/skipped
- [ ] token 过期（捕获 `AuthError(reason="token_expired")`）跳过继续、记 skipped、汇总列"需重新抓清单"；complete=false 半份默认拒绝（`--allow-partial` 覆盖）

### 验收
- [ ] 真链路：插件导出真实 notes.json，`rbcp batch` 跑 ≥5 条出 Markdown（含 1 视频；验收口径 = **主站 API 走代理**，音频字节按设计默认不走）
- [ ] 测试：errors 映射 / batch 断点-跳过-失败汇总 / pipeline.fetch_single + proxy 透传 / 出口探测 / token 过期信号

### NOT in scope（→ 阶段 2，M4 之后）
插件 popup UI / 导入收信箱 / 一键转发 / Clash 轮替代理 / WebUI 批量进度 / inbox 表。

### 与红线 #9
抓清单 pydoll → 插件；pydoll 降为不稳定可选项。M2b（pydoll 版）保留为可选，不删。

---

## M5 · 流式+用量统计 + WebUI v2（待启动，0.4.0 后）

> 来源：0.4.0 发布后用户实测反馈 + provider 调研。详见 [M4 交付 + UX 迭代](docs/devlog/2026-06-06-m4-ship-and-ux-iteration.md)。建议拆成两批，先做 M5a（解掉现有痛点）。
> 2026-06-06 范围调整：provider 可配（Gemini 入口）因无真实需求**移出 M5a**，进下方待办区；M5a 改为「流式修超时 + 用量统计」（用户提出要看每任务 ASR/VLM 花多少 token/时间/钱）。

### M5a · 流式修超时 + 任务用量统计（高优先，一个 PR，0.4.1）

**流式修超时**：
- [x] `llm_clean` 改流式 `stream=True`（解析 SSE 累加 `delta.content`，不引 SDK）：read 超时只需覆盖 token 间隔，长文不再撞 180s。根因见 devlog（非流式 + 180s read 超时 vs 长文 ~300s 生成）。
- [x] 顺带：流式路径下 `_retry_network` 对 llm_clean 别再当网络抖动重试 3 次放大等待；保留大默认超时（如 600s）兜底。
- [x] `vlm` 同样支持流式 / 大超时。
- [x] SSE 解析别写死 DashScope 专属字段（为以后切 provider 留门，但**本轮不做配置项**）。

**任务用量统计（P1h）**：
- [x] `model.py` 三个调用返回 usage：ASR（音频秒数 + 调用耗时）、VLM/LLM（prompt/completion token 数 + 耗时）。流式场景取最后一个 SSE 块的 usage 字段（OpenAI 兼容需 `stream_options: {"include_usage": true}`，DashScope 是否支持/默认带，实现前查官方文档实测）。
- [x] 单价表：查 DashScope 官方定价写成常量（paraformer-v2 按秒、qwen3-vl-flash / qwen-plus 按千 token），估算每任务费用。价格变了改一处。
- [x] storage：jobs 表加 `usage` 字段（JSON：各阶段用量/耗时/估算费用），迁移用 `ALTER TABLE ... IF NOT EXISTS` 风格与现有迁移一致。
- [x] WebUI 详情页展示用量明细（ASR x 秒 / LLM x token / 共 ¥y）；列表页顶部累计总费用。
- [x] 测试：SSE 流式解析（伪造分块响应）、usage 落库、费用估算、旧任务无 usage 字段时页面不崩。

**移出本轮**：
- ~~LLM/VLM `base_url+model+api_key` 做成 `.env` 可配（Gemini 入口）~~ → 用户暂无换模型需求，移入待办（见下）。调研结论保留在 devlog：可切，但 ASR 切不了；VLM 切非 DashScope 时图片须走 base64 data URL。
- **ASR 不动**：Gemini OpenAI 兼容层不支持音频转写 + 无结构化说话人分离，paraformer 短期保留；要换是独立课题。

### 待办（无触发不做）
- provider env 化（`RBCP_LLM_BASE_URL`/`_MODEL`/`_API_KEY`，VLM 同理，默认 DashScope，不引 SDK）：等真实换模型需求出现再做；M5a 流式改造已留好泛化解析的门。
- **模型横评实验（平台化才触发）**：对比不同 ASR/VLM/LLM 模型的**效果 / 成本 / 延迟 / 耗时**，给「该用哪个模型」一个数据支撑而非拍脑袋。重点验 **VLM 切 Gemini 免费层**能省多少（图文识别场景）。**触发条件 = 做成多用户平台**（个体用户成本已 trivial，几毛钱一条，不值得动；平台聚合量大才需要省）。价格调研结论（2026-06-08，全球比价）：现状 paraformer-v2(ASR 0.29元/小时,含每月免费10h+中文最稳+免费说话人分离) + qwen3-vl-flash(VLM 0.0012元/张) **已是全球最便宜档**；唯一「每天循环白嫖」是 Gemini 免费层（一套额度覆盖音频+图像），但 ASR 走 Gemini 丢说话人分离。详见 [全球模型比价](docs/devlog/2026-06-08-global-model-pricing-and-benchmark-plan.md)。

### M5b · WebUI v2（0.5.0，进行中 2026-06-07）
- [x] 主页面整合「单条 / 批量」两个标签，去掉独立 `/batches` 页（路由重定向回主页）。
- [x] 批次进任务列表：每批一个标题/名字（可自定义，缺省自动生成），默认显示前几条（可滚动），可展开全部。
- [x] **批量逐条建任务**：`run_batch` 每条建 job（`batch_item` 加 `job_id` 列关联），批次条目可点进 `/jobs/{id}` 详情，用量账单/重试全部复用任务体系。
- [x] 导入按钮/下拉框重做（现在粗糙）。
- [x] **去重检测**：`dedup_key(url)`（B 站 BV 号 / 小红书 note_id 归一，token 参数不同也算同内容）。单条提交已成功下过 → 409 + 已有任务信息，前端弹「已下过，是否重下」，force 才重下；批量导入默认跳过已下过的、报跳过数，可勾选强制全量。
- [x] 顺手：`rbcp serve` 加 `--port`（现在写死 8000，多会话规则里"--port 错开"才成立）。
- **中途取消**：评估结论暂不做——取消主要为应对重复下载，去重做了就基本不需要；真做是 async 控制大件，性价比低。

#### M5b Eval（验收标准，完工=逐条过）

后端（pytest）：
- E1 单条去重：提交与已 done 任务同内容的链接（参数不同）→ 409 + `existing_job_id`；`force=true` → 正常建新任务
- E2 批量去重：`/api/import-list` 默认跳过已下过的笔记、响应报 `skipped_duplicates`；`force=true` 全量重下
- E3 批次取名：batch 表有 `title`（旧库迁移）；导入可传自定义名，缺省自动生成；`GET /api/batches` 返回 title+计数
- E4 批量建任务：`run_batch` 逐条建 job 并随状态推进（done 带 usage / failed 留痕）；`batch_item.job_id` 关联（旧库迁移）
- E5 旧库兼容：0.4.1 库打开自动迁移，旧数据不丢、页面不崩

前端（浏览器实测 + 截图）：
- E6 主页两标签「单条/批量」，`/batches` 重定向回主页
- E7 批量标签的导入交互（选文件/粘贴）重做后清晰可用
- E8 批次卡片进任务列表：标题+进度计数，默认前几条可滚动、可展开全部；条目点进 `/jobs/{id}` 详情正常
- E9 提交重复链接 → 弹「已下过，是否重下」，确认后真重下
- E10 单条提交/详情/重试回归不破

工程：
- E11 全量 pytest 绿 + check-leaks 干净 + Codex review 无 P1
- E12 `rbcp serve --port 8123` 真起得来

---

## 开放问题（待讨论，未决策）

> 记录还没拍板、需要专门讨论的方向。讨论清楚后转成 PRD/PLAN 的正式条目。

### Q1 · 产品形态：自部署服务端 / 打包客户端 / 命令行 / 包？ ✅ 已定（2026-06-03）

> 完整诊断与部署拓扑见 [产品形态定案与 V3 范围](docs/devlog/2026-06-03-product-form-and-v3-scope.md)。

候选（讨论时的四个方向）：自部署服务端 / 打包客户端(Tauri) / 纯 CLI / Python 包。

**决策**：不收敛到单一入口，而是明确"投入哪条、明确不做哪条"：

- **现在做**（零成本服务真实用户：作者 + 技术早期采用者 + Agent）：
  1. 自部署 WebUI 做成**手机可远程访问**（远程访问首选 Tailscale 私有网；FRP 公网等加鉴权再上）。这解决作者本人不用它的根因——现状 localhost 自部署手机够不着。
  2. 正式发 **PyPI**（`uv build`/`uv publish`；用户 `pipx install` 或 `uv tool install`，同一个包两种装法都行）。
- **门控待触发（P2，不是否决）**：Tauri/Electron 桌面 GUI，触发两条缺一不做——(a) 有真实非技术用户开口；(b) API Key 上手路径想清楚。GUI 框架选型 + 视觉设计一并放这阶段。
- **架构纪律（现在守）**：`service/` 核心保持前端无关（不 import fastapi/typer、无加载副作用）。现状 `service/` + `web/` + `cli.py` 已是"核心 + 多薄壳"，GUI 以后是第三层薄壳。**不为"将来三模式"提前抽 launcher**（违反反过度抽象红线）。

**安全前提**：WebUI 现状 `serve` 绑 `0.0.0.0` 且无鉴权（`app/web/routes.py`）。私有网自用安全；**任何公网暴露前必须先加最简鉴权**，否则等于把百炼 API Key 钱包和知识库挂公网。

**关键判断**：CLI/WebUI/包三者成本低且已建好，真正贵的只有 Tauri 这条非技术用户路（打包/Mac 公证/Windows 签名/ffmpeg 跨平台/自动更新/两套 CI）；零需求阶段不提前烧。GUI 不是"加启动 flag"，是独立的**第二条分发线**（桌面 app 不能 pipx 装）。

**V3 范围（2026-06-03 确认）**：(1) 上架 PyPI；(2) 打通 WSL 自部署（mirrored 网络 + Tailscale 手机/Mac 访问 + 输出目录走 `/mnt/c` 给群晖 Synology Drive 同步到 Mac）；(3) GUI / 知识库浏览页后期，守 `service/` 干净留门。

---

### Q2 · 知识库文件的浏览与管理（远程/手机）

知识库现状是 `~/transcript/`（或配 `RBCP_OUTPUT_DIR`）下一堆 Markdown + `_index.sqlite`。手机经 WebUI 看/复制文本够用；但作者要在 Mac 上**文件系统级**操作这批 md（Obsidian 类工具编辑管理），WebUI 给不了文件夹。V3 走"输出目录指到 Windows 本地盘 + 群晖 Synology Drive 同步到 Mac"过渡。后续是否给 WebUI 加知识库浏览页（列出/全文搜/读单篇）作为统一方案，**待 Q1 自部署跑起来后再定**。

---

## 风险与缓解

| 风险 | 概率 | 缓解 |
|---|---|---|
| 小红书风控触发（即使国内 IP） | 中 | 保留 cookie 配置；串行限流强制；UA 伪装 |
| B 站字幕质量参差 | 高 | 不自动判断；M2d 提供手动"重抽 ASR"按钮 |
| VLM 图片 token 成本失控（10+ 图笔记） | 低 | 全量处理 + 并发调用，成本可接受；如确需限制，后期加配置 |
| ~~dashscope 不是 OpenAI 兼容~~ VLM/LLM 已确认 OpenAI 兼容 | 低 | M0 验证完毕，风险降低 |
| 小红书爬取自实现复杂度超预期 | 中 | M0 研读上游逻辑，超 2 天预估则退回 fork |
| asyncio.Queue 在多 worker 部署下状态混乱 | 高 | SPEC 强制单进程 uvicorn，禁用 --workers |
| 文件下载接口路径穿越 | 高 | 所有文件接口走 job_id 反查，不接受用户 path |
| ~~MCP 入口删除带坏业务函数~~ | — | 参考移植，无 MCP 入口，风险不存在 |
| 上游图片防盗链 | 中 | VLM 调用走"URL 优先 + tempfile 兜底"双轨 |

---

## 阶段顺序

| 阶段 | 时机 |
|---|---|
| M0 + M1a + M1b | P0，必须先做 |
| M2 | P0 稳定运行后启动 |
| M3 | 按需，长期可选 |

---

## Eng Review 决议（2026-05-09，第一轮）

/plan-eng-review 产出的 P0 架构补充决议：

1. **extractor.py 拆分**：`service/extractor.py`（编排 + 调 model）+ `service/fetcher.py`（HTTP 爬取 + 解析）
2. **新增 model.py**：`service/model.py` 包含 ModelProvider Protocol + DashscopeProvider
3. **SPEC §2 目录更新**：删除 `config/` 目录，改为根目录 `.env` + `.env.example`
4. **B 站无字幕处理**：API 返回无字幕时自动走 ASR，frontmatter status 标 `asr`（不违反红线 #10）
5. **DB driver**：sqlite3 标准库（不用 aiosqlite），P0 单进程阻塞影响可忽略
6. **event loop 保护**：`asyncio.create_task(asyncio.to_thread(sync_fn))` 包装阻塞操作
7. **后台任务异常捕获**：try/except 包装 + mark_failed，防止任务静默卡在 running
8. **进程重启清理**：启动时把所有 status=running 的任务改为 failed
9. **输出路径可配**：环境变量 `RBCP_OUTPUT_DIR`，默认 `~/transcript/`
10. **配置发现顺序**：环境变量 > `~/.config/rbcp/.env` > 当前目录 `.env`
11. **分发方式（dispatch）**：if/elif 分发，遵循 CLAUDE.md 反过度抽象原则

## Eng Review 决议（2026-05-09，第二轮——M0 后）

M0 调研完成后的架构修正：

12. **ASR 统一走异步文件转写**：不做短/长音频切换，统一用录音文件异步转写 REST API（提交+轮询）
13. **ASR 模型可切换**：默认 paraformer-v2（0.288 元/h），可切 qwen3-asr-flash-filetrans（0.792 元/h）
14. **去掉 dashscope SDK 依赖**：ASR 走 REST，VLM/LLM 走 OpenAI 兼容 HTTP，全部用 requests 完成
15. **OSS 流式中转放 model.py**：作为 DashscopeProvider 私有方法，不单独拆文件
16. **配置项简化**：去掉 `RBCP_ASR_LONG_MODEL`，只保留 `RBCP_ASR_MODEL`（默认 paraformer-v2）
17. **依赖精简**：requests / ffmpeg-python / python-dotenv / fastapi / uvicorn / jinja2 / typer（7 个，不含 dashscope/openai/mcp）
18. **python-dotenv 加入**：.env 自动加载；python-multipart P0 不需要（无文件上传）
19. **ffmpeg-python 保留**：链式 API 比 subprocess 可读性好，P0 场景简单不会踩坑

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | CLEAR | 8 proposals, 4 accepted, 4 deferred |
| Outside Voice | `codex` | Independent 2nd opinion | 1 | issues_found | 4 findings adopted (event loop, restart, config) |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 6 issues, 0 critical gaps |
| Eng Review R2 | `/plan-eng-review` | M0 调研后修正 | 1 | CLEAR | D1-D7: ASR 统一/去 SDK/加 dotenv |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **CODEX R1:** event loop 阻塞、restart 清理、输出路径可配、配置发现顺序 — 全部采纳
- **CODEX R2:** 20 findings, 修复 SPEC os.getenv 默认值/PLAN dashscope SDK 引用/SPEC 阻塞列表；加 python-dotenv 依赖
- **CROSS-MODEL:** 无重大分歧。R1 Codex 认为 P0 范围太大（建议砍到单平台），review 保持三平台。R2 Codex 建议 subprocess 替代 ffmpeg-python，保留 ffmpeg-python
- **UNRESOLVED:** 0
- **VERDICT:** CEO + ENG CLEARED — ready to implement
