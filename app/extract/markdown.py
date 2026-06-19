"""Markdown filename helpers."""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader

from app.extract.extractor import ExtractResult


_SPECIAL_CHARS = set('/\\:*?"<>|')
_WHITESPACE_RE = re.compile(r"\s+")
_PLATFORM_DIRS = {
    "bilibili": "bili",
    "xiaohongshu": "xhs",
}


def _is_emoji(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x1F000 <= codepoint <= 0x1FAFF
        or 0x2600 <= codepoint <= 0x27BF
        or codepoint in {0x200D, 0xFE0E, 0xFE0F}
        or unicodedata.category(char) in {"Cs"}
    )


def _sanitize_part(value: str) -> str:
    cleaned: list[str] = []

    for char in value.replace("\u3000", " "):
        if char in _SPECIAL_CHARS:
            continue
        if ord(char) <= 0x1F:
            continue
        if _is_emoji(char):
            continue
        cleaned.append(char)

    return _WHITESPACE_RE.sub(" ", "".join(cleaned)).strip()


def sanitize_filename(title: str, author: str | None, date: str, suffix_id: str) -> str:
    """Return a safe markdown filename stem for a note."""
    safe_author = _sanitize_part(author) if author else ""
    if not safe_author:
        safe_author = "unknown_author"

    safe_title = _sanitize_part(title)
    if not safe_title:
        safe_title = suffix_id
    else:
        safe_title = safe_title[:60]

    return f"{date}-{safe_author}-{safe_title}-{suffix_id}"


def render_and_write(result: ExtractResult, output_dir: Path) -> Path:
    """Render an extraction result as Markdown and atomically write it."""
    subdir_name = _PLATFORM_DIRS.get(result.platform)
    if subdir_name is None:
        raise ValueError(f"Unsupported platform: {result.platform}")

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date = result.published_at or fetched_at
    suffix_id = _result_suffix_id(result)
    filename = sanitize_filename(result.title, result.author, date, suffix_id)

    target_dir = output_dir / subdir_name
    target_dir.mkdir(parents=True, exist_ok=True)
    final_path = target_dir / f"{filename}.md"
    tmp_path = final_path.with_name(f"{final_path.name}.tmp")

    content = _render_markdown(result, fetched_at=fetched_at)
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, final_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return final_path


def _render_markdown(result: ExtractResult, fetched_at: str) -> str:
    metadata = dict(result.metadata or {})
    template_dir = Path(__file__).with_name("templates")
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=False,
        keep_trailing_newline=True,
    )
    template = env.get_template("note.md.j2")
    return template.render(
        platform=result.platform,
        content_type=result.content_type,
        url=result.url,
        author=result.author,
        author_id=result.author_id,
        title=result.title,
        published_at=result.published_at,
        fetched_at=fetched_at,
        duration_sec=metadata.get("duration_sec"),
        image_count=metadata.get("image_count"),
        asr_model=metadata.get("asr_model") or os.getenv("RBCP_ASR_MODEL", "paraformer-v2"),
        speaker_count=metadata.get("speaker_count"),
        vision_model=metadata.get("vision_model") or os.getenv("RBCP_VLM_MODEL", "qwen3-vl-flash"),
        media_paths=metadata.get("media_paths"),
        status=metadata.get("status"),
        author_url=_author_url(result),
        # .md 正文用清洗版（用户定）；canonical 原文 result.text 留给 Digest/锚定层。
        text=result.readable_text,
    )


def _result_suffix_id(result: ExtractResult) -> str:
    metadata = result.metadata or {}
    # raw_info 已从冻结契约移除：唯一需要的 post_id 早已被 _base_metadata 写进 metadata。
    for key in ("post_id", "bvid", "note_id", "id"):
        value = metadata.get(key)
        if value:
            return str(value)

    parsed = urlparse(result.url)
    match = re.search(r"/video/([^/?#]+)", parsed.path)
    if match:
        return match.group(1)

    path_parts = [part for part in parsed.path.split("/") if part]
    if path_parts:
        return path_parts[-1]

    return hashlib.sha1(result.url.encode("utf-8")).hexdigest()[:12]


def _author_url(result: ExtractResult) -> str:
    if result.platform == "bilibili" and result.author_id:
        return f"space.bilibili.com/{result.author_id}"
    if result.platform == "xiaohongshu" and result.author_id:
        return f"www.xiaohongshu.com/user/profile/{result.author_id}"
    return urlparse(result.url).netloc
