---
date: 2026-06-06
type: milestone
priority: high
related: [PLAN.md, CHANGELOG.md, docs/devlog/2026-06-05-m4-wave1-contracts-and-token-spike.md]
status: active
---

# M4 交付 0.4.0 + 用户实测驱动的一轮 UX 迭代

> 博主安全批量 + 错误地基（M4）合并，发 0.4.0。随后用户在真实主机上用，连续暴露一批"测试测不到、真用才现形"的问题，多 agent 并行修掉。记录交付内容、迭代方法、几个真 bug 的根因。

## 交付内容（0.4.0）

M4 全部合并：MV3 插件抓小红书清单（popup 手动导出/复制）+ `rbcp batch` 走代理批量（断点续传/token 跳过/出口探测）+ WebUI `/batches` 导入页 + 结构化错误体系（`service/errors.py` + `format_error_for_user`）+ service 层日志 + 代理穿透。详见 CHANGELOG 0.4.0。

执行方式：波1 并行写计划 + token 过期 spike → 波2 串行 M4a 锁契约 → M4b‖M4c 并行 → 每条流过 Codex review。见 [波1 契约+spike](2026-06-05-m4-wave1-contracts-and-token-spike.md)。

## 迭代方法：能并行的派 agent，耦合的自己做

用户实测后一次性给一批反馈，明确要"并行处理"。判断：**独立文件的派后台 agent，耦合的自己串**（硬并行耦合代码是负价值）。

- **派了 agent（互不相交）**：插件 popup UI、插件剪贴板复制、DashScope 超时重试、URL CJK 兼容提取、模型/Gemini 调研。
- **自己做（耦合 routes/storage/templates/errors）**：URL 清理接入、重试原地、traceback 脱敏、输入框放行、网络文案。
- **每条码流过 Codex review**：抓到多个真 bug（见下）。
- 教训复用：后台长跑 agent 遇 ECONNRESET 会半途死（一次 M4c agent 只留个 RED 测试就断），salvage 测试 + 主会话接手比重派稳；终态产物让 agent 边做边 commit。

## 测试测不到、真用才现形的真 bug（最值得记）

这一轮最有价值的是：**单测全绿，但真实部署一用就崩/泄漏**。再次印证"完工=用户视角真链路跑得通"。

1. **分享文案粘贴报错——根因在前端不在后端**：后端 `clean_url` 早就能从「【标题】… https://…」抽干净 URL（拿 4 条真实分享串实测全过），但 WebUI 单篇输入框是 `<input type="url">`，浏览器嫌"不是合法 URL"在**提交前**就拦下了。改 `type="text"` 才放行。→ 端到端要测**真实输入路径**，不能只测后端函数。

2. **Python traceback 泄漏服务器路径/用户名**：失败任务把完整 traceback（含 `/home/<用户名>/...`、`.venv` 路径、行号）存进 `log_excerpt` 直接显示。作为产品这是隐私/安全隐患。改：`log_excerpt` 存**脱敏异常链摘要**（`类型: 信息`），完整 traceback 只进服务器日志。

3. **长文 llm_clean 超时——非流式 + 180s read 超时的设计缺陷**（调研定位）：50 分钟视频转录 ≈ 1-2 万 token，qwen-plus **非流式**生成 ≈ 300s，必撞 `timeout=(10,180)` 的 read 超时；`_retry_network` 还当网络抖动重试 3 次放大等待。短视频 <180s 所以"有的成功有的失败"。**不是网络、不是额度**（额度会返回 HTTP 429=ApiError，不是 timeout）。正解=流式 `stream=True`（read 超时只需覆盖 token 间隔）。→ 留作下一轮。

## Provider 调研结论

LLM/VLM 已走 OpenAI 兼容端点，接 Gemini（免费额度大，2.5 Flash-Lite 1000 RPD）只需 `base_url+model+api_key` 做成 `.env` 可配，不引 SDK（守红线）。坑：VLM 图片走 base64 data URL（复用 tempfile 兜底）、SSE/错误体泛化。**ASR 切不过去**——Gemini OpenAI 兼容层不支持音频转写 + 无结构化说话人分离，paraformer 短期保留。

## 影响 / 下一步

0.4.0 发布。下一轮（见 PLAN M5）：流式修超时 + LLM/VLM provider env 化（开 Gemini 入口）；WebUI v2（单条/批量整合 + 批次进任务列表 + 去重）。中途取消评估后暂不做（去重覆盖其动机）。
