---
date: 2026-06-02
type: decision
priority: high
related: [PRD.md, SPEC.md, PLAN.md, CLAUDE.md]
status: active
---

# 设计：博主全量下载 + 评论提取（P1 · M2b/M2c）

> 单篇给人用、博主批量给 Agent 用。两个功能（博主全量、评论）的产品定义 + 一处项目哲学变更（媒体可落盘）+ 实现方式定为 pydoll 拦截器。

---

# 第一部分 · 产品视角（看这段就能决策）

## 这次改动是什么

主体是**功能增加**，附带一处**项目哲学变更**和一点技术调整：

1. **新增能力一：博主全量** —— 给一个博主主页链接，把他的笔记成批下载，而不是一条条手动贴。
2. **新增能力二：评论提取** —— 下载一篇笔记时，可以连同它的评论（含楼中楼回复）一起存下来。
3. **项目哲学变更：媒体可落盘** —— 原来规定"知识库只存转录后的文字，原始图片/视频一律删"。现在放宽：可选地把原始视频/图片留到本地（存在独立目录，不混进知识库）。这条改了项目的一条核心红线，是这次最重的一处。

## 给谁用，怎么用

同一套功能，三种入口，底层选项完全一致：

| 入口 | 谁用 | 选项怎么给（以"带评论"为例） |
|---|---|---|
| 网页 GUI | 人 | 勾选框 ☑ 带评论 |
| 命令行 CLI | 人 / 脚本 | 加开关 `--comments` |
| Agent | 跟 AI 说人话 | "下载这篇，带评论" → AI 翻译成 `--comments` |

工具本身只认开关；"人话 → 开关"的翻译由 Agent 在外面完成，工具不解析自然语言。

**定位**：
- **单篇笔记 → 主要给人用**（网页点一下，或一条命令）。
- **博主全量 → 主要给 Agent 用**（先列清单，Agent 按规则挑出要的，再逐条下）。筛选规则（关键词或别的）不写死进工具，交给 Agent，灵活。

## 下载一篇笔记，能选什么

默认就抓**正文 + 把图片/视频转成文字**。其余是叠加的可选项：

| 选项 | 作用 |
|---|---|
| （默认） | 正文 + 媒体转录（图片识别 / 视频转文字）|
| 带评论 | 额外抓全量评论，默认连楼中楼回复 |
| 只要一级评论 | 配合"带评论"，不要楼中楼 |
| 存媒体 | 额外把原始视频/图片留到本地独立目录（副功能，主要为留视频）|
| 纯文本 | 跳过图片识别和视频转写，只取网页现成正文（Agent 想省时省钱时用）|

两种最常用的组合：① 正文 + 媒体转录；② 再加全量评论。

## 博主全量，两种方式

1. **全量下载**：给博主链接，配置项和单篇一样，把他所有笔记下下来。
2. **只下一部分**（Agent 驱动）：先让工具列出清单（只有标题，不下载），Agent 帮你挑（比如标题含某关键词），再逐条下。

**下载整个博主前一定先预览**：工具先告诉你"这博主一共 X 篇（图文 N / 视频 M），预计耗时 Y"，你（或 Agent 替你）确认了再真正开下。绝不闷头一把全下。

## 不做的

- B 站博主全量（B 站是另一套机制，单独再说）
- 评论的树形可视化界面、评论词云
- "只要图片不要正文"这类拆细的选项（一篇笔记要么图要么视频，没人会只要图不要字）

---

# 第二部分 · 工程细节（产品决策不需要看这段）

## 实现方式：浏览器拦截器（pydoll）

小红书的"列博主笔记清单"和"拉评论"两个接口要动态签名，签名算法藏在网页里、约季度变。不自己实现签名（维护负担重），改用 **pydoll**（一个轻量库，用 CDP 协议连本机已装的 Chrome，不打包浏览器）驱动浏览器，让小红书自己的网页 JS 算签名，我们拦截接口返回的 JSON。已实测：列表 1350 条零风控（见 [拦截器经验](2026-06-02-xhs-blogger-full-fetch-via-interceptor.md)）。

**单篇正文不走这套**——现有 `fetcher.py`（requests + 解析网页 `__INITIAL_STATE__`）已经能抓，不需要浏览器/签名。浏览器只用于"列清单"和"拉评论"。

## 组件

| 文件 | 职责 | 碰浏览器 |
|---|---|---|
| `app/service/discover.py`（新）| pydoll 驱动 Chrome，拦截 `user_posted`/`comment` 接口。**全项目唯一碰浏览器处**，对外只暴露 `discover_user_posts(url)`、`discover_comments(url)` | 是（异步）|
| `app/service/comments.py`（新）| 评论数据 → `{note_id}.comments.md`（一级+二级嵌套）| 否 |
| `app/cli.py`（改）| 加 `list` / `fetch` 命令 | 否 |
| `app/web/routes.py`（改）| `POST /api/uploaders`、`POST /api/comments`，复用现有 `/api/jobs` 队列 | 否 |
| `app/service/extractor.py`（改）| 支持"纯文本"（跳过 VLM/ASR）、"存媒体"（媒体移出 tempfile 到 RBCP_MEDIA_DIR）| 否 |

解析与浏览器分离便于测试：纯函数 `parse_user_posted(json)->list[Note]`、`parse_comments(json)->list[Comment]` 单测；`discover_*` 薄壳做集成测试。

## 命令面

```
rbcp list  <博主url> [--json]                          # 清单(id+标题+类型+日期+token+总数+预估)，不下载
rbcp fetch <url> [--all] [--comments [--no-sub]] \
                 [--save-media] [--text-only] [--json] [--yes]
```

## 并发模型

- `discover.py` 是 async（pydoll 原生），**不能塞进现有 `asyncio.to_thread`**（那是给同步阻塞代码的，见 routes.py:117）；作为原生 async 任务 await，CLI 侧用 `asyncio.run()` 包。
- 浏览器任务**串行化**（一次一个 Chrome），避免多会话并发抬高风控；Chrome 生命周期 try/finally 保证用完即关。

## 边界 / 异常

| 异常 | 处理 |
|---|---|
| 风控/验证码中途触发 | 返回**部分清单 + 明确告警**，绝不静默截断（曾踩 65 截断当全量的坑）|
| 博主 0 笔记 / 私密 | 清晰报错 |
| 笔记已删/私密（跳号）| 清单标注，不计失败 |
| cookie 中途过期 | 失败标"请刷新 cookie"，可断点续传 |
| `--all` 重跑 | 按 note_id 跳过已下载，续传 |
| 单篇失败 | 标 failed 留痕，不影响其他篇 |
| 评论逐篇量大（160+）| 单篇按需为主；批量评论可断点续 + 逐篇留痕 + 限流 |

## 红线 #5 新措辞

旧：「媒体文件不进知识库。音频流、图片必须只存在于 tempfile，任务结束自动清理。」

新：「媒体文件不进知识库（`~/transcript` 只放 Markdown + `_index.sqlite`）。默认转录即删（tempfile）。可选 `--save-media` 时，原始媒体存到独立的 `RBCP_MEDIA_DIR`（默认 `~/transcript-media/`，按 note_id 命名），不混入知识库。」

实现提醒：视频笔记 ASR 现可能只取音频；`--save-media` 要存完整视频，需额外下原视频。

## 依赖 / 宿主

- 新增 **pydoll**（P1 依赖，CDP 连系统 Chrome，不打包 chromium）。
- 宿主机器需装 Chrome/Edge。本地服务器部署时为"无头 Chrome + 注入 `.env` 的 `XHS_COOKIE`"形态（已验证）。

## 测试策略

- 纯函数单测：`parse_user_posted` / `parse_comments`（fixture：真实接口 JSON）——解析、翻页 cursor+has_more、风控部分截断告警
- `comments.py` 格式化 → `.comments.md` 嵌套
- `extractor.py` 回归：纯文本 / 存媒体不破坏原有全量转写
- 集成：真实小博主 happy path（list 拿清单）+ 真实笔记评论（写出 .comments.md）

## 文档传导（本设计确认后）

| 文档 | 改什么 |
|---|---|
| PRD.md | 博主全量/评论的产品定义；单篇人·批量 Agent 定位；三种入口；媒体落盘哲学变更 |
| SPEC.md | `list`/`fetch` 命令面、`POST /api/uploaders`/`/api/comments`、改不变量 #5、加 pydoll 依赖、RBCP_MEDIA_DIR |
| PLAN.md | M2b/M2c 实现方式改 pydoll；并发模型、串行化、预览确认 |
| CLAUDE.md | 红线 #5 改措辞；P1 依赖清单加 pydoll |

## eng review 结论

- ✅ 复杂度不超标（2 新 + 3 改）、充分复用现有（fetcher/队列/storage/markdown）
- ⚠️ P1 并发：discover async vs to_thread，边界已定
- ⚠️ P1 风控：评论逐篇 160+ 是最大未验证点，单篇按需 + 续传 + 留痕兜底
- ⚠️ P2 依赖：pydoll + 宿主 Chrome，文档写明
- ⚠️ 红线：#5 措辞已改（媒体存独立目录）
