"""模型服务端点解析（0.7）：ASR / VLM / LLM 可分别指向不同服务商。

背景：百炼 DashScope 已迁到「千问AI平台」（``maas.qianwenaiapi.com``），新模型
（新模型如 ``qwen3.7-flash`` / ``qwen3.8-flash``）只在 ``cn-beijing.maas.qianwenaiapi.com``
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

DEFAULT_ASR_BASE_URL = QIANWEN_ASR_BASE_URL
DEFAULT_CHAT_BASE_URL = QIANWEN_CHAT_BASE_URL

# 性价比选型（2026-10-21 按千问AI平台价格表核算）：
# - ASR: paraformer-v2 0.00008 元/秒（0.288 元/小时），且支持说话人分离；
#   qwen3-asr-flash-filetrans / fun-asr 均 0.00022 元/秒（0.792 元/小时）。
# - VLM/LLM: qwen3.7-flash 0.2/0.8 元每百万 token（≤32K），比 qwen3.8-flash
#   （0.8/2.7）便宜约 4 倍；两者都支持图片/视频、结构化输出、1M 上下文。
#   注意两者都默认开启思考模式，必须显式 enable_thinking=false，否则短文本
#   清洗也会烧掉上千 output token（实测）。
DEFAULT_ASR_MODEL = "paraformer-v2"
DEFAULT_VLM_MODEL = "qwen3.7-flash"
DEFAULT_LLM_MODEL = "qwen3.7-flash"
DEFAULT_THINKING = False

# VLM 图片传法：auto=非 DashScope 服务商自动转 base64；url=始终传 URL；
# base64=始终下载后内联（小红书防盗链/第三方网关不取图时用）。
IMAGE_MODES = ("auto", "url", "base64")
DEFAULT_IMAGE_MODE = "auto"

# 设置页预设。base_url 是「OpenAI 兼容 base」，不含 /chat/completions。
# 0.7 起只保留千问AI平台 + 自定义；旧百炼 DashScope 不再作为预设（需要时手填 URL）。
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


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def llm_thinking() -> bool:
    """LLM 思考模式，默认关：qwen3.7/3.8-flash 默认开，短文本清洗会烧上千 token。"""
    return _env_bool("RBCP_LLM_THINKING", DEFAULT_THINKING)


def vlm_thinking() -> bool:
    """VLM 思考模式，默认关（识图+OCR 不需要长思维链）。"""
    return _env_bool("RBCP_VLM_THINKING", DEFAULT_THINKING)


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
