from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

import app.extract.fetcher as fetcher
# ExtractResult 是冻结契约类型（contracts），此处 re-export 保持 0.5.x 旧导入路径
# `from app.extract.extractor import ExtractResult` 仍解析到同一类型（消除双类型隐患）。
from app.extract.contracts import ExtractResult, Segment, text_fingerprint
from app.extract.errors import NetworkError, UnsupportedUrlError
from app.extract.model import ModelProvider


_log = logging.getLogger("rbcp.extractor")


def detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    if host == "bilibili.com" or host.endswith(".bilibili.com") or host == "b23.tv" or host.endswith(".b23.tv"):
        return "bilibili"
    if host == "xiaohongshu.com" or host.endswith(".xiaohongshu.com") or host == "xhslink.com" or host.endswith(".xhslink.com"):
        return "xiaohongshu"
    raise UnsupportedUrlError(
        f"Unsupported URL platform: {url}", operation="detect_platform"
    )


def extract_url(
    url: str,
    provider: ModelProvider,
    *,
    text_only: bool = False,
    save_media: bool = False,
    proxies: dict[str, str] | None = None,
) -> ExtractResult:
    platform = detect_platform(url)
    if platform == "bilibili":
        info = fetcher.fetch_bilibili(url, proxies=proxies)
        raw_text, segments, metadata = _extract_bilibili_text(info, provider, text_only=text_only)
    elif platform == "xiaohongshu":
        info = fetcher.fetch_xiaohongshu(url, proxies=proxies)
        raw_text, segments, metadata = _extract_xiaohongshu_text(info, provider, text_only=text_only)
    else:
        raise UnsupportedUrlError(
            f"Unsupported URL platform: {url}", operation="detect_platform"
        )

    if save_media:
        media_dir = Path(os.getenv("RBCP_MEDIA_DIR", "~/transcript-media")).expanduser()
        media_paths = _save_media(info, media_dir)
        metadata["media_paths"] = [str(p) for p in media_paths]

    # 封面缩略图来源：B 站取 view_data['pic']；小红书图文取首图当封面。
    # 只放进 metadata（ExtractResult 是冻结契约，不加字段）。
    cover_url = info.get("cover_url") or (info.get("image_urls") or [None])[0]
    if cover_url:
        metadata["cover_url"] = cover_url

    # 决策 C：text=canonical 原始原文（锚定坐标系）；readable_text=清洗版（.md 正文用）；两份都存。
    readable_text = provider.llm_clean(raw_text)
    return ExtractResult(
        platform=str(info.get("platform") or platform),
        content_type=str(info.get("content_type") or ""),
        title=str(info.get("title") or ""),
        author=str(info.get("author") or ""),
        author_id=_optional_str(info.get("author_id")),
        published_at=_format_published_at(info.get("published_at"), platform),
        url=str(info.get("url") or url),
        text=raw_text,
        readable_text=readable_text,
        text_sha256=text_fingerprint(raw_text),
        metadata=metadata,
        segments=segments,
    )


def _extract_bilibili_text(
    info: dict[str, Any],
    provider: ModelProvider,
    *,
    text_only: bool = False,
) -> tuple[str, tuple[Segment, ...] | None, dict[str, Any]]:
    subtitle_text = info.get("subtitle_text")
    metadata = _base_metadata(info)

    if text_only:
        # text_only 模式：字幕 > desc > title，跳过 ASR（无句级 segments）
        metadata["status"] = "text_only"
        if subtitle_text:
            return str(subtitle_text), None, metadata
        desc = info.get("desc")
        if desc:
            return str(desc), None, metadata
        return str(info.get("title") or ""), None, metadata

    if subtitle_text:
        metadata["status"] = "subtitle"
        return str(subtitle_text), None, metadata

    media_url = info.get("audio_url") or info.get("video_url")
    metadata["status"] = "asr"
    asr_text, segments = provider.asr(str(media_url or ""), referer=info.get("referer"))
    _annotate_speaker_count(metadata, asr_text)
    return asr_text, segments, metadata


def _extract_xiaohongshu_text(
    info: dict[str, Any],
    provider: ModelProvider,
    *,
    text_only: bool = False,
) -> tuple[str, tuple[Segment, ...] | None, dict[str, Any]]:
    metadata = _base_metadata(info)
    content_type = info.get("content_type")

    if text_only:
        # text_only 模式：desc > title，跳过 VLM/ASR（无句级 segments）
        metadata["status"] = "text_only"
        desc = info.get("desc")
        if desc:
            return str(desc), None, metadata
        return str(info.get("title") or ""), None, metadata

    if content_type == "image_note":
        image_urls = [_normalize_image_url(str(url)) for url in info.get("image_urls") or []]
        metadata["status"] = "vision"
        metadata["image_count"] = len(image_urls)
        # 图文走 VLM，无句级时间戳 → segments=None（坐标用 image_index）
        return "\n\n".join(provider.vlm(image_url) for image_url in image_urls), None, metadata

    media_url = info.get("audio_url") or info.get("video_url")
    metadata["status"] = "asr"
    asr_text, segments = provider.asr(str(media_url or ""), referer=info.get("referer"))
    _annotate_speaker_count(metadata, asr_text)
    return asr_text, segments, metadata


_SPEAKER_LABEL_RE = re.compile(r"说话人(\d+)：")


def _annotate_speaker_count(metadata: dict[str, Any], asr_text: str) -> None:
    """从「说话人N：」标签统计说话人数，≥2 才写入 frontmatter。"""
    speakers = set(_SPEAKER_LABEL_RE.findall(asr_text or ""))
    if len(speakers) >= 2:
        metadata["speaker_count"] = len(speakers)


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


# ─── save_media 辅助 ──────────────────────────────────────────────────────────

_XHS_REFERER = "https://www.xiaohongshu.com/"
_BILI_REFERER = "https://www.bilibili.com/"

_MEDIA_DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
}


def _save_media(info: dict[str, Any], media_dir: Path) -> list[Path]:
    """把原始媒体文件下载到 media_dir/{post_id}/ 子目录，返回已写入的路径列表。

    - 图文笔记：下载 image_urls 列表里的每张图
    - 视频笔记/B站视频：下载 video_url（完整视频）
    - 原子写：先写 .part，成功后 os.replace
    - 幂等：目标文件已存在则跳过
    - 防盗链：带 Referer header（取 info["referer"] 或平台默认值）
    """
    post_id = str(info.get("post_id") or "unknown")
    platform = str(info.get("platform") or "")
    referer = str(info.get("referer") or (
        _XHS_REFERER if platform == "xiaohongshu" else _BILI_REFERER
    ))

    save_dir = media_dir / post_id
    save_dir.mkdir(parents=True, exist_ok=True)

    headers = {**_MEDIA_DOWNLOAD_HEADERS, "Referer": referer}
    saved: list[Path] = []

    content_type = info.get("content_type")
    if content_type == "image_note":
        image_urls = [str(u) for u in (info.get("image_urls") or []) if u]
        for idx, img_url in enumerate(image_urls):
            ext = _guess_ext(img_url, default=".jpg")
            dest = save_dir / f"image_{idx:03d}{ext}"
            if _download_file(img_url, dest, headers):
                saved.append(dest)
    else:
        # 视频类型：优先 video_url，其次 audio_url
        media_url = info.get("video_url") or info.get("audio_url")
        if media_url:
            ext = _guess_ext(str(media_url), default=".mp4")
            dest = save_dir / f"video{ext}"
            if _download_file(str(media_url), dest, headers):
                saved.append(dest)

    return saved


def _download_file(url: str, dest: Path, headers: dict[str, str]) -> bool:
    """下载单个文件到 dest，原子写（.part + os.replace），幂等（已存在跳过）。
    返回 True 表示实际下载了（包括跳过已存在），False 表示 URL 为空。
    """
    if not url:
        return False
    if dest.exists():
        return True  # 已存在，幂等跳过

    part_path = dest.with_suffix(dest.suffix + ".part")
    response = requests.get(url, headers=headers, timeout=60)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        body = ""
        try:
            body = (response.text or "")[:500]
        except Exception:  # noqa: BLE001
            body = ""
        status = getattr(response, "status_code", None)
        _log.error("[save_media] download HTTP %s url=%s body=%s", status, url, body)
        raise NetworkError(
            f"media download failed (HTTP {status})",
            operation="save_media",
            debug_context={"status": status, "url": url},
        ) from exc
    part_path.write_bytes(response.content)
    os.replace(str(part_path), str(dest))
    return True


def _guess_ext(url: str, default: str = ".bin") -> str:
    """从 URL 路径猜文件扩展名，取不到就用 default。"""
    path = urlparse(url).path
    if "." in path.rsplit("/", 1)[-1]:
        ext = "." + path.rsplit(".", 1)[-1].split("?")[0].lower()
        if len(ext) <= 6:  # 合理的扩展名长度
            return ext
    return default
