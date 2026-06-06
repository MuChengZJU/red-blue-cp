"""M5a：流式 SSE 解析 + usage 采集 — 契约测试。

流式动机：非流式 + 180s read 超时撞长文生成（~300s），见
docs/devlog/2026-06-06-m4-ship-and-ux-iteration.md。
usage 动机：用户要看每任务 ASR/VLM/LLM 花多少 token/时间/钱（P1h）。

spike 实证（_sandbox/spike_usage/）：
- chat/completions 传 stream_options.include_usage 后，最后一个 SSE 块
  choices=[] 且带 usage（prompt_tokens/completion_tokens）。
- 转写任务 poll 响应顶层带 usage.duration（秒，计费单位）。
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.service.model import DashscopeProvider, _parse_sse_stream


# ── 测试 helper：伪造流式响应 ──────────────────────────────────

def _sse_lines(chunks: list[str], usage: dict | None = None) -> list[str]:
    lines = []
    for c in chunks:
        lines.append(
            "data: " + json.dumps({"choices": [{"delta": {"content": c}}]})
        )
    if usage is not None:
        lines.append("data: " + json.dumps({"choices": [], "usage": usage}))
    lines.append("data: [DONE]")
    return lines


def _mock_stream_response(chunks: list[str], usage: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.iter_lines.return_value = iter(_sse_lines(chunks, usage))
    return resp


_USAGE = {"prompt_tokens": 13, "completion_tokens": 39, "total_tokens": 52}


# ── _parse_sse_stream 纯函数 ──────────────────────────────────

class TestParseSseStream:

    def test_accumulates_delta_content(self):
        text, usage = _parse_sse_stream(iter(_sse_lines(["你好", "，", "世界"])))
        assert text == "你好，世界"

    def test_returns_usage_from_final_chunk(self):
        text, usage = _parse_sse_stream(iter(_sse_lines(["ok"], usage=_USAGE)))
        assert usage == _USAGE

    def test_usage_none_when_absent(self):
        text, usage = _parse_sse_stream(iter(_sse_lines(["ok"])))
        assert usage is None

    def test_skips_empty_and_non_data_lines(self):
        lines = ["", ": keep-alive", *_sse_lines(["a", "b"])]
        text, usage = _parse_sse_stream(iter(lines))
        assert text == "ab"

    def test_stops_at_done(self):
        lines = _sse_lines(["a"]) + ["data: " + json.dumps({"choices": [{"delta": {"content": "残"}}]})]
        text, usage = _parse_sse_stream(iter(lines))
        assert text == "a"

    def test_tolerates_chunk_without_delta_content(self):
        # 首块常只有 role 没 content；不该崩
        lines = [
            "data: " + json.dumps({"choices": [{"delta": {"role": "assistant"}}]}),
            *_sse_lines(["正文"]),
        ]
        text, usage = _parse_sse_stream(iter(lines))
        assert text == "正文"


# ── llm_clean 流式 ────────────────────────────────────────────

class TestLlmCleanStreaming:

    @patch("app.service.model.requests.post")
    def test_returns_accumulated_text(self, mock_post):
        mock_post.return_value = _mock_stream_response(["清洗", "后的", "文本"], _USAGE)
        provider = DashscopeProvider(api_key="test-key")
        assert provider.llm_clean("raw") == "清洗后的文本"

    @patch("app.service.model.requests.post")
    def test_payload_requests_stream_with_usage(self, mock_post):
        mock_post.return_value = _mock_stream_response(["ok"], _USAGE)
        provider = DashscopeProvider(api_key="test-key")
        provider.llm_clean("raw")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["stream"] is True
        assert payload["stream_options"] == {"include_usage": True}
        assert mock_post.call_args.kwargs["stream"] is True

    @patch("app.service.model.requests.post")
    def test_read_timeout_covers_token_gap_not_full_generation(self, mock_post):
        # 流式后 read 超时只需覆盖 token 间隔；600s 是兜底不是常态
        mock_post.return_value = _mock_stream_response(["ok"], _USAGE)
        provider = DashscopeProvider(api_key="test-key")
        provider.llm_clean("raw")
        timeout = mock_post.call_args.kwargs["timeout"]
        assert timeout[1] >= 600

    @patch("app.service.model.requests.post")
    def test_records_usage_event(self, mock_post):
        mock_post.return_value = _mock_stream_response(["ok"], _USAGE)
        provider = DashscopeProvider(api_key="test-key")
        provider.llm_clean("raw")
        assert len(provider.usage_events) == 1
        event = provider.usage_events[0]
        assert event["stage"] == "llm_clean"
        assert event["model"] == "qwen-plus"
        assert event["input_tokens"] == 13
        assert event["output_tokens"] == 39
        assert event["elapsed_seconds"] >= 0

    @patch("app.service.model.requests.post")
    def test_no_usage_in_stream_still_returns_text(self, mock_post):
        # DashScope 不回 usage 时正文照常，event 记 None token（页面端兜底）
        mock_post.return_value = _mock_stream_response(["ok"])
        provider = DashscopeProvider(api_key="test-key")
        assert provider.llm_clean("raw") == "ok"
        event = provider.usage_events[0]
        assert event["input_tokens"] is None
        assert event["output_tokens"] is None

    @patch("app.service.model.requests.post")
    def test_midstream_timeout_does_not_retry_post(self, mock_post):
        # 建连重试归 _retry_network；流中断不能整段重跑（放大等待的根因）
        resp = MagicMock()
        resp.status_code = 200

        def _broken_lines(**kwargs):
            yield "data: " + json.dumps({"choices": [{"delta": {"content": "半"}}]})
            raise requests.exceptions.ConnectionError("mid-stream drop")

        resp.iter_lines.side_effect = _broken_lines
        mock_post.return_value = resp
        provider = DashscopeProvider(api_key="test-key")
        from app.service.errors import NetworkError

        with pytest.raises(NetworkError):
            provider.llm_clean("raw")
        assert mock_post.call_count == 1

    @patch("app.service.model.requests.post")
    def test_http_error_still_raises_api_error(self, mock_post):
        from app.service.errors import ApiError

        resp = MagicMock()
        resp.status_code = 429
        resp.text = '{"error": "quota exceeded"}'
        mock_post.return_value = resp
        provider = DashscopeProvider(api_key="test-key")
        with pytest.raises(ApiError):
            provider.llm_clean("raw")


# ── vlm 流式 ──────────────────────────────────────────────────

class TestVlmStreaming:

    @patch("app.service.model.requests.post")
    def test_returns_accumulated_text(self, mock_post):
        mock_post.return_value = _mock_stream_response(["图片里", "有只猫"], _USAGE)
        provider = DashscopeProvider(api_key="test-key")
        assert provider.vlm("https://example.com/cat.jpg") == "图片里有只猫"

    @patch("app.service.model.requests.post")
    def test_records_usage_event_per_image(self, mock_post):
        mock_post.return_value = _mock_stream_response(["ok"], _USAGE)
        provider = DashscopeProvider(api_key="test-key")
        provider.vlm("https://example.com/1.jpg")
        mock_post.return_value = _mock_stream_response(["ok"], _USAGE)
        provider.vlm("https://example.com/2.jpg")
        stages = [e["stage"] for e in provider.usage_events]
        assert stages == ["vlm", "vlm"]
        assert provider.usage_events[0]["model"] == "qwen3-vl-flash"


# ── asr usage ─────────────────────────────────────────────────

class TestAsrUsage:

    def test_records_audio_seconds_from_poll_usage(self):
        # spike 实证：poll 响应顶层 usage.duration = 计费秒数
        provider = DashscopeProvider(api_key="test-key")
        poll_payload = {
            "output": {
                "task_status": "SUCCEEDED",
                "results": [{"transcription_url": "https://example.com/r.json"}],
            },
            "usage": {"duration": 10},
        }
        with (
            patch.object(provider, "_upload_audio_to_oss", return_value="oss://k"),
            patch.object(provider, "_submit_transcription_task", return_value="tid"),
            patch("app.service.model.requests.get") as mock_get,
            patch("app.service.model._extract_transcription_text", return_value="转写文本"),
        ):
            poll_resp = MagicMock()
            poll_resp.status_code = 200
            poll_resp.json.return_value = poll_payload
            mock_get.return_value = poll_resp
            assert provider.asr("https://example.com/a.mp3") == "转写文本"

        event = provider.usage_events[0]
        assert event["stage"] == "asr"
        assert event["model"] == "paraformer-v2"
        assert event["audio_seconds"] == 10
        assert event["elapsed_seconds"] >= 0


class TestStreamResponseClosed:

    @patch("app.service.model.requests.post")
    def test_response_closed_after_parse(self, mock_post):
        # Codex review P2：[DONE] 即停不读到 EOF，不 close 会占住连接池
        resp = _mock_stream_response(["ok"], _USAGE)
        mock_post.return_value = resp
        provider = DashscopeProvider(api_key="test-key")
        provider.llm_clean("raw")
        resp.close.assert_called_once()

    @patch("app.service.model.requests.post")
    def test_response_closed_even_on_midstream_error(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200

        def _broken_lines(**kwargs):
            raise requests.exceptions.ConnectionError("drop")
            yield  # pragma: no cover

        resp.iter_lines.side_effect = _broken_lines
        mock_post.return_value = resp
        provider = DashscopeProvider(api_key="test-key")
        from app.service.errors import NetworkError

        with pytest.raises(NetworkError):
            provider.llm_clean("raw")
        resp.close.assert_called_once()
