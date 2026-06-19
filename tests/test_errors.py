"""service/errors.py 异常契约测试。

锁定 M4a 契约：异常最小集 + 结构化字段 + format_error_for_user()。
M4b 各 service 按这些类抛、M4c batch 按 kind/reason 分流，都依赖本契约。
"""

import pytest

from app.extract.errors import (
    RbcpError,
    UnsupportedUrlError,
    ConfigError,
    NetworkError,
    ApiError,
    RiskControlError,
    AuthError,
    ParseError,
    format_error_for_user,
)


# ── 基类结构化字段 ───────────────────────────────────────────────

class TestRbcpErrorFields:

    def test_message_is_str_exception(self):
        exc = ConfigError("missing api key")
        assert str(exc) == "missing api key"
        assert exc.message == "missing api key"

    def test_debug_context_defaults_to_empty_dict(self):
        exc = ConfigError("x")
        assert exc.debug_context == {}

    def test_carries_platform_and_operation(self):
        exc = NetworkError("timeout", platform="bilibili", operation="fetch_detail")
        assert exc.platform == "bilibili"
        assert exc.operation == "fetch_detail"

    def test_retryable_falls_back_to_class_default(self):
        assert NetworkError("x").retryable is True
        assert ConfigError("x").retryable is False

    def test_explicit_retryable_overrides_default(self):
        assert NetworkError("x", retryable=False).retryable is False
        assert ConfigError("x", retryable=True).retryable is True


# ── 各子类 kind / default_retryable ─────────────────────────────

class TestSubclassKinds:

    @pytest.mark.parametrize("cls,kind,retryable", [
        (UnsupportedUrlError, "unsupported_url", False),
        (ConfigError, "config", False),
        (NetworkError, "network", True),
        (ApiError, "api", False),
        (RiskControlError, "risk_control", True),
        (AuthError, "auth", False),
        (ParseError, "parse", False),
    ])
    def test_kind_and_default_retryable(self, cls, kind, retryable):
        exc = cls("msg")
        assert exc.kind == kind
        assert exc.retryable is retryable

    def test_all_subclasses_are_rbcp_error(self):
        for cls in (UnsupportedUrlError, ConfigError, NetworkError, ApiError,
                    RiskControlError, AuthError, ParseError):
            assert issubclass(cls, RbcpError)


# ── ApiError 专属字段 ───────────────────────────────────────────

class TestApiError:

    def test_carries_provider_api_code_payload(self):
        exc = ApiError("FAILED", provider="dashscope", api_code=400,
                       payload_excerpt='{"code":400,"msg":"bad"}')
        assert exc.provider == "dashscope"
        assert exc.api_code == 400
        assert exc.payload_excerpt == '{"code":400,"msg":"bad"}'

    def test_mirrors_fields_into_debug_context(self):
        exc = ApiError("x", provider="bilibili", api_code=-412)
        assert exc.debug_context["provider"] == "bilibili"
        assert exc.debug_context["api_code"] == -412


# ── AuthError 专属字段 ──────────────────────────────────────────

class TestAuthError:

    def test_carries_reason(self):
        exc = AuthError("token gone", reason="token_expired")
        assert exc.reason == "token_expired"
        assert exc.debug_context["reason"] == "token_expired"


# ── format_error_for_user 人话映射 ──────────────────────────────

class TestFormatErrorForUser:

    def test_user_message_override_wins(self):
        exc = NetworkError("connection reset", user_message="网络抖了，重试一下")
        assert format_error_for_user(exc) == "网络抖了，重试一下"

    def test_unsupported_url_message(self):
        out = format_error_for_user(UnsupportedUrlError("douyin"))
        assert "不支持" in out

    def test_risk_control_message(self):
        out = format_error_for_user(RiskControlError("captcha"))
        assert "风控" in out

    def test_auth_token_expired_vs_cookie_expired(self):
        token = format_error_for_user(AuthError("x", reason="token_expired"))
        cookie = format_error_for_user(AuthError("x", reason="cookie_expired"))
        assert "重新抓清单" in token
        assert "login" in cookie or "登录" in cookie
        assert token != cookie

    def test_api_message_includes_provider_and_code_but_not_payload(self):
        exc = ApiError("x", provider="dashscope", api_code=429,
                       payload_excerpt="SECRET_BODY_SHOULD_NOT_LEAK")
        out = format_error_for_user(exc)
        assert "dashscope" in out
        assert "429" in out
        assert "SECRET_BODY_SHOULD_NOT_LEAK" not in out

    def test_network_message_includes_exit_ip_when_present(self):
        exc = NetworkError("proxy dead", debug_context={"exit_ip": "1.2.3.4"})
        out = format_error_for_user(exc)
        assert "1.2.3.4" in out

    def test_non_rbcp_error_falls_back(self):
        out = format_error_for_user(ValueError("some raw python error"))
        assert "some raw python error" in out

    def test_non_rbcp_error_truncates_long_message(self):
        out = format_error_for_user(ValueError("x" * 1000))
        assert len(out) < 500
