"""URL → Markdown 管道（M4a）。cli 和 batch 共用 fetch_single；proxy 在此构造一次往下传。"""

from __future__ import annotations

from urllib.parse import urlparse

import requests

from app.service.errors import ConfigError

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
    """
    return requests.get(
        "https://api.ipify.org",
        proxies=proxies,
        trust_env=False,
        timeout=10,
    ).text.strip()
