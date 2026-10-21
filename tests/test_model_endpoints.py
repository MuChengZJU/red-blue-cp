"""0.7 · 模型服务端点解析 + 自定义 provider 契约测试。

覆盖：
- base_url 拼接/补全（OpenAI 兼容 / DashScope 原生 ASR）
- 各能力 env 覆盖与空串回退、VLM 继承 LLM
- provider 用各自 base_url/api_key/model 发请求
- 第三方服务商 VLM 图片自动 base64（防盗链/网关不取图）
- URL 直传失败后回退 base64
- 连通性探测
"""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

import app.model_endpoints as ep
from app.extract.errors import ApiError, ConfigError
from app.extract.model import (
    DashscopeProvider,
    build_asr_url,
    build_chat_completions_url,
)

_ENV_KEYS = (
    "DASHSCOPE_API_KEY",
    "RBCP_ASR_BASE_URL", "RBCP_ASR_API_KEY", "RBCP_ASR_MODEL",
    "RBCP_VLM_BASE_URL", "RBCP_VLM_API_KEY", "RBCP_VLM_MODEL",
    "RBCP_LLM_BASE_URL", "RBCP_LLM_API_KEY", "RBCP_LLM_MODEL",
    "RBCP_VLM_IMAGE_MODE",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


# ── URL 拼接 ──────────────────────────────────────────────────

class TestUrlBuilding:

    def test_appends_chat_completions(self):
        assert build_chat_completions_url("https://api.example.com/v1") == (
            "https://api.example.com/v1/chat/completions"
        )

    def test_domain_only_gets_v1(self):
        assert build_chat_completions_url("https://api.example.com") == (
            "https://api.example.com/v1/chat/completions"
        )

    def test_strips_trailing_slash(self):
        assert build_chat_completions_url("https://api.example.com/v1/") == (
            "https://api.example.com/v1/chat/completions"
        )

    def test_full_url_not_duplicated(self):
        url = "https://api.example.com/v1/chat/completions"
        assert build_chat_completions_url(url) == url

    def test_empty_raises(self):
        with pytest.raises(ConfigError):
            build_chat_completions_url("  ")

    def test_asr_url(self):
        assert build_asr_url("https://asr.example.com/api/v1/", "uploads") == (
            "https://asr.example.com/api/v1/uploads"
        )

    def test_asr_url_empty_raises(self):
        with pytest.raises(ConfigError):
            build_asr_url("", "uploads")


# ── 端点解析 ──────────────────────────────────────────────────

class TestEndpoints:

    def test_defaults_point_to_qianwen(self):
        asr, vlm, llm = ep.asr_endpoint(), ep.vlm_endpoint(), ep.llm_endpoint()
        assert asr.base_url == ep.QIANWEN_ASR_BASE_URL
        assert llm.base_url == ep.QIANWEN_CHAT_BASE_URL
        assert vlm.base_url == ep.QIANWEN_CHAT_BASE_URL
        assert asr.model == "paraformer-v2"
        assert vlm.model == "qwen3.7-flash"
        assert llm.model == "qwen3.7-flash"

    def test_empty_env_falls_back_to_defaults(self, clean_env):
        for key in _ENV_KEYS:
            clean_env.setenv(key, "")
        assert ep.asr_endpoint().base_url == ep.DEFAULT_ASR_BASE_URL
        assert ep.asr_endpoint().model == ep.DEFAULT_ASR_MODEL
        assert ep.vlm_endpoint().model == ep.DEFAULT_VLM_MODEL
        assert ep.llm_endpoint().model == ep.DEFAULT_LLM_MODEL

    def test_asr_key_falls_back_to_shared_key(self, clean_env):
        clean_env.setenv("DASHSCOPE_API_KEY", "sk-shared")
        assert ep.asr_endpoint().api_key == ""  # 端点层不塞共享 key，由 provider 回退
        provider = DashscopeProvider(api_key=ep.shared_api_key())
        assert provider.asr_api_key == "sk-shared"
        assert provider.llm_api_key == "sk-shared"

    def test_per_capability_env_overrides(self, clean_env):
        clean_env.setenv("RBCP_ASR_BASE_URL", "https://asr.example.com/api/v1")
        clean_env.setenv("RBCP_ASR_API_KEY", "asr-key")
        clean_env.setenv("RBCP_ASR_MODEL", "fun-asr")
        clean_env.setenv("RBCP_LLM_BASE_URL", "https://llm.example.com/v1")
        clean_env.setenv("RBCP_LLM_API_KEY", "llm-key")
        clean_env.setenv("RBCP_LLM_MODEL", "my-llm")
        clean_env.setenv("RBCP_VLM_MODEL", "my-vlm")
        asr, vlm, llm = ep.asr_endpoint(), ep.vlm_endpoint(), ep.llm_endpoint()
        assert (asr.base_url, asr.api_key, asr.model) == (
            "https://asr.example.com/api/v1", "asr-key", "fun-asr"
        )
        assert (llm.base_url, llm.api_key, llm.model) == (
            "https://llm.example.com/v1", "llm-key", "my-llm"
        )
        # VLM 未单独配 base/key → 继承 LLM
        assert (vlm.base_url, vlm.api_key, vlm.model) == (
            "https://llm.example.com/v1", "llm-key", "my-vlm"
        )

    def test_vlm_own_endpoint_wins(self, clean_env):
        clean_env.setenv("RBCP_LLM_BASE_URL", "https://llm.example.com/v1")
        clean_env.setenv("RBCP_VLM_BASE_URL", "https://vlm.example.com/v1")
        clean_env.setenv("RBCP_VLM_API_KEY", "vlm-key")
        vlm = ep.vlm_endpoint()
        assert vlm.base_url == "https://vlm.example.com/v1"
        assert vlm.api_key == "vlm-key"

    def test_image_mode_defaults_and_validation(self, clean_env):
        assert ep.vlm_image_mode() == "auto"
        clean_env.setenv("RBCP_VLM_IMAGE_MODE", "base64")
        assert ep.vlm_image_mode() == "base64"
        clean_env.setenv("RBCP_VLM_IMAGE_MODE", "bogus")
        assert ep.vlm_image_mode() == "auto"

    def test_thinking_defaults_off_and_env_override(self, clean_env):
        assert ep.llm_thinking() is False
        assert ep.vlm_thinking() is False
        clean_env.setenv("RBCP_LLM_THINKING", "true")
        clean_env.setenv("RBCP_VLM_THINKING", "1")
        assert ep.llm_thinking() is True
        assert ep.vlm_thinking() is True
        clean_env.setenv("RBCP_LLM_THINKING", "bogus")
        assert ep.llm_thinking() is False

    def test_detect_preset(self):
        assert ep.detect_preset(ep.QIANWEN_ASR_BASE_URL, ep.QIANWEN_CHAT_BASE_URL) == "qianwen"
        assert ep.detect_preset("https://x/api/v1", "https://x/v1") == "custom"


# ── provider 请求走各自端点 ────────────────────────────────────

def _stream_response(text: str = "ok") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.text = ""
    resp.iter_lines.return_value = iter([
        "data: " + json.dumps({"choices": [{"delta": {"content": text}}]}),
        "data: [DONE]",
    ])
    return resp


def _http_error(status: int, body: str = "denied") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = body
    return resp


class TestProviderEndpoints:

    @patch("app.extract.model.requests.post")
    def test_llm_uses_custom_base(self, mock_post):
        mock_post.return_value = _stream_response()
        provider = DashscopeProvider(
            api_key="k", llm_base_url="https://custom.example.com/v1"
        )
        provider.llm_clean("raw")
        assert mock_post.call_args.args[0] == "https://custom.example.com/v1/chat/completions"

    @patch("app.extract.model.requests.post")
    def test_vlm_uses_custom_base_and_key(self, mock_post):
        mock_post.return_value = _stream_response("图")
        provider = DashscopeProvider(
            api_key="shared",
            vlm_base_url="https://vlm.example.com/v1",
            vlm_api_key="vlm-key",
            image_mode="url",
        )
        provider.vlm("https://img.example.com/a.jpg")
        assert mock_post.call_args.args[0] == "https://vlm.example.com/v1/chat/completions"
        assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer vlm-key"

    @patch("app.extract.model.requests.post")
    def test_llm_uses_llm_key(self, mock_post):
        mock_post.return_value = _stream_response()
        provider = DashscopeProvider(
            api_key="shared", llm_api_key="llm-key", vlm_api_key="vlm-key"
        )
        provider.llm_clean("raw")
        assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer llm-key"

    @patch("app.extract.model.requests.get")
    def test_asr_policy_uses_custom_base_and_key(self, mock_get):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"data": {"upload_dir": "x"}}
        mock_get.return_value = resp
        provider = DashscopeProvider(
            api_key="shared",
            asr_base_url="https://asr.example.com/api/v1",
            asr_api_key="asr-key",
        )
        provider._get_upload_policy()
        assert mock_get.call_args.args[0] == "https://asr.example.com/api/v1/uploads"
        assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer asr-key"

    @patch("app.extract.model.requests.post")
    def test_complete_json_retries_without_response_format(self, mock_post):
        mock_post.side_effect = [
            _http_error(400, '{"error":{"message":"response_format is not supported"}}'),
            _stream_response('{"highlights":[]}'),
        ]
        provider = DashscopeProvider(api_key="k")
        text, _usage = provider.complete_json("prompt")
        assert text == '{"highlights":[]}'
        assert "response_format" not in mock_post.call_args_list[1].kwargs["json"]

    @patch("app.extract.model.requests.post")
    def test_complete_json_does_not_mask_unrelated_400(self, mock_post):
        mock_post.return_value = _http_error(400, '{"error":{"message":"model not found"}}')
        provider = DashscopeProvider(api_key="k")
        with pytest.raises(ApiError):
            provider.complete_json("prompt")
        assert mock_post.call_count == 1


# ── VLM 图片双轨 ──────────────────────────────────────────────

def _mock_image_session(mock_session_cls, *, content: bytes = b"fake-jpeg") -> MagicMock:
    session = mock_session_cls.return_value.__enter__.return_value
    image_resp = MagicMock()
    image_resp.status_code = 200
    image_resp.headers = {"Content-Type": "image/jpeg"}
    image_resp.iter_content.return_value = [content]
    image_resp.__enter__ = MagicMock(return_value=image_resp)
    image_resp.__exit__ = MagicMock(return_value=False)
    session.get.return_value = image_resp
    return session


class TestVlmImageMode:

    @patch("app.extract.model.requests.Session")
    @patch("app.extract.model.requests.post")
    def test_custom_provider_inlines_image_base64(self, mock_post, mock_session_cls):
        mock_post.return_value = _stream_response("图")
        _mock_image_session(mock_session_cls)
        provider = DashscopeProvider(
            api_key="k", vlm_base_url="https://third-party.example.com/v1"
        )
        provider.vlm("https://img.example.com/a.jpg", referer="https://www.xiaohongshu.com/")
        payload = mock_post.call_args.kwargs["json"]
        image_url = payload["messages"][0]["content"][1]["image_url"]["url"]
        assert image_url.startswith("data:image/jpeg;base64,")
        assert base64.b64decode(image_url.split(",", 1)[1]) == b"fake-jpeg"
        # 下载图片时必须带 referer（小红书防盗链）
        headers = mock_session_cls.return_value.__enter__.return_value.get.call_args.kwargs["headers"]
        assert headers["Referer"] == "https://www.xiaohongshu.com/"

    @patch("app.extract.model.requests.Session")
    @patch("app.extract.model.requests.post")
    def test_trusted_provider_uses_url_first(self, mock_post, mock_session_cls):
        mock_post.return_value = _stream_response("图")
        provider = DashscopeProvider(api_key="k")  # 默认千问，服务端能抓 URL
        provider.vlm("https://img.example.com/a.jpg")
        payload = mock_post.call_args.kwargs["json"]
        image_url = payload["messages"][0]["content"][1]["image_url"]["url"]
        assert image_url == "https://img.example.com/a.jpg"
        mock_session_cls.assert_not_called()

    @patch("app.extract.model.requests.Session")
    @patch("app.extract.model.requests.post")
    def test_url_fetch_failure_falls_back_to_base64(self, mock_post, mock_session_cls):
        mock_post.side_effect = [_http_error(403), _stream_response("图")]
        _mock_image_session(mock_session_cls)
        provider = DashscopeProvider(api_key="k")  # 默认千问；模拟服务端取图 403
        provider.vlm("https://img.example.com/a.jpg")
        assert mock_post.call_count == 2
        second_payload = mock_post.call_args.kwargs["json"]
        image_url = second_payload["messages"][0]["content"][1]["image_url"]["url"]
        assert image_url.startswith("data:image/jpeg;base64,")

    @patch("app.extract.model.requests.Session")
    @patch("app.extract.model.requests.post")
    def test_url_mode_does_not_fallback(self, mock_post, mock_session_cls):
        mock_post.return_value = _http_error(403)
        provider = DashscopeProvider(api_key="k", image_mode="url")
        with pytest.raises(ApiError):
            provider.vlm("https://img.example.com/a.jpg")
        assert mock_post.call_count == 1
        mock_session_cls.assert_not_called()


# ── 连通性探测 ────────────────────────────────────────────────

class TestProbe:

    @patch("app.extract.model.requests.post")
    def test_probe_llm(self, mock_post):
        mock_post.return_value = _stream_response("ok")
        result = DashscopeProvider(api_key="k", llm_base_url="https://llm.example.com/v1").probe("llm")
        assert result["ok"] is True
        assert result["target"] == "llm"
        assert result["model"] == "qwen3.7-flash"
        assert result["base_url"] == "https://llm.example.com/v1"

    @patch("app.extract.model.requests.get")
    def test_probe_asr_uses_policy(self, mock_get):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"data": {"upload_dir": "x"}}
        mock_get.return_value = resp
        result = DashscopeProvider(api_key="k").probe("asr")
        assert result["ok"] is True
        assert result["target"] == "asr"

    def test_probe_unknown_target(self):
        with pytest.raises(ConfigError):
            DashscopeProvider(api_key="k").probe("nope")


# ── 思考模式（qwen3.7/3.8-flash 默认开，必须显式关） ──────────

class TestThinkingMode:

    @patch("app.extract.model.requests.post")
    def test_qwen_thinking_off_by_default(self, mock_post):
        mock_post.return_value = _stream_response()
        provider = DashscopeProvider(api_key="k")
        provider.llm_clean("raw")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["enable_thinking"] is False

    @patch("app.extract.model.requests.post")
    def test_qwen_thinking_can_be_enabled(self, mock_post):
        mock_post.return_value = _stream_response()
        provider = DashscopeProvider(api_key="k", llm_thinking=True)
        provider.llm_clean("raw")
        assert mock_post.call_args.kwargs["json"]["enable_thinking"] is True

    @patch("app.extract.model.requests.post")
    def test_custom_provider_does_not_receive_qwen_extension(self, mock_post):
        mock_post.return_value = _stream_response()
        provider = DashscopeProvider(
            api_key="k", llm_base_url="https://third-party.example.com/v1", image_mode="url"
        )
        provider.llm_clean("raw")
        assert "enable_thinking" not in mock_post.call_args.kwargs["json"]
