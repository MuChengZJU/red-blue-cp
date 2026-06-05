"""小红书博主全量 / 评论抓取（P1）。

全项目唯一碰浏览器的模块。分两层：

1. **纯函数解析层**（本文件上半部，无 I/O）：把接口返回的 JSON 解析成 dataclass。
   单测直接喂 `tests/fixtures/xhs/` 的脱敏 JSON，不需要浏览器、不需要 pydoll。

2. **浏览器壳层**（本文件下半部，async）：pydoll 驱动系统 Chrome，注入 XHR/fetch
   拦截器抓接口返回，翻页、判风控，调上面的纯函数解析。

**pydoll 必须懒加载**（只在壳层函数内部 `import`），保证 `from app.service.discover
import Note, Comment` 在没装 pydoll 的环境也能用（comments.py 及其单测依赖这一点）。

契约见 SPEC §4.4。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

# 请求计数/频率日志：保护账号，跑完打一条 summary，方便看抓得猛不猛
_log = logging.getLogger("rbcp.discover")


# ─────────────────────────────────────────────────────────────────────────────
# 数据模型（契约，SPEC §4.4.1）—— 已定稿，并行开发依赖此处，勿改字段
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Note:
    note_id: str
    title: str            # 来自 display_title，可能为 ""
    type: str             # "image" | "video"（接口 normal→image，video→video）
    xsec_token: str       # 一次性、会过期；拼单篇 fetch 的 URL 用
    author: str           # user.nickname
    author_id: str        # user.user_id
    liked_count: int      # 接口给字符串，解析转 int


@dataclass
class NotePage:
    notes: list[Note]
    cursor: str           # 下一页游标；末页为 ""
    has_more: bool


@dataclass
class Comment:
    comment_id: str       # 接口 id
    note_id: str
    content: str
    author: str           # user_info.nickname
    author_id: str        # user_info.user_id
    like_count: int       # 接口字符串 → int
    ip_location: str      # 可能为 ""
    create_time: int      # 毫秒级 epoch
    reply_to: str | None  # 回复对象昵称（target_comment.user_info.nickname）；一级评论为 None
    sub_comments: list["Comment"] = field(default_factory=list)  # 仅一级评论非空
    # 以下三个仅一级评论有意义，供浏览器壳判断是否要续拉楼中楼：
    sub_comment_count: int = 0
    sub_comment_has_more: bool = False
    sub_comment_cursor: str = ""


@dataclass
class CommentPage:
    comments: list[Comment]   # 一级评论（内联 sub_comments 已解析进 .sub_comments）
    cursor: str
    has_more: bool


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数解析层（SPEC §4.4.2）—— Phase 1-A 用 TDD 实现，下面是待填的桩
# ─────────────────────────────────────────────────────────────────────────────


def _to_int(value, default: int = 0) -> int:
    """接口计数字段健壮转 int：真实数据里可能是 ""（空串）/ None / 数字字符串。"""
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_user_posted(resp_json: dict) -> NotePage:
    """解析单页 user_posted 响应。只解析当前页，不翻页、不发请求。

    resp_json 是接口返回的整个 JSON（含顶层 success/code/data）。
    """
    data = resp_json["data"]
    cursor: str = data.get("cursor", "")
    has_more: bool = bool(data.get("has_more", False))

    notes: list[Note] = []
    for raw in data.get("notes", []):
        # type 映射：normal → "image"，video → "video"
        raw_type = raw.get("type", "normal")
        note_type = "video" if raw_type == "video" else "image"

        # liked_count 接口给字符串（真实数据里可能是空串），健壮转 int
        interact = raw.get("interact_info") or {}
        liked_count = _to_int(interact.get("liked_count"))

        user = raw.get("user", {})
        notes.append(Note(
            note_id=raw["note_id"],
            title=raw.get("display_title", ""),
            type=note_type,
            xsec_token=raw.get("xsec_token", ""),
            author=user.get("nickname", user.get("nick_name", "")),
            author_id=user.get("user_id", ""),
            liked_count=liked_count,
        ))

    return NotePage(notes=notes, cursor=cursor, has_more=has_more)


def _parse_one_comment(raw: dict) -> Comment:
    """把接口单条评论 dict 解析成 Comment（不含子评论递归，子评论由调用方处理）。"""
    user_info = raw.get("user_info", {})
    target = raw.get("target_comment")
    reply_to: str | None = None
    if target:
        target_user = target.get("user_info", {})
        reply_to = target_user.get("nickname") or None

    return Comment(
        comment_id=raw["id"],
        note_id=raw.get("note_id", ""),
        content=raw.get("content", ""),
        author=user_info.get("nickname", ""),
        author_id=user_info.get("user_id", ""),
        like_count=_to_int(raw.get("like_count")),
        ip_location=raw.get("ip_location", ""),
        create_time=_to_int(raw.get("create_time")),
        reply_to=reply_to,
    )


def parse_comment_page(resp_json: dict) -> CommentPage:
    """解析一级评论页（comment/page）。

    一级评论的内联 sub_comments 也解析进 .sub_comments，
    并填好 sub_comment_count / sub_comment_has_more / sub_comment_cursor。
    """
    data = resp_json["data"]
    cursor: str = data.get("cursor", "")
    has_more: bool = bool(data.get("has_more", False))

    comments: list[Comment] = []
    for raw in data.get("comments", []):
        comment = _parse_one_comment(raw)
        # 一级评论 reply_to 强制为 None（接口里一级评论不带 target_comment）
        comment.reply_to = None

        # 填楼中楼元信息
        comment.sub_comment_count = _to_int(raw.get("sub_comment_count"))
        comment.sub_comment_has_more = bool(raw.get("sub_comment_has_more", False))
        comment.sub_comment_cursor = raw.get("sub_comment_cursor", "")

        # 解析内联 sub_comments
        inline_subs: list[Comment] = []
        for sub_raw in raw.get("sub_comments", []):
            inline_subs.append(_parse_one_comment(sub_raw))
        comment.sub_comments = inline_subs

        comments.append(comment)

    return CommentPage(comments=comments, cursor=cursor, has_more=has_more)


def parse_sub_comments(resp_json: dict) -> tuple[list[Comment], str, bool]:
    """解析楼中楼页（comment/sub/page）。返回 (子评论 list, cursor, has_more)。"""
    data = resp_json["data"]
    cursor: str = data.get("cursor", "")
    has_more: bool = bool(data.get("has_more", False))

    subs: list[Comment] = []
    for raw in data.get("comments", []):
        subs.append(_parse_one_comment(raw))

    return subs, cursor, has_more


def merge_sub_comments(
    comments: list[Comment],
    subs_by_root: dict[str, list[Comment]],
) -> list[Comment]:
    """把续拉到的楼中楼按 root comment_id 合并进对应一级评论的 .sub_comments。

    去重（按 comment_id）、保序。纯函数，浏览器壳抓完所有页后调用一次。
    """
    import copy

    result: list[Comment] = []
    for comment in comments:
        extra = subs_by_root.get(comment.comment_id, [])
        if not extra:
            result.append(comment)
            continue

        # 以已有 sub_comments 的 comment_id 为基础，追加去重
        existing_ids: dict[str, Comment] = {
            s.comment_id: s for s in comment.sub_comments
        }
        merged_subs = list(comment.sub_comments)  # 保留原有顺序

        for sub in extra:
            if sub.comment_id not in existing_ids:
                merged_subs.append(sub)
                existing_ids[sub.comment_id] = sub

        # 返回新 Comment 对象，避免 in-place 修改原对象影响调用方
        new_comment = copy.copy(comment)
        new_comment.sub_comments = merged_subs
        result.append(new_comment)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 浏览器壳层（async）—— pydoll 在函数内部懒加载，纯函数层不依赖浏览器
# ─────────────────────────────────────────────────────────────────────────────

class RiskControlError(RuntimeError):
    """撞上小红书安全验证（captcha）墙，无法继续抓取。调用方应标 failed 留痕。"""


class CookieError(RuntimeError):
    """cookie 没配/没登录/文件无效。区别于网络错误，提示用户先 rbcp login。"""


# 全局串行化：一次只允许一个 Chrome 在跑（避免多会话并发抬高风控）。
# 第二个 discover 请求排队等待，不并发开第二个浏览器。
_BROWSER_LOCK = asyncio.Lock()

# 抓接口响应走 pydoll 原生网络捕获（enable_network_events + get_network_logs +
# get_network_response_body），不用 JS 注入——pydoll 里页面早在注入前就抓走了原始
# fetch 引用，覆盖 fetch/XHR 钩不到页面真实请求（实测 JS 拦截器抓 0）。原生捕获稳，
# 且请求 URL 直接从事件里拿（楼中楼 root_comment_id 更好取）。

_USER_ID_RE = re.compile(r"/user/profile/([0-9a-fA-F]+)")
_ROOT_ID_RE = re.compile(r"[?&]root_comment_id=([^&]+)")
_NOTE_ID_RE = re.compile(r"/(?:explore|discovery/item|search_result)/([0-9a-fA-F]+)")


def note_id_from_url(url: str) -> str:
    """从笔记 URL 抠 note_id；抠不到时退回 URL 末段（去 query）。"""
    m = _NOTE_ID_RE.search(url)
    if m:
        return m.group(1)
    tail = url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    return tail or "unknown_note"


def _cookies_from_string(raw: str) -> list[dict]:
    """原始 cookie 串 'a=1; b=2' → pydoll set_cookies 格式（统一挂 .xiaohongshu.com）。"""
    cookies: list[dict] = []
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": ".xiaohongshu.com",
            "path": "/",
        })
    return cookies


def _cookies_from_file(path: Path) -> list[dict]:
    """cookie JSON 文件 → pydoll 格式。兼容 {"cookies":[...]} 和裸数组 [...] 两种结构。

    每条至少要 name/value；domain/path/expires/httpOnly/secure/sameSite 有则透传。
    （Playwright/CDP 风格的导出文件即此结构，与具体工具无关。）
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_list = data.get("cookies", []) if isinstance(data, dict) else data
    cookies: list[dict] = []
    for c in raw_list:
        if "name" not in c or "value" not in c:
            continue
        cp: dict = {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ".xiaohongshu.com"),
            "path": c.get("path", "/"),
        }
        exp = c.get("expires")
        if isinstance(exp, (int, float)) and exp > 0:
            cp["expires"] = exp
        if c.get("httpOnly") is not None:
            cp["httpOnly"] = bool(c["httpOnly"])
        if c.get("secure") is not None:
            cp["secure"] = bool(c["secure"])
        if c.get("sameSite") in ("Strict", "Lax", "None"):
            cp["sameSite"] = c["sameSite"]
        cookies.append(cp)
    return cookies


# `rbcp login` 扫码登录后 cookie 的默认落盘位置
_DEFAULT_COOKIE_FILE = "~/.config/rbcp/xhs_cookies.json"


def _resolve_cookie_file() -> Path:
    """cookie 文件路径：RBCP_XHS_COOKIE_FILE 优先，否则默认 ~/.config/rbcp/xhs_cookies.json。"""
    return Path(os.getenv("RBCP_XHS_COOKIE_FILE") or _DEFAULT_COOKIE_FILE).expanduser()


def _load_cookies() -> list[dict]:
    """解析小红书 cookie，供 pydoll set_cookies。按优先级取来源：

    1. 环境变量 ``XHS_COOKIE``（原始串 'web_session=...; a1=...'）。
    2. 环境变量 ``RBCP_XHS_COOKIE_FILE`` 指向的 cookie JSON 文件。
    3. 默认文件 ``~/.config/rbcp/xhs_cookies.json``（``rbcp login`` 扫码后存这）。

    都没有则报错（壳层会把它转成失败留痕，提示先跑 rbcp login）。
    """
    raw = os.getenv("XHS_COOKIE", "").strip()
    if raw:
        return _cookies_from_string(raw)

    explicit = os.getenv("RBCP_XHS_COOKIE_FILE", "").strip()
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.append(Path(_DEFAULT_COOKIE_FILE).expanduser())

    for path in candidates:
        if path.is_file():
            cookies = _cookies_from_file(path)
            if cookies:
                return cookies

    raise CookieError(
        "未配置小红书 cookie：先跑 `rbcp login` 扫码登录，"
        "或在 .env 设 XHS_COOKIE='web_session=...; a1=...' / RBCP_XHS_COOKIE_FILE 指向 cookie 文件"
    )


def _cookie_field(cookie, key, default=None):
    """pydoll get_cookies 返回的条目可能是 dict 或对象，统一取字段。"""
    if isinstance(cookie, dict):
        return cookie.get(key, default)
    return getattr(cookie, key, default)


async def login_and_save_cookies(
    cookie_file: Path | None = None, *, interactive: bool = True, on_ready=None
) -> tuple[int, Path]:
    """弹有头浏览器到小红书，等用户扫码登录，把 cookie 存到本地文件。

    **不自动猜是否登录**（小红书给游客也发 web_session，自动判断会误触发秒关）。
    交互模式下等用户扫完码、回终端按回车再读 cookie。返回 (有效 cookie 条数, 落盘路径)。
    这是最终用户获取登录态的入口（不依赖任何外部工具），也是开发期刷新 cookie 的统一办法。

    interactive=False 用于自动化/测试：开页后立即读当前 cookie（由 on_ready 钩子控制时机）。
    """
    from pydoll.browser.chromium import Chrome

    target = (cookie_file or _resolve_cookie_file()).expanduser()
    chrome = Chrome()
    cookies: list = []
    try:
        tab = await chrome.start(headless=False)  # 有头：用户要看到二维码
        await tab.go_to("https://www.xiaohongshu.com")
        if interactive:
            await asyncio.to_thread(
                input,
                "\n>>> 浏览器已打开。请用手机扫码登录小红书；看到自己的头像、"
                "进入首页后，回到这里按【回车】保存 cookie……\n",
            )
        if on_ready is not None:
            await on_ready(tab, chrome)
        cookies = await chrome.get_cookies()
    finally:
        try:
            await chrome.stop()
        except Exception:  # noqa: BLE001
            pass

    out: list[dict] = []
    for c in cookies:
        domain = _cookie_field(c, "domain") or ""
        if "xiaohongshu" not in domain:
            continue
        entry = {
            "name": _cookie_field(c, "name"),
            "value": _cookie_field(c, "value"),
            "domain": domain,
            "path": _cookie_field(c, "path", "/"),
        }
        for k in ("expires", "httpOnly", "secure", "sameSite"):
            v = _cookie_field(c, k)
            if v is not None:
                entry[k] = v
        out.append(entry)

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        json.dumps({"cookies": out}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(tmp, target)
    return sum(1 for c in out if c.get("value")), target


def _script_value(resp):
    """从 pydoll execute_script 的返回里抠出 JS 求值结果。"""
    try:
        return resp["result"]["result"]["value"]
    except (KeyError, TypeError):
        return None


async def _start_chrome():
    from pydoll.browser.chromium import Chrome

    chrome = Chrome()
    tab = await chrome.start(headless=True)
    await chrome.set_cookies(_load_cookies())
    return chrome, tab


async def _eval(tab, expr: str):
    return _script_value(await tab.execute_script(expr))


async def _fetch_new_bodies(tab, url_filter: str, seen_rids: set, out: list) -> None:
    """把 get_network_logs 里新出现、能取到响应体的请求追加到 out=[(url, body_text)]。

    取不到 body 的（preflight / 还没 ready）跳过且不标记 seen，下一轮再试。
    """
    try:
        logs = await tab.get_network_logs(filter=url_filter)
    except Exception:  # noqa: BLE001 - 网络事件没开等异常，按无新数据处理
        return
    for ev in logs:
        params = ev.get("params", {}) if isinstance(ev, dict) else {}
        rid = params.get("requestId")
        if not rid or rid in seen_rids:
            continue
        url = (params.get("request") or {}).get("url", "")
        try:
            body = await tab.get_network_response_body(rid)
        except Exception:  # noqa: BLE001 - body 没 ready / preflight 无 body
            continue
        if body:
            seen_rids.add(rid)
            out.append((url, body))


# 风控/验证墙标志：小红书弹验证时标题/正文出现这些词，且不会有业务接口返回
_RISK_MARKERS = ("安全验证", "验证码", "captcha", "滑动验证", "请完成验证")


async def _is_risk_page(tab) -> bool:
    title = (await _eval(tab, "document.title") or "")
    if any(m in title for m in _RISK_MARKERS):
        return True
    hit = await _eval(
        tab,
        "(function(){var t=document.body?document.body.innerText.slice(0,500):'';"
        "return /安全验证|验证码|滑动验证|请完成验证/.test(t);})()")
    return bool(hit)


def _log_rate(label: str, *, requests: int, scrolls: int, elapsed: float, extra: str = "") -> None:
    """打一条抓取频率 summary：接口请求数 / 滚动次数 / 耗时 / 估算请求频率。

    requests 指捕获到的签名接口响应数（user_posted/comment 等），就是真正打到
    小红书的那些请求——盯这个数和频率，别把账号搞炸。
    """
    rate = (requests / elapsed * 60) if elapsed > 0 else 0.0
    _log.info(
        "[%s] 接口请求 %d 次 / 滚动 %d 次 / 耗时 %.1fs / 约 %.1f 请求·分钟⁻¹%s",
        label, requests, scrolls, elapsed, rate, (" / " + extra) if extra else "",
    )


def _build_list_contract(user_id, notes, complete, incomplete_reason) -> dict:
    image_notes = sum(1 for n in notes if n.type == "image")
    video_notes = sum(1 for n in notes if n.type == "video")
    return {
        "user_id": user_id,
        "complete": complete,
        "incomplete_reason": None if complete else incomplete_reason,
        "captured": len(notes),
        "estimated_total": None,
        "estimate": {
            "image_notes": image_notes,
            "video_notes": video_notes,
            # 清单接口拿不到每篇图片数/时长，vlm_calls 取图文篇数下界，asr_minutes 未知
            "vlm_calls": image_notes,
            "asr_minutes": None,
        },
        "notes": [
            {
                "note_id": n.note_id,
                "title": n.title,
                "type": n.type,
                "liked_count": n.liked_count,
                "xsec_token": n.xsec_token,
            }
            for n in notes
        ],
    }


async def discover_user_posts(user_url: str) -> dict:
    """列博主全量笔记清单。返回 SPEC §4.3 的 list 输出契约（含 complete 字段）。

    complete 只在**确认看到 has_more=false**时为 True；否则一律 False + incomplete_reason，
    Agent 不得当全量。浏览器任务全局串行化，Chrome 生命周期 try/finally 保证关闭。
    """
    async with _BROWSER_LOCK:
        m = _USER_ID_RE.search(user_url)
        user_id = m.group(1) if m else ""
        scroll_wait = float(os.getenv("RBCP_DISCOVER_SCROLL_WAIT", "2.2"))
        max_pages = int(os.getenv("RBCP_DISCOVER_MAX_PAGES", "80"))

        complete = False
        incomplete_reason: str | None = None
        pages: list[tuple[str, str]] = []   # [(url, body_text)]
        seen_rids: set = set()
        chrome = None
        t0 = time.monotonic()
        scrolls = 0
        try:
            chrome, tab = await _start_chrome()
            await tab.enable_network_events()
            await tab.go_to(user_url)
            await asyncio.sleep(3)

            risk = await _is_risk_page(tab)
            if risk:
                incomplete_reason = "risk_control"
            last_count, stall = 0, 0
            while not risk:
                await tab.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                scrolls += 1
                await asyncio.sleep(scroll_wait)
                await _fetch_new_bodies(tab, "user_posted", seen_rids, pages)

                if pages:
                    obj = json.loads(pages[-1][1])
                    if obj.get("success") is False or obj.get("code") not in (0, None):
                        incomplete_reason = "risk_control"
                        break
                    if obj.get("data", {}).get("has_more") is False:
                        complete = True
                        break

                if len(pages) == last_count:
                    stall += 1
                    if stall >= 3:
                        # 滚到底但没看到 has_more=false：无法确认拉全，按未完整处理
                        incomplete_reason = "network"
                        break
                else:
                    stall = 0
                last_count = len(pages)
                if len(pages) >= max_pages:
                    incomplete_reason = "network"
                    break

            # 收尾再扫一遍，捞还没 ready 的 body
            await _fetch_new_bodies(tab, "user_posted", seen_rids, pages)
        except CookieError:
            # cookie 没配/没登录：报准确原因，别混成 network
            incomplete_reason = "cookie_expired"
        except Exception as exc:  # noqa: BLE001 - 壳层兜底，细节进 reason
            incomplete_reason = incomplete_reason or "network"
            # 真实异常别丢：reason 只留机器码，详情进日志供排查（audit #5）
            _log.warning("user_posted 抓取兜底异常：%s", exc, exc_info=True)
        finally:
            if chrome is not None:
                try:
                    await chrome.stop()
                except Exception:  # noqa: BLE001
                    pass

        notes: list[Note] = []
        seen: set[str] = set()
        for _url, body_text in pages:
            try:
                page = parse_user_posted(json.loads(body_text))
            except Exception:  # noqa: BLE001 - 跳过坏页
                continue
            for note in page.notes:
                if note.note_id in seen:
                    continue
                seen.add(note.note_id)
                notes.append(note)

        if not notes and incomplete_reason is None:
            # 一条都没抓到，多半 cookie 失效 / 登录墙
            incomplete_reason = "cookie_expired"
        if incomplete_reason is not None:
            complete = False

        _log_rate(
            "user_posted", requests=len(pages), scrolls=scrolls,
            elapsed=time.monotonic() - t0,
            extra=f"{len(notes)}笔记 complete={complete} reason={incomplete_reason}",
        )
        return _build_list_contract(user_id, notes, complete, incomplete_reason)


async def discover_comments(note_url: str, *, with_sub: bool = True) -> list[Comment]:
    """抓单篇笔记评论（默认含楼中楼）。返回一级评论 list（sub_comments 已嵌套）。"""
    async with _BROWSER_LOCK:
        scroll_wait = float(os.getenv("RBCP_DISCOVER_SCROLL_WAIT", "2.0"))
        max_rounds = int(os.getenv("RBCP_COMMENT_MAX_ROUNDS", "60"))
        chrome = None
        l1_pages: list[tuple[str, str]] = []   # comment/page [(url, body)]
        sub_pages: list[tuple[str, str]] = []  # comment/sub/page [(url, body)]
        seen_rids: set = set()
        t0 = time.monotonic()
        scrolls = 0
        try:
            chrome, tab = await _start_chrome()
            await tab.enable_network_events()
            await tab.go_to(note_url)
            await asyncio.sleep(3)

            if await _is_risk_page(tab):
                # 撞验证墙，没法抓评论；抛出由调用方标 failed 留痕
                raise RiskControlError("评论抓取撞小红书安全验证，请稍后重试或刷新 cookie")

            last_count, stall = 0, 0
            for _ in range(max_rounds):
                # 滚评论容器 + 主窗，触发一级评论翻页
                await tab.execute_script(
                    "(function(){var c=document.querySelector("
                    "'.comments-el,.comments-container,.note-scroller,.comment-list');"
                    "if(c)c.scrollTop=c.scrollHeight;window.scrollTo(0,document.body.scrollHeight);})()")
                scrolls += 1
                if with_sub:
                    # 点开"展开 N 条回复"，触发 comment/sub/page
                    await tab.execute_script(
                        "(function(){var es=[].slice.call(document.querySelectorAll('*'))"
                        ".filter(function(e){return e.children.length===0&&/展开|条回复/.test(e.textContent||'')"
                        "&&(e.textContent||'').length<20;});es.slice(0,10).forEach(function(e){"
                        "try{e.click();}catch(x){}});})()")
                await asyncio.sleep(scroll_wait)

                await _fetch_new_bodies(tab, "comment/page", seen_rids, l1_pages)
                if with_sub:
                    await _fetch_new_bodies(tab, "comment/sub/page", seen_rids, sub_pages)
                total = len(l1_pages) + len(sub_pages)

                page_has_more = True
                if l1_pages:
                    obj = json.loads(l1_pages[-1][1])
                    page_has_more = bool(obj.get("data", {}).get("has_more", False))

                if total == last_count:
                    stall += 1
                    if stall >= 3 and not page_has_more:
                        break
                    if stall >= 5:
                        break
                else:
                    stall = 0
                last_count = total

            await _fetch_new_bodies(tab, "comment/page", seen_rids, l1_pages)
            if with_sub:
                await _fetch_new_bodies(tab, "comment/sub/page", seen_rids, sub_pages)
        finally:
            if chrome is not None:
                try:
                    await chrome.stop()
                except Exception:  # noqa: BLE001
                    pass

        # 一级评论：拼所有页，按 comment_id 去重
        comments: list[Comment] = []
        seen: set[str] = set()
        for _url, body_text in l1_pages:
            try:
                page = parse_comment_page(json.loads(body_text))
            except Exception:  # noqa: BLE001
                continue
            for c in page.comments:
                if c.comment_id in seen:
                    continue
                seen.add(c.comment_id)
                comments.append(c)

        # 楼中楼续拉：按 URL 里的 root_comment_id 归组
        subs_by_root: dict[str, list[Comment]] = {}
        for url, body_text in sub_pages:
            rm = _ROOT_ID_RE.search(url)
            if not rm:
                continue
            root_id = rm.group(1)
            try:
                subs, _, _ = parse_sub_comments(json.loads(body_text))
            except Exception:  # noqa: BLE001
                continue
            subs_by_root.setdefault(root_id, []).extend(subs)

        merged = merge_sub_comments(comments, subs_by_root)
        _log_rate(
            "comments", requests=len(l1_pages) + len(sub_pages), scrolls=scrolls,
            elapsed=time.monotonic() - t0,
            extra=f"{len(merged)}条一级 +{len(sub_pages)}楼中楼页",
        )
        return merged
