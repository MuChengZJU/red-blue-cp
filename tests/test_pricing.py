"""M5a：单价表 + 费用估算 — 契约测试。

单价来源：阿里云百炼「模型调用价格」官方页（2026-06-06 查证）：
- paraformer-v2：0.00008 元/秒（按输入音频秒数，输出不计费）
- qwen-plus（0-128K 档，非思考输出）：输入 0.0008 / 输出 0.002 元每千 token
- qwen3-vl-flash（0-32K 档）：输入 0.00015 / 输出 0.0015 元每千 token
"""

import pytest

from app.service.pricing import summarize_usage


class TestSummarizeUsage:

    def test_asr_cost_by_audio_seconds(self):
        events = [{"stage": "asr", "model": "paraformer-v2",
                   "audio_seconds": 3600, "elapsed_seconds": 120.0}]
        summary = summarize_usage(events)
        assert summary["events"][0]["cost_yuan"] == pytest.approx(0.288)
        assert summary["total_cost_yuan"] == pytest.approx(0.288)

    def test_llm_cost_by_tokens(self):
        events = [{"stage": "llm_clean", "model": "qwen-plus",
                   "input_tokens": 10000, "output_tokens": 5000,
                   "elapsed_seconds": 30.0}]
        summary = summarize_usage(events)
        # 10000/1000*0.0008 + 5000/1000*0.002 = 0.008 + 0.01
        assert summary["events"][0]["cost_yuan"] == pytest.approx(0.018)

    def test_vlm_cost_by_tokens(self):
        events = [{"stage": "vlm", "model": "qwen3-vl-flash",
                   "input_tokens": 2000, "output_tokens": 1000,
                   "elapsed_seconds": 5.0}]
        summary = summarize_usage(events)
        # 2000/1000*0.00015 + 1000/1000*0.0015 = 0.0003 + 0.0015
        assert summary["events"][0]["cost_yuan"] == pytest.approx(0.0018)

    def test_total_sums_multiple_events(self):
        events = [
            {"stage": "asr", "model": "paraformer-v2",
             "audio_seconds": 600, "elapsed_seconds": 60.0},
            {"stage": "llm_clean", "model": "qwen-plus",
             "input_tokens": 1000, "output_tokens": 1000, "elapsed_seconds": 10.0},
        ]
        summary = summarize_usage(events)
        assert summary["total_cost_yuan"] == pytest.approx(0.048 + 0.0028)

    def test_unknown_model_cost_none_but_kept(self):
        # 不认识的模型不瞎编价格：cost 记 None，event 保留（用量本身仍有价值）
        events = [{"stage": "llm_clean", "model": "future-model",
                   "input_tokens": 1000, "output_tokens": 1000, "elapsed_seconds": 1.0}]
        summary = summarize_usage(events)
        assert summary["events"][0]["cost_yuan"] is None
        assert summary["total_cost_yuan"] == 0.0

    def test_missing_tokens_cost_none(self):
        # DashScope 没回 usage 时 token 为 None → 不算钱、不崩
        events = [{"stage": "llm_clean", "model": "qwen-plus",
                   "input_tokens": None, "output_tokens": None, "elapsed_seconds": 1.0}]
        summary = summarize_usage(events)
        assert summary["events"][0]["cost_yuan"] is None

    def test_empty_events_returns_none(self):
        # text_only / 纯字幕任务可能一次模型都没调
        assert summarize_usage([]) is None
