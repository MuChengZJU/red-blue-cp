---
date: 2026-06-05
type: experience
priority: high
related: [PLAN.md, SPEC.md, docs/devlog/2026-06-02-xhs-blogger-full-fetch-via-interceptor.md]
status: active
---

# 小红书博主批量：浏览器插件抓列表 + CLI 下载转录，全链路技术验证

> 探索结论：「插件抓链接列表 → CLI 走代理换详情(需 token 不需 cookie) → CDN 下字节 → VLM 转录」整条链路实测无盲区。所有实验代码隔离在 `_sandbox/`（`exp/blogger-extension-spike` 分支），未进 `app/`。

## 背景与架构

P1 博主全量的获取方式，除已记录的 pydoll 拦截器外，这次探索另一条路——**浏览器扩展（MV3）抓列表**。明确为两环节：

1. **抓链接列表** → 浏览器插件（带登录态，旁路读取页面自己发的接口）
2. **下载 + 转录** → CLI/GUI（rbcp），用户在本地跑

## 实测发现（均有数据）

### 1. MV3 main-world hook 能完整抓博主列表
- `world:"MAIN"` + `run_at:"document_start"` 的内容脚本，赶在页面自己用 `fetch`/`XHR` 之前包住它，接住翻页时的 `user_posted` 响应。
- 某博主一次滚动**完整抓到全部笔记**（翻到 `has_more:false`），**带 xsec_token 比例 100%**，慢滚零验证码。
- 页面自身有"滚到底自动翻页"机制，插件跟着接返回即可，不必自写翻页。
- 与 `2026-06-02` 那篇拦截器同理，只是换成扩展形态；机制已被两篇实测验证。

### 2. 换详情：需 xsec_token（门票），不需 cookie
- `fetch_xiaohongshu` 不带 cookie，从 explore 页 HTML 抠 `__INITIAL_STATE__`。
- 实测：**带 token → 拿到标题+图片**；**不带 token → 进去了但内容是空壳（title 空、imgs=0）**。小红书把 xsec_token 做成访问详情的强制门票（防纯 note_id 遍历），公开笔记也要。
- 关键认知：**xsec_token 是"内容门票"不是"用户身份"**。它由列表接口/分享下发、会过期，且**插件抓列表时每条已一并拿到、存在导出 JSON 里**。所以下载时从 JSON 取 token 拼 URL 即可，**全程无需登录/cookie**。
- token 来源不限：`pc_feed`（列表）和 `pc_share`（分享）都能换详情；`explore/` 和 `discovery/item/` 两种 URL 格式 rbcp 都吃。

### 3. 防 IP：下载是 IP 风险非账号风险，海外代理可行
- 单篇下载不带 cookie → 触发的是 **IP 级限流，不连累账号**。
- requests 默认读 `HTTPS_PROXY` 环境变量，**rbcp 零改码即可走代理**。
- 实测海外机房代理（单节点）：慢速 5 条全过；**并发 30 条 / 8 worker，1.5s 全过零封**。说明小红书对"无 cookie 抓 explore 页"本身就宽松。
- **固定共享出口 IP（如校园网）必须走代理**——被标记会连累整个出口且固定 IP 洗不掉。这是"要不要代理"的决定性约束。

### 4. CDN 下字节：高并发宽松
- 用换详情拿到的图片直链，**12 并发下 36 张图，2.6s / 11.3MB，零失败**。CDN 是分发流量的，宽松、且不卡 token（直链自带 CDN 签名）。

### 5. 端到端
- 1 条真完整跑通：走代理换详情 → 下图 → `qwen3-vl-flash` 识别 → 出 Markdown，frontmatter 齐、`status: vision`、正文是真实 OCR 内容。

## 关键结论

- **技术全链路无盲区。** 插件抓链接 → 代理换详情 → CDN 下字节 → VLM 转录，每段都有实测数据。
- **IP 池/国内住宅代理对"自用规模"非必需**，海外代理够；多节点（Clash `load-balance` / 直接跑 mihomo CLI 内核 + `external-controller`）是"上规模/无人值守/做服务"才需要。
- **做生意的最优 IP 策略不是建 IP 池，而是把抓取放客户端**——每个用户用自己住宅 IP+会话，风险与成本分散，且最像真人。中心化 IP 池把法律+风控+成本全堆自己头上。

## 与红线 #9 的关系

红线 #9 锁定 P1 博主全量用 **pydoll**。浏览器扩展是**另一条技术路线**，已验通，但**是否替代/并存 pydoll 属于范围决策，未定**，需正式立项（改 PRD/SPEC/PLAN）后才动 `app/`。本文只记技术事实。

## 约束 / 待测

- **xsec_token 会过期**：列表与下载别隔太久，过期需让插件重抓列表。
- 批量并发的**大规模累积拐点**（几千条/天、反复跑）未测。
- 媒体字节走代理会吃代理流量；CDN 那步是否可不走代理（CDN 不做 IP 风控）值得验证以省流量。

## 隔离

所有实验代码在 `_sandbox/xhs-capture-spike/`（插件 spike）和 `_sandbox/batch-download-test/`（批量下载 driver），均在 `exp/blogger-extension-spike` 分支，未进 `app/`、未改 `main`。
