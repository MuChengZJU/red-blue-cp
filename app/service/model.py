from __future__ import annotations

import mimetypes
import time
import uuid
from pathlib import Path
from typing import Any, Iterator, Protocol, runtime_checkable
from urllib.parse import urlparse

import requests


CHAT_COMPLETIONS_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
UPLOAD_POLICY_URL = "https://dashscope.aliyuncs.com/api/v1/uploads"
TRANSCRIPTION_URL = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
TASK_URL_TEMPLATE = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"

DEFAULT_MEDIA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
}

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
    def asr(self, audio_url: str, referer: str | None = None) -> str:
        ...

    def vlm(self, image_url: str) -> str:
        ...

    def llm_clean(self, raw_text: str) -> str:
        ...


class DashscopeProvider:
    def __init__(
        self,
        api_key: str,
        asr_model: str = "paraformer-v2",
        vlm_model: str = "qwen3-vl-flash",
        llm_model: str = "qwen-plus",
        diarization_enabled: bool = True,
        speaker_count: int | None = None,
        proxies: dict[str, str] | None = None,
        media_proxies: dict[str, str] | None = None,
    ) -> None:
        self.api_key = api_key
        self.asr_model = asr_model
        self.vlm_model = vlm_model
        self.llm_model = llm_model
        self.diarization_enabled = diarization_enabled
        self.speaker_count = speaker_count
        # 主站调用走 proxies；CDN 媒体字节走 media_proxies（默认 None=不走，护 IP 在主站层）
        self._proxies = proxies
        self._media_proxies = media_proxies

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
        response = requests.post(
            CHAT_COMPLETIONS_URL,
            headers=self._json_auth_headers(),
            json=payload,
            timeout=(10, 180),
            proxies=self._proxies,
        )
        response.raise_for_status()
        return _extract_chat_text(response.json())

    def vlm(self, image_url: str) -> str:
        payload = {
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
        response = requests.post(
            CHAT_COMPLETIONS_URL,
            headers=self._json_auth_headers(),
            json=payload,
            timeout=(10, 180),
            proxies=self._proxies,
        )
        response.raise_for_status()
        return _extract_chat_text(response.json())

    def asr(self, audio_url: str, referer: str | None = None) -> str:
        oss_url = self._upload_audio_to_oss(audio_url, referer=referer)
        task_id = self._submit_transcription_task(oss_url)
        return self._wait_for_transcription(task_id)

    def _json_auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
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
                audio_response.raise_for_status()
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
                upload_response.raise_for_status()
        return f"oss://{key}"

    def _get_upload_policy(self) -> dict[str, Any]:
        response = requests.get(
            UPLOAD_POLICY_URL,
            headers=self._json_auth_headers(),
            params={
                "action": "getPolicy",
                "model": self.asr_model,
            },
            timeout=60,
            proxies=self._proxies,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError(f"DashScope upload policy response missing data: {payload}")
        return data

    def _submit_transcription_task(self, oss_url: str) -> str:
        headers = {
            **self._json_auth_headers(),
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
        response = requests.post(
            TRANSCRIPTION_URL,
            headers=headers,
            json=body,
            timeout=60,
            proxies=self._proxies,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"DashScope transcription submit {response.status_code}: "
                f"body={body!r} resp={response.text}"
            )
        payload = response.json()
        task_id = (payload.get("output") or {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"DashScope transcription response missing task_id: {payload}")
        return task_id

    def _wait_for_transcription(self, task_id: str) -> str:
        headers = self._json_auth_headers()
        deadline = time.monotonic() + 7200
        last_payload: dict[str, Any] | None = None

        while time.monotonic() < deadline:
            response = requests.get(
                TASK_URL_TEMPLATE.format(task_id=task_id),
                headers=headers,
                timeout=60,
                proxies=self._proxies,
            )
            response.raise_for_status()
            last_payload = response.json()
            output = last_payload.get("output") or {}
            task_status = output.get("task_status")

            if task_status == "SUCCEEDED":
                text = _extract_transcription_text(output, proxies=self._proxies)
                if text:
                    return text
                raise RuntimeError(f"DashScope transcription succeeded without text: {last_payload}")
            if task_status == "FAILED":
                raise RuntimeError(f"DashScope transcription failed: {last_payload}")

            time.sleep(2)

        raise RuntimeError(f"DashScope transcription timed out: {last_payload}")


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


def _extract_chat_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return str(content)


def _extract_transcription_text(
    output: dict[str, Any], *, proxies: dict[str, str] | None = None
) -> str:
    result = output.get("result") or {}
    urls = []
    if result.get("transcription_url"):
        urls.append(result["transcription_url"])
    for item in output.get("results") or []:
        if isinstance(item, dict) and item.get("transcription_url"):
            urls.append(item["transcription_url"])

    for url in urls:
        response = requests.get(url, timeout=60, proxies=proxies)
        response.raise_for_status()
        text = _format_transcription(response.json())
        if text:
            return text
    return ""


def _format_transcription(payload: dict[str, Any]) -> str:
    """把转写结果 JSON 格式化为文本。

    多说话人（diarization 开启且识别出 ≥2 人）→ 按 speaker_id 分组，输出「说话人N：…」。
    单一说话人 / 无 speaker_id 字段 → 回退纯文本（拼 transcripts[].text）。
    一人配音演多角色会被识别成同一 speaker，按单人降级——拆分交给后续 LLM 后处理。
    纯函数，不发网络请求，便于单测。
    """
    transcripts = [t for t in payload.get("transcripts") or [] if isinstance(t, dict)]

    sentences: list[tuple[Any, str]] = []
    for transcript in transcripts:
        for sentence in transcript.get("sentences") or []:
            if not isinstance(sentence, dict):
                continue
            text = (sentence.get("text") or "").strip()
            if text:
                sentences.append((sentence.get("speaker_id"), text))

    speakers = {sid for sid, _ in sentences if sid is not None}

    if len(speakers) <= 1:
        parts = [
            (t.get("text") or "").strip()
            for t in transcripts
            if (t.get("text") or "").strip()
        ]
        if parts:
            return "\n".join(parts)
        return "\n".join(text for _, text in sentences)

    turns: list[str] = []
    current_sid: Any = _UNSET
    buffer: list[str] = []
    for sid, text in sentences:
        if sid != current_sid and buffer:
            turns.append(_format_speaker_turn(current_sid, buffer))
            buffer = []
        current_sid = sid
        buffer.append(text)
    if buffer:
        turns.append(_format_speaker_turn(current_sid, buffer))
    return "\n\n".join(turns)


_UNSET = object()


def _format_speaker_turn(speaker_id: Any, texts: list[str]) -> str:
    label = f"说话人{int(speaker_id) + 1}" if isinstance(speaker_id, int) else "说话人"
    return f"{label}：{''.join(texts)}"


def _content_length(response: requests.Response) -> int:
    value = response.headers.get("Content-Length") or "0"
    try:
        length = int(value)
    except (TypeError, ValueError):
        length = 0
    if length <= 0:
        raise RuntimeError("Remote audio is missing Content-Length")
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
