from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import app.service.fetcher as fetcher
from app.service.model import ModelProvider


@dataclass
class ExtractResult:
    platform: str
    content_type: str
    title: str
    author: str
    author_id: str | None
    published_at: str | None
    url: str
    text: str
    metadata: dict[str, Any]
    raw_info: dict[str, Any]


def detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    if host == "bilibili.com" or host.endswith(".bilibili.com") or host == "b23.tv" or host.endswith(".b23.tv"):
        return "bilibili"
    if host == "xiaohongshu.com" or host.endswith(".xiaohongshu.com") or host == "xhslink.com" or host.endswith(".xhslink.com"):
        return "xiaohongshu"
    raise ValueError(f"Unsupported URL platform: {url}")


def extract_url(url: str, provider: ModelProvider) -> ExtractResult:
    platform = detect_platform(url)
    if platform == "bilibili":
        info = fetcher.fetch_bilibili(url)
        raw_text, metadata = _extract_bilibili_text(info, provider)
    elif platform == "xiaohongshu":
        info = fetcher.fetch_xiaohongshu(url)
        raw_text, metadata = _extract_xiaohongshu_text(info, provider)
    else:
        raise ValueError(f"Unsupported URL platform: {url}")

    cleaned_text = provider.llm_clean(raw_text)
    return ExtractResult(
        platform=str(info.get("platform") or platform),
        content_type=str(info.get("content_type") or ""),
        title=str(info.get("title") or ""),
        author=str(info.get("author") or ""),
        author_id=_optional_str(info.get("author_id")),
        published_at=_format_published_at(info.get("published_at"), platform),
        url=str(info.get("url") or url),
        text=cleaned_text,
        metadata=metadata,
        raw_info=info,
    )


def _extract_bilibili_text(
    info: dict[str, Any],
    provider: ModelProvider,
) -> tuple[str, dict[str, Any]]:
    subtitle_text = info.get("subtitle_text")
    metadata = _base_metadata(info)
    if subtitle_text:
        metadata["status"] = "subtitle"
        return str(subtitle_text), metadata

    media_url = info.get("audio_url") or info.get("video_url")
    metadata["status"] = "asr"
    return provider.asr(str(media_url or ""), referer=info.get("referer")), metadata


def _extract_xiaohongshu_text(
    info: dict[str, Any],
    provider: ModelProvider,
) -> tuple[str, dict[str, Any]]:
    metadata = _base_metadata(info)
    content_type = info.get("content_type")

    if content_type == "image_note":
        image_urls = [_normalize_image_url(str(url)) for url in info.get("image_urls") or []]
        metadata["status"] = "vision"
        metadata["image_count"] = len(image_urls)
        return "\n\n".join(provider.vlm(image_url) for image_url in image_urls), metadata

    media_url = info.get("audio_url") or info.get("video_url")
    metadata["status"] = "asr"
    return provider.asr(str(media_url or ""), referer=info.get("referer")), metadata


def _base_metadata(info: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("post_id", "duration_sec", "video_url", "audio_url"):
        if info.get(key) is not None:
            metadata[key] = info.get(key)
    return metadata


def _normalize_image_url(url: str) -> str:
    if url.startswith("//"):
        return f"https:{url}"
    return url


def _format_published_at(value: Any, platform: str) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str) and _looks_like_date(value):
        return value[:10]

    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return str(value)

    if platform == "xiaohongshu" and timestamp > 10_000_000_000:
        timestamp /= 1000
    if platform == "bilibili" and timestamp > 10_000_000_000:
        timestamp /= 1000

    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")


def _looks_like_date(value: str) -> bool:
    try:
        datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
