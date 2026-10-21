"""模型服务端点解析（0.7）：ASR / VLM / LLM 可分别指向不同服务商。

背景：百炼 DashScope 已迁到「千问AI平台」（``maas.qianwenaiapi.com``），新模型
（如本版默认 VLM ``qwen3.8-flash``）只在 ``cn-beijing.maas.qianwenaiapi.com``
区域端点提供；旧默认 VLM ``qwen3-vl-flash`` 不在新模型列表里。同时用户需要接
第三方 OpenAI 兼容服务。因此把「服务商/模型」从硬编码 URL 里拆出来，按能力分别解析：

- **ASR**：仍走 DashScope 原生异步转写协议（上传 policy → 提交任务 → 轮询）。
  只要服务商兼容这套协议（千问AI平台 / 百炼），就能换 base_url + key + model。
- **VLM / LLM**：走 OpenAI 兼容 ``/chat/completions``，可指向任意兼容服务
  （千问AI平台、OpenRouter、DeepSeek、Gemini 的 OpenAI 兼容层、自建网关等）。

解析优先级（空串一律等同未设；``RBCP_*_API_KEY`` 为空时回退共享 key）::

    ASR:  RBCP_ASR_BASE_URL  > 默认
    ASR:  RBCP_ASR_API_KEY   > DASHSCOPE_API_KEY
    LLM:  RBCP_LLM_BASE_URL  > 默认
    LLM:  RBCP_LLM_API_KEY   > DASHSCOPE_API_KEY
    VLM:  RBCP_VLM_BASE_URL  > RBCP_LLM_BASE_URL > 默认
    VLM:  RBCP_VLM_API_KEY   > RBCP_LLM_API_KEY  > DASHSCOPE_API_KEY

默认值全部指向千问AI平台；要回旧百炼，把 base_url 设成
``https://dashscope.aliyuncs.com/api/v1``（ASR）和
``https://dashscope.aliyuncs.com/compatible-mode/v1``（VLM/LLM）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# 千问AI平台（DashScope 的新入口）
QIANWEN_ASR_BASE_URL = "https://cn-beijing.maas.qianwenaiapi.com/api/v1"
QIANWEN_CHAT_BASE_URL = "https://cn-beijing.maas.qianwenaiapi.com/compatible-mode/v1"

# 旧百炼 DashScope（保留 preset，供老 key / 老模型继续用）
DASHSCOPE_ASR_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
DASHSCOPE_CHAT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

DEFAULT_ASR_BASE_URL = QIANWEN_ASR_BASE_URL
DEFAULT_CHAT_BASE_URL = QIANWEN_CHAT_BASE_URL

DEFAULT_ASR_MODEL = "paraformer-v2"
DEFAULT_VLM_MODEL = "qwen3.8-flash"
DEFAULT_LLM_MODEL = "qwen-plus"

# VLM 图片传法：auto=非 DashScope 服务商自动转 base64；url=始终传 URL；
# base64=始终下载后内联（小红书防盗链/第三方网关不取图时用）。
IMAGE_MODES = ("auto", "url", "base64")
DEFAULT_IMAGE_MODE = "auto"

# 设置页预设。base_url 是「OpenAI 兼容 base」，不含 /chat/completions。
# 预设同时带推荐模型：切旧百炼时必须把 VLM 换回 qwen3-vl-flash，否则新模型在旧端点 404。
PROVIDER_PRESETS = (
    {
        "id": "qianwen",
        "label": "千问AI平台（默认）",
        "asr_base_url": QIANWEN_ASR_BASE_URL,
        "llm_base_url": QIANWEN_CHAT_BASE_URL,
        "asr_model": DEFAULT_ASR_MODEL,
        "vlm_model": DEFAULT_VLM_MODEL,
        "llm_model": DEFAULT_LLM_MODEL,
    },
    {
        "id": "dashscope",
        "label": "百炼 DashScope（旧）",
        "asr_base_url": DASHSCOPE_ASR_BASE_URL,
        "llm_base_url": DASHSCOPE_CHAT_BASE_URL,
        "asr_model": DEFAULT_ASR_MODEL,
        "vlm_model": "qwen3-vl-flash",
        "llm_model": DEFAULT_LLM_MODEL,
    },
    {
        "id": "custom",
        "label": "自定义 OpenAI 兼容",
        "asr_base_url": "",
        "llm_base_url": "",
        "asr_model": "",
        "vlm_model": "",
        "llm_model": "",
    },
)


@dataclass(frozen=True)
class Endpoint:
    """单个能力的生效配置。api_key 可能为空（由调用方回退）。"""

    base_url: str
    api_key: str
    model: str


def _env(*names: str) -> str:
    """按顺序取第一个非空环境变量（strip 后）；都没有返回空串。

    用 ``or`` 语义而非 ``os.getenv(name, default)``：设置页历史上会把空串写进
    env，空串必须等同未设，否则 ``model=""`` 会原样发给服务商（HTTP 400）。
    """
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def shared_api_key() -> str:
    """兼容旧配置的共享 key。"""
    return _env("DASHSCOPE_API_KEY")


def asr_endpoint() -> Endpoint:
    return Endpoint(
        base_url=_env("RBCP_ASR_BASE_URL") or DEFAULT_ASR_BASE_URL,
        api_key=_env("RBCP_ASR_API_KEY"),
        model=_env("RBCP_ASR_MODEL") or DEFAULT_ASR_MODEL,
    )


def llm_endpoint() -> Endpoint:
    return Endpoint(
        base_url=_env("RBCP_LLM_BASE_URL") or DEFAULT_CHAT_BASE_URL,
        api_key=_env("RBCP_LLM_API_KEY"),
        model=_env("RBCP_LLM_MODEL") or DEFAULT_LLM_MODEL,
    )


def vlm_endpoint() -> Endpoint:
    """VLM 未单独配置时继承 LLM（多数人 VLM/LLM 用同一服务商）。"""
    llm = llm_endpoint()
    return Endpoint(
        base_url=_env("RBCP_VLM_BASE_URL") or llm.base_url,
        api_key=_env("RBCP_VLM_API_KEY") or llm.api_key,
        model=_env("RBCP_VLM_MODEL") or DEFAULT_VLM_MODEL,
    )


def vlm_image_mode() -> str:
    mode = _env("RBCP_VLM_IMAGE_MODE").lower() or DEFAULT_IMAGE_MODE
    return mode if mode in IMAGE_MODES else DEFAULT_IMAGE_MODE


def detect_preset(asr_base_url: str, chat_base_url: str) -> str:
    """按 base_url 反推设置页预设 id（只用于 UI 回显，未知即 custom）。"""
    asr = (asr_base_url or "").rstrip("/")
    chat = (chat_base_url or "").rstrip("/")
    for preset in PROVIDER_PRESETS:
        if preset["id"] == "custom":
            continue
        if asr == preset["asr_base_url"].rstrip("/") and chat == preset["llm_base_url"].rstrip("/"):
            return preset["id"]
    return "custom"
