from __future__ import annotations

import base64
import json
import logging
import mimetypes
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol, TypeVar, runtime_checkable
from urllib.parse import urlparse

import requests

from app.extract.contracts import Segment, build_canonical_text_and_segments
from app.extract.errors import ApiError, ConfigError, NetworkError, ParseError
from app.model_endpoints import (
    DEFAULT_ASR_BASE_URL,
    DEFAULT_ASR_MODEL,
    DEFAULT_CHAT_BASE_URL,
    DEFAULT_IMAGE_MODE,
    DEFAULT_LLM_MODEL,
    DEFAULT_VLM_MODEL,
    IMAGE_MODES,
)


_log = logging.getLogger("rbcp.model")

_BODY_EXCERPT_LIMIT = 2000

_RETRY_MAX_ATTEMPTS = 3

_T = TypeVar("_T")


def _retry_network(
    operation: str,
    fn: Callable[[], _T],
    *,
    max_attempts: int = _RETRY_MAX_ATTEMPTS,
) -> _T:
    """对网络抖动重试：仅捕 requests 的 Timeout/ConnectionError，指数退避（1/2/4s）。

    最多 max_attempts 次，全失败抛 NetworkError（带 operation）。
    非网络异常（含 HTTP 4xx 抛出的 ApiError）不重试，原样冒泡。
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_exc = exc
            _log.warning(
                "[%s] 网络异常第 %d/%d 次：%s",
                operation, attempt + 1, max_attempts, exc,
            )
            if attempt + 1 < max_attempts:
                time.sleep(2 ** attempt)
    _log.error("[%s] 网络重试 %d 次仍失败", operation, max_attempts)
    raise NetworkError(
        f"DashScope {operation} 网络重试 {max_attempts} 次仍失败",
        platform="dashscope",
        operation=operation,
        debug_context={"attempts": max_attempts},
    ) from last_exc


def _body_excerpt(response: requests.Response, limit: int = _BODY_EXCERPT_LIMIT) -> str:
    try:
        return (response.text or "")[:limit]
    except Exception:  # noqa: BLE001
        return ""


def _raise_dashscope_for_status(response: requests.Response, *, operation: str) -> None:
    """DashScope JSON API 非 2xx：先打 body 日志再抛 ApiError（带 code + payload）。"""
    if response.status_code < 400:
        return
    body = _body_excerpt(response)
    _log.error("[dashscope %s] HTTP %s body=%s", operation, response.status_code, body)
    raise ApiError(
        f"DashScope {operation} HTTP {response.status_code}",
        provider="dashscope",
        api_code=response.status_code,
        payload_excerpt=body,
        platform="dashscope",
        operation=operation,
    )


# 流式超时：connect 10s；read 是「相邻 SSE 块的最大间隔」不是整段生成时长，
# 600s 纯兜底（非流式时代 180s read 撞长文 ~300s 生成是 M5a 要修的根因）。
_STREAM_TIMEOUT = (10, 600)


def _parse_sse_stream(lines: Iterator[str]) -> tuple[str, dict[str, Any] | None]:
    """解析 OpenAI 兼容 SSE 流：累加 delta.content，取末块 usage。

    传 stream_options.include_usage 后最后一个数据块 choices=[] 且带 usage
    （spike 实证，见 _sandbox/spike_usage/）。服务端不回 usage 时返回 None。
    """
    parts: list[str] = []
    usage: dict[str, Any] | None = None
    for line in lines:
        if not line or not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            break
        chunk = json.loads(data)
        if isinstance(chunk.get("usage"), dict):
            usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            content = (choice.get("delta") or {}).get("content")
            if isinstance(content, str):
                parts.append(content)
    return "".join(parts), usage


def build_chat_completions_url(base_url: str) -> str:
    """OpenAI 兼容 base → chat/completions 完整 URL。

    允许用户填 ``.../v1``、``.../compatible-mode/v1``、``.../openai`` 等 base，
    也容忍直接填完整 ``.../chat/completions``（不重复拼）。
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ConfigError("模型服务 base_url 为空")
    if base.endswith("/chat/completions"):
        return base
    # 只填了域名（https://api.example.com）时补 /v1，避免拼成 /chat/completions 404。
    if urlparse(base).path in ("", "/"):
        base = base + "/v1"
    return base + "/chat/completions"


def build_asr_url(base_url: str, path: str) -> str:
    """DashScope 原生 ASR base（``.../api/v1``）+ 子路径。"""
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ConfigError("ASR 服务 base_url 为空")
    return base + "/" + path.lstrip("/")


DEFAULT_MEDIA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
}

# 单张图片内联上限：超过就报错，别把 base64 撑进几百 MB 的请求体。
_MAX_INLINE_IMAGE_BYTES = 10 * 1024 * 1024

LLM_CLEAN_PROMPT = (
    "请对以下原始文本做轻量清洗，只提升可读性，不新增信息，不摘要。"
    "保留原意，输出纯文本。"
    "如果文本里有「说话人1：」「说话人2：」这类说话人标记，必须原样保留标记和分行，不要合并或删除。\n\n"
)

VLM_PROMPT = (
    "请分析这张图片，提取可见文字并简要描述画面信息。"
    "不要编造图片中不存在的内容，输出纯文本。"
)


@runtime_checkable
class ModelProvider(Protocol):
    def asr(
        self, audio_url: str, referer: str | None = None
    ) -> tuple[str, tuple[Segment, ...]]:
        """转写音频 → (canonical text, segments)。segments 句级、char offset 对齐 text。"""
        ...

    def vlm(self, image_url: str, referer: str | None = None) -> str:
        ...

    def llm_clean(self, raw_text: str) -> str:
        ...


class DashscopeProvider:
    """DashScope 原生 ASR + OpenAI 兼容 VLM/LLM 的混合 provider。

    类名保留 ``DashscopeProvider`` 是历史兼容（CLI/Web/测试都这么 import）；现在
    ASR 与 chat 的 base_url / api_key 都可分别配置，因此它实际能接：
    - 千问AI平台（默认，``cn-beijing.maas.qianwenaiapi.com``）
    - 旧百炼 DashScope
    - 任意 OpenAI 兼容的 VLM/LLM 服务（OpenRouter / DeepSeek / Gemini 兼容层等）
    ASR 仍要求服务商兼容 DashScope 异步转写协议。
    """

    def __init__(
        self,
        api_key: str,
        asr_model: str = DEFAULT_ASR_MODEL,
        vlm_model: str = DEFAULT_VLM_MODEL,
        llm_model: str = DEFAULT_LLM_MODEL,
        diarization_enabled: bool = True,
        speaker_count: int | None = None,
        proxies: dict[str, str] | None = None,
        media_proxies: dict[str, str] | None = None,
        *,
        asr_base_url: str = DEFAULT_ASR_BASE_URL,
        chat_base_url: str = DEFAULT_CHAT_BASE_URL,
        asr_api_key: str | None = None,
        vlm_api_key: str | None = None,
        llm_api_key: str | None = None,
        vlm_base_url: str | None = None,
        llm_base_url: str | None = None,
        image_mode: str = DEFAULT_IMAGE_MODE,
    ) -> None:
        self.api_key = api_key
        self.asr_model = asr_model
        self.vlm_model = vlm_model
        self.llm_model = llm_model
        self.diarization_enabled = diarization_enabled
        self.speaker_count = speaker_count
        self.asr_base_url = asr_base_url
        self.llm_base_url = llm_base_url or chat_base_url
        self.vlm_base_url = vlm_base_url or self.llm_base_url
        # 每个能力可独立 key；未单独配就回退共享 api_key（旧 DASHSCOPE_API_KEY 语义）。
        self.asr_api_key = asr_api_key or api_key
        self.vlm_api_key = vlm_api_key or llm_api_key or api_key
        self.llm_api_key = llm_api_key or api_key
        self.image_mode = image_mode if image_mode in IMAGE_MODES else DEFAULT_IMAGE_MODE
        # 主站调用走 proxies；CDN 媒体字节走 media_proxies（默认 None=不走，护 IP 在主站层）
        self._proxies = proxies
        self._media_proxies = media_proxies
        # 用量账本（P1h）：每次模型调用追加一条 event，pipeline 收尾时读走。
        # fetch_single / _create_pipeline_fn 每任务建新 provider，无跨任务串账。
        self.usage_events: list[dict[str, Any]] = []

    def llm_clean(self, raw_text: str) -> str:
        payload = {
            "model": self.llm_model,
            "messages": [
                {
                    "role": "user",
                    "content": f"{LLM_CLEAN_PROMPT}{raw_text}",
                }
            ],
        }
        text, usage = self._stream_chat_completion(
            payload, operation="llm_clean", base_url=self.llm_base_url, api_key=self.llm_api_key
        )
        return text

    def complete_json(
        self, prompt: str, *, operation: str = "digest"
    ) -> tuple[str, dict[str, Any] | None]:
        """调 LLM 产 JSON（response_format=json_object）。给 rbcp-digest 用（鸭子注入）。

        复用 _stream_chat_completion → 继承 SSE 流式/重试/usage 记账（stage=operation）。
        并非所有第三方 OpenAI 兼容服务都支持 response_format：只有报错体明确指向
        response_format/JSON 时才去掉它重试一次，其余错误原样冒泡（不掩盖真实原因）。
        """
        payload = {
            "model": self.llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }
        try:
            return self._stream_chat_completion(
                payload,
                operation=operation,
                base_url=self.llm_base_url,
                api_key=self.llm_api_key,
            )
        except ApiError as exc:
            body = (exc.payload_excerpt or "").lower()
            unsupported = "response_format" in body or "json mode" in body
            if exc.api_code not in {400, 404, 422} or not unsupported:
                raise
            _log.warning(
                "[%s] 服务商不支持 response_format，去掉后重试一次（HTTP %s）",
                operation, exc.api_code,
            )
            payload.pop("response_format", None)
            return self._stream_chat_completion(
                payload,
                operation=operation,
                base_url=self.llm_base_url,
                api_key=self.llm_api_key,
            )

    def vlm(self, image_url: str, referer: str | None = None) -> str:
        """图片理解。

        图片传法由 ``image_mode`` 决定：
        - ``auto``：DashScope/千问（能直接抓公网 URL）传 URL；第三方服务先下载并
          转 base64 data URL（避免防盗链/网关不取图）。
        - ``url``：始终传 URL，失败不重试。
        - ``base64``：始终下载后内联。

        ``url``/``auto`` 下若服务商取图失败（400/403/404/422），回退下载一次再试，
        对齐 SPEC「URL 优先喂 VLM，失败回退 tempfile」的双轨约定。
        """
        inline = self._should_inline_image(image_url)
        if inline:
            image_url = self._image_as_data_url(image_url, referer)
        payload = self._vlm_payload(image_url)
        try:
            text, usage = self._stream_chat_completion(
                payload, operation="vlm", base_url=self.vlm_base_url, api_key=self.vlm_api_key
            )
            return text
        except ApiError as exc:
            if (
                inline
                or self.image_mode != "auto"
                or not self._is_image_fetch_error(exc)
                or not _is_http_url(image_url)
            ):
                raise
            _log.warning("[vlm] URL 直传失败（HTTP %s），回退 base64 重试", exc.api_code)
            try:
                data_url = self._image_as_data_url(image_url, referer)
            except Exception:  # noqa: BLE001 - 下载失败时保留原始模型错误
                raise exc
            text, usage = self._stream_chat_completion(
                self._vlm_payload(data_url),
                operation="vlm",
                base_url=self.vlm_base_url,
                api_key=self.vlm_api_key,
            )
            return text

    def _vlm_payload(self, image_url: str) -> dict[str, Any]:
        return {
            "model": self.vlm_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VLM_PROMPT},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
        }

    def _should_inline_image(self, image_url: str) -> bool:
        if image_url.startswith("data:") or not _is_http_url(image_url):
            return False
        if self.image_mode == "base64":
            return True
        if self.image_mode == "url":
            return False
        # auto：只有千问/百炼的服务端会主动抓公网图片；第三方网关通常不抓。
        return not _provider_fetches_image_url(self.vlm_base_url)

    @staticmethod
    def _is_image_fetch_error(exc: ApiError) -> bool:
        return exc.api_code in {400, 403, 404, 422}

    def _image_as_data_url(self, image_url: str, referer: str | None) -> str:
        """下载图片 → data URL（带 referer，防小红书防盗链；超 10MB 拒绝）。"""
        headers = dict(DEFAULT_MEDIA_HEADERS)
        if referer:
            headers["Referer"] = referer
        with requests.Session() as session:
            session.trust_env = False
            if self._media_proxies:
                session.proxies.update(self._media_proxies)
            with session.get(
                image_url, headers=headers, timeout=60, stream=True, allow_redirects=True
            ) as response:
                if response.status_code >= 400:
                    body = _body_excerpt(response)
                    _log.error(
                        "[download_image] HTTP %s url=%s body=%s",
                        response.status_code, image_url, body,
                    )
                    raise NetworkError(
                        f"image download HTTP {response.status_code}",
                        operation="download_image",
                        debug_context={"status": response.status_code, "url": image_url},
                    )
                content_type = (response.headers.get("Content-Type") or "image/jpeg").split(
                    ";", 1
                )[0].strip() or "image/jpeg"
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > _MAX_INLINE_IMAGE_BYTES:
                        raise NetworkError(
                            f"image too large (> {_MAX_INLINE_IMAGE_BYTES} bytes)",
                            operation="download_image",
                            debug_context={"url": image_url},
                        )
                    chunks.append(chunk)
        encoded = base64.b64encode(b"".join(chunks)).decode("ascii")
        return f"data:{content_type};base64,{encoded}"

    def probe(self, kind: str) -> dict[str, Any]:
        """连通性探测：ASR 只取上传凭证（不计费），VLM/LLM 发一条极短 chat。

        给设置页「测试连接」用；失败抛 RbcpError（route 层翻成人话）。
        """
        t0 = time.monotonic()
        if kind == "asr":
            self._get_upload_policy()
            return {
                "ok": True,
                "target": "asr",
                "model": self.asr_model,
                "base_url": self.asr_base_url,
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }
        if kind == "vlm":
            base_url, api_key, model = self.vlm_base_url, self.vlm_api_key, self.vlm_model
        elif kind == "llm":
            base_url, api_key, model = self.llm_base_url, self.llm_api_key, self.llm_model
        else:
            raise ConfigError(f"未知的探测目标：{kind}")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "只回复 ok"}],
            "max_tokens": 8,
        }
        text, _usage = self._stream_chat_completion(
            payload,
            operation=f"probe_{kind}",
            base_url=base_url,
            api_key=api_key,
            timeout=(10, 60),
        )
        return {
            "ok": True,
            "target": kind,
            "model": model,
            "base_url": base_url,
            "reply": text.strip()[:100],
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
        }

    def _stream_chat_completion(
        self,
        payload: dict[str, Any],
        *,
        operation: str,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: tuple[int, int] = _STREAM_TIMEOUT,
    ) -> tuple[str, dict[str, Any] | None]:
        """流式调 chat/completions：建连可重试，流中断不重试（整段重跑放大等待）。

        usage 顺手记进 self.usage_events（token 数 + 耗时）。
        """
        url = build_chat_completions_url(base_url or self.llm_base_url)
        key = api_key if api_key is not None else self.llm_api_key
        body = {
            **payload,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        t0 = time.monotonic()
        response = _retry_network(
            operation,
            lambda: requests.post(
                url,
                headers=self._json_auth_headers(key),
                json=body,
                timeout=timeout,
                stream=True,
                proxies=self._proxies,
            ),
        )
        _raise_dashscope_for_status(response, operation=operation)
        try:
            text, usage = _parse_sse_stream(response.iter_lines(decode_unicode=True))
        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
        ) as exc:
            _log.error("[%s] SSE 流中断（不重试）：%s", operation, exc)
            raise NetworkError(
                f"{operation} 流式响应中断",
                platform="model",
                operation=operation,
            ) from exc
        finally:
            # [DONE] 即停不读到 EOF；不 close 会占住连接池里的连接（Codex review）
            response.close()
        self.usage_events.append({
            "stage": operation,
            "model": payload.get("model"),
            "input_tokens": (usage or {}).get("prompt_tokens"),
            "output_tokens": (usage or {}).get("completion_tokens"),
            "elapsed_seconds": round(time.monotonic() - t0, 1),
        })
        return text, usage

    def asr(
        self, audio_url: str, referer: str | None = None
    ) -> tuple[str, tuple[Segment, ...]]:
        t0 = time.monotonic()
        oss_url = self._upload_audio_to_oss(audio_url, referer=referer)
        task_id = self._submit_transcription_task(oss_url)
        text, segments, audio_seconds = self._wait_for_transcription(task_id)
        self.usage_events.append({
            "stage": "asr",
            "model": self.asr_model,
            "audio_seconds": audio_seconds,
            "elapsed_seconds": round(time.monotonic() - t0, 1),
        })
        return text, segments

    def _json_auth_headers(self, api_key: str | None = None) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key if api_key is not None else self.api_key}",
            "Content-Type": "application/json",
        }

    def _upload_audio_to_oss(self, audio_url: str, referer: str | None = None) -> str:
        policy = self._get_upload_policy()
        media_headers = dict(DEFAULT_MEDIA_HEADERS)
        if referer:
            media_headers["Referer"] = referer

        with requests.Session() as session:
            session.trust_env = False  # 防环境变量代理把 CDN 媒体字节也带走
            if self._media_proxies:
                session.proxies.update(self._media_proxies)
            with session.get(
                audio_url,
                headers=media_headers,
                timeout=120,
                stream=True,
                allow_redirects=True,
            ) as audio_response:
                if audio_response.status_code >= 400:
                    body = _body_excerpt(audio_response)
                    _log.error(
                        "[download_media] HTTP %s url=%s body=%s",
                        audio_response.status_code, audio_url, body,
                    )
                    raise NetworkError(
                        f"audio download HTTP {audio_response.status_code}",
                        operation="download_media",
                        debug_context={"status": audio_response.status_code, "url": audio_url},
                    )
                content_length = _content_length(audio_response)
                file_name = _filename_from_url(audio_url)
                content_type = _content_type(audio_url, audio_response, file_name)
                key = f"{str(policy['upload_dir']).rstrip('/')}/{file_name}"

                form = StreamingMultipartForm(
                    boundary=f"dashscope-{uuid.uuid4().hex}",
                    fields=[
                        ("OSSAccessKeyId", policy["oss_access_key_id"]),
                        ("Signature", policy["signature"]),
                        ("policy", policy["policy"]),
                        ("x-oss-object-acl", policy["x_oss_object_acl"]),
                        ("x-oss-forbid-overwrite", policy["x_oss_forbid_overwrite"]),
                        ("key", key),
                        ("success_action_status", "200"),
                    ],
                    file_field_name="file",
                    file_name=file_name,
                    file_content_type=content_type,
                    file_chunks=audio_response.iter_content(chunk_size=1024 * 1024),
                    file_size=content_length,
                )
                upload_response = session.post(
                    policy["upload_host"],
                    data=form,
                    headers={
                        "Content-Type": f"multipart/form-data; boundary={form.boundary}",
                        "Content-Length": str(len(form)),
                    },
                    timeout=(60, 1800),
                )
                if upload_response.status_code >= 400:
                    body = _body_excerpt(upload_response)
                    _log.error("[oss_upload] HTTP %s body=%s", upload_response.status_code, body)
                    raise ApiError(
                        f"OSS upload HTTP {upload_response.status_code}",
                        provider="oss",
                        api_code=upload_response.status_code,
                        payload_excerpt=body,
                        platform="dashscope",
                        operation="oss_upload",
                    )
        return f"oss://{key}"

    def _get_upload_policy(self) -> dict[str, Any]:
        response = _retry_network(
            "get_upload_policy",
            lambda: requests.get(
                build_asr_url(self.asr_base_url, "uploads"),
                headers=self._json_auth_headers(self.asr_api_key),
                params={
                    "action": "getPolicy",
                    "model": self.asr_model,
                },
                timeout=60,
                proxies=self._proxies,
            ),
        )
        _raise_dashscope_for_status(response, operation="get_upload_policy")
        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, dict):
            _log.error("[get_upload_policy] response missing data: %r", payload)
            raise ParseError(
                "DashScope upload policy response missing data",
                platform="dashscope", operation="get_upload_policy",
            )
        return data

    def _submit_transcription_task(self, oss_url: str) -> str:
        headers = {
            **self._json_auth_headers(self.asr_api_key),
            "X-DashScope-Async": "enable",
            "X-DashScope-OssResourceResolve": "enable",
        }
        parameters: dict[str, Any] = {
            "channel_id": [0],
            "language_hints": ["zh"],
        }
        if self.diarization_enabled:
            # 说话人分离仅单声道生效；channel_id=[0] 已满足。speaker_count 为可选人数提示。
            parameters["diarization_enabled"] = True
            if self.speaker_count:
                parameters["speaker_count"] = self.speaker_count
        body = {
            "model": self.asr_model,
            "input": {"file_urls": [oss_url]},
            "parameters": parameters,
        }
        response = _retry_network(
            "submit_transcription",
            lambda: requests.post(
                build_asr_url(self.asr_base_url, "services/audio/asr/transcription"),
                headers=headers,
                json=body,
                timeout=60,
                proxies=self._proxies,
            ),
        )
        if response.status_code >= 400:
            resp_body = _body_excerpt(response)
            _log.error(
                "[submit_transcription] HTTP %s req_body=%r resp=%s",
                response.status_code, body, resp_body,
            )
            raise ApiError(
                f"DashScope transcription submit HTTP {response.status_code}",
                provider="dashscope",
                api_code=response.status_code,
                payload_excerpt=resp_body,
                platform="dashscope",
                operation="submit_transcription",
            )
        payload = response.json()
        task_id = (payload.get("output") or {}).get("task_id")
        if not task_id:
            _log.error("[submit_transcription] response missing task_id: %r", payload)
            raise ParseError(
                "DashScope transcription response missing task_id",
                platform="dashscope", operation="submit_transcription",
            )
        return task_id

    def _wait_for_transcription(
        self, task_id: str
    ) -> tuple[str, tuple[Segment, ...], int | None]:
        """轮询转写任务到完成。返回 (文本, segments, 计费音频秒数)。

        计费秒数来自 poll 响应**顶层** usage.duration（spike 实证），不是 output 里。
        """
        headers = self._json_auth_headers(self.asr_api_key)
        deadline = time.monotonic() + 7200
        last_payload: dict[str, Any] | None = None

        while time.monotonic() < deadline:
            response = _retry_network(
                "poll_transcription",
                lambda: requests.get(
                    build_asr_url(self.asr_base_url, f"tasks/{task_id}"),
                    headers=headers,
                    timeout=60,
                    proxies=self._proxies,
                ),
            )
            _raise_dashscope_for_status(response, operation="poll_transcription")
            last_payload = response.json()
            output = last_payload.get("output") or {}
            task_status = output.get("task_status")

            if task_status == "SUCCEEDED":
                text, segments = _extract_transcription_text(output, proxies=self._proxies)
                if text:
                    audio_seconds = (last_payload.get("usage") or {}).get("duration")
                    return text, segments, audio_seconds
                _log.error("[poll_transcription] succeeded without text: %r", last_payload)
                raise ParseError(
                    "DashScope transcription succeeded without text",
                    platform="dashscope", operation="poll_transcription",
                )
            if task_status == "FAILED":
                excerpt = str(last_payload)[:_BODY_EXCERPT_LIMIT]
                _log.error("[poll_transcription] task FAILED: %s", excerpt)
                raise ApiError(
                    "DashScope transcription failed",
                    provider="dashscope",
                    payload_excerpt=excerpt,
                    platform="dashscope", operation="poll_transcription",
                )

            time.sleep(2)

        _log.error("[poll_transcription] timed out: %r", last_payload)
        raise NetworkError(
            "DashScope transcription timed out",
            platform="dashscope", operation="poll_transcription",
        )


class StreamingMultipartForm:
    def __init__(
        self,
        *,
        boundary: str,
        fields: list[tuple[str, str]],
        file_field_name: str,
        file_name: str,
        file_content_type: str,
        file_chunks: Iterator[bytes],
        file_size: int,
    ) -> None:
        self.boundary = boundary
        self.file_chunks = file_chunks
        self.file_size = file_size
        self._prefix = self._build_prefix(fields, file_field_name, file_name, file_content_type)
        self._suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")

    def __iter__(self) -> Iterator[bytes]:
        yield self._prefix
        for chunk in self.file_chunks:
            if chunk:
                yield chunk
        yield self._suffix

    def __len__(self) -> int:
        return len(self._prefix) + self.file_size + len(self._suffix)

    def _build_prefix(
        self,
        fields: list[tuple[str, str]],
        file_field_name: str,
        file_name: str,
        file_content_type: str,
    ) -> bytes:
        parts: list[bytes] = []
        for name, value in fields:
            parts.append(
                (
                    f"--{self.boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    f"{value}\r\n"
                ).encode("utf-8")
            )
        parts.append(
            (
                f"--{self.boundary}\r\n"
                f'Content-Disposition: form-data; name="{file_field_name}"; filename="{file_name}"\r\n'
                f"Content-Type: {file_content_type}\r\n\r\n"
            ).encode("utf-8")
        )
        return b"".join(parts)


def _extract_transcription_text(
    output: dict[str, Any], *, proxies: dict[str, str] | None = None
) -> tuple[str, tuple[Segment, ...]]:
    result = output.get("result") or {}
    urls = []
    if result.get("transcription_url"):
        urls.append(result["transcription_url"])
    for item in output.get("results") or []:
        if isinstance(item, dict) and item.get("transcription_url"):
            urls.append(item["transcription_url"])

    for url in urls:
        response = _retry_network(
            "fetch_transcription_result",
            lambda url=url: requests.get(url, timeout=60, proxies=proxies),
        )
        _raise_dashscope_for_status(response, operation="fetch_transcription_result")
        text, segments = build_canonical_text_and_segments(response.json())
        if text:
            return text, segments
    return "", ()


def _format_transcription(payload: dict[str, Any]) -> str:
    """把转写结果 JSON 格式化为 canonical 文本（多说话人「说话人N：」分组）。

    薄包装：复用 build_canonical_text_and_segments 的 text 部分，与 segments 同源、
    不重复装配逻辑（DRY）。保留此函数名供旧测试 / 旧调用兼容。
    """
    return build_canonical_text_and_segments(payload)[0]


def _content_length(response: requests.Response) -> int:
    value = response.headers.get("Content-Length") or "0"
    try:
        length = int(value)
    except (TypeError, ValueError):
        length = 0
    if length <= 0:
        _log.error("[download_media] remote audio missing Content-Length")
        raise NetworkError(
            "Remote audio is missing Content-Length",
            operation="download_media",
        )
    return length


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = Path(path).name
    return name or f"{uuid.uuid4().hex}.bin"


def _content_type(source_url: str, response: requests.Response, file_name: str) -> str:
    header_value = response.headers.get("Content-Type") or ""
    content_type = header_value.split(";", 1)[0].strip()
    if content_type:
        return content_type
    guessed, _ = mimetypes.guess_type(file_name or source_url)
    return guessed or "application/octet-stream"


def _is_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _provider_fetches_image_url(base_url: str) -> bool:
    """千问/百炼的服务端会主动抓公网图片；第三方兼容网关大多不会。

    ``auto`` 模式下用它决定「URL 直传」还是「先下载转 base64」。
    """
    host = (urlparse(base_url).hostname or "").lower()
    return host.endswith("qianwenaiapi.com") or host.endswith("aliyuncs.com")
