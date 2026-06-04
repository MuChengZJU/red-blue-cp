# XHS user_posted 抓取 · 浏览器插件可行性 spike

> 一次性技术验证，不是功能代码。验证完整个目录可删。
>
> **结果（2026-06-04）：PASS。** MV3 `world:"MAIN"`+`document_start` 钩子拦到了
> 页面发的 `user_posted` XHR，连续 3 页各 30 条、`has_more:true`、`cursor` 翻页正常，
> 慢滚未触发验证码。结构路径 `data.data.notes` 对得上。
> 待确认：每条笔记的 `xsec_token` 是否在（样本需展开核对）。
> 留意：日志出现过 `loginStatusInterceptor` 的"薯队长遇到点小麻烦"风控味提示
> （在登录态检查接口，非 user_posted），印证 devlog 的"慢滚"纪律。

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
