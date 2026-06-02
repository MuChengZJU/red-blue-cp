---
date: 2026-06-02
type: experience
priority: high
related: [PLAN.md, SPEC.md, REFERENCES.md]
status: active
---

# 小红书博主全量笔记：用 XHR 拦截器抓 user_posted，绕开风控

> 抓某博主全部笔记链接，别滚动 DOM（触发风控 + 虚拟滚动丢数据），注入 XHR 拦截器接住页面自己发的 `user_posted` 接口 JSON，翻页直接收割。1350 条零限流零验证码。

## 背景

需求：下载博主「ENTP老家」名为「从空空如也到借假修真：ENTP顶级之路」系列的全部笔记为 Markdown。

P0 的 `rbcp run` 只支持单条 URL，博主全量是 P1（未启动）。第一反应是用浏览器自动化滚动博主主页、从 DOM 里抓笔记卡片链接，再逐条 `rbcp run`。结果：

- 滚了 60+ 次后小红书弹**图形验证码**，主页 feed 被截断（稳定只返回最新 ~65 条系列就转问答）。
- 反复重导 cookie、换 5 种滚动策略（跳底/小步/绝对定位）都突破不了。

## 决策 / 现象 / 经验

### 1. 触发风控的根因是「滚动渲染轰炸」，不是下载

滚动找链接时，每次滚动+渲染都在打小红书服务器，几百次请求集中在几分钟内 → 被风控标记。**下载本身（`rbcp run` 单条，走 `.env` cookie）从没触发过风控。**

### 2. 正解：注入 XHR 拦截器抓 `user_posted` 接口（不抓 DOM、不自己签名）

博主主页的笔记靠分页接口加载，返回干净 JSON。做法：

1. 在已登录页面注入钩子，包住 `XMLHttpRequest` + `fetch`，把 URL 含 `user_posted` 的响应 JSON 存进 `window.__rbcpCaptured`。
2. 滚动触发翻页 —— 每滚一次 = 页面发一个 `user_posted` 请求 = 30 条笔记，钩子自动接住。
3. 读 `window.__rbcpCaptured` 导出全部 `note_id + display_title + xsec_token`。

**实测 45 页 1350 条笔记，零限流、零验证码。** 因为这是页面正常的分页请求（个位数/分钟级），不是渲染轰炸。

接口细节（参考 Spider_XHS `apis/xhs_pc_apis.py`，实测确认）：

```
主机:  edith.xiaohongshu.com   ← 注意不是 www，相对路径 fetch 会 500
一级:  GET /api/sns/web/v1/user_posted
       参数: num=30, cursor, user_id, image_formats, xsec_token, xsec_source
       翻页: cursor + has_more 循环，直到 has_more=false
评论:  GET /api/sns/web/v2/comment/page        (一级评论, cursor+has_more)
       GET /api/sns/web/v2/comment/sub/page    (二级子评论, 每条一级评论再翻)
```

### 3. 浏览器内代签可行但更麻烦，拦截器更优

- `window._webmsxyw(path, '')` 能生成 `{X-s, X-t}` 签名（MediaCrawler 就用它）。
- 但 raw `fetch` **不会自动加签**（签名不是全局 fetch 拦截器）；手动加了 X-s/X-t 仍 500，网关还要 `x-s-common`。
- 自己复刻全套签名 = 月度失效要追更的维护负担。**拦截器让页面自己签，零签名维护。**

### 4. 范围教训：别信 DOM 卡片标题，信接口数据

- DOM 卡片标题被**截断**（100+ 集都显示成「…（第一」），靠它认集数会误判。
- 接口 `display_title` 是**完整标题**（「…（第一百零一）｜…」），集数准确。
- 虚拟滚动会**卸载**划过去的卡片节点，完整列表从不同时存在于 DOM —— 这也是「直接读整页 DOM」行不通的根因。

### 5. 博主编号会乱，完整性核对按内容不按文件名

- 本系列实际是**第 1～165 集**（一开始误判从 45 集起，因为 feed 没加载到早期）。
- **第 21、30、56、91、131 集是博主跳号**（feed 里根本没有）；佐证：**第 97、130 集各重复发了两次**。这博主编号本来就乱，跳号正常，不是漏抓。
- 核对脚本坑：早期笔记标题是「ENTP␣顶级之路」（带空格），晚期是「ENTP顶级之路」（无空格）。按文件名 glob `*ENTP顶级之路*` 会漏掉空格变体 → 假阴性。**按文件内容正则匹配，别按文件名。**

### 6. 登录态持久化

`browse state save xhs` 把 cookie 存到 `.gstack/browse-states/xhs.json`（已被 `.gitignore` 第 12 行 `.gstack/` 覆盖，不进 git）。扛得住浏览器重启，不用每次重导 cookie。

## 理由

| 方案 | 取舍 |
|---|---|
| 滚动抓 DOM | ❌ 触发风控 + 虚拟滚动丢数据 + 标题截断 |
| 自己实现 x-s 签名（纯 Python / Node） | ❌ 月度失效追更，维护负担重 |
| 依赖 / 内嵌 MediaCrawler | ❌ 它是完整应用非库，含 Playwright+DB+配置，且仅限非商业用途（与本仓库 MIT 冲突） |
| **XHR 拦截器抓 user_posted** | ✅ 不抓 DOM、不碰签名、请求数从几百降到个位数、几乎不触发风控 |

接口地址/参数是事实（不受版权保护），自己写 ~50 行实现 = 参考移植，延续 P0 既有路子。

## 影响

| 文件/模块 | 影响 |
|---|---|
| PLAN.md | **建议**把 M2b 博主全量 / M2c 评论的实现从「外部 CLI（`xhs user-posts`/`xhs comments`）」改为「XHR 拦截器抓 `user_posted` / `comment/page`」。属改实现方式，需对话确认后再动 SPEC/PLAN，本文只记建议未改文档 |
| CLAUDE.md 红线 #9 | 该改向与红线「不引入 xiaohongshu-cli」**一致**（红线本就不想依赖那些 CLI） |
| 代码 | 未改。本次为一次性运营操作（手动注入 + `rbcp run` 逐条），未落地到 `app/` |

## 后续 / 复盘

- 本次产出：160 集（第 1～165 集去掉 5 个跳号）共 162 个文件，落在 `~/transcript/xhs/`。
- 待定：是否把「拦截器抓 user_posted/comment」落地为项目功能（博主全量 + 评论全量）。确认后补 SPEC/PLAN。
- 风险提醒：`x-s` 签名算法约季度更新、动态 cookie ~10 分钟刷新；单 IP 安全节流约 10–20 请求/分钟（来源见 REFERENCES）。拦截器方案因走页面自身请求，天然规避签名追更。
