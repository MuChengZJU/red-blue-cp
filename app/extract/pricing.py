"""模型用量 → 费用估算（P1h）。

单价常量，来源：千问AI平台「模型价格」官方页
https://platform.qianwenai.com/docs/developer-guides/getting-started/model-prices
（2026-10-21 查证；旧百炼 https://help.aliyun.com/zh/model-studio/model-pricing）。
价格变了改这里一处。

口径说明（估算值，不是账单）：
- paraformer-v2 按输入音频秒数计费，输出不计费；
- qwen3.7-flash / qwen3.5-flash / qwen3.6-flash 按输入 token 阶梯计价，单次请求
  输入落在哪档、该请求所有 token 都按那档结算（官方规则）；
- 本项目默认关闭思考模式（``RBCP_*_THINKING=false``），思考 token 会按输出价计费，
  不关的话短文本清洗也会烧上千 token；
- 未收录的自定义模型费用记 None（用量仍展示，不瞎编价格）；
- 免费额度（ASR 每月 10 小时等）不在估算内扣除——展示的是目录价成本。
"""

from __future__ import annotations

from typing import Any

# 元/秒（按输入音频秒数）。仅收录「按音频时长」计费、且能由秒数估价的模型。
ASR_PRICES_YUAN_PER_SECOND = {
    "paraformer-v2": 0.00008,  # = 0.288 元/小时
    "qwen3-asr-flash-filetrans": 0.00022,
    "qwen-audio-3.0-asr-flash-filetrans": 0.00022,
    "fun-asr": 0.00022,
}

# 元/千 token（输入, 输出），不分阶梯的模型
CHAT_PRICES_YUAN_PER_1K = {
    "qwen-plus": (0.0008, 0.002),
    "qwen-plus-latest": (0.0008, 0.002),
    "qwen3.8-flash": (0.0008, 0.0027),
    "qwen3.5-ocr": (0.0005, 0.002),
    "qwen-vl-ocr": (0.0003, 0.0005),
    # 旧百炼模型（老配置继续可用）
    "qwen3-vl-flash": (0.00015, 0.0015),
}

# 阶梯计价：[(输入上限 token, 输入 元/千 token, 输出 元/千 token), ...]。
# 规则来自官方计费说明：单次请求输入落在哪档，该请求**所有** token 都按那档单价结算。
CHAT_TIERED_PRICES_YUAN_PER_1K = {
    "qwen3.7-flash": [
        (32_000, 0.0002, 0.0008),
        (256_000, 0.0006, 0.0024),
        (1_000_000, 0.0012, 0.0048),
    ],
    "qwen3.5-flash": [
        (128_000, 0.0002, 0.002),
        (256_000, 0.0008, 0.008),
        (1_000_000, 0.0012, 0.012),
    ],
    "qwen3.6-flash": [
        (256_000, 0.0012, 0.0072),
        (1_000_000, 0.0048, 0.0288),
    ],
    "qwen3-vl-plus": [
        (32_000, 0.001, 0.01),
        (128_000, 0.0015, 0.015),
        (256_000, 0.003, 0.03),
    ],
}


def _event_cost_yuan(event: dict[str, Any]) -> float | None:
    """单个 usage event 的估算费用。模型不认识或用量缺失 → None（不瞎编）。"""
    model = event.get("model")

    if event.get("stage") == "asr":
        price = ASR_PRICES_YUAN_PER_SECOND.get(model or "")
        seconds = event.get("audio_seconds")
        if price is None or not isinstance(seconds, (int, float)):
            return None
        return round(seconds * price, 6)

    model = model or ""
    input_tokens = event.get("input_tokens")
    output_tokens = event.get("output_tokens")
    if input_tokens is None or output_tokens is None:
        return None

    tiers = CHAT_TIERED_PRICES_YUAN_PER_1K.get(model)
    if tiers:
        input_price, output_price = tiers[-1][1], tiers[-1][2]
        for limit, in_price, out_price in tiers:
            if input_tokens <= limit:
                input_price, output_price = in_price, out_price
                break
    else:
        prices = CHAT_PRICES_YUAN_PER_1K.get(model)
        if prices is None:
            return None
        input_price, output_price = prices
    return round(
        input_tokens / 1000 * input_price + output_tokens / 1000 * output_price, 6
    )


def summarize_usage(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """usage events → 落库结构：每条补 cost_yuan，汇总 total_cost_yuan。

    无 event（text_only / 纯字幕任务）返回 None。
    """
    if not events:
        return None
    priced = [{**event, "cost_yuan": _event_cost_yuan(event)} for event in events]
    total = round(
        sum(e["cost_yuan"] for e in priced if e["cost_yuan"] is not None), 6
    )
    return {"events": priced, "total_cost_yuan": total}
