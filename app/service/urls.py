"""输入 URL 清理：从分享文案里抽 URL + 去平台追踪参数。

- 浏览器地址栏直接复制 → 干净 URL（原样）。
- 手机/网页「分享」按钮 → 带标题文字 + 追踪后缀，正则抽 URL + 去垃圾参数。
- B 站：保留 p（分P）、t（起始秒），其余追踪参数全删。
- 小红书：**保留 xsec_token + xsec_source**（缺 token 看不了详情），其余删。
  保留参数时不重新编码，避免破坏 xsec_token 尾部的 base64 `=`。
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_URL_RE = re.compile(r"https?://[^\s　]+", re.IGNORECASE)
_BILI_KEEP = {"p", "t"}
_XHS_KEEP = {"xsec_token", "xsec_source"}
# 分享文案 URL 常见尾随包裹/标点
_TRAILING = "】>)）」』，。、,. \t\r\n"


def clean_url(raw: str) -> str:
    if not raw:
        return raw
    text = raw.strip()
    match = _URL_RE.search(text)
    url = match.group(0) if match else text
    url = url.rstrip(_TRAILING)

    parts = urlsplit(url)
    host = (parts.netloc or "").lower()
    if not parts.scheme or not host:
        return url  # 不是 URL，原样返回交上层平台校验

    if "bilibili.com" in host or host == "b23.tv" or host.endswith(".b23.tv"):
        keep = _BILI_KEEP
    elif "xiaohongshu.com" in host or "xhslink.com" in host or "xhs.cn" in host:
        keep = _XHS_KEEP
    else:
        return urlunsplit(parts)  # 其他站点不动参数

    # 不用 urlencode 重编码，保留原始 value（护 xsec_token 的 base64 尾 `=`）
    kept = [
        pair for pair in parts.query.split("&")
        if pair and pair.split("=", 1)[0] in keep
    ]
    return urlunsplit(parts._replace(query="&".join(kept)))
