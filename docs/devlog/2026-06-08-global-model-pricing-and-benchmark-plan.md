---
date: 2026-06-08
type: research
priority: medium
related: [PLAN.md, docs/devlog/2026-06-07-m5a-streaming-and-usage.md]
status: active
---

# 模型成本调研（阿里云免费额度 + 全球比价）+ 横评实验立项

> 起因：有同学提"阿里云 ASR/VLM 有免费额度，能不能轮换白嫖"。两轮联网调研（阿里云免费额度规则 + 全球厂商比价）得出结论：**现状已是成本最优，不用换**；真要再省只有 Gemini 免费层这一条，且只对平台化（量大）有意义。把横评实验写进 PLAN 待办，触发条件=做平台。

## 调研一：阿里云免费额度能不能轮换白嫖？→ 基本不能

核心事实（来源 help.aliyun.com/zh/model-studio）：
- 免费额度**按模型独立**发放（轮换前提成立）。
- 但**每月循环**的几乎只有 **Paraformer 系列**（ASR，10 小时/月，每月 1 日自动发）；其余 ASR（qwen3-asr / fun-asr）和**全部 VLM** 都是**一次性新人额度**（开通后 90 天，到期归零）。
- 所以：ASR 轮换没用（每月免费的只有 paraformer，我们已在用）；VLM 轮换不可持续（全一次性，叠大一次性池但不循环）。

## 调研二：全球 ASR/VLM 比价（人民币，汇率 7.2）

**ASR（每小时音频成本，便宜→贵）**：
- paraformer-v2 ≈0.29 ＝ Gemini 2.5 Flash-Lite ≈0.29（并列最便宜）
- → AssemblyAI 1.08 / Deepgram 2.09 / gpt-4o-transcribe 2.59 / Omni 模型 5~7（杀鸡用牛刀）
- Claude 不支持音频输入。paraformer-v2 额外带：每月免费 10h + 中文最稳 + **免费自带说话人分离**（Gemini/OpenAI/Omni 都没有可靠分离）。

**VLM（每张小红书图 ≈1500 输入+200 输出 token，便宜→贵）**：
- qwen3-vl-flash ≈0.0012 元/张（全球最便宜）→ Gemini 2.5 Flash-Lite ≈0.0017 → GPT/Claude 旗舰 0.004~0.018（贵一个数量级）

**唯一「每天循环白嫖」= Gemini 免费层**（同一套额度覆盖音频理解 + 视觉，按天 RPD 重置）。阿里云只有 paraformer 月度循环；OpenAI/Anthropic 无循环免费层。

## 结论

现状 **paraformer-v2（ASR）+ qwen3-vl-flash（VLM）已是全球最便宜档**，无需换栈。一条 1 小时视频实际成本 ≈ 0.29（ASR）+ 几分钱（LLM 清洗）≈ **几毛钱**。对个体用户成本 trivial，不值得为省它加 provider 切换的复杂度。

## 立项：模型横评实验（PLAN 待办，平台化才触发）

做成多用户平台时，量聚合起来省钱才有意义。那时跑一次横评：
- **维度**：效果（转写/识图准确度）× 成本 × 延迟 × 总耗时
- **重点**：VLM 切 Gemini 免费层能省多少（图文识别场景，Gemini 视觉免费且每天循环）
- **约束**：ASR 大概率仍留 paraformer（Gemini ASR 丢说话人分离）；横评依赖 M5a 待办的「provider env 化」先落地（base_url/model/key 可配）
- **不做的前提**：个体用户阶段不做——成本已 trivial，纯增复杂度

数字会过期（各家频繁调价 + Gemini 已上 3.x 系列），真做横评时以当时官方价为准，本文仅存调研方法与当时结论。
