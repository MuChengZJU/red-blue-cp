---
date: 2026-06-05
type: experience
priority: high
related: [docs/blogger-safe-batch-feature.md, docs/error-handling-audit.md]
status: active
---

# Codex 独立 review：博主安全批量方案 + 异常契约 + 并行切割

> 用 Codex（gpt-5.5, read-only, high effort）独立 review 了「博主安全批量」方案、异常契约草案、错误审计 Top5、以及"先锁契约就能两条流并行"的判断。Codex 纠正了几处乐观判断，**全部采纳**。

## Codex 挖出的硬货

### 1. 代理覆盖不全（实锤，Top1 风险）
`model.py:125` `session.trust_env = False`——**视频/ASR 的音频下载会绕过环境变量代理，用本机 IP 直连**。所以"走代理 = 安全"对视频笔记不成立（图文走代理 OK，视频音频下载漏了）。固定共享出口 IP（多人共用一个出口）场景下尤其是洞。**修代理覆盖是地基的一部分。**

### 2. 并行相交面被低估（推翻"先锁契约即可并行"的乐观）
- 批量流"不碰 service"不成立：`_fetch_single` 穿过 `extract_url → fetcher/model/markdown`，批量错误 UX 必然依赖 service 异常契约。
- **`storage.py` 是隐藏相交点**：收信箱、批次任务、断点续传都要新持久化，错误流重试也动 `retry_count`；现仅单表 `jobs`、无迁移机制。
- `cli.py` / `web/routes.py` 两条流都要改、冲突概率高。
- → 结论：硬拆两条并行流收益不大、合并冲突高。**先串行打厚地基（公共接缝）再并行。**

### 3. 异常契约改进（少类 + 结构化字段）
- `NetworkError` 太粗、`ApiError(status+body)` 不够（B站 code≠0 / DashScope FAILED / missing task_id 不是简单 HTTP status）。
- 缺 `ParseError`（INITIAL_STATE 缺失/note 找不到——页面结构变/空壳/风控）、`ConfigError`（key 空/代理非法/cookie 不可读）。
- `TokenExpiredError` 别只靠"title 空"判（误伤真空标题）；并入 `AuthError`。
- 建议最小集：`RbcpError / UnsupportedUrlError / ConfigError / NetworkError / ApiError / RiskControlError / AuthError / ParseError` + 结构化字段 `kind/platform/operation/retryable/user_message/debug_context`。别过早建大类树。

### 4. 阶段 1 降范围
只做「导出 JSON + CLI batch + schema 校验（加 `schema_version`）+ 单 URL 代理 + 单机断点」。**收信箱 / 一键转发 / Clash 轮替后置，别和异常重构同轮硬并。**

### 5. 方案坑（被低估的）
- `notes.json` 要 `schema_version`，否则插件字段变动 batch 静默坏。
- `complete=true` 可信度：用户停止滚动 ≠ 完整，必须基于 `has_more=false`。
- token 过期非唯一失败形态（还有 token/IP 不一致、验证页、空壳、媒体 URL 过期、DashScope 拉远端失败）。
- 断点续传粒度要先定义（note_id 成功即跳？Markdown 已存算成功？中途失败保留部分？）。
- 代理验证不能只看配置存在，要出口探测 + 实际请求路径确认生效。
- CDN 不走代理与"安全批量"有冲突边界（媒体/ASR 下载仍可能暴露本机 IP）。
- 一键转发"零 token + 人工确认"防不了本机网页刷爆收信箱，要限 CORS origin / body size / 批次数 / 只监听 localhost / 去重。
- MV3 `world:MAIN` hook 不是一次验证就稳定，插件端要持久化原始响应样本和失败诊断。

### Codex 的 Top 3 风险
1. 代理没覆盖真实高风险请求（视频/ASR 绕过代理）。
2. 批量流过早依赖未结构化的 service 异常，最后只能字符串匹配做错误 UX。
3. Web 收信箱/批次需要新存储模型，和现有 job/retry 改造合并冲突 + 拖慢。

## 采纳决定

**全采纳。** 修正执行路线：
- **先串行锁公共地基**：① `service/errors.py`（最小集 + 结构化字段）+ `format_error_for_user()` ② 把 `_fetch_single` 抽成 service 可复用函数 ③ 修代理覆盖（`trust_env`，让媒体下载也能走代理）④ 定批量/收信箱的 storage 模型 + 迁移。
- **再并行**：地基锁定后，错误流（填充各 service 异常+日志）‖ 博主批量流（阶段 1 CLI batch）。零散 UX（detail 展示、平台校验、markdown 模板）小范围并行。
- **阶段 1 降范围**：只 CLI batch（导出 JSON + schema 校验 + 单 URL 代理 + 单机断点）。收信箱/一键转发/Clash 轮替 → 阶段 2。
