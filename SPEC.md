# SPEC · Red Blue CP

> **自古红蓝出 CP —— B 站小红书 Content Pipeline**

## 1. 模块分层（运行时架构）

```
┌─ 入口层 ──────────────────────────────────────────┐
│  WebUI (FastAPI + Jinja2 + HTMX)                 │
│  CLI  (typer)                                     │
│  ↓ 共享同一组业务函数                             │
├─ 业务层 (P0) ─────────────────────────────────────┤
│  service/model.py        ModelProvider + Dashscope │
│  service/extractor.py    编排：调 fetcher + model  │
│  service/fetcher.py      HTTP 爬取 + 解析响应     │
│  service/markdown.py     frontmatter + 模板 + 写入 │
│  service/storage.py      SQLite jobs CRUD         │
├─ 适配层 (P1 引入) ────────────────────────────────┤
│  PlatformAdapter   ModelAdapter   CliSubprocess  │
├─ 存储层 ──────────────────────────────────────────┤
│  Filesystem      (~/transcript/)                 │
│  SQLite Index    (jobs / 后续 fts5)              │
└──────────────────────────────────────────────────┘
```

**P0 阶段不引入**：PlatformAdapter / ModelAdapter / CliSubprocess / Pipeline 类体系 / asyncio.Queue / SSE / FTS5。

---

## 2. P0 代码组织

```
app/
  service/
    model.py            # ModelProvider Protocol + DashscopeProvider
    extractor.py        # 编排：调 fetcher 获取数据 + 调 model 转文字
                        # 输入 URL，输出 ExtractResult
    fetcher.py          # HTTP 爬取 B站/小红书 API + 解析响应
    markdown.py         # frontmatter + 正文模板 + sanitize + 原子写入
    storage.py          # SQLite jobs CRUD（sqlite3 标准库）
  web/
    routes.py           # 输入页 + 任务列表 + 详情 + 下载
    templates/          # Jinja2 模板
  cli.py                # rbcp run <url>
.env                    # 见下方配置项列表（gitignored）
.env.example            # 配置模板（含所有配置项 + 默认值注释）
```

配置发现顺序：环境变量 > `~/.config/rbcp/.env` > 当前目录 `.env`。

### 配置项

| 变量名 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `DASHSCOPE_API_KEY` | 是 | — | 百炼 API Key |
| `XHS_COOKIE` | 否 | — | 小红书 cookie（公开笔记不需要） |
| `RBCP_OUTPUT_DIR` | 否 | `~/transcript` | Markdown 输出目录 |
| `RBCP_ASR_MODEL` | 否 | `paraformer-v2` | 录音文件转写 ASR 模型（REST 异步提交+轮询，可选 qwen3-asr-flash-filetrans） |
| `RBCP_VLM_MODEL` | 否 | `qwen3-vl-flash` | 图片理解 VLM 模型（OpenAI 兼容） |
| `RBCP_LLM_MODEL` | 否 | `qwen-plus` | 文本清理 LLM 模型（OpenAI 兼容） |

代码里 `os.getenv("RBCP_ASR_MODEL", "paraformer-v2")` 带默认值读取，不配就用默认。

P0 走捷径：
- 提交 URL → `asyncio.create_task(asyncio.to_thread(sync_extract_and_save, url))` 后台跑
- 所有阻塞操作（requests / sqlite3 / ffmpeg）通过 `to_thread` 避免阻塞事件循环
- 后台任务用 try/except 包装，异常时 `mark_failed`，防止任务静默卡在 running
- CLI 同步阻塞，跑完返回路径
- WebUI 任务列表用轮询（2s 拉一次 `/api/jobs`）
- 不抽 Pipeline 接口，三种内容类型在 `extractor.py` 内部用 if/elif 分发

---

## 3. 数据流

```
URL ──→ Job (status=pending)
     ↓
service.extractor.extract_url(url, provider)
     ├─ fetcher 爬取平台数据（requests + cookie）
     ├─ B 站视频：有字幕 → 用字幕；无字幕 → provider.asr()（自动，status=asr）
     ├─ 小红书视频：音频流通过 OSS 流式中转发 ASR；失败 → ffmpeg 下载后发 ASR
     ├─ 小红书图文：所有图片并发调 provider.vlm()（URL 优先 + tempfile 兜底）
     ├─ provider.llm_clean() 清理文本
     └─ 转换成 ExtractResult dataclass
     ↓
service.markdown.render_and_write(result)
     ├─ sanitize 文件名
     ├─ Jinja2 渲染 frontmatter + 正文
     ├─ 写 .tmp 文件
     └─ os.replace 原子替换
     ↓
service.storage.mark_done(job_id, md_path)
     ↓
WebUI / CLI 读 SQLite + 文件返回给用户
```

---

## 4. 接口约定

### 4.1 REST API（WebUI ↔ Backend）

P0 必备：

```
POST /api/jobs                      # 提交单条 URL，返回 job_id
GET  /api/jobs?limit=20&offset=0    # 任务列表，前端轮询
GET  /api/jobs/{id}                 # 任务详情
GET  /api/jobs/{id}/markdown        # 渲染 MD 内容（用于详情页展示）
GET  /api/jobs/{id}/download        # 下载 .md（带 Content-Disposition）
```

P1 增加：

```
POST /api/jobs/batch                # 批量提交
POST /api/jobs/{id}/rerun           # 强制重抽（B 站手动 ASR）
POST /api/uploaders/{platform}/{uid}/posts  # 拉博主作品列表
POST /api/comments                  # 评论提取
GET  /api/jobs/zip?ids=1,2,3        # 批量打包下载（按 id，不暴露 path）
```

**安全约束**：所有文件接口必须通过 `job_id` 反查 `md_path`，**不允许**用户传任意 path（防路径穿越）。

### 4.2 CLI 命令

P0 必备：

```
rbcp run <url>                  # 单条，同步阻塞，输出 md_path
rbcp serve                      # 启 WebUI
```

P1 增加：

```
rbcp batch <file>               # 批量，每行一个 URL
rbcp uploader <platform> <uid>  # 拉博主作品列表（不自动跑）
rbcp comments <url>             # 评论提取
```

CLI 内部直接 `from app.service import extractor`，**不走 HTTP**。

---

## 5. SQLite Schema

### 5.1 jobs 表（P0 完整版）

```sql
CREATE TABLE jobs (
  id            INTEGER PRIMARY KEY,
  url           TEXT NOT NULL,
  platform      TEXT,           -- bilibili | xiaohongshu
  content_type  TEXT,           -- video | image_note
  status        TEXT NOT NULL,  -- pending | running | done | failed
  md_path       TEXT,
  title         TEXT,
  author        TEXT,
  error_message TEXT,
  log_excerpt   TEXT,
  retry_count   INTEGER DEFAULT 0,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at DESC);
```

### 5.2 P1 加字段

```sql
ALTER TABLE jobs ADD COLUMN source_uid    TEXT;   -- 博主 uid（来自博主全量任务）
ALTER TABLE jobs ADD COLUMN published_at  TEXT;
ALTER TABLE jobs ADD COLUMN duration_sec  INTEGER;
ALTER TABLE jobs ADD COLUMN image_count   INTEGER;
ALTER TABLE jobs ADD COLUMN asr_model     TEXT;
ALTER TABLE jobs ADD COLUMN vision_model  TEXT;
```

### 5.3 P2 加 FTS5

```sql
CREATE VIRTUAL TABLE jobs_fts USING fts5(title, author, content='jobs');
-- 触发器同步，省略
```

---

## 6. Markdown 文件规范

### 6.1 命名

输出路径可通过环境变量 `RBCP_OUTPUT_DIR` 配置，默认 `~/transcript/`。

```
~/transcript/
├── bili/{YYYY-MM-DD}-{up_name}-{safe_title}-{BV_id}.md
├── xhs/{YYYY-MM-DD}-{author}-{safe_title}-{note_id}.md
└── xhs/{YYYY-MM-DD}-{author}-{safe_title}-{note_id}.comments.md
```

### 6.2 文件名 sanitize 规则

```
safe_title  = 去除 / \ : * ? " < > | + 控制字符 + emoji
            + 压缩连续空白
            + 中英文空格统一
            + 截断到 60 字符
safe_author = 缺失 → "unknown_author"
date        = published_at 缺失 → fetched_at
suffix      = 始终拼 BV_id / note_id 防冲突
```

### 6.3 原子写入

```
1. 写入 {final_path}.tmp
2. os.replace({tmp_path}, {final_path})
3. 失败时清理 tmp
```

### 6.4 frontmatter 模板

```yaml
---
platform: bilibili | xiaohongshu
type: video | image_note
url: <原链接>
author: <作者名>
author_id: <作者 ID>
title: <原标题>
published_at: 2025-MM-DD
fetched_at: 2026-MM-DD
duration_sec: 600          # 视频特有
image_count: 9             # 图文特有
asr_model: <RBCP_ASR_MODEL 配置值>
vision_model: <RBCP_VLM_MODEL 配置值>
status: subtitle | asr | vision | asr_force
tags: []
---

# {title}

> [{author}]({author_url}) · {published_at} · [原链接]({url})

## 转录文本 / 图文 OCR

{text}
```

---

## 7. 部署约束（必须执行）

```
MVP 仅支持单进程：
  uvicorn app.web.routes:app --host 0.0.0.0    （不用 --workers）

绑定 0.0.0.0 而非 127.0.0.1，兼容 WSL2 mirrored networking + tailscale 等外部访问场景。

任务队列是进程内：P0 用 asyncio.create_task + asyncio.to_thread，P1 引入 asyncio.Queue + N worker。
P0 阶段没有真队列。启动时把所有 status=running 的任务改为 failed（进程重启清理）。

P0 安全已知限制（局域网/tailscale 部署下可接受）：
- WebUI 无认证（P1 加 basic auth）
- 无 SSRF 防护（用户提交 URL 后端直接抓取）

P1 引入持久化前不要做多进程部署。
```

---

## 8. 媒体文件处理

### 8.1 原则

- **持久化产物只有**：Markdown / 纯文本 / 元数据
- **允许临时存在**：tempfile.TemporaryDirectory 内的音频流、图片
- **任务结束后自动清理**：通过 context manager 保证

### 8.2 小红书图片 VLM 调用

```
多图笔记全量处理，不设 max_images 上限。VLM 调用可并发（成本低、速度快）。

1. 优先：把图片 URL 直接喂给 qwen3-vl-flash（可并发）
2. 失败回退（单张）：
   - 用 requests.get 下载到 tempfile
   - 必须保留 referer / user-agent headers（小红书图片有防盗链）
   - 喂给 VLM 后立即删除
```

不要把"URL 直接喂模型"当作稳定主路径，必须做双轨。

### 8.3 视频音频 ASR 调用

```
主路径：OSS 流式中转 → 异步文件转写（上游已验证，无需本地 ffmpeg）

1. 从 DashScope 获取临时 OSS 上传凭证（GET /api/v1/uploads?action=getPolicy）
2. 边下载音频流（带 Referer header）边上传到 DashScope 临时 OSS bucket（1MB 分块）
3. 得到 oss:// 路径
4. REST 异步提交转写任务（POST /api/v1/services/audio/asr/transcription）
5. 轮询任务状态直到完成

模型选择：统一用录音文件异步转写模型
- 默认：paraformer-v2（0.288 元/小时，免费 10h/月）
- 可选：qwen3-asr-flash-filetrans（0.792 元/小时，新模型）
- 通过 RBCP_ASR_MODEL 配置切换

失败回退：
   - ffmpeg -i <mp4_url> -vn -c:a copy <tempfile.m4a>
   - 上传后喂给 ASR
   - 用完即删

注：小红书视频 masterUrl 是 MP4 直链（非 m3u8），B 站音频是 .m4s 直链（DASH 格式）
```

---

## 9. 失败任务持久化

每条失败任务必须在 SQLite 留下：

```
url
platform
content_type           可选
status = failed
error_message          单行错误摘要
log_excerpt            最后 50 行日志或异常 traceback
retry_count
created_at
updated_at
```

WebUI 任务列表必须能区分 `done` 和 `failed`，并展示 `error_message` 让用户知道为什么失败（小红书风控场景下尤其重要）。

---

## 10. 关键决策记录

| 决策 | 选 | 不选 | 理由 |
|---|---|---|---|
| 队列 | asyncio.Queue (P1) / create_task (P0) | celery / rq | 单机、单进程、零依赖 |
| 前端 | HTMX + Jinja2 服务端渲染 | React | 无 build step |
| 索引 | SQLite | Postgres | 单文件、无运维 |
| 中间媒体 | tempfile，跑完即删 | 落盘缓存 | 需求明确"无中间媒体进知识库" |
| 图片 VLM | URL 优先 + tempfile 兜底 | 单一路径 | 防盗链、签名过期 |
| 远程访问 | tailscale | 公网 frp | 私有网络更安全、零配置 |
| 部署 | 单进程 uvicorn，禁 --workers | 多 worker | asyncio.Queue 不跨进程 |
| MCP 入口 | ~~保留不动~~ 不存在（参考移植） | fork 上游 | 从零写无 MCP 入口，P2 按需新建 |
| Pipeline 抽象 | P0 不做 | 一开始就分层 | 过度抽象，先验证可行性 |
| 模型抽象 | P1e 最后做 | 早期抽象 | P0 锁定百炼，全部用 requests 调 REST/OpenAI-HTTP，不依赖 dashscope SDK |
| 文件下载 | 经 job_id 反查 | 直接传 path | 防路径穿越 |

---

## 11. 修订记录

| 版本 | 改动 |
|---|---|
| v1 | 初稿：CLI + skill 范式 |
| v2 | 改 WebUI + CLI 双入口；明确本地 Markdown 主存储；加飞书同步、远程访问 |
| v3 | 砍 MCP 入口；模型抽象推到 P1；图文笔记走 VLM；分 P0/P1/P2 |
| v3.1 | 接受外部审阅：P0 砍到极简 / 不删 MCP / 安全 API / 单进程约束 / 失败持久化 / 文件名 sanitize |
| v3.2 | 项目命名为 Red Blue CP（红蓝CP）；CLI 命令 spx → rbcp；包名 red-blue-cp |
| v3.3 | M0 调研修正：ASR 走 OSS 流式中转而非直传 URL；小红书视频是 MP4 非 m3u8；VLM/LLM 走 OpenAI 兼容 HTTP |
| v3.4 | Eng review 2：ASR 统一走异步文件转写（去掉短/长切换）；去掉 dashscope SDK 依赖；模型可通过 .env 切换 |
| v3.5（当前） | 加 python-dotenv 依赖；修正 SPEC 阻塞操作列表去掉 dashscope；依赖 7 个 |
