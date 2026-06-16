"""rbcp 业务异常最小集（M4a 锁定契约）。

扁平继承：所有子类直接继承 RbcpError，区分靠 `kind` 字段 + 类型，不建中间抽象层
（遵循 CLAUDE.md 反过度抽象）。携带结构化字段，供 CLI/Web 出口层统一翻人话。

- service 层：抛这些类，`message` 放技术原因、`payload_excerpt` 放 response body。
  **不**在 service 层调 format_error_for_user（那是出口层的事）。
- CLI/Web 出口层：捕获后调 format_error_for_user(exc) 出人话；调试细节进日志。
"""

from __future__ import annotations

from typing import Any, Literal

ErrorKind = Literal[
    "unsupported_url", "config", "network", "api", "risk_control", "auth", "parse",
]


class RbcpError(Exception):
    """所有 rbcp 业务异常基类。"""

    kind: ErrorKind = "config"
    default_retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        platform: str | None = None,
        operation: str | None = None,
        retryable: bool | None = None,
        user_message: str | None = None,
        debug_context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.platform = platform
        self.operation = operation
        self.retryable = self.default_retryable if retryable is None else retryable
        self.user_message = user_message
        self.debug_context = dict(debug_context) if debug_context else {}


class UnsupportedUrlError(RbcpError):
    kind = "unsupported_url"
    default_retryable = False


class ConfigError(RbcpError):
    kind = "config"
    default_retryable = False


class NetworkError(RbcpError):
    kind = "network"
    default_retryable = True


class ApiError(RbcpError):
    kind = "api"
    default_retryable = False

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        api_code: str | int | None = None,
        payload_excerpt: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.provider = provider
        self.api_code = api_code
        self.payload_excerpt = payload_excerpt
        self.debug_context.setdefault("provider", provider)
        self.debug_context.setdefault("api_code", api_code)
        self.debug_context.setdefault("payload_excerpt", payload_excerpt)


class RiskControlError(RbcpError):
    kind = "risk_control"
    default_retryable = True


class AuthError(RbcpError):
    """Cookie 失效 + token 过期合并（贪婪并入）。reason 区分具体情形。"""

    kind = "auth"
    default_retryable = False

    def __init__(
        self,
        message: str,
        *,
        reason: Literal["cookie_expired", "token_expired"] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.reason = reason
        self.debug_context.setdefault("reason", reason)


class ParseError(RbcpError):
    kind = "parse"
    default_retryable = False


def format_error_for_user(exc: Exception) -> str:
    """把异常翻成给终端用户看的可操作中文。CLI 和 Web 共用。

    - RbcpError：优先 user_message；否则按 kind 出默认人话。
    - 非 RbcpError：兜底「未知错误」+ str(exc) 截断。
    不含 traceback；调试细节（debug_context / payload_excerpt）由日志层落，不进这里。
    """
    if not isinstance(exc, RbcpError):
        return f"未知错误：{str(exc)[:200]}"

    if exc.user_message:
        return exc.user_message

    if exc.kind == "unsupported_url":
        return "不支持的链接：只支持 B 站和小红书。"
    if exc.kind == "config":
        return f"配置有误：{exc.message}。请检查 .env（API Key / 代理地址）。"
    if exc.kind == "network":
        exit_ip = exc.debug_context.get("exit_ip")
        if exit_ip:
            return f"代理未生效（当前出口={exit_ip}）。请检查代理是否连通。"
        return "网络或服务响应超时（可能内容过长，或网络 / 服务不稳）。请稍后重试。"
    if exc.kind == "api":
        provider = exc.debug_context.get("provider") or "服务端"
        code = exc.debug_context.get("api_code")
        code_part = f" code={code}" if code is not None else ""
        return f"服务端报错（{provider}{code_part}）。稍后重试或查看日志。"
    if exc.kind == "risk_control":
        return "触发风控，建议慢速 / 换节点 / 稍后重试。"
    if exc.kind == "auth":
        if exc.debug_context.get("reason") == "token_expired":
            return "访问令牌已过期（xsec_token 失效）。单篇请重新复制分享链接；批量请重新抓清单。"
        return "登录已失效，请重跑 rbcp login。"
    if exc.kind == "parse":
        return "页面解析失败（可能改版 / 空壳 / 风控）。稍后重试或反馈。"
    return f"未知错误：{exc.message[:200]}"
