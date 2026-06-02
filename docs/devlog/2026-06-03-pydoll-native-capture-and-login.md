---
date: 2026-06-03
type: experience
priority: high
related: [SPEC.md, PLAN.md, docs/devlog/2026-06-02-blogger-full-and-comments-design.md]
status: active
---

# Phase 2 实测复盘：pydoll 原生捕获 + 扫码登录的两个坑

> 博主全量/评论的浏览器壳（pydoll）从"能编译、单测全绿"到"真链路跑通"，中间踩了两个只有真跑才暴露的坑：① JS 注入拦截器在 pydoll 里抓不到接口，得改原生网络捕获；② 扫码登录用 web_session 判断"登录成功"是错的（游客也有）。两个都验证了 CLAUDE.md「里程碑必须真链路实测」。

## 背景

M2b/M2c 的纯函数解析层 + CLI/路由接线先用并行 SubAgent + mock 做完了（单测全绿）。轮到浏览器壳（`discover.py` 的 `discover_user_posts`/`discover_comments`/`login`）真连小红书时，连环踩坑。

## 坑一：pydoll 里 JS 注入拦截器抓不到接口（抓 0）

**现象**：壳里注入 XHR/fetch 拦截器（上个会话用 gstack browse 实测可行的那套），滚动翻页后捕获到 **0** 个 `user_posted`。但页面标题、笔记 DOM 都正常加载，不是没登录、不是风控。

**定位**：用 pydoll 原生 `get_network_logs(filter="user_posted")` 一看，**8 个请求确实发出去了**——请求在发，只是我的 JS 拦截器没钩到。

**根因**：pydoll 里页面的应用脚本**早在我注入拦截器之前就抓走了原始 `fetch`/`XMLHttpRequest` 引用**（很多 SPA 在模块初始化时就缓存 fetch）。我后注入的覆盖版本被绕过，页面用的还是它自己缓存的原始 fetch。gstack browse 当时能成，是因为它的注入时机在页面脚本之前（`addScriptToEvaluateOnNewDocument` 一类）。

**解法**：弃用 JS 注入，改 **pydoll 原生网络捕获**：
- `await tab.enable_network_events()`（导航前开）
- 滚动后 `get_network_logs(filter=...)` 拿请求事件（含 requestId 和 **URL**）
- `get_network_response_body(request_id)` 取响应体
- 取不到 body 的（preflight/还没 ready）跳过，按 requestId 去重累积
- 楼中楼的 `root_comment_id` **直接从请求事件的 URL 取**，比 JS 拦截器还干净

**实测**：清单抓 90 笔记（真标题/token/点赞），评论抓到含楼中楼并正确嵌套渲染。

**教训**：浏览器自动化抓接口，**别默认 JS 注入能钩到页面请求**——注入时机决定成败。用库的原生网络事件（CDP `Network.*`）更稳，且能拿到请求 URL。

## 坑二：扫码登录用 web_session 判断"登录成功"是错的

**现象**：`rbcp login` 弹出浏览器后**几秒就自己关了**，用户根本没机会扫码；存下的 cookie 拿去抓取 0 条。

**根因**：登录检测逻辑是"轮询到出现名为 `web_session` 的 cookie 就算登录成功"。但**小红书给未登录游客也发 `web_session`**，页面一加载就有，于是第一次轮询就误判"成功"、关窗走人，存的是游客 cookie。

**解法**：**不自动猜**。交互式登录就老老实实等用户操作完——扫完码、回终端**按回车**再读 cookie（`asyncio.to_thread(input, ...)`，不阻塞事件循环）。

**教训**：判断"用户完成了某个交互"，别用"出现某个看似相关的信号"来猜，尤其当那个信号在未完成状态下也存在。交互式流程让用户显式确认最可靠。

## 顺带做的两件事

1. **请求计数/频率日志**（账号保护）：每次抓取收尾打一条 summary——接口请求次数 / 滚动次数 / 耗时 / 估算请求频率。实测清单 ~7-14 请求·分钟⁻¹、评论 ~4 请求·分钟⁻¹，温和。
2. **cookie 三来源 + `rbcp login`**：生产读 `.env` 的 `XHS_COOKIE`；也支持 `RBCP_XHS_COOKIE_FILE` 指向 cookie JSON；都没有就回退默认文件 `~/.config/rbcp/xhs_cookies.json`（`rbcp login` 扫码后存这）。最终用户拿 cookie 的正路是 `rbcp login`（不依赖任何外部工具），不是 gstack（那是开发期捷径）。

## 影响

| 文件/模块 | 影响 |
|---|---|
| `app/service/discover.py` | 抓取改 pydoll 原生捕获；加 `login_and_save_cookies`、cookie 三来源、频率日志、风控页检测 |
| `app/cli.py` | 加 `login`/`list`/`fetch` 命令 |
| PLAN.md | M2b/M2c 标完成 |
| `.env.example` | 补 cookie 两种来源 + 媒体目录 + discover 调参 |

## 后续 / 复盘

- 楼中楼在 ENTP老家 的笔记上没数据（评论太少），靠用户给的一条热门笔记才真验到——**找对测试数据本身是成本**，真链路实测要预备"能触发目标路径"的样本。
- 全量 1350 笔记的完整 `complete=true` 路径没真跑（账号保护 + 时间），但 `has_more=false` 收尾逻辑清晰、限页路径已验证。
