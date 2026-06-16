"""model.py 结构化异常 + 日志 + response body（M4b audit #1）。

DashScope 调用失败时：先打 response body 摘要，再抛 ApiError/NetworkError，
不再裸 raise_for_status / RuntimeError 吞细节。
"""

from unittest.mock import patch, MagicMock

import pytest

from app.extract.model import DashscopeProvider
from app.extract.errors import ApiError, NetworkError


def _resp(*, status_code=200, text="", json_data=None):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    if json_data is not None:
        r.json.return_value = json_data
    return r


class TestLlmCleanErrors:

    @patch("app.extract.model.requests.post")
    def test_http_error_raises_api_error_with_body(self, mock_post, caplog):
        mock_post.return_value = _resp(status_code=400, text='{"code":"InvalidApiKey"}')
        provider = DashscopeProvider(api_key="bad")
        with caplog.at_level("ERROR"):
            with pytest.raises(ApiError) as ei:
                provider.llm_clean("text")
        assert ei.value.provider == "dashscope"
        assert ei.value.api_code == 400
        assert "InvalidApiKey" in (ei.value.payload_excerpt or "")
        assert "InvalidApiKey" in caplog.text


class TestVlmErrors:

    @patch("app.extract.model.requests.post")
    def test_http_error_raises_api_error(self, mock_post):
        mock_post.return_value = _resp(status_code=403, text="forbidden")
        provider = DashscopeProvider(api_key="k")
        with pytest.raises(ApiError) as ei:
            provider.vlm("https://img/x.jpg")
        assert ei.value.api_code == 403


class TestUploadPolicyErrors:

    @patch("app.extract.model.requests.get")
    def test_policy_http_error_raises_api_error(self, mock_get):
        mock_get.return_value = _resp(status_code=401, text="unauthorized")
        provider = DashscopeProvider(api_key="k")
        with pytest.raises(ApiError):
            provider._get_upload_policy()


class TestSubmitTranscriptionErrors:

    @patch("app.extract.model.requests.post")
    def test_submit_http_error_raises_api_error_with_body(self, mock_post):
        mock_post.return_value = _resp(status_code=400, text='{"message":"bad audio"}')
        provider = DashscopeProvider(api_key="k")
        with pytest.raises(ApiError) as ei:
            provider._submit_transcription_task("oss://x")
        assert ei.value.api_code == 400
        assert "bad audio" in (ei.value.payload_excerpt or "")


class TestWaitTranscriptionErrors:

    @patch("app.extract.model.requests.get")
    def test_task_failed_raises_api_error(self, mock_get):
        mock_get.return_value = _resp(
            status_code=200,
            json_data={"output": {"task_status": "FAILED", "message": "转写失败"}},
        )
        provider = DashscopeProvider(api_key="k")
        with pytest.raises(ApiError):
            provider._wait_for_transcription("task-id")
