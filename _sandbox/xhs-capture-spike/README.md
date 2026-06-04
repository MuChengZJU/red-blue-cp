# XHS user_posted 抓取 · 浏览器插件可行性 spike

> 一次性技术验证，不是功能代码。验证完整个目录可删。
>
> **结果（2026-06-04）：PASS（两个博主实测）。** MV3 `world:"MAIN"`+`document_start`
> 钩子拦到页面发的 `user_posted` XHR。第二个博主**完整跑到 `has_more:false`**（端到端
> 抓完整个博主，每页 30 条、cursor 翻页正常、慢滚无验证码）。结构路径 `data.data.notes` 对。
> 页面自身有"滚到底自动翻页"机制（`getApiSnsWebV1UserPosted`→`fetchNotes`→`onListEnd` debounced），
> 插件跟着接返回即可，不必自写翻页。
> 账号/目标状态是变量：第一个博主页（账号已被软限流，封面图都加载不出）出现过
> `loginStatusInterceptor` 的"薯队长遇到点小麻烦"，只翻 3 页；第二个干净账号跑到底。
> → 守 devlog 纪律：慢滚 + 别用已被盯上的号。
>
> **端到端闭环（2026-06-04，累计模式）：** 某博主一次滚动完整抓 **326 条**
> （`has_more:false`），**带 xsec_token 326/326**，类型 normal 322 + video 4，
> 自动导出 `xhs-notes-326.json`。每条 `{note_id, title, type, xsec_token, url}`，
> url 形如 `https://www.xiaohongshu.com/explore/{id}?xsec_token=...&xsec_source=pc_user`，
> 即 rbcp 单篇 fetch 可直接消费的格式。整条链路（插件抓全表→拼可用 URL→落 JSON→喂 rbcp）实测通。

## 验什么

博主全量批量如果走浏览器插件，核心机制是：插件注入一段"主世界"脚本，
在小红书页面自己用 `fetch`/`XHR` 之前包住它，接住博主主页翻页时发出的
`user_posted` 分页响应（每页 ~30 条：note_id + 标题 + xsec_token）。

这一招在 `docs/devlog/2026-06-02-xhs-blogger-full-fetch-via-interceptor.md`
里已用注入式拦截器实测过（1350 条零验证码）。本 spike 只验**换成 MV3 插件
形态后，`world:"MAIN"` + `document_start` 注入是否同样拦得到**——这是
"插件 vs pydoll" 决策唯一没被验证过的技术点。

## 怎么跑（你自己在登录小红书的 Chrome 里跑）

1. Chrome 打开 `chrome://extensions`，右上角开「开发者模式」。
2. 点「加载已解压的扩展程序」，选本目录 `_sandbox/xhs-capture-spike/`。
3. 打开任意小红书博主主页（你已登录的状态）。
4. F12 打开 Console，向下手动滚动几屏。

## 怎么判定

- Console 出现 `[SPIKE user_posted] ... 命中 ... 笔记数: N` → **锁住**。
  插件能拿到列表，路线可行，可以去做完整插件。顺便看 `样本` 里
  `has_xsec` 是否为 true、`笔记字段未命中` 有没有出现，把返回结构契约也确认了。
- 滚动有新笔记加载、但 Console 一条 `[SPIKE]` 命中都没有 → **退回 pydoll**。
  说明小红书改了传输或防了 hook。

## 纪律（来自 devlog 教训）

触发风控的是"滚动渲染轰炸"，不是抓取本身。**手动滚、慢慢滚**。
别为了快写自动猛滚——那才会弹验证码。

## 边界

- 插件只负责"在用户登录态里抓列表"这一步（有风险、必须在浏览器里做的部分）。
- 真正的转录（ASR/VLM 烧 API）归 rbcp CLI，不在插件里。
- `xsec_token` 一次性会过期，抓完尽快交给 rbcp 下，别隔几天。
