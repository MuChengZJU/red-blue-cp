# REFERENCES · Red Blue CP

> **自古红蓝出 CP —— B 站小红书 Content Pipeline**

外部仓库选型。

## 仓库映射表

| 仓库 | 能干什么 | 不能/不适合干什么 | 项目里的定位 |
|---|---|---|---|
| **JNHFlow21/social-post-extractor-mcp** | 直接把 B 站/小红书链接转成文本；支持视频转写、小红书图文图片理解、输出 `script.md` / `info.json` | 原本是 MCP，不是 WebUI/CLI 产品；项目较新（5⭐ 21 commits Alpha） | **P0 参考源**，研读其 SDK 调用和爬取逻辑，自主架构实现 |
| **runesleo/x-reader** | 覆盖 7+ 平台的通用内容读取器 | **无法提取小红书内容** | **竞品参考**，Red Blue CP 是唯一覆盖 B站+小红书的开源项目 |
| **public-clis/bilibili-cli** | B 站字幕、音频提取、评论、UP 主视频列表、JSON 输出 | 不负责整体知识库入库；不是 WebUI | **P1 接入**，用于 B 站博主全量、字幕兜底、强制 ASR |
| **jackwener/xiaohongshu-cli** | 小红书读笔记、搜索、评论、用户主页、博主笔记列表 | **不能下载图片/视频**，所以不能直接做小红书视频转写/图文 OCR | **P1 接入**，用于小红书博主全量和评论提取 |
| **jackwener/xhs-cli** | 浏览器自动化版小红书 CLI，可能更抗风控 | 更重、更慢，需要浏览器环境 | **P2 备胎**，API 版失效时再用 |
| **jackwener/opencli** | 把网站变成 CLI，复用浏览器登录态 | 太泛化；本项目已有更直接工具 | **不进 MVP**，未来登录态兜底 |
| **epiral/bb-browser** | "浏览器就是 API"，给 Agent 复用已登录浏览器 | 工程复杂，不适合 P0/P1 主链路 | **P2 兜底**，适合自己账号复盘/后台页面 |
| **Panniantong/Agent-Reach** | 帮你安装和配置一堆工具 | 它是工具集合 / installer，不是核心能力本身 | **不采用**，只做参考 |
| **HKUDS/CLI-Anything** | 把复杂软件包装成 agent-native CLI | 本项目 CLI 简单，typer 手写够了 | **不采用** |

---

## 一句话决策

- **P0 参考 `social-post-extractor-mcp` 逻辑，自主实现**（不 fork）
- **P1 再接 `bilibili-cli` 和 `xiaohongshu-cli`**
- 其他仓库都是兜底、参考或过度工程化，先不要引入

---

## 引入时机

```
P0:
  social-post-extractor-mcp
    → 参考其逻辑（不 fork）
    → 自主实现 WebUI + CLI + Markdown exporter + SQLite + ModelProvider

P1:
  bilibili-cli
    → uv tool install bilibili-cli[audio]
    → subprocess 调 user-videos / video --subtitle / audio
    → 用于 B 站博主全量、字幕拉取（备用）、强制 ASR 时音频抽取

  xiaohongshu-cli
    → uv tool install xiaohongshu-cli
    → subprocess 调 user-posts / comments --all
    → 用于小红书博主全量、评论提取

P2:
  xhs-cli                 # API 版风控失效时
  opencli                 # 浏览器登录态兜底
  bb-browser              # 自己账号复盘 / 后台页面访问

不采用:
  Agent-Reach             # 工具集合，不是核心能力
  CLI-Anything            # 项目体量不需要这套 harness
```

---

## 关键能力对比（P1 接入时参考）

### B 站

| 能力 | bilibili-cli | social-post-extractor-mcp |
|---|---|---|
| 视频字幕（CC + 自动） | ✅ `bili video BV... --subtitle-timeline --json` | ✅ 自带 |
| 视频转写（ASR） | ❌ 需自接 ASR | ✅ 自带（paraformer-v2） |
| 音频抽取 | ✅ `bili audio BV... --segment 25` 出 16kHz WAV | ⚠️ 内部走 ffmpeg-python |
| UP 主视频列表 | ✅ `bili user-videos UID --max 200` | ❌ 不支持 |
| 评论 | ✅ `bili video BV... --comments` | ❌ 不支持 |
| AI 总结（B 站官方） | ✅ `bili video BV... --ai` | ❌ 不支持 |

**P1 分工**：博主全量用 bilibili-cli；单条转写继续用 social-post-extractor-mcp 的整合链路。

### 小红书

| 能力 | xiaohongshu-cli | social-post-extractor-mcp |
|---|---|---|
| 笔记正文（desc 字段） | ✅ `xhs read URL --json` | ✅ 自带 |
| 视频转写（ASR） | ❌ 不下载视频 | ✅ 自带 |
| 图文图片视觉理解 | ❌ | ✅ 自带（qwen3-vl-flash） |
| 博主笔记列表 | ✅ `xhs user-posts <user_id>` | ❌ 不支持 |
| 评论（含子评论） | ✅ `xhs comments URL --all --json` | ❌ 不支持 |
| 限流策略 | 内置 1-1.5s 抖动，**禁止并行** | 自实现 |

**P1 分工**：博主全量和评论用 xiaohongshu-cli；单条转写/视觉用 social-post-extractor-mcp。

---

## social-post-extractor-mcp 内部依赖（pyproject.toml）

```
mcp >= 1.0.0       # MCP 协议层（fork 后保留入口不动）
requests           # HTTP 抓取
ffmpeg-python      # 音视频处理
tqdm               # 进度条
dashscope          # 阿里云百炼 SDK（ASR + 视觉 + 清理 LLM 都靠它）
fastapi            # HTTP 服务器（本项目继承复用）
uvicorn            # ASGI 服务器（本项目继承复用）
jinja2             # 模板引擎（本项目继承复用）
websockets         # WebSocket
python-socks       # SOCKS 代理
```

**关键事实**：
1. 它**不依赖** bilibili-cli / xiaohongshu-cli，是用 requests 自己实现的抓取
2. 唯一对外 CLI 依赖在 README 写明：`social_analyze_owner_posts`（自己账号复盘）需要 opencli/bb-browser
3. 模型层硬绑 `dashscope` SDK；不是 OpenAI 兼容，要换模型必须重写适配（P1e 任务）
4. 没有传统 OCR 库，"OCR" 实际是 qwen3-vl-flash 视觉模型

---

## 风险与备选

| 主路径失效场景 | 备选 |
|---|---|
| 小红书 API 风控（xiaohongshu-cli 失效） | xhs-cli（浏览器自动化版） |
| 小红书需要登录态访问后台数据 | opencli / bb-browser |
| dashscope 不可用或成本飙升 | P1e 完成后切 OpenAI 兼容服务（Groq / 火山 / 自建 vllm） |
| qwen3-vl-flash 视觉效果不达标 | P2 加 PaddleOCR 备选通路 |
| 上游 social-post-extractor-mcp 长期不维护 | fork 自己维护，依赖少（10 个包） |

---

## 与上游同步策略

- 不主动从上游 `git pull`，避免破坏改造
- 重大上游修复（小红书签名更新等）按需 cherry-pick
- 自己的改动只放在 `app/` 目录下，不混入 `social_post_extractor_mcp/`，方便上游同步
