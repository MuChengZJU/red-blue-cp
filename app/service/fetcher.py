from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

BILIBILI_VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
BILIBILI_PLAYER_URL = "https://api.bilibili.com/x/player/v2"
BILIBILI_PLAYURL_URL = "https://api.bilibili.com/x/player/playurl"
BV_RE = re.compile(r"BV[0-9A-Za-z]{5,}")


def fetch_bilibili(url: str) -> dict[str, Any]:
    """Fetch Bilibili video metadata, subtitles, and media URLs."""
    page_url = _resolve_bilibili_url(url)
    bvid = _extract_bvid(page_url)
    if not bvid:
        raise ValueError(f"Could not find Bilibili BV id in URL: {url}")

    view_payload = _get_json(BILIBILI_VIEW_URL, params={"bvid": bvid}, referer=page_url)
    view_data = _api_data(view_payload, "Bilibili video info")
    pages = view_data.get("pages") or []
    first_page = pages[0] if pages else {}
    cid = view_data.get("cid") or first_page.get("cid")
    aid = view_data.get("aid")

    subtitle_text = None
    if cid:
        subtitle_text = _fetch_bilibili_subtitle(page_url, bvid, cid)

    audio_url = None
    video_url = None
    if cid:
        audio_url, video_url = _fetch_bilibili_media_urls(page_url, bvid, cid)

    owner = view_data.get("owner") or {}
    canonical_url = f"https://www.bilibili.com/video/{bvid}"
    return _standard_result(
        platform="bilibili",
        content_type="video",
        title=view_data.get("title"),
        author=owner.get("name"),
        author_id=owner.get("mid"),
        post_id=bvid,
        published_at=view_data.get("pubdate") or view_data.get("ctime"),
        url=canonical_url,
        subtitle_text=subtitle_text,
        audio_url=audio_url,
        video_url=video_url,
        image_urls=[],
        duration_sec=view_data.get("duration"),
        referer=canonical_url,
        desc=view_data.get("desc") or None,
        raw={"view": view_payload, "aid": aid, "cid": cid},
    )


def fetch_xiaohongshu(url: str) -> dict[str, Any]:
    """Fetch Xiaohongshu note metadata from the page initial state."""
    response = requests.get(
        url,
        headers={**DEFAULT_HEADERS, "Referer": "https://www.xiaohongshu.com/"},
        timeout=30,
        allow_redirects=True,
    )
    response.raise_for_status()
    final_url = response.url or url
    initial_state = _extract_xhs_initial_state(response.text)
    note = _extract_xhs_note(initial_state)

    post_id = _first_present(note, "noteId", "note_id", "id") or _xhs_id_from_url(final_url)
    user = _first_dict(note, "user", "userInfo", "author")
    author = _first_present(user, "nickname", "name", "userName")
    author_id = _first_present(user, "userId", "user_id", "id")

    video_url = _extract_xhs_video_url(note)
    image_urls = _extract_xhs_image_urls(note)
    content_type = "video" if video_url else "image_note"
    timestamp = _first_present(note, "time", "timestamp", "publishTime", "publish_time")

    return _standard_result(
        platform="xiaohongshu",
        content_type=content_type,
        title=_first_present(note, "title", "displayTitle") or "",
        author=author,
        author_id=author_id,
        post_id=post_id,
        published_at=timestamp,
        url=final_url,
        subtitle_text=None,
        audio_url=video_url,
        video_url=video_url,
        image_urls=image_urls,
        duration_sec=_first_present(note, "duration", "durationSec", "duration_sec"),
        referer=final_url,
        desc=_first_present(note, "desc", "description", "content") or None,
        raw=initial_state,
    )


def _resolve_bilibili_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host == "b23.tv" or host.endswith(".b23.tv"):
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=30, allow_redirects=True)
        response.raise_for_status()
        return response.url or url
    return url


def _extract_bvid(url: str) -> str | None:
    match = BV_RE.search(url)
    return match.group(0) if match else None


def _get_json(
    endpoint: str,
    *,
    params: dict[str, Any],
    referer: str | None = None,
) -> dict[str, Any]:
    headers = dict(DEFAULT_HEADERS)
    if referer:
        headers["Referer"] = referer
    response = requests.get(endpoint, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected JSON response from {endpoint}: {payload!r}")
    return payload


def _api_data(payload: dict[str, Any], label: str) -> dict[str, Any]:
    code = payload.get("code", 0)
    if code not in (0, "0", None):
        raise RuntimeError(f"{label} API returned error: {payload}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"{label} API response missing data: {payload}")
    return data


def _fetch_bilibili_subtitle(page_url: str, bvid: str, cid: Any) -> str | None:
    payload = _get_json(BILIBILI_PLAYER_URL, params={"bvid": bvid, "cid": cid}, referer=page_url)
    data = _api_data(payload, "Bilibili player")
    subtitle_entries = ((data.get("subtitle") or {}).get("subtitles")) or []
    if not subtitle_entries:
        return None

    subtitle_url = _first_present(subtitle_entries[0], "subtitle_url", "url")
    if not subtitle_url:
        return None
    subtitle_url = _with_protocol(str(subtitle_url))
    subtitle_payload = _get_json(subtitle_url, params={}, referer=page_url)
    body = subtitle_payload.get("body") or []
    lines = [
        str(item.get("content", "")).strip()
        for item in body
        if isinstance(item, dict) and str(item.get("content", "")).strip()
    ]
    return "\n".join(lines) if lines else None


def _fetch_bilibili_media_urls(page_url: str, bvid: str, cid: Any) -> tuple[str | None, str | None]:
    payload = _get_json(
        BILIBILI_PLAYURL_URL,
        params={"bvid": bvid, "cid": cid, "fnval": 16, "fourk": 1},
        referer=page_url,
    )
    data = _api_data(payload, "Bilibili playurl")
    dash = data.get("dash") or {}
    audio = dash.get("audio") or []
    video = dash.get("video") or []
    audio_url = _media_base_url(audio[0]) if audio else None
    video_url = _media_base_url(video[0]) if video else None
    return audio_url, video_url


def _media_base_url(entry: dict[str, Any]) -> str | None:
    value = _first_present(entry, "baseUrl", "base_url")
    return _with_protocol(str(value)) if value else None


def _extract_xhs_initial_state(html: str) -> dict[str, Any]:
    marker = "window.__INITIAL_STATE__"
    start = html.find(marker)
    if start == -1:
        raise RuntimeError("Xiaohongshu page missing window.__INITIAL_STATE__")

    equals = html.find("=", start)
    if equals == -1:
        raise RuntimeError("Xiaohongshu initial state assignment is malformed")

    json_text = _read_js_object_literal(html, equals + 1)
    json_text = re.sub(r":\s*undefined", ":null", json_text)
    json_text = re.sub(r"\bundefined\b", "null", json_text)
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Failed to parse Xiaohongshu initial state") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected Xiaohongshu initial state: {payload!r}")
    return payload


def _read_js_object_literal(text: str, start: int) -> str:
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] not in "[{":
        raise RuntimeError("Xiaohongshu initial state does not start with JSON")

    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escape = False
    quote = ""
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                in_string = False
            continue
        if char in ('"', "'"):
            in_string = True
            quote = char
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise RuntimeError("Xiaohongshu initial state JSON is incomplete")


def _extract_xhs_note(initial_state: dict[str, Any]) -> dict[str, Any]:
    note_state = initial_state.get("note") if isinstance(initial_state.get("note"), dict) else {}
    detail_map = note_state.get("noteDetailMap") if isinstance(note_state, dict) else None
    if isinstance(detail_map, dict) and detail_map:
        for value in detail_map.values():
            if isinstance(value, dict):
                note = value.get("note") or value.get("noteData") or value
                if isinstance(note, dict):
                    return note

    note = _find_xhs_note(initial_state)
    if note is None:
        raise RuntimeError("Xiaohongshu note detail not found in initial state")
    return note


def _find_xhs_note(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        keys = set(value)
        if {"title", "user"}.issubset(keys) or {"displayTitle", "user"}.issubset(keys):
            return value
        for child in value.values():
            found = _find_xhs_note(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_xhs_note(child)
            if found is not None:
                return found
    return None


def _extract_xhs_video_url(note: dict[str, Any]) -> str | None:
    video = _first_dict(note, "video", "videoInfo")
    candidates: list[Any] = []
    if video:
        candidates.extend(
            [
                _first_present(video, "masterUrl", "url", "videoUrl"),
                _first_present(video.get("media") if isinstance(video.get("media"), dict) else {}, "streamUrl"),
            ]
        )
        stream = video.get("media", {}).get("stream") if isinstance(video.get("media"), dict) else None
        if isinstance(stream, dict):
            for stream_items in stream.values():
                if isinstance(stream_items, list):
                    for item in stream_items:
                        if isinstance(item, dict):
                            candidates.append(_first_present(item, "masterUrl", "url", "backupUrls"))

    for candidate in candidates:
        if isinstance(candidate, list):
            candidate = candidate[0] if candidate else None
        if candidate:
            return _with_protocol(str(candidate))
    return None


def _extract_xhs_image_urls(note: dict[str, Any]) -> list[str]:
    image_entries = _first_present(note, "imageList", "images", "image_list") or []
    urls: list[str] = []
    if isinstance(image_entries, list):
        for image in image_entries:
            if isinstance(image, str):
                urls.append(_with_protocol(image))
            elif isinstance(image, dict):
                value = _first_present(image, "url", "traceId", "fileId")
                url_default = image.get("urlDefault")
                if isinstance(url_default, str):
                    value = url_default
                elif isinstance(url_default, dict):
                    value = _first_present(url_default, "url")
                if value:
                    urls.append(_with_protocol(str(value)))
    return urls


def _first_present(mapping: Any, *keys: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _first_dict(mapping: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _with_protocol(url: str) -> str:
    if url.startswith("//"):
        return f"https:{url}"
    return url


def _xhs_id_from_url(url: str) -> str | None:
    parts = [part for part in urlparse(url).path.split("/") if part]
    return parts[-1] if parts else None


def _standard_result(
    *,
    platform: str,
    content_type: str,
    title: Any,
    author: Any,
    author_id: Any,
    post_id: Any,
    published_at: Any,
    url: str,
    subtitle_text: str | None,
    audio_url: str | None,
    video_url: str | None,
    image_urls: list[str],
    duration_sec: Any,
    referer: str,
    raw: dict[str, Any],
    desc: str | None = None,
) -> dict[str, Any]:
    return {
        "platform": platform,
        "content_type": content_type,
        "title": str(title or ""),
        "author": str(author or ""),
        "author_id": str(author_id or "") if author_id is not None else None,
        "post_id": str(post_id or "") if post_id is not None else None,
        "published_at": published_at,
        "url": url,
        "subtitle_text": subtitle_text,
        "audio_url": audio_url,
        "video_url": video_url,
        "image_urls": image_urls,
        "duration_sec": duration_sec,
        "referer": referer,
        "desc": desc or None,
        "raw": raw,
    }
