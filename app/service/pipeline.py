"""URL → Markdown 管道（M4a）。cli 和 batch 共用 fetch_single；proxy 在此构造一次往下传。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

import requests

from app.service.errors import ConfigError
from app.service.extractor import extract_url
from app.service.markdown import render_and_write
from app.service.model import DashscopeProvider

_ALLOWED_PROXY_SCHEMES = {"http", "https"}


def build_proxies(proxy: str | None) -> dict[str, str] | None:
    """proxy URL → requests proxies dict。None/空 → None（直连）。

    阶段 1 只支持 http/https（socks5 需 PySocks，破"阶段1不加依赖"红线 → 拒绝）。
    无 scheme / 非法 → ConfigError。
    """
    if not proxy:
        return None
    scheme = urlparse(proxy).scheme.lower()
    if not scheme:
        raise ConfigError(f"代理地址缺少 scheme（应形如 http://host:port）：{proxy}")
    if scheme not in _ALLOWED_PROXY_SCHEMES:
        raise ConfigError(f"阶段 1 仅支持 http/https 代理，不支持 {scheme}（如用 Clash 请开 http 混合端口）")
    return {"http": proxy, "https": proxy}


def probe_exit_ip(proxies: dict[str, str] | None) -> str:
    """查当前出口 IP（走给定 proxies），用于开跑前确认代理真生效。

    trust_env=False 防环境变量代理干扰判定——只认显式传入的 proxies。
    注意：trust_env 是 Session 的属性，不是 requests.get 的参数（直接传会 TypeError）。
    """
    with requests.Session() as session:
        session.trust_env = False
        return session.get(
            "https://api.ipify.org",
            proxies=proxies,
            timeout=10,
        ).text.strip()


def _provider_from_env(
    api_key: str,
    *,
    proxies: dict[str, str] | None = None,
    media_proxies: dict[str, str] | None = None,
) -> DashscopeProvider:
    asr_model = os.getenv("RBCP_ASR_MODEL", "paraformer-v2")
    diarization_enabled = os.getenv("RBCP_ASR_DIARIZATION", "true").strip().lower() in {
        "1", "true", "yes", "on",
    }
    speaker_count_raw = os.getenv("RBCP_ASR_SPEAKER_COUNT", "").strip()
    speaker_count = int(speaker_count_raw) if speaker_count_raw.isdigit() else None
    return DashscopeProvider(
        api_key=api_key,
        asr_model=asr_model,
        diarization_enabled=diarization_enabled,
        speaker_count=speaker_count,
        proxies=proxies,
        media_proxies=media_proxies,
    )


def fetch_single(
    url: str,
    *,
    api_key: str,
    output_dir: Path,
    comments: bool = False,
    sub: bool = True,
    save_media: bool = False,
    text_only: bool = False,
    proxy: str | None = None,
) -> dict:
    """抓单篇笔记：正文转录（+可选媒体落盘/纯文本）+ 可选评论。返回结果摘要。

    cli run/fetch 和 service/batch.py 都调它；cli 只做参数解析 + 输出。
    proxy 走主站护 IP（explore 详情 + DashScope）；CDN 媒体字节默认不走。
    """
    proxies = build_proxies(proxy)
    provider = _provider_from_env(api_key, proxies=proxies)
    result = extract_url(
        url, provider, text_only=text_only, save_media=save_media, proxies=proxies
    )
    md_path = render_and_write(result, output_dir=output_dir)
    out: dict = {"md_path": str(md_path), "title": result.title}

    if comments:
        from app.service import discover
        from app.service.comments import write_comments_md
        from app.service.discover import note_id_from_url

        note_comments = asyncio.run(discover.discover_comments(url, with_sub=sub))
        comments_path = write_comments_md(
            note_id_from_url(url), note_comments, output_dir, note_title=result.title
        )
        out["comments_path"] = str(comments_path)
        out["comment_count"] = len(note_comments)

    return out
