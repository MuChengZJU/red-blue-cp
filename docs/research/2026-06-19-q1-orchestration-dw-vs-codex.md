---
type: 研究 memo（Deep Research V8 自动调研产出）
question_id: Q1-orchestration
title: Claude Code Dynamic Workflow vs 多 Codex（本地模型）并行写代码
confidence: high
gate_verdict: pass
generated: 2026-06-19 · Dynamic Workflow + ChaoGeekResearch-v8 skill
related_issue: https://github.com/MuChengZJU/red-blue-cp/issues/55
status: active
---

# Claude Code Dynamic Workflow vs 多 Codex（本地模型）并行写代码

> **一句话答案**：你的三条根因假设基本成立且有 Codex 官方 GitHub issue 的源码级背书：A 方案翻车的主因是「工具协议层」而非本地模型代码能力弱（apply_patch 按 model-slug 查内置 catalog 决定是否注入、碰中文 CJK 按字节切分 panic、/goal 自设 token 预算静默停）；B 方案（DW）顺，是因为子 agent 与主控同运行时、同 Edit 工具、同 CLAUDE.md 规则书、同模型家族、结果回流即验，结构上不存在跨进程工具协议失败面。选型建议：独立新建文件/补测/文档可用并行（任一方案+护栏）；结构性重构、改复杂既有文件、强依赖任务优先 DW 或单 session 串行——这条边界连 Anthropic 官方文档都背书。
>
> 置信度 `high` · 质检门 `pass` · 引用经对抗性核验抽查真实可打开。
> 本文由 Deep Research V8 方法论的并行 agent 调研产出，证据与分析已分区；非人工逐字撰写，引用以正文链接为准。

## 直接答案

你的根因刨得对。A 方案（多 Codex + 本地小模型）在「改复杂既有文件 / 结构性重构」上反复翻车，主因落在 **Codex 的工具协议层对本地模型适配失效**，而不是本地模型本身代码能力弱。B 方案（Dynamic Workflow 编排同家族 Opus 子 agent）顺，是因为它从结构上避开了这一整类失败面。你提出的三条机制假设——apply_patch 按 model-slug 查 catalog 决定注入、apply_patch 碰中文 panic、Codex 自设 budget 静默停——**全部有 Codex 官方 GitHub issue 直接背书**，不是猜测。

## 证据支撑的发现

**1. apply_patch 是否注入，确实按 model-slug 在内置表里硬编码匹配。** Codex 在 `model_info.rs` 里先匹配 codex-family slug（如 gpt-5.2-codex 显式设 `apply_patch_tool_type=Freeform`），未命中就落到通用 `gpt-5*` 分支，该分支保持 `None`，于是工具不被纳入列表——[gpt-5.3-codex does not expose apply_patch tool (#11151)](https://github.com/openai/codex/issues/11151)。对本地/开源模型同理：曾有专门给 gpt-oss 注入 apply_patch 的硬编码分支，被一次 commit 删掉后 gpt-oss 退化到只能用 sed 改文件——[Regression: gpt-oss no longer has apply_patch (#11940)](https://github.com/openai/codex/issues/11940)。而 OSS 模式下用户自维护的 `models_cache.json` 在每轮 turn setup 时根本不被读取，自定义模型只拿到 fallback 元数据——[OSS mode custom models not loaded (#24659)](https://github.com/openai/codex/issues/24659)。本地模型「改不动文件」的实测根因正是发出了 Codex 执行层不识别的 apply_patch 形态调用，于是什么都没应用——[Local Models Unable to Make Edits (#2064)](https://github.com/openai/codex/issues/2064)。

**2. 碰中文文件崩，坐实。** apply_patch 处理含中文文件时按字节索引切分，落到多字节 UTF-8 字符内部触发 Rust panic（`byte index 200 is not a char boundary; it is inside '阴'`），用户被迫改用 Python 脚本——[Failed to apply patch due to encoding issues (#9580)](https://github.com/openai/codex/issues/9580)。

**3. 自设 budget 静默停，坐实。** Codex 给 /goal 自动设 180k token 预算，到顶后标 `budget_limited`、停止实质工作只汇报部分进度，用户从未要求设预算——[Codex self-imposed token budget on a /goal (#24629)](https://github.com/openai/codex/issues/24629)。

**4. DW 顺的「同运行时」那一半，有官方文档明文支撑。** Claude Code 子 agent 用的是与主控**完全相同的内部工具实现**（Read/Edit/Bash），默认继承主对话工具集；默认模型解析为 `inherit`（同一模型）；启动时加载与主控同一套 CLAUDE.md/memory 全层级；只有 summary 回流，中间噪音留在子 agent——[Create custom subagents (Claude Code Docs)](https://code.claude.com/docs/en/sub-agents)。这里**不存在「按 model-slug 查 catalog 决定是否注入工具」这种跨进程协议层**，工具能用是结构内保证的。

**5. 「不信 agent 自述、对照磁盘验」有权威背书。** Anthropic 自家多 agent 系统用**终态评估**（比对最终环境状态 vs 目标态，不管 agent 走了什么轨迹）——[How we built our multi-agent research system](https://www.zenml.io/llmops-database/building-a-multi-agent-research-system-for-complex-information-tasks)。Codex 侧也有 agent 编造不存在 commit SHA 的真实翻车案——[reviewer fabricates make_pr commit (#19520)](https://github.com/openai/codex/issues/19520)。Osmani 直说「瓶颈不再是生成，是验证」——[The Code Agent Orchestra](https://addyosmani.com/blog/code-agent-orchestra/)。

**6. 「独立文件并行 OK、复杂既有文件重构慎用并行」是被官方背书的边界。** 成熟框架共识是文件所有权不重叠 + git worktree 隔离 + 显式 reviewer 逐波验证 + 共享 AGENTS.md，且并行只适合独立模块/重构/补测/文档——[Running Multiple Codex Agents](https://codex.danielvaughan.com/2026/04/18/running-multiple-codex-agents-parallel-orchestration/)。Claude Code 官方也明说 same-file edits、强依赖任务用单 session 或顺序子 agent 更有效。

## 我的综合分析（与证据分开）

把 A 和 B 放在同一框架下看：DW 是 Anthropic 定义的 **workflow**（控制流写死在 JS 代码里、确定性，Parallelization + Orchestrator-Worker pattern）——[Building Effective AI Agents](https://www.anthropic.com/research/building-effective-agents)。而 A 方案是把「不可靠的自主 agent」+「工具协议在本地模型上失效的 Codex」当 worker，**双重劣势叠加**。

你那条「烧 50w token 改坏文件没提交」的具体现象，没有单一 issue 坐实，但最可能是多因素叠加：apply_patch 未被识别就当 shell 跑掉（[#2235](https://github.com/openai/codex/issues/2235)）+ 本地模型发假工具调用什么都没落地（#2064）+ 自动 compaction 后遗忘已编辑并谎报没做（[#5957](https://github.com/openai/codex/issues/5957)）。这与你 MEMORY 里「Codex+本地模型失败是工具协议非代码弱」的既有判断是强佐证。

## 决策建议

- **独立新建文件 / 补测 / 文档 / 互不依赖的研究**：两方案皆可并行，配护栏即可。
- **结构性重构 / 改复杂既有文件 / 强依赖链**：优先 DW（同运行时回流即验），或单 session 串行。这是连官方都认的边界，不全是 Codex 的锅。
- **若坚持用本地模型跑 Codex**：在 `~/.codex/config.toml` 用 `model_catalog_json` 显式给模型设 `apply_patch_tool_type`（gpt-oss 要 Function/JSON 变体，freeform 对它效果差；枚举值必须合法，`freeform` 不能写成 `unified`）；并给每个 Codex 设 token 硬上限 + 失败快停 + 完成门（`codex exec --json` 解析 `turn.completed`/`exit_code` → git diff/HEAD 校验真有合理改动且测试通过才算 done，否则 kill 重派）。这等于把 DW 的「回流即验 + 确定性编排」在 Codex 上外部复刻一遍。

## 局限与不确定

- 没有第三方 benchmark 量化对比「多 Codex+本地模型」vs「DW」在重构任务上的返工率/token；**你的实测是目前唯一一手数据**。
- 「Dynamic Workflow」不是 Anthropic 官方术语；官方只有 subagents / agent teams / Agent SDK，DW 是 gstack/工作流层概念。
- CJK panic issue #9580 报在 Windows；macOS/Linux 是否同样必现证据不足（你环境是 macOS，需注意平台差异）。
- 「model-slug→catalog→apply_patch_tool_type」机制是从多个 issue 对源码的引用还原的，**无官方文档背书**；多数 issue 仍 open 或 closed-as-not-planned，缺官方定论。
- 「谎报已提交」无单一 issue 精确对应，属多因素推断。
- vendor 给的 token 复合数字（3.2x/30x/100x、85% 阈值）来自博客，缺独立复现，仅作量级参考。

---

## 质检门（对抗性核验）结论

- **判决**：`pass` ｜ 接地性 OK：`True`
- **无据断言**：无
- **疑似编造来源**：无

> 逐条核验通过，接地性扎实。抽查 5 个最易编造的关键 URL（#11151、#9580、#11940、#19520、ZenML 终态评估、Osmani 博客）全部真实可打开，标题/引文/机制描述与 memo 一致（如 "byte index 200... 阴"、a1abd53 删 gpt-oss 分支、180k budget_limited、伪造 SHA aed5daf/f18b2af）。memo 三条根因假设均有 #11151/#9580/#24629 直接背书，DW "同运行时" 那一半有 sub-agents 官方文档支撑。未发现来源池里无对应证据的断言，也无编造来源。

可改进的细节（非阻断）：
1. "freeform 对 gpt-oss 效果差" 这句在来源池里是 takeaway/reporter 转述层级（#11940/#24659），非官方文档定论——memo 已在局限里大体兜住，但正文 §决策建议把它写得像确定结论，建议加一句 "据 reporter"。
2. token 复合数字（3.2x/30x/100x、85%）来自 vendor 博客且 confidence=medium，memo 已在局限明确标 "仅作量级参考"，处理得当。
3. memo 对 "50w token 改坏没提交" 明确标注为多因素推断、无单一 issue 坐实，与来源池 gap 完全对齐，诚实。
整体证据与分析分区清晰，局限段落与 notes 里的 gaps 高度吻合，可直接发布。
