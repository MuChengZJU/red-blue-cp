---
date: 2026-06-03
type: milestone
priority: medium
related: [CLAUDE.md, SPEC.md]
status: active
---

# WebUI 从零重做「红蓝品牌」设计 + 浏览器自动化 QA

> 旧 WebUI 平庸且有 UX 硬伤（Markdown 原始符号直出、AI 味渐变 banner、系统字）。从零重做视觉与交互，选定「红蓝品牌」方向，并用 gstack 浏览器自动化对真实库做全面 QA，当场修了 4 个 bug。仅动 `app/web/`，未碰 service/依赖。

## 背景

P0 的 WebUI 是功能可用但视觉/交互粗糙的初版：

- **详情页把 Markdown 当原始文本塞进黑底 `<pre>`** —— 产品卖点是「沉淀成可读知识库」，结果用户读到的是 `#` `**` 原始符号。
- 顶部红粉蓝渐变 banner、系统字（`-apple-system`），整体像没设计过。
- 列表每 2 秒整体 `innerHTML` 重绘，闪烁；运行中无进度反馈；空状态只有「暂无任务」。

用户要求「从零开始做 UIUX」。走 `/design-consultation` 出了 4 个方向的 GPT Image 2 提示词，用户选定**方案 3「红蓝品牌」**（红=小红书 / 蓝=B站 撞色做主角，大圆角，活泼友好）。

## 现象 / 做了什么

**1. 全新设计系统（`base.html`）**
红蓝拼色 logo + 渐变字、Plus Jakarta Sans（拉丁文，Bunny Fonts CDN，中文回落系统字）、品牌色 CSS 变量、大圆角、全局 toast、暗色代码块、响应式。移除旧渐变 banner。

**2. 首页交互优化（`index.html`）**
- 输入即识别平台（B站/小红书/未识别三态 chip）
- 状态筛选（全部/处理中/已完成/失败，点击过滤）
- **防闪烁刷新**：用 signature 门控，内容不变就不重绘（杀掉每 2 秒的闪烁）
- 运行计时（独立 1s ticker，与列表重绘解耦）、新任务高亮、空状态引导
- 卡片源链接只显示 `host+path`，去掉 `vd_source`/`xsec_token` 等超长 query，单行省略

**3. 详情页（`detail.html`）**
- **渲染 ⇄ 源码切换**：marked.js 转 HTML + DOMPurify 清洗（内容是爬来的，防 XSS）
- 渲染态**剥掉 YAML frontmatter**、面包屑、类型标签、键盘 `r`/`c`/`Esc`

**4. 浏览器自动化 QA（gstack browse，打真实 `~/transcript` 库）发现并修 4 个 bug：**

| 严重度 | 问题 | 根因 | 修复 |
|---|---|---|---|
| 中 | 详情页「渲染太大」 | 真实 md 都带 YAML frontmatter，marked 把「一段文字紧跟 `---`」当 setext H2，整块元信息（含超长 URL）渲成巨大标题 | 渲染态 `stripFrontmatter` 剥掉头部，源码态保留原文 |
| 中 | 坏的 `/jobs/{id}` 返回裸 JSON | 路由直接 `raise HTTPException` | 返回带样式的「任务不存在」页（仍 404 状态） |
| 中 | 长 URL 撑满卡片 2-3 行 | 显示完整 URL 含超长 query | 只显示 host+path，单行省略 |
| 中 | 失败页/404 页工具栏没真隐藏 | `.toolbar{display:flex}` 作者样式盖掉了 `[hidden]` 的 UA `display:none` | 加 `[hidden]{display:none!important}` |

「秒表不准」经受控实测排除——计时逻辑正确（`0:01→0:05` 增量/绝对值都对），用户看到的是**演示假数据**（seed 的 running 任务卡在那一刻不动）。额外加了防御：时间戳异常（负/超 24h，多为跨时区/时钟问题）时不显示数字而非显示错值。

## 理由

- **方案 3 而非纯工具/编辑器风**：用户选的，红蓝品牌有记忆点，和「红蓝CP」名字呼应；平台色（蓝=B站/红=小红书）顺势变成功能性标识而非纯装饰。
- **marked + DOMPurify 走 CDN**：和现有 htmx 同路子，非 Python 依赖，不破 P0「不加依赖」红线。内容是爬来的，渲染成 HTML 必须清洗防注入。
- **strip frontmatter 只在渲染态**：详情页头部已经从 DB 记录显示作者/平台/时间，frontmatter 冗余；源码态保留原文（用户想看就看）。
- **404 返回模板而非 raise**：保持 404 状态（契约测试不破），但给带样式的页面而非裸 JSON。

## 影响

| 文件/模块 | 影响 |
|---|---|
| `app/web/templates/base.html` | 整套设计系统重写；新增 `[hidden]` 修复、`.job-src` 省略样式 |
| `app/web/templates/index.html` | 平台识别、筛选、防闪烁刷新、计时、URL 缩短 |
| `app/web/templates/detail.html` | 渲染/源码切换、frontmatter 剥离、键盘快捷键、404 处理 |
| `app/web/routes.py` | `job_detail` 缺失任务返回带样式 404 页（不再 raise 裸 JSON） |
| `tests/test_web_templates.py` | 新增 21 个测试锁定上述 UI 契约（含 4 个 QA 修复的回归）；全量 264 单测通过 |
| 依赖 | 无新增 Python 依赖；前端 marked/DOMPurify/Plus Jakarta Sans 走 CDN |

## 复盘 / 经验

1. **演示数据要贴近真实**：第一版用手写、无 frontmatter 的 `sample.md` 截图自测，看着很完美，但真实 md 都带 YAML frontmatter——掩盖了 marked 把 frontmatter 渲成巨大 setext 标题的 bug。**自测数据缺了真实数据的关键特征，就测不出真实问题。** 用真实库 + 浏览器自动化才暴露。
2. **`hidden` 属性会被 `display:flex` 等作者样式静默盖掉**：UA 的 `[hidden]{display:none}` 优先级低，写了 `.toolbar{display:flex}` 后 `el.hidden=true` 视觉上不生效（JS 属性是 true，但元素照样显示）。需要显式 `[hidden]{display:none!important}`。
3. **改 `routes.py` 必须重启 uvicorn**：Jinja2 模板每请求从磁盘热重载，但 Python 路由模块只在启动时 import 一次。改了路由不重启 = 看到的还是旧逻辑（404 修复一度「没生效」就是这个）。
4. **YAML frontmatter 的 setext 陷阱**：`一行文字\n---` 被 markdown 当二级标题。任何渲染带 frontmatter 的 md 都要先剥离。
5. **worktree 里 Write 用主仓库硬编码绝对路径会写错地方**：文件落到主仓库而非 worktree，路径要基于当前 worktree 根。
