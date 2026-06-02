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

P0 = M0 + M1a + M1b（+ M1c 增强）≈ 2-2.5 天（CC 辅助开发）→ **已完成，首个可用版本 v0.1.0**
P1 = M2 ≈ 3-5 天（未启动）
P2 = M3，按需（未启动）

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

### M2b · 博主全量（✅ 完成 2026-06-03）

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
