---
date: 2026-06-07
type: milestone
priority: high
related: [PLAN.md, CHANGELOG.md, docs/devlog/2026-06-06-m4-ship-and-ux-iteration.md]
status: active
---

# M5a 交付 0.4.1：流式修长文超时 + 任务用量/费用统计

> 0.4.0 实测痛点（长视频清洗必超时）的根因修复 + 用户新需求（看每任务花多少 token/时间/钱）。
> 单流 TDD，一个 PR（#35），无 worktree 并行——5 条任务几乎全落在 `service/model.py`，接缝耦合，硬并行负价值。

## 范围调整（开工前）

原 M5a 含「LLM/VLM provider env 化（开 Gemini 入口）」。用户明确表示**暂无换模型需求**，
反而提出新需求：**每任务的 ASR/VLM 用量、耗时、费用统计**。调整：

- provider env 化 → 移入 PLAN 待办区（等真实需求触发）；流式改造顺手把 SSE 解析写泛化，留门不做配置项
- 新增 P1h（PRD）：任务用量/费用统计

## Spike 先行（开工前 10 分钟，两个 API 事实实测）

按「锁定前对具体调用做 10 行 spike」的规矩，实测了两个文档说了不算的问题
（脚本在 `_sandbox/spike_usage/`）：

1. **DashScope 流式 usage 回执**：传 `stream_options: {"include_usage": true}` 后，
   最后一个 SSE 块 `choices=[]` 且带完整 usage（prompt/completion tokens）——与 OpenAI 标准一致 ✅
2. **ASR 计费秒数从哪拿**：用 `say` 合成 10 秒真语音走完整转写链路，发现 poll 响应
   **顶层** `usage: {"duration": 10}`（秒，计费单位）——现有代码只读了旁边的 `output`，
   补读一个字段就行，零额外请求 ✅

两个事实直接锁死了实现方案，没有返工。

## 交付内容

**流式修超时**（0.4.0「短视频成功、长视频失败」的根因）：
- `llm_clean`/`vlm` 改流式 SSE（`_parse_sse_stream` 纯函数，不引 SDK）。
  原非流式 + 180s read 超时 vs 长文 ~300s 生成 = 必撞；重试 3 次放大等待。
  流式后 read 超时只覆盖 token 间隔（600s 纯兜底）。
- 建连可重试（`_retry_network`），流中断不重试（整段重跑放大等待），响应 finally 关闭。

**用量统计（P1h）**：
- `provider.usage_events` 账本（每任务新建 provider，无跨任务串账）→
  `pricing.summarize_usage()` 按官方目录价补 `cost_yuan` →
  随 `mark_done` 落 `jobs.usage`（JSON 列，旧库 PRAGMA 检查 + ALTER 原地迁移）。
- WebUI：详情页「用量与费用」折叠账单；列表页累计估算；`GET /api/stats`。
- 单价常量收口 `service/pricing.py`，调价改一处；不认识的模型 cost 记 None 不瞎编。
- 口径：目录价估算，不扣免费额度（ASR 每月送 10 小时）——页面数 ≥ 实际账单。

## 真用才现形（又一例）

真链路实测（真实 B 站视频 → 账单落库 → 浏览器截图验证）发现：累计费用 `toFixed(2)`
把 ¥0.002 显示成「累计估算 ¥0.00」——单测全绿，截图一看就穿帮。小额改 4 位小数。

## Codex review 修 3 项

1. **重试残留旧账单**（P2）：`reset_for_retry` 清了 md_path 没清 usage，重试期间 stats 继续报上一轮的钱 → 顺带置 NULL
2. **流式响应不关闭**（P2，最值钱）：`[DONE]` 即停不读到 EOF，不 `close()` 每次调用占住一个连接，常驻服务慢性漏 → finally close
3. **详情页跨重试残留账单**（P3）：页面开着不动，任务重试后用量面板还显示上一轮 → 非 done 状态隐藏

三项都是「单测测不到、长期运行/特定操作序列才暴露」的形态——独立 review 当合并门继续有效。

## 数字

406 → 449 测试，全程 TDD；PR#35 + 文档 PR#36；tag v0.4.1 自动发 PyPI；GitHub Release 已发。

## 影响 / 下一步

M5b（WebUI v2）：主页单条/批量整合、批次进任务列表、导入重做、去重检测。见 PLAN M5b（含验收 Eval）。
小技术债：`rbcp serve` 无 `--port` 参数（写死 8000），M5b 顺手补。
