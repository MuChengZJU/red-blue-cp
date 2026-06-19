# PRD · Red Blue CP

> **自古红蓝出 CP —— B 站小红书 Content Pipeline**

## 项目定位

把 B 站和小红书的视频/图文内容转成纯文本，沉淀成本地 Markdown 知识库。模型默认百炼，开源后期可换。

---

## 功能架构（五层）

### 第一层 · 形态

- **WebUI**：手机 + 电脑浏览器（自部署服务端；远程访问首选 Tailscale 私有网，公网暴露须先加鉴权）
- **CLI**：AI Agent 接入 + 脚本调用

两个入口共享同一组业务函数。`service/` 核心保持**前端无关**（不依赖 fastapi/typer），WebUI 与 CLI 是其上的薄壳——这条纪律给未来的 GUI 客户端留门（GUI 即第三层薄壳）。

**形态与分发定位（2026-06-03 定，详见 [PLAN §Q1](PLAN.md) / [devlog](devlog/2026-06-03-product-form-and-v3-scope.md)）**：不收敛到单一入口。CLI + 自部署 WebUI 走 **PyPI 分发**（`pipx`/`uv tool` 装）；**Tauri 桌面 GUI 客户端为门控 P2**（有真实非技术用户 + API Key 上手路径想清楚才做），属独立的第二条分发线。

**入口与受众定位**：同一套功能选项，三种方式设置——WebUI 给**勾选框**、CLI 给**开关**、Agent 听**人话**翻译成开关（工具本身不解析自然语言，翻译在 Agent 侧完成）。其中：

- **单篇笔记 → 主要给人用**：浏览器点一下，或一条命令。
- **博主全量 → 主要给 Agent 用**：先列清单，Agent 按规则筛选，再逐条下。筛选规则不写死进工具，交 Agent，保持灵活。

**0.6 形态演进（2026-06-15 定，详见 [PLAN v0.6](PLAN.md) / [devlog](devlog/2026-06-15-0.6-speed-read-product.md)）**：从"管道 + 自部署 WebUI"演进为**给人的速览产品**（引擎仍开源，加产品层）。

- 产品 = **RBCP**，一条 Pipeline：**Extract**（采集转录→忠实原文，无损）→ **Digest**（高亮/卡片/脉络，有损 LLM，与 Extract 隔离）→ **Render**。
- 形态壳：**RBCP CLI**（`rbcp`，给 Agent/脚本/批量）+ **RBCP Desktop**（Tauri GUI，给人，灵魂=速览；**原门控 P2 桌面 GUI 在此正式启动**）+ 将来 **RBCP Mobile**（触达，连云）。
- **RBCP Cloud（私有）** = 托管后端 + 计费，单独私有仓库，**不在开源范围**。
- 命名消歧：单说 RBCP=整个产品；指明用 RBCP CLI / RBCP Desktop / RBCP Mobile。
- 砍：本地模型（伪需求）；defer：收藏夹同步（隐私）、知识库管理（保留最小 Library）。

### 第二层 · 核心流水线

| 平台 | 内容类型 | 主路径 | 兜底 |
|---|---|---|---|
| B 站 | 视频 | 平台字幕；无字幕时自动 ASR | UI 手动按钮切 ASR（P1） |
| 小红书 | 视频 | 音频 URL 直发云 ASR；失败回退 ffmpeg 下载后 ASR | — |
| 小红书 | 图文 | 全量图片并发 VLM（URL 优先 + tempfile 兜底） | 后期可加 PaddleOCR 备选 |

每条流水线最终持久化的产物只有 Markdown、纯文本和元数据。媒体文件（音频流、图片）默认只存在于 tempfile 临时目录，任务结束后自动清理，**不进入 `~/transcript/`**。

**项目哲学变更（P1）**：原则上知识库只放转录后的文字。但**可选**地保留原始媒体——用户开启「存媒体」时，原始视频/图片存到**独立目录** `RBCP_MEDIA_DIR`（默认 `~/transcript-media/`，按 note_id 命名），不混进知识库。主要场景是想留视频。默认仍是转录即删。

视频/音频走 ASR 时默认开启**说话人分离**（按声纹区分对谈中的不同人），多人对谈的转录正文标注「说话人N：」。单人内容自动降级为纯文本；单人配音演多角色这类无法靠声纹区分的，由后续 LLM 后处理拆分。

B 站不自动判断字幕质量，由用户在 UI 手动触发"重抽 ASR"。

### 第三层 · 任务调度

1. **单链接**：即时处理
2. **批量链接**：粘贴一批 URL，串行 + 限流
3. **博主全量**：列清单 → 过滤 → 确认 → 下载
   - 拉取实现（小红书）：**抓清单走浏览器插件（MV3 拦 `user_posted`）+ 下载走 rbcp 代理批量**（安全版，见 [博主安全批量](blogger-safe-batch-feature.md)）；pydoll 版（M2b）转为不稳定可选项。B 站另一套机制，本期不做。
   - 过滤：列清单（id+标题+类型+日期），由 **Agent 按规则筛选**（关键词或其他），工具不预设过滤维度
   - 下载前**先预览**：报「共 X 篇（图文 N / 视频 M），预计耗时 Y」，确认后再下；`--all` 默认要确认，`--yes` 跳过
   - 内容选项与单篇一致（带评论 / 存媒体 / 纯文本）

### 第四层 · 辅助功能（独立模块）

**小红书评论提取**
- 叠加在单篇下载上（「带评论」开关），或独立对一篇笔记抓评论
- 默认抓全量评论**含二级（楼中楼）回复**，可选只要一级
- 输出：`{note_id}.comments.md`（一级 + 二级嵌套）
- 实现：pydoll 拦截 `comment/page` + `comment/sub/page` 接口（同博主全量那套浏览器代签）
- 不做可视化树形 UI

### 第五层 · 出口

#### 5.1 本地 Markdown 落盘（主存储）

```
~/transcript/
├── bili/{YYYY-MM-DD}-{up_name}-{title}-{BV_id}.md
├── xhs/{YYYY-MM-DD}-{author}-{title}-{note_id}.md
├── xhs/{YYYY-MM-DD}-{author}-{title}-{note_id}.comments.md
└── _index.sqlite
```

frontmatter 字段：

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
asr_model: paraformer-v2
vision_model: qwen3-vl-flash
status: subtitle | asr | vision | asr_force
tags: []                   # 远期手动/自动加
---
```

#### 5.2 WebUI 出口

| 能力 | 形态 |
|---|---|
| 渲染 | 服务端 Jinja2 + 前端 markdown 库实时渲染 |
| 复制 | 三种粒度：全文 / 仅正文 / 仅 frontmatter |
| 下载 | 单 `.md` 下载、批量打包 zip |
| 手机分享 | Web Share API |

#### 5.3 飞书多维表格同步

放在 P2，本阶段不做。

### 第六层 · 基础设施

| 关注点 | MVP | 后期 |
|---|---|---|
| 模型 | ModelProvider Protocol + DashscopeProvider（百炼 paraformer-v2 / qwen3-vl-flash / qwen-plus） | OpenAI 兼容适配层 |
| 内容存储 | 本地 Markdown + frontmatter | — |
| 索引存储 | SQLite（任务状态） | + FTS5 全文 |
| 中间媒体 | tempfile 临时目录，跑完即删；可选 `--save-media` 存到独立 `RBCP_MEDIA_DIR`（不进知识库） | — |
| 部署位置 | 本地服务器（国内 IP，避免小红书海外风控） | — |
| 远程访问 | tailscale 私有网络（首选）或 frp 中转阿里云日本 | — |
| 失败任务持久化 | url / platform / error_type / error_message / log_excerpt / created_at / updated_at / retry_count | — |

---

## 范围外

- 抖音平台
- MCP server（P0 参考移植不 fork，无 MCP 入口；P2 按需新建）
- Get 笔记历史数据迁移（独立项目）
- DreameClaw skill 形态
- 复杂字幕时间戳 / 视频播放器嵌入
- 评论可视化树形 UI
- MVP 阶段的主题索引知识库（远期愿景）

---

## 实施优先级

### P0 · 跑通 URL → MD（核心闭环）

> 目标：从前端粘一个链接，几分钟后桌面多一个 Markdown 文件。

| 模块 | 内容 |
|---|---|
| 流水线 | B 站视频 / 小红书视频 / 小红书图文，三条全跑通（视频 ASR 默认开说话人分离） |
| 模型 | ModelProvider Protocol + DashscopeProvider（唯一实现） |
| 存储 | 本地 Markdown 落盘 + frontmatter，目录结构定死 |
| 索引 | SQLite jobs 表（schema 见 SPEC） |
| WebUI | 单页：输入框 + 任务列表 + 详情查看 + 下载（轮询，无 SSE） |
| CLI | `rbcp run <url>` 同步阻塞，吐 MD 路径 |
| 部署 | 本地服务器局域网访问，不上公网 |

**P0 不包含**：批量、博主全量、评论、手动 ASR 切换、模型抽象、远程访问、飞书、SSE、FTS5、Pipeline 类抽象、外部 CLI 依赖。

### P1 · 能用 → 好用

按子优先级**串行**进行（不并行）：

```
P1a · 批量 + 限流              (1 天)
P1b · 博主全量（pydoll 拦截器） (1.5 天) ✅ M2b 交付；抓清单主路径已演进为插件，见 P1g
P1c · 评论提取（同套浏览器代签）(0.5 天) ✅ M2c 交付
P1d · B 站手动 ASR 切换         (0.5 天)
P1e · 模型抽象层（最后做）       (1.5 天)
P1f · 远程访问 tailscale         (0.5 天)
P1g · 博主安全批量（插件抓清单 + 代理批量下载 + 错误地基）= M4，把 P1b 的"能跑残次品"补成安全可用
P1h · 任务用量/费用统计（M5a）：每任务记录 ASR 音频时长、VLM/LLM token 数、各阶段耗时，按官方单价估算费用；详情页展示明细，列表页展示累计
```

模型抽象（P1e）单独排足时间，**不要与 P1a-d 并行**——ASR（REST 异步转写）和 VLM/LLM（OpenAI 兼容 HTTP）两种调用模式差异大，要统一到多 Provider 接口需要独立时间。

### P2 · 完善（按需）

| 模块 | 触发条件 |
|---|---|
| 飞书多维表格同步 | 多端同步真实痛了再做 |
| 移动端响应式深度适配 | 手机用得多了 |
| 图片 OCR 备选（PaddleOCR） | VLM 出问题或成本太高 |
| SQLite FTS5 全文检索 | 文档量过百再做 |
| 任务失败重试 / 断点续抓 / 自动 cooldown | 风控经常踩坑了再做 |

---

## 关键决策回顾

- 形态从三入口（WebUI + CLI + MCP）砍到双入口；参考移植不 fork，无 MCP 入口
- 小红书图文 MVP 走 VLM，OCR 是 P2 备选不是 P0 必需
- 远期 LLM Wiki 不进需求文档，本项目交付 Markdown 文件库即可
- 飞书移到 P2
- P0 原则："产物正确"，不要"架构优雅"
- 博主全量"抓清单"从 pydoll 改浏览器插件（pydoll 串行裸 IP 不安全、不可分发）；下载走代理（应对固定共享出口 IP）；pydoll 降为不稳定可选项。详见 [博主安全批量](blogger-safe-batch-feature.md)（2026-06-05）
