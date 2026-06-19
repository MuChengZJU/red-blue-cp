"""DashScope 网络调用的超时/连接错误重试（audit #5）。

requests.exceptions.Timeout / ConnectionError → 指数退避重试，最多 3 次，
3 次都失败抛 NetworkError。HTTP 4xx（ApiError）等非网络异常不重试，原样抛。
"""

from unittest.mock import patch, MagicMock

import pytest
import requests

from app.extract.model import DashscopeProvider, _retry_network
from app.extract.errors import ApiError, NetworkError


def _resp(*, status_code=200, text="", json_data=None):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    if json_data is not None:
        r.json.return_value = json_data
    return r


def _chat_ok(text="cleaned"):
    # M5a 起 chat/completions 走流式 SSE
    import json as _json

    r = _resp(status_code=200)
    r.iter_lines.return_value = iter([
        "data: " + _json.dumps({"choices": [{"delta": {"content": text}}]}),
        "data: [DONE]",
    ])
    return r


@pytest.fixture(autouse=True)
def _no_sleep():
    """退避 sleep 置空，测试不真睡。"""
    with patch("app.extract.model.time.sleep") as mock_sleep:
        yield mock_sleep


# ── 重试 helper 直接测 ──────────────────────────────────────────

class TestRetryHelper:

    def test_returns_immediately_on_success(self):
        fn = MagicMock(return_value="ok")
        assert _retry_network("op", fn) == "ok"
        assert fn.call_count == 1

    def test_retries_then_succeeds(self, _no_sleep):
        fn = MagicMock(
            side_effect=[
                requests.exceptions.Timeout("read timed out"),
                requests.exceptions.ConnectionError("conn reset"),
                "ok",
            ]
        )
        assert _retry_network("op", fn) == "ok"
        assert fn.call_count == 3
        # 退避两次（第 1、2 次失败后），不在最后一次后睡
        assert _no_sleep.call_count == 2

    def test_exhausts_and_raises_network_error(self, _no_sleep):
        fn = MagicMock(side_effect=requests.exceptions.Timeout("read timed out"))
        with pytest.raises(NetworkError) as exc_info:
            _retry_network("poll_transcription", fn)
        assert fn.call_count == 3
        assert exc_info.value.operation == "poll_transcription"
        # 指数退避 1, 2（最后一次失败不睡）
        sleeps = [c.args[0] for c in _no_sleep.call_args_list]
        assert sleeps == [1, 2]

    def test_non_network_exception_not_retried(self):
        fn = MagicMock(side_effect=ValueError("boom"))
        with pytest.raises(ValueError):
            _retry_network("op", fn)
        assert fn.call_count == 1

    def test_api_error_not_retried(self):
        """ApiError（非网络）原样冒泡，不重试。"""
        fn = MagicMock(side_effect=ApiError("bad", provider="dashscope"))
        with pytest.raises(ApiError):
            _retry_network("op", fn)
        assert fn.call_count == 1


# ── llm_clean 端到端走重试 ──────────────────────────────────────

class TestLlmCleanRetry:

    @patch("app.extract.model.requests.post")
    def test_timeout_twice_then_success(self, mock_post):
        mock_post.side_effect = [
            requests.exceptions.Timeout("read timeout=180"),
            requests.exceptions.Timeout("read timeout=180"),
            _chat_ok("cleaned"),
        ]
        provider = DashscopeProvider(api_key="k")
        assert provider.llm_clean("raw") == "cleaned"
        assert mock_post.call_count == 3

    @patch("app.extract.model.requests.post")
    def test_always_timeout_raises_network_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("read timeout=180")
        provider = DashscopeProvider(api_key="k")
        with pytest.raises(NetworkError):
            provider.llm_clean("raw")
        assert mock_post.call_count == 3

    @patch("app.extract.model.requests.post")
    def test_connection_error_retried(self, mock_post):
        mock_post.side_effect = [
            requests.exceptions.ConnectionError("conn reset"),
            _chat_ok("cleaned"),
        ]
        provider = DashscopeProvider(api_key="k")
        assert provider.llm_clean("raw") == "cleaned"
        assert mock_post.call_count == 2

    @patch("app.extract.model.requests.post")
    def test_http_400_not_retried_raises_api_error(self, mock_post):
        mock_post.return_value = _resp(status_code=400, text='{"code":"InvalidApiKey"}')
        provider = DashscopeProvider(api_key="bad")
        with pytest.raises(ApiError):
            provider.llm_clean("raw")
        assert mock_post.call_count == 1


# ── vlm 走重试 ─────────────────────────────────────────────────

class TestVlmRetry:

    @patch("app.extract.model.requests.post")
    def test_timeout_twice_then_success(self, mock_post):
        mock_post.side_effect = [
            requests.exceptions.Timeout("t"),
            requests.exceptions.Timeout("t"),
            _chat_ok("desc"),
        ]
        provider = DashscopeProvider(api_key="k")
        assert provider.vlm("http://img") == "desc"
        assert mock_post.call_count == 3

    @patch("app.extract.model.requests.post")
    def test_http_400_not_retried(self, mock_post):
        mock_post.return_value = _resp(status_code=400, text="{}")
        provider = DashscopeProvider(api_key="k")
        with pytest.raises(ApiError):
            provider.vlm("http://img")
        assert mock_post.call_count == 1


# ── _wait_for_transcription 轮询走重试 ──────────────────────────

class TestWaitForTranscriptionRetry:

    @patch("app.extract.model.requests.get")
    def test_poll_timeout_retried_then_succeeds(self, mock_get):
        succeeded = _resp(
            status_code=200,
            json_data={
                "output": {
                    "task_status": "SUCCEEDED",
                    "results": [],
                    "result": {},
                }
            },
        )
        # 头两次轮询请求超时，第三次拿到 SUCCEEDED（无 transcription_url → ParseError）
        mock_get.side_effect = [
            requests.exceptions.Timeout("t"),
            requests.exceptions.Timeout("t"),
            succeeded,
        ]
        provider = DashscopeProvider(api_key="k")
        from app.extract.errors import ParseError
        with pytest.raises(ParseError):
            provider._wait_for_transcription("task-1")
        assert mock_get.call_count == 3

    @patch("app.extract.model.requests.get")
    def test_poll_always_timeout_raises_network_error(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("t")
        provider = DashscopeProvider(api_key="k")
        with pytest.raises(NetworkError):
            provider._wait_for_transcription("task-1")
        assert mock_get.call_count == 3
