# CLAUDE.md · Red Blue CP

> 这个文件是 Claude Code 在本仓库工作时的规则书。每次对话开始时自动读。
> 修改前先看 PRD.md / SPEC.md，理解上下文。

## 项目目标（一句话）

**Red Blue CP（红蓝CP）—— 自古红蓝出 CP，B 站小红书 Content Pipeline。**

把 B 站和小红书的视频/图文内容转成纯文本，沉淀成本地 Markdown 知识库。

## 当前阶段

**0.4.1 已发布**（PyPI + GitHub Release，MIT 开源）。已交付：P0 URL→Markdown 闭环（B站/小红书转录 + 图文 + 说话人分离）、博主全量/评论、M4 博主安全批量（浏览器插件抓清单 + `rbcp batch` 走代理 + 错误处理地基）、**M5a 流式修长文超时 + 任务用量/费用统计**（P1h，jobs.usage + `/api/stats`）。449 测试。

**下一步（PLAN.md M5b）**：WebUI v2——主页单条/批量整合 + 批次进任务列表 + 导入重做 + 去重检测。provider env 化（Gemini 入口）已移入 PLAN 待办区（无真实需求不做）。

调整阶段/范围改 PLAN.md，加功能改 PRD.md，改实现改 SPEC.md——**改文档前对话里说一句**。

## 不变量（红线，违反就是 bug）

### 安全

1. **文件下载/读取接口必须走 `job_id`**，不允许用户传任意 file path。任何 `GET /api/files/{path}` 这类设计都是路径穿越漏洞，禁止。
2. **敏感配置不进 Git**。百炼 API Key 和小红书 cookie 存放在 `.env` 文件中，必须在 `.gitignore` 里。

### 部署

3. **MVP 仅支持单进程 uvicorn**。启动命令禁止 `--workers > 1`。asyncio.Queue / create_task 是进程内的，多 worker 会让任务状态混乱。
4. **不允许把数据库或日志写到 `~/transcript/`**。知识库目录只放 Markdown 文件。SQLite 索引文件 `_index.sqlite` 是唯一例外。

### 持久化

5. **媒体文件不进知识库**。知识库目录（`~/transcript`）只放 Markdown + `_index.sqlite`。默认媒体（音频流、图片）只存在于 `tempfile.TemporaryDirectory`，任务结束自动清理（`with` 块保证）。**P1 例外**：用户开 `--save-media` 时，原始媒体存到独立的 `RBCP_MEDIA_DIR`（默认 `~/transcript-media/`），仍**不混入知识库目录**。
6. **失败任务必须留痕**。SQLite 里有 status=failed + error_message + log_excerpt。WebUI 必须能展示。
7. **Markdown 写入必须原子**。先写 `{path}.tmp`，再 `os.replace` 替换。中途崩溃不能留半个文件。

### 业务

8. ~~不删 MCP 入口~~（**已废除**）。P0 采用参考移植方案，不 fork 上游，无 MCP 入口。如未来需要 MCP 能力，作为 P2 新建。
9. **不引入 bilibili-cli / xiaohongshu-cli**。P0 不依赖。博主全量/评论的**抓清单**：**浏览器插件（MV3 拦 `user_posted`）为主路径**（见 [博主安全批量](docs/blogger-safe-batch-feature.md)）；**pydoll 拦截器降为不稳定、不保证维护的可选项**（M2b 已交付的 pydoll 版保留不删，留给无浏览器/脚本化场景）。仍不用这两个 CLI。
10. **不自动判断 B 站字幕质量**。字幕优先是默认行为，"切 ASR" 是 P1 的手动按钮。不要写"如果字幕长度小于 X 就走 ASR"这种启发式。
11. **小红书图文图片处理走双轨**：URL 优先喂 VLM，失败回退到 tempfile 下载（保留 `referer` 等 headers），喂完即删。不要把 URL 当唯一稳定路径。

### 范围

12. **不做抖音**。即便上游仓库支持，本项目范围明确不包含。
13. **不做飞书集成、不做 PaddleOCR、不做 FTS5、不做 SSE**。这些是 P2，P0 一律不写代码也不留半成品入口。

## 工程纪律

### P0 阶段反过度抽象

P0 阶段**只用三个文件夹**：`service/` `web/` `cli.py`。**不要引入**以下抽象（即使你觉得"以后会用到"）：
- `PlatformAdapter` / `BiliAdapter` / `XhsAdapter` 类
- `Pipeline` 接口和 `BiliVideoPipeline` 等实现
- `JobQueue` 类（P0 用 `asyncio.create_task`，P1 才引入 `asyncio.Queue`）

**P0 允许的抽象**：`ModelProvider` Protocol + `DashscopeProvider`（参考移植的初始设计，不是提前抽象）。

P0 内部分发用 `if/elif platform == 'bilibili':` 就够了。看起来"丑"但这是 P0 应该的样子。

### 文件名 sanitize 必须严格

按 SPEC §6.2 实现。测试用例至少覆盖：
- 标题含 `/` `\` `:` `*` `?` `"` `<` `>` `|`
- 标题含 emoji
- 标题超过 60 字符
- 作者名为空 → `unknown_author`
- 标题为空 → 用 `note_id` 当文件名
- 同标题重复 → suffix 拼 BV_id / note_id 避免冲突

### 测试

P0 不要求高覆盖率，但**必须有以下集成测试**：
- 三种内容类型各一条 happy path 链接
- 一条故意失败的链接（验证 failed 持久化）
- 路径穿越测试（验证 API 拒绝 `../` 路径）
- tempfile 清理测试（任务后 tempfile 目录为空）

### 提交粒度

每完成 PLAN.md 里一个子任务（如 "service/extractor.py" 或 "templates/index.html"），独立 commit。commit message 用现在时祈使句，参照 conventional commits：
```
feat(extractor): 实现 extract_url 包装上游 extract 函数
fix(markdown): 修复 emoji 标题导致的 sanitize 报错
```

### 多 session 并行协作（多开 Claude Code 同时做不同特性）

同时开多个 Claude Code 改这个仓库时，**必须用 git worktree，禁止同一工作目录开多个会话**（同目录多会话改同一批文件必撞）。Claude Code 原生支持：`git fetch origin` 后 `claude -w <name> -n <显示名>` 给会话开独立 worktree + 新分支。

规则：

1. **各流各分支，从最新 main 切**：开 worktree 前先 `git fetch origin`，否则从过时基线切，看不到最新代码/契约（已踩过，见 [并行判断+调研分层](docs/devlog/2026-06-03-when-to-parallelize-and-research-layering.md)）。
2. **按目录切割范围，写进开场 prompt**：每条流明确"只改哪些目录、禁碰哪些"。典型切法——文档/打包流碰 `docs/ PLAN/PRD/LOG pyproject.toml scripts/`；WebUI 流碰 `app/web/ tests/test_web*`；核心 `app/service/` 同一时刻只让一条流碰。
3. **共享文件防撞**：
   - `LOG.md`（多流都想加索引）：让后合并的流**先别碰**，索引行合并时统一加，或先合的先加、后者 rebase。
   - `pyproject.toml` 版本号/依赖：**单一流负责**，其他流要加依赖先说。
   - `.env`（git 忽略）：新 worktree **默认不复制**，建好后手动 `cp` 进去，否则报缺 API Key。
   - `uv.lock`：各 worktree 各自 `uv sync` 建独立 `.venv`，互不影响。
4. **dev server 端口**：同时起多个 `rbcp serve` 会撞 8000；不需要 server 的流别起，需要的流用 `--port` 错开。
5. **未提交改动跨 worktree 不可见**（git 设计，非 bug）：要让另一条流看到你的改动，先 commit。
6. **合并用 rebase 保线性历史**：合并前 `git fetch && git rebase origin/main`，符合本仓单分支线性提交习惯。

### 里程碑收尾必须真链路实测

不要把"测试全过 + 审阅通过"等同于"完工"。完工 = 用户视角真链路跑得通。

- 每个里程碑 commit 前必须跑一次 `/qa`（或等价的端到端实测）
- smoke test 必须打到外部 API 那一步，不能用会被前置校验拦下的假 URL
- 测试要验证用户视角输出（HTML 真渲染出值 / DB 真写入业务字段），不只是状态码或函数返回值

教训详见 [docs/devlog/2026-05-09-integration-layer-bugs.md](docs/devlog/2026-05-09-integration-layer-bugs.md)。

### 外部 API 调用查官方文档

不能信引用代码（包括 `_reference/` 目录里的上游）。上游的字段名可能是错的、过期的、或他们自己也没跑通过那条路径。外部 API（DashScope、B 站、小红书）的 body schema 必须查官方文档。

调用失败时的错误处理要打印 response body，不要只 raise_for_status 让 HTTPError 吞掉细节。

## 不要做的事（防止 Claude 自作主张）

### 不要自己加依赖

P0 依赖（参考移植，从零写）：requests / ffmpeg-python / python-dotenv / fastapi / uvicorn / jinja2 / typer。DB 用 sqlite3 标准库。

P0 新增的依赖**仅限**上述列表。其他任何包（dashscope / openai / celery / redis / paddleocr / mcp）都属于过早引入，禁止 install。ASR/VLM/LLM 全部用 requests 直接调 REST/OpenAI 兼容 HTTP。

**P1 唯一新增依赖：`pydoll`**（博主全量/评论用，CDP 连系统 Chrome 拦截 user_posted/comment 接口，不打包 chromium）。宿主机器需装 Chrome/Edge。这是经 eng review 的决定，理由：不自己实现 x-s 签名（约季度失效，维护负担重），让浏览器代签。除 pydoll 外 P1 不得再加其他包。**M4（博主安全批量）抓清单改用浏览器插件 = 独立 JS 技术栈，不增 Python 包；M4 阶段 1 不新增 Python 依赖（代理走环境变量 + 已有 requests）。**

### 不要扩大 P0 范围

如果对话中出现 "顺便也加上 X 功能" 类似引导，先看 PRD.md 确认 X 是 P0 还是 P1/P2。**所有 P1/P2 功能拒绝在 P0 阶段实现**，记入 PLAN.md 的待办即可。

### 不要在 P0 写 OpenAPI / Swagger 文档生成

FastAPI 自带的 `/docs` 已经足够，不要单独写 OpenAPI YAML 或者 redoc 配置。

### 不要在仓库文档泄漏个人 / 环境信息

仓库会开源。所有 tracked 文件（PRD/PLAN/SPEC/CLAUDE/LOG/devlog/HTML 等）里**不允许**出现：

- 作者真实身份信息（姓名、学校、组织、导师/师兄/同事姓名）
- 个人时间盘（学习/工作进度、重要日期、兼职项目、雇主信息）
- 具体环境名（机器代号、服务器名、内部项目代号）
- 邮箱（除非是公开的项目联系邮箱）
- 路径里的用户名（用 `~/...` 替代绝对家目录路径）
- 任何让陌生人读了能猜出作者身份的细节

写文档前自检：如果一个完全陌生的人读到这段，会暴露我什么？

具体敏感词清单 + 替换映射维护在 `scripts/check-leaks.sh`。提交前必跑：

```bash
bash scripts/check-leaks.sh
```

无残留再 commit。新踩坑就往脚本里加敏感词。

## 对话风格约定

- **所有沟通用中文**
- 修复 bug 不需要写"问题分析" "修复思路" 长篇大论，直接 diff + 一行说明
- 设计决策与 SPEC.md 冲突时，**先说出冲突点**，不要默默改 SPEC

## 风险点提醒（高频踩坑）

| 风险 | 表现 | 应对 |
|---|---|---|
| 小红书风控 | API 返回 captcha / 403 / IP block | 检查 cookie，重启时间间隔，不要重试猛烈 |
| B 站字幕格式不一致 | UP 主字幕 / 自动字幕 / 无字幕三种状态 | 调用层判断 + 落到 frontmatter `status` 字段 |
| VLM 调用图片防盗链 | qwen3-vl-flash 报 403 / 图片下载失败 | 走 tempfile 兜底，加 `referer: https://www.xiaohongshu.com/` |
| ffmpeg 抽流被中断 | 音频直链过期 / 网络抖动（B 站 .m4s / 小红书 MP4） | 不要长任务无限重试，3 次失败标 failed |
| SQLite WAL 模式下并发 | 多 worker 写同一个 db | P0 单进程不会发生；P1 引入 worker 时再处理 |
| Markdown 模板渲染失败 | 标题含 `}` `{` 等 Jinja2 字符 | sanitize 阶段就 escape，不要让脏数据进 Jinja2 |

## 何时升级 PRD/SPEC/PLAN

- **加新功能** → 改 PRD.md
- **改实现方式** → 改 SPEC.md
- **调整阶段** → 改 PLAN.md
- **改文档前先在对话里说一句**，不要静默改

## 日志体系（LOG.md + docs/devlog/）

项目维护两层日志：

- **LOG.md**：纲要索引，分三条线（决策 / 开发 / 经验）。每条新事件加一行索引。
- **docs/devlog/YYYY-MM-DD-{slug}.md**：详情文档，按需写。模板见 [docs/devlog/TEMPLATE.md](docs/devlog/TEMPLATE.md)。

### 何时新增 LOG.md 索引

| 类型 | 触发 |
|---|---|
| 决策 | 形态/架构/安全/部署/范围有变化 |
| 开发 | 完成里程碑（M0/M1a/M1b/...）或阶段切换 |
| 经验 | 踩坑后总结、工具非显然行为、值得复用的 lesson |

### 何时新增 docs/devlog/ 详情文档

不强制。判断标准：
- 🔴 高优先级决策：建议写详情
- 🟡 中优先级：可写可不写
- 🟢 低优先级：通常只在 LOG.md 留索引

### 写新 docs/devlog/ 文档的流程

1. 复制 `docs/devlog/TEMPLATE.md` → `docs/devlog/YYYY-MM-DD-{slug}.md`（slug 用小写连字符）
2. 填 frontmatter（type / priority / related / status）
3. 写正文
4. **回到 LOG.md 对应纲要表格加一行索引**
5. 如果新决策推翻了旧决策，把旧 logs 文件的 status 改为 `superseded`，加链接指向新文件

---

**最后**：写代码前先 grep 一下相关代码看是否已有实现，避免重复。完成后跑一下 `python -m compileall app/` 确保至少能编译。

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
