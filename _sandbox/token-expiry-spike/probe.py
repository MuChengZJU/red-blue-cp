"""token 过期信号 spike（探索用，不进 app/）。

目的：搞清"过期/无效 xsec_token"的 explore 详情页响应到底长什么样，
以便锁定 batch 里"token 过期跳过"的可靠判定信号（避免 Codex 警告的 title 空误伤）。

用法（仓库根目录）：
  uv run python _sandbox/token-expiry-spike/probe.py "<explore url>"
  # 直连。如需走代理验真实 batch 场景：
  HTTPS_PROXY='http://...' uv run python _sandbox/token-expiry-spike/probe.py "<url>"

直接复用 app 的解析路径，保证信号和生产一致。不抛异常、不写盘。
"""

from __future__ import annotations

import sys

import requests

from app.service.fetcher import (
    DEFAULT_HEADERS,
    _extract_xhs_initial_state,
    _extract_xhs_note,
)

MARKERS = (
    "__INITIAL_STATE__",
    "noteDetailMap",
    "薯队长",
    "captcha",
    "verifyType",
    "当前笔记",
    "笔记不存在",
    "扫码登录",
    "redirectReason",
)


def probe(url: str) -> None:
    r = requests.get(
        url,
        headers={**DEFAULT_HEADERS, "Referer": "https://www.xiaohongshu.com/"},
        timeout=30,
        allow_redirects=True,
    )
    text = r.text
    print(f"HTTP {r.status_code}  final={r.url}  len={len(text)}")
    for m in MARKERS:
        print(f"  has[{m}]: {m in text}")

    try:
        st = _extract_xhs_initial_state(text)
    except Exception as e:  # noqa: BLE001
        print(f"  [state1] _extract_xhs_initial_state RAISED: {e}")
        return
    note_state = st.get("note") if isinstance(st.get("note"), dict) else {}
    dm = note_state.get("noteDetailMap") if isinstance(note_state, dict) else None
    if isinstance(dm, dict):
        print(f"  [state] INITIAL_STATE OK; noteDetailMap keys={list(dm.keys())}")
    else:
        print(f"  [state] INITIAL_STATE OK; noteDetailMap={dm!r}")

    try:
        n = _extract_xhs_note(st)
        title = n.get("title") or n.get("displayTitle")
        imgs = n.get("imageList") or n.get("image_urls") or []
        print(f"  [state2] note FOUND; title={title!r}; img_count={len(imgs) if hasattr(imgs,'__len__') else '?'}")
    except Exception as e:  # noqa: BLE001
        print(f"  [state3] _extract_xhs_note RAISED: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("需要一个 explore url 参数")
    probe(sys.argv[1])
