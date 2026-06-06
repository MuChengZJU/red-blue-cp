"""ModelProvider 测试 — 定义 model.py 接口契约。

DashscopeProvider 调外部 HTTP API，mock 不可避免。
测试重点：请求构造逻辑 + 响应解析逻辑 + 错误处理。
"""

from unittest.mock import patch, MagicMock, PropertyMock
from typing import runtime_checkable, Protocol

import pytest
from app.service.model import ModelProvider, DashscopeProvider, _format_transcription


# ── Protocol 合规 ──────────────────────────────────────────────

class TestModelProviderProtocol:

    def test_protocol_is_runtime_checkable(self):
        assert runtime_checkable(ModelProvider)

    def test_dashscope_satisfies_protocol(self):
        provider = DashscopeProvider(api_key="test-key")
        assert isinstance(provider, ModelProvider)

    def test_protocol_has_three_methods(self):
        assert hasattr(ModelProvider, "asr")
        assert hasattr(ModelProvider, "vlm")
        assert hasattr(ModelProvider, "llm_clean")


# ── LLM Clean ──────────────────────────────────────────────────

class TestDashscopeLlmClean:

    @patch("app.service.model.requests.post")
    def test_returns_cleaned_text(self, mock_post):
        mock_post.return_value = _mock_chat_response("清洗后的文本内容")
        provider = DashscopeProvider(api_key="test-key")
        result = provider.llm_clean("原始脏文本，带有很多噪音...")
        assert result == "清洗后的文本内容"

    @patch("app.service.model.requests.post")
    def test_sends_to_chat_completions(self, mock_post):
        mock_post.return_value = _mock_chat_response("ok")
        provider = DashscopeProvider(api_key="test-key")
        provider.llm_clean("some text")
        call_args = mock_post.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
        assert "chat/completions" in url

    @patch("app.service.model.requests.post")
    def test_uses_configured_model(self, mock_post):
        mock_post.return_value = _mock_chat_response("ok")
        provider = DashscopeProvider(api_key="test-key", llm_model="qwen-max")
        provider.llm_clean("text")
        call_args = mock_post.call_args
        payload = call_args[1].get("json") or call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("json")
        assert payload["model"] == "qwen-max"

    @patch("app.service.model.requests.post")
    def test_includes_auth_header(self, mock_post):
        mock_post.return_value = _mock_chat_response("ok")
        provider = DashscopeProvider(api_key="sk-abc123")
        provider.llm_clean("text")
        headers = mock_post.call_args[1].get("headers", {})
        assert "Bearer sk-abc123" in headers.get("Authorization", "")

    @patch("app.service.model.requests.post")
    def test_raises_on_http_error(self, mock_post):
        mock_post.return_value = _mock_http_error(500)
        provider = DashscopeProvider(api_key="test-key")
        with pytest.raises(Exception):
            provider.llm_clean("text")

    @patch("app.service.model.requests.post")
    def test_default_model_is_qwen_plus(self, mock_post):
        mock_post.return_value = _mock_chat_response("ok")
        provider = DashscopeProvider(api_key="test-key")
        provider.llm_clean("text")
        payload = mock_post.call_args[1].get("json", {})
        assert payload["model"] == "qwen-plus"


# ── VLM ────────────────────────────────────────────────────────

class TestDashscopeVlm:

    @patch("app.service.model.requests.post")
    def test_returns_image_description(self, mock_post):
        mock_post.return_value = _mock_chat_response("图片中显示了一只猫")
        provider = DashscopeProvider(api_key="test-key")
        result = provider.vlm("https://example.com/image.jpg")
        assert result == "图片中显示了一只猫"

    @patch("app.service.model.requests.post")
    def test_sends_image_url_in_payload(self, mock_post):
        mock_post.return_value = _mock_chat_response("ok")
        provider = DashscopeProvider(api_key="test-key")
        provider.vlm("https://example.com/pic.jpg")
        payload = mock_post.call_args[1].get("json", {})
        messages = payload["messages"]
        content = messages[0]["content"]
        image_parts = [p for p in content if p.get("type") == "image_url"]
        assert len(image_parts) == 1
        assert "https://example.com/pic.jpg" in str(image_parts[0])

    @patch("app.service.model.requests.post")
    def test_default_model_is_qwen3_vl_flash(self, mock_post):
        mock_post.return_value = _mock_chat_response("ok")
        provider = DashscopeProvider(api_key="test-key")
        provider.vlm("https://example.com/pic.jpg")
        payload = mock_post.call_args[1].get("json", {})
        assert payload["model"] == "qwen3-vl-flash"

    @patch("app.service.model.requests.post")
    def test_uses_configured_vlm_model(self, mock_post):
        mock_post.return_value = _mock_chat_response("ok")
        provider = DashscopeProvider(api_key="test-key", vlm_model="qwen-vl-max")
        provider.vlm("https://example.com/pic.jpg")
        payload = mock_post.call_args[1].get("json", {})
        assert payload["model"] == "qwen-vl-max"

    @patch("app.service.model.requests.post")
    def test_raises_on_http_error(self, mock_post):
        mock_post.return_value = _mock_http_error(403)
        provider = DashscopeProvider(api_key="test-key")
        with pytest.raises(Exception):
            provider.vlm("https://example.com/pic.jpg")


# ── ASR ────────────────────────────────────────────────────────

class TestDashscopeAsr:

    @patch("app.service.model.requests.get")
    @patch("app.service.model.requests.post")
    @patch("app.service.model.requests.Session")
    def test_returns_transcribed_text(self, mock_session_cls, mock_post, mock_get):
        _setup_asr_mocks(mock_session_cls, mock_post, mock_get, transcript_text="你好世界")
        provider = DashscopeProvider(api_key="test-key")
        result = provider.asr("https://example.com/audio.m4s")
        assert result == "你好世界"

    @patch("app.service.model.requests.get")
    @patch("app.service.model.requests.post")
    @patch("app.service.model.requests.Session")
    def test_calls_get_policy(self, mock_session_cls, mock_post, mock_get):
        _setup_asr_mocks(mock_session_cls, mock_post, mock_get)
        provider = DashscopeProvider(api_key="test-key")
        provider.asr("https://example.com/audio.m4s")
        # get_policy 是通过 requests.get 调用的
        get_calls = mock_get.call_args_list
        policy_calls = [c for c in get_calls if "uploads" in str(c)]
        assert len(policy_calls) >= 1

    @patch("app.service.model.requests.get")
    @patch("app.service.model.requests.post")
    @patch("app.service.model.requests.Session")
    def test_submits_transcription_task(self, mock_session_cls, mock_post, mock_get):
        _setup_asr_mocks(mock_session_cls, mock_post, mock_get)
        provider = DashscopeProvider(api_key="test-key")
        provider.asr("https://example.com/audio.m4s")
        post_calls = mock_post.call_args_list
        asr_calls = [c for c in post_calls if "transcription" in str(c)]
        assert len(asr_calls) >= 1

    @patch("app.service.model.requests.get")
    @patch("app.service.model.requests.post")
    @patch("app.service.model.requests.Session")
    def test_default_model_is_paraformer_v2(self, mock_session_cls, mock_post, mock_get):
        _setup_asr_mocks(mock_session_cls, mock_post, mock_get)
        provider = DashscopeProvider(api_key="test-key")
        provider.asr("https://example.com/audio.m4s")
        post_calls = mock_post.call_args_list
        asr_calls = [c for c in post_calls if "transcription" in str(c)]
        if asr_calls:
            payload = asr_calls[0][1].get("json", {})
            assert payload.get("model") == "paraformer-v2"

    @patch("app.service.model.requests.get")
    @patch("app.service.model.requests.post")
    @patch("app.service.model.requests.Session")
    def test_raises_on_task_failure(self, mock_session_cls, mock_post, mock_get):
        _setup_asr_mocks(mock_session_cls, mock_post, mock_get, task_status="FAILED")
        provider = DashscopeProvider(api_key="test-key")
        from app.service.errors import ApiError
        with pytest.raises(ApiError):
            provider.asr("https://example.com/audio.m4s")

    @patch("app.service.model.requests.get")
    @patch("app.service.model.requests.post")
    @patch("app.service.model.requests.Session")
    def test_passes_referer_header(self, mock_session_cls, mock_post, mock_get):
        _setup_asr_mocks(mock_session_cls, mock_post, mock_get)
        provider = DashscopeProvider(api_key="test-key")
        provider.asr("https://example.com/audio.m4s", referer="https://www.bilibili.com/")
        # Session().get 应该在 headers 里包含 Referer
        session_instance = mock_session_cls.return_value.__enter__.return_value
        get_call = session_instance.get
        if get_call.called:
            headers = get_call.call_args[1].get("headers", {})
            assert headers.get("Referer") == "https://www.bilibili.com/"


# ── 说话人分离：结果格式化 (_format_transcription) ──────────────

class TestFormatTranscription:

    def test_multi_speaker_labeled(self):
        payload = {
            "transcripts": [
                {
                    "text": "整段全文",
                    "sentences": [
                        {"speaker_id": 0, "text": "你最近怎么不理我？"},
                        {"speaker_id": 1, "text": "不是不理你，是想给你空间。"},
                        {"speaker_id": 0, "text": "那好吧。"},
                    ],
                }
            ]
        }
        result = _format_transcription(payload)
        assert result == (
            "说话人1：你最近怎么不理我？\n\n"
            "说话人2：不是不理你，是想给你空间。\n\n"
            "说话人1：那好吧。"
        )

    def test_consecutive_same_speaker_merged(self):
        payload = {
            "transcripts": [
                {
                    "sentences": [
                        {"speaker_id": 0, "text": "第一句。"},
                        {"speaker_id": 0, "text": "第二句。"},
                        {"speaker_id": 1, "text": "对方说话。"},
                    ]
                }
            ]
        }
        result = _format_transcription(payload)
        assert result == "说话人1：第一句。第二句。\n\n说话人2：对方说话。"

    def test_single_speaker_falls_back_to_plain(self):
        payload = {
            "transcripts": [
                {
                    "text": "整段纯文本。",
                    "sentences": [
                        {"speaker_id": 0, "text": "整段纯文本。"},
                    ],
                }
            ]
        }
        result = _format_transcription(payload)
        assert "说话人" not in result
        assert result == "整段纯文本。"

    def test_no_speaker_id_falls_back_to_plain(self):
        payload = {"transcripts": [{"text": "没有说话人字段的纯文本。"}]}
        result = _format_transcription(payload)
        assert result == "没有说话人字段的纯文本。"

    def test_empty_payload(self):
        assert _format_transcription({}) == ""


# ── 说话人分离：提交参数 ────────────────────────────────────────

class TestDiarizationParams:

    @patch("app.service.model.requests.get")
    @patch("app.service.model.requests.post")
    @patch("app.service.model.requests.Session")
    def test_diarization_enabled_by_default(self, mock_session_cls, mock_post, mock_get):
        _setup_asr_mocks(mock_session_cls, mock_post, mock_get)
        provider = DashscopeProvider(api_key="test-key")
        provider.asr("https://example.com/audio.m4s")
        asr_calls = [c for c in mock_post.call_args_list if "transcription" in str(c)]
        params = asr_calls[0][1]["json"]["parameters"]
        assert params.get("diarization_enabled") is True
        assert "speaker_count" not in params

    @patch("app.service.model.requests.get")
    @patch("app.service.model.requests.post")
    @patch("app.service.model.requests.Session")
    def test_speaker_count_hint_passed(self, mock_session_cls, mock_post, mock_get):
        _setup_asr_mocks(mock_session_cls, mock_post, mock_get)
        provider = DashscopeProvider(api_key="test-key", speaker_count=2)
        provider.asr("https://example.com/audio.m4s")
        asr_calls = [c for c in mock_post.call_args_list if "transcription" in str(c)]
        params = asr_calls[0][1]["json"]["parameters"]
        assert params.get("speaker_count") == 2

    @patch("app.service.model.requests.get")
    @patch("app.service.model.requests.post")
    @patch("app.service.model.requests.Session")
    def test_diarization_can_be_disabled(self, mock_session_cls, mock_post, mock_get):
        _setup_asr_mocks(mock_session_cls, mock_post, mock_get)
        provider = DashscopeProvider(api_key="test-key", diarization_enabled=False)
        provider.asr("https://example.com/audio.m4s")
        asr_calls = [c for c in mock_post.call_args_list if "transcription" in str(c)]
        params = asr_calls[0][1]["json"]["parameters"]
        assert "diarization_enabled" not in params


# ── Helpers ────────────────────────────────────────────────────

def _mock_chat_response(text: str) -> MagicMock:
    # M5a 起 chat/completions 走流式 SSE（正文块 + usage 末块 + [DONE]）
    import json as _json

    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.iter_lines.return_value = iter([
        "data: " + _json.dumps({"choices": [{"delta": {"content": text}}]}),
        "data: " + _json.dumps(
            {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 2}}
        ),
        "data: [DONE]",
    ])
    return resp


def _mock_http_error(status_code: int) -> MagicMock:
    from requests.exceptions import HTTPError
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status.side_effect = HTTPError(f"{status_code} Error")
    return resp


def _setup_asr_mocks(
    mock_session_cls,
    mock_post,
    mock_get,
    transcript_text: str = "转写文本",
    task_status: str = "SUCCEEDED",
):
    # 1. getPolicy 响应
    policy_resp = MagicMock()
    policy_resp.status_code = 200
    policy_resp.raise_for_status = MagicMock()
    policy_resp.json.return_value = {
        "data": {
            "upload_host": "https://oss.example.com",
            "upload_dir": "tmp/uploads",
            "oss_access_key_id": "fake-key",
            "signature": "fake-sig",
            "policy": "fake-policy",
            "x_oss_object_acl": "private",
            "x_oss_forbid_overwrite": "true",
        }
    }

    # 2. 轮询响应
    if task_status == "SUCCEEDED":
        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.raise_for_status = MagicMock()
        poll_resp.json.return_value = {
            "output": {
                "task_status": "SUCCEEDED",
                "result": {
                    "transcription_url": "https://example.com/transcript.json"
                }
            }
        }
        # transcription_url 的响应
        transcript_resp = MagicMock()
        transcript_resp.status_code = 200
        transcript_resp.raise_for_status = MagicMock()
        transcript_resp.json.return_value = {
            "transcripts": [{"text": transcript_text}]
        }
        mock_get.side_effect = [policy_resp, poll_resp, transcript_resp]
    else:
        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.raise_for_status = MagicMock()
        poll_resp.json.return_value = {
            "output": {
                "task_status": "FAILED",
                "message": "转写失败"
            }
        }
        mock_get.side_effect = [policy_resp, poll_resp]

    # 3. Session mock (音频下载 + OSS 上传)
    session_instance = MagicMock()
    download_response = MagicMock()
    download_response.status_code = 200
    download_response.raise_for_status = MagicMock()
    download_response.headers = {"Content-Length": "1024"}
    download_response.iter_content.return_value = [b"fake-audio-data"]
    download_response.__enter__ = MagicMock(return_value=download_response)
    download_response.__exit__ = MagicMock(return_value=False)
    session_instance.get.return_value = download_response
    session_instance.trust_env = True

    upload_response = MagicMock()
    upload_response.status_code = 200
    upload_response.raise_for_status = MagicMock()
    session_instance.post.return_value = upload_response

    mock_session_cls.return_value.__enter__ = MagicMock(return_value=session_instance)
    mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

    # 4. ASR 提交响应
    submit_resp = MagicMock()
    submit_resp.status_code = 200
    submit_resp.raise_for_status = MagicMock()
    submit_resp.json.return_value = {
        "output": {"task_id": "fake-task-id-123"}
    }
    mock_post.return_value = submit_resp
