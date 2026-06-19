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

# URL 提取：CJK 兼容——遇中文字符 / 全角标点 / CJK 标点 / emoji 即停止，
# 避免把分享文案里紧跟 URL 的中文尾巴（如「，复制本条信息」）吞进 URL。
_URL_RE = re.compile(
    r"https?://[^"
    r"\s"  # 任意空白（含半角空格 / 换行）
    r"　-〿"  # CJK 符号和标点（含全角空格 　、。〈〉「」 等）
    r"一-鿿"  # CJK 统一表意（汉字）
    r"＀-￯"  # 全角 ASCII / 半宽片假名（含 ， 。 ！ ？ 【 】 等）
    r"☀-➿⬀-⯿︀-️\U0001f000-\U0001faff"  # emoji / 杂项符号 / 变体选择符
    r"]+",
    re.IGNORECASE,
)
_BILI_KEEP = {"p", "t"}
_XHS_KEEP = {"xsec_token", "xsec_source"}
# 分享文案 URL 常见尾随包裹/标点
_TRAILING = "】>)）」』，。、,. \t\r\n"


# 去重键（M5b E1）：同内容不同参数（xsec_token/追踪参数）归一到同一个键。
# 短链（b23.tv/xhslink）不发请求解析不了内容 id → None（不猜，跳过去重）。
_BV_RE = re.compile(r"/video/(BV[0-9A-Za-z]+)")
_XHS_NOTE_RE = re.compile(r"/(?:explore|discovery/item|search_result|item)/([0-9a-fA-F]{8,})")


def dedup_key(url: str) -> str | None:
    """URL → 内容唯一键（'bili:BV…' / 'xhs:note_id'）；解析不出返回 None。"""
    if not url:
        return None
    host = (urlsplit(url).netloc or "").lower()
    if "bilibili.com" in host:
        m = _BV_RE.search(url)
        return f"bili:{m.group(1)}" if m else None
    if "xiaohongshu.com" in host:
        m = _XHS_NOTE_RE.search(url)
        return f"xhs:{m.group(1).lower()}" if m else None
    return None


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
