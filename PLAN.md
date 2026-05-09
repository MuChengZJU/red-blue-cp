# PLAN · Red Blue CP

> **自古红蓝出 CP —— B 站小红书 Content Pipeline**

## 里程碑总览

| 阶段 | 天数 | 目标 |
|---|---|---|
| M0 | 0.5-1 | 研读上游 + 评估复杂度（参考移植） |
| M1a | 1 | CLI 极简闭环 + ModelProvider |
| M1b | 0.5 | WebUI 最小页 |
| M2 | 3-5 | P1 规模化（按子优先级串行） |
| M3 | 按需 | P2 完善 |

P0 = M0 + M1a + M1b ≈ 2-2.5 天（CC 辅助开发）
P1 = M2 ≈ 3-5 天
P2 = M3，按需

---

## M0 · 研读上游 + 评估复杂度（0.5-1 天）

> **参考移植**：研读上游 social-post-extractor-mcp 的代码，理解 SDK 调用和爬取逻辑，评估自实现复杂度。

### 任务清单

- [ ] clone [JNHFlow21/social-post-extractor-mcp](https://github.com/JNHFlow21/social-post-extractor-mcp)（只读参考，不 fork）
- [ ] 研读上游代码，重点理解三件事：
  - [ ] dashscope SDK 调用方式（ASR / VLM / LLM 三种形态）
  - [ ] 小红书爬取签名逻辑（cookie、headers、防盗链）
  - [ ] B 站视频字幕/音频获取逻辑
- [ ] 评估自实现复杂度：
  - 某单项预估超过 2 天 → 退回方案 A（fork + 旁路包装）
  - 可控 → 继续参考移植
- [ ] 配置百炼 API Key 到 `.env`，验证 SDK 调用通路

### 不做的事

- [ ] ~~fork 上游~~（只读参考）
- [ ] ~~装 bilibili-cli / xiaohongshu-cli~~（P1 才用）
- [ ] ~~抽 PlatformAdapter / Pipeline~~（M1 不需要）

### 出口

理解上游核心逻辑，确认自实现可行性。决定是继续参考移植还是退回 fork。

---

## M1a · CLI 极简闭环（1 天）

> 目标：终端跑 `rbcp run <url>`，桌面多一个 Markdown 文件。

### 任务清单

- [ ] **service/model.py**
  - [ ] `ModelProvider` Protocol（asr / vlm / llm_clean 三个方法）
  - [ ] `DashscopeProvider` 实现（调用 dashscope SDK）
- [ ] **service/extractor.py**
  - [ ] 新增 `extract_url(url, provider) -> ExtractResult`
  - [ ] `ExtractResult` dataclass 包含：platform / content_type / title / author / author_id / published_at / url / text / metadata / raw_info
  - [ ] 内部 if/elif 分发 B 站视频 / 小红书视频 / 小红书图文（不抽 Pipeline）
  - [ ] 自实现内容提取逻辑（参考上游，直接调 dashscope SDK + requests）
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
  - [ ] 依赖列表（不含 mcp）
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

## M1b · WebUI 最小页（0.5 天）

> 目标：浏览器粘 URL，看到结果。

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

## M2 · P1 规模化（3-5 天，子任务串行不并行）

### M2a · 批量 + 限流（1 天）

- [ ] `service/queue.py`：asyncio.Queue + N worker
- [ ] 启动时从 SQLite 重建（pending/running 任务回到 pending）
- [ ] 限流配置：
  - 小红书 worker = 1，间隔 ≥ 2s
  - B 站 worker = 2-4
- [ ] `POST /api/jobs/batch` 接受 URL 数组
- [ ] CLI `rbcp batch <file>`

### M2b · 博主全量（1.5 天）

- [ ] `uv tool install bilibili-cli[audio] xiaohongshu-cli`
- [ ] `service/uploader.py`：subprocess 调 `bili user-videos` / `xhs user-posts`
- [ ] `POST /api/uploaders/{platform}/{uid}/posts` 拉列表
- [ ] WebUI 列表页 + 过滤（时长 / 发布日期 / 关键词）+ 勾选（全选 + 单选）+ 入队按钮
- [ ] CLI `rbcp uploader <platform> <uid>` 输出列表（不自动跑）

### M2c · 评论提取（0.5 天）

- [ ] `service/comments.py`：subprocess 调 `xhs comments URL --all --json`
- [ ] `POST /api/comments` 单笔记
- [ ] 输出 JSON + Markdown 伴生文件（`{note_id}.comments.md`）
- [ ] CLI `rbcp comments <url>`

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
| VLM 图片 token 成本失控（10+ 图笔记） | 中 | 加 `max_images` 软限制（默认 9），超限拒绝 |
| dashscope 不是 OpenAI 兼容，模型抽象工作量低估 | 中 | M2e 单独排足 1.5 天，不与 M2a-d 并行 |
| 小红书爬取自实现复杂度超预期 | 中 | M0 研读上游逻辑，超 2 天预估则退回 fork |
| asyncio.Queue 在多 worker 部署下状态混乱 | 高 | SPEC 强制单进程 uvicorn，禁用 --workers |
| 文件下载接口路径穿越 | 高 | 所有文件接口走 job_id 反查，不接受用户 path |
| ~~MCP 入口删除带坏业务函数~~ | — | 参考移植，无 MCP 入口，风险不存在 |
| 上游图片防盗链 | 中 | VLM 调用走"URL 优先 + tempfile 兜底"双轨 |

---

## 时间盘建议

考虑到本职工作 + ***一周一天 + 近期结业下阶段：

| 阶段 | 建议时间窗 |
|---|---|
| M0 + M1a + M1b | 5 月内（一个完整周末，CC 辅助） |
| M2 | **下阶段后**再做 |
| M3 | 长期可选 |

**P0（M0 + M1a + M1b）应当在结业下阶段前完成**，让本地 Markdown 知识库的核心闭环可用。
**P1 在下阶段后启动**，避开关键期。
