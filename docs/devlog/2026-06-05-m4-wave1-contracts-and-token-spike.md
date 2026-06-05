---
date: 2026-06-05
type: experience
priority: high
related: [PLAN.md, docs/blogger-safe-batch-feature.md, docs/error-handling-audit.md]
status: active
---

# M4 波1：契约交叉核对 + token 过期信号 spike

> 波1（三流并行写计划）收尾。两个非显然结论落盘：① proxy 穿透必须扩 M4a 文件边界；② 小红书过期 token 的可靠判定信号是重定向到 `/404` + `error_code=300031`，**不是** title 空。

## 背景

M4 按 §十二（plan-eng-review 锁定）执行：先串行 M4a 打地基锁公共接缝，再 M4b ‖ M4c 并行。波1 三条流各产出详细实施计划 + 测试清单。组织者交叉核对三份计划时挖出一个接缝漏洞、并对唯一开放接缝（token 过期判定）做了实证 spike。

## 现象 / 经验

### 一、proxy 穿透穿不过 M4a 原定文件边界（已修正）

§十二 的 a3 只写"修 `model.py` 的 `trust_env`"。但 `fetch_single(..., proxy=None)` 这个锁定契约要真生效，proxy 得一路穿到下载层：

- `extract_url`（extractor.py）原本没有 proxy 参数
- fetcher.py 有 4 处裸 `requests.get`（explore 详情 / b23 短链 / B 站 API），都不接 proxy
- model.py `session.trust_env = False`（约 line 125）**主动屏蔽代理**，导致媒体/主站调用都不走

而 extractor.py + fetcher.py 原归 M4b。**结论：M4a 文件边界扩到包含 extractor.py + fetcher.py 的 proxy 穿透改动**（只加 `proxies=` 参数，不动异常处理——异常仍归 M4b）。设计：显式 `proxies=` dict 一路传，`trust_env=False` 保持以防环境变量漏代理。阶段 1 只支持 http/https 代理（socks5 需 PySocks，破"阶段1不加依赖"红线，显式拒绝）。

> 教训复用：契约"锁定"= 决策敲定且**写成别人能依赖的形式**。一个穿不到下载层的 `proxy` 参数就是没锁住。组织者在 fan out 前核对契约可达性，正是这条价值所在。

### 二、proxy 验收口径：主站走代理，CDN 媒体字节默认不走

PLAN 原写"验证 trust_env 修复后**音频走代理**"，与 §五"CDN 媒体字节**默认不走代理**"矛盾（音频流就是 CDN）。已定口径（采纳 M4a 解读）：

- **走代理**：主站调用（explore 详情、DashScope API、OSS 上传策略/提交/轮询/拉转写结果）——这才是护 IP 的点。
- **默认不走**（可配置开）：CDN 媒体字节（音频流、图片、视频）——CDN 不做 IP 风控，省代理流量。
- "trust_env 修复"的真义 = 让**该走代理的主站调用**走（修复前因 `trust_env=False` 且无 proxies，连这些都没走），而非强制音频字节走代理。

### 三、token 过期判定信号 spike（替掉"title 空"）

§十一 拍板"token 过期跳过继续"，但**怎么识别过期**三份计划打架：M4c 主张"title 空/空壳"，M4a 反对（Codex 警告会误伤真空标题/被删笔记），M4b 说"该放别处"——等于没人落地。做了 10 行 spike（`_sandbox/token-expiry-spike/probe.py`，复用 app 的 `_extract_xhs_initial_state`/`_extract_xhs_note` 保证信号与生产一致）。

用同一个真实 note_id，对比有效 token vs 无效 token：

| 信号 | 有效 token | 无效/过期 token |
|---|---|---|
| `response.url`（跟完重定向）跳 `/404` | 否 | **是** |
| `error_code=300031`（"当前笔记暂时无法浏览"）在 final_url | 无 | **有** |
| `noteDetailMap` 的 key | 真 note_id | 字面量 `'null'` |
| 解析出的 note | 真笔记（title、图齐全） | 空壳，title=None，0 图 |

**锁定信号：请求后查 `response.url`，含 `/404` 或 `error_code=300031` → token 失效。** 必须在 `_extract_xhs_note` 解析**之前**查——否则现状会捞到 `null` 键的空壳、title=None 蒙混过去（这正是 Codex 警告的坑：现状代码不抛错、靠 title 空判会误伤）。

为什么可靠：有效笔记永远以**真 note_id 为 key**落在 `noteDetailMap`、且不跳 `/404`，所以"真空标题的有效笔记"不会被误判。过期/被删/无效 token 都回 300031——对 batch 而言都是"跳过 + 提示重抓"，无需再细分。

落地分工（三方各归各位）：
- **M4a**：`AuthError(reason="token_expired")` 类在契约里（`reason` 字段保留）。
- **M4b**：在 `fetch_xiaohongshu` 请求后加 final_url 检测 → 抛 `AuthError(reason="token_expired", platform="xiaohongshu", operation="fetch_detail")`。
- **M4c**：batch 循环捕获该异常 → 记 `batch_item(status=skipped, error_message="token_expired")`、跳过继续，汇总列"需重新抓清单"；其他未知码走兜底记 failed（不崩批）。

### 四、其余波1 对齐项（机械决定，已定）

- **storage 方法名以 M4a 为准**（M4c 计划里的 `upsert_batch_item` 等改用 M4a 的 `add_batch_items`/`mark_batch_item_*`）。
- **notes.json 加 `schema_version: 1`**（§四样例原漏，§九/§十二 都要求校验；插件写、batch 校验）。
- **`detail.html` 人话翻译走前端轻量 JS 映射**（`format_error_for_user` 是 Python，前端 JS 调不到；靠 `error_message` 的 kind 前缀匹配，零 schema 改动、不越 M4a 界）。
- **`routes.py` 新增相交点**：M4b 改 `create_job`（平台早校验，audit #4）+ M4c 加导入清单路由 → 不同函数 git 能自动合，进"后合者 rebase"清单。
- **markdown.py 模板注入**（autoescape=False 未 escape `{}`）不纳入 M4b，单列技术债（属渲染安全，与错误流正交）。

## 影响

波1 完成：三份计划 + 契约交叉核对 + 唯一开放接缝实证锁死。进波2——M4a TDD（errors → storage → proxy 穿透 → pipeline）→ 合并锁接口 → M4b ‖ M4c 并行。
