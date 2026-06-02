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
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


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


# 全局串行化：一次只允许一个 Chrome 在跑（避免多会话并发抬高风控）。
# 第二个 discover 请求排队等待，不并发开第二个浏览器。
_BROWSER_LOCK = asyncio.Lock()

# XHR/fetch 拦截器：钩住 user_posted / comment/page / comment/sub/page，
# 同时存 URL 和响应体（{u, t}）——楼中楼续拉页要靠 URL 里的 root_comment_id 归组。
_INTERCEPTOR_JS = r"""
(function(){
  if (window.__rbcp_cap) return 'already';
  window.__rbcp_cap = {user_posted:[], comment_page:[], comment_sub:[]};
  function cls(u){ if(!u||typeof u!=='string')return null;
    if(u.indexOf('/user_posted')!==-1)return 'user_posted';
    if(u.indexOf('/comment/sub/page')!==-1)return 'comment_sub';
    if(u.indexOf('/comment/page')!==-1)return 'comment_page'; return null;}
  var oO=XMLHttpRequest.prototype.open,oS=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open=function(m,u){this.__u=u;return oO.apply(this,arguments);};
  XMLHttpRequest.prototype.send=function(){var x=this;x.addEventListener('load',function(){
    try{var k=cls(x.__u);if(k)window.__rbcp_cap[k].push({u:x.__u,t:x.responseText});}catch(e){}});
    return oS.apply(this,arguments);};
  var oF=window.fetch;window.fetch=function(){var a=arguments;
    var u=(a[0]&&a[0].url)?a[0].url:a[0];
    return oF.apply(this,a).then(function(r){try{var k=cls(u);
      if(k)r.clone().text().then(function(t){window.__rbcp_cap[k].push({u:u,t:t});});}catch(e){}
      return r;});};
  return 'installed';
})()
"""

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


def _load_cookies() -> list[dict]:
    """解析小红书 cookie，供 pydoll set_cookies。按优先级取来源：

    1. 环境变量 ``XHS_COOKIE``（原始串 'web_session=...; a1=...'）—— 生产首选。
    2. 环境变量 ``RBCP_XHS_COOKIE_FILE``（指向 cookie JSON 文件）—— dev / 自动化用。

    两者都没有则报错（壳层会把它转成失败留痕）。
    """
    raw = os.getenv("XHS_COOKIE", "").strip()
    if raw:
        return _cookies_from_string(raw)

    file_path = os.getenv("RBCP_XHS_COOKIE_FILE", "").strip()
    if file_path:
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise RuntimeError(f"RBCP_XHS_COOKIE_FILE 指向的文件不存在：{path}")
        cookies = _cookies_from_file(path)
        if not cookies:
            raise RuntimeError(f"RBCP_XHS_COOKIE_FILE 文件里没有可用 cookie：{path}")
        return cookies

    raise RuntimeError(
        "未配置小红书 cookie：在 .env 设 XHS_COOKIE='web_session=...; a1=...'，"
        "或设 RBCP_XHS_COOKIE_FILE 指向 cookie JSON 文件"
    )


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
        pages: list[str] = []
        chrome = None
        try:
            chrome, tab = await _start_chrome()
            await tab.go_to(user_url)
            await asyncio.sleep(3)
            await tab.execute_script(_INTERCEPTOR_JS)

            risk = await _is_risk_page(tab)
            if risk:
                incomplete_reason = "risk_control"
            last_count, stall = 0, 0
            while not risk:
                await tab.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(scroll_wait)
                count = int(await _eval(
                    tab, "(window.__rbcp_cap&&window.__rbcp_cap.user_posted.length)||0") or 0)

                latest = await _eval(
                    tab,
                    "window.__rbcp_cap&&window.__rbcp_cap.user_posted.length?"
                    "window.__rbcp_cap.user_posted[window.__rbcp_cap.user_posted.length-1].t:''")
                if latest:
                    obj = json.loads(latest)
                    if obj.get("success") is False or obj.get("code") not in (0, None):
                        incomplete_reason = "risk_control"
                        break
                    if obj.get("data", {}).get("has_more") is False:
                        complete = True
                        break

                if count == last_count:
                    stall += 1
                    if stall >= 3:
                        # 滚到底但没看到 has_more=false：无法确认拉全，按未完整处理
                        incomplete_reason = "network"
                        break
                else:
                    stall = 0
                last_count = count
                if count >= max_pages:
                    incomplete_reason = "network"
                    break

            raw = await _eval(
                tab,
                "JSON.stringify((window.__rbcp_cap?window.__rbcp_cap.user_posted:[])"
                ".map(function(x){return x.t;}))")
            pages = json.loads(raw or "[]")
        except Exception as exc:  # noqa: BLE001 - 壳层兜底，细节进 reason
            incomplete_reason = incomplete_reason or "network"
            if not pages:
                incomplete_reason = "network"
            _ = exc
        finally:
            if chrome is not None:
                try:
                    await chrome.stop()
                except Exception:  # noqa: BLE001
                    pass

        notes: list[Note] = []
        seen: set[str] = set()
        for page_text in pages:
            try:
                page = parse_user_posted(json.loads(page_text))
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

        return _build_list_contract(user_id, notes, complete, incomplete_reason)


async def discover_comments(note_url: str, *, with_sub: bool = True) -> list[Comment]:
    """抓单篇笔记评论（默认含楼中楼）。返回一级评论 list（sub_comments 已嵌套）。"""
    async with _BROWSER_LOCK:
        scroll_wait = float(os.getenv("RBCP_DISCOVER_SCROLL_WAIT", "2.0"))
        max_rounds = int(os.getenv("RBCP_COMMENT_MAX_ROUNDS", "60"))
        chrome = None
        page_texts: list[str] = []
        sub_items: list[dict] = []
        try:
            chrome, tab = await _start_chrome()
            await tab.go_to(note_url)
            await asyncio.sleep(3)
            await tab.execute_script(_INTERCEPTOR_JS)

            if await _is_risk_page(tab):
                # 撞验证墙，没法抓评论；返回空（壳层不抛，调用方按空处理）
                raise RiskControlError("评论抓取撞小红书安全验证，请稍后重试或刷新 cookie")

            last_count, stall = 0, 0
            for _ in range(max_rounds):
                # 滚评论容器 + 主窗，触发一级评论翻页
                await tab.execute_script(
                    "(function(){var c=document.querySelector("
                    "'.comments-el,.comments-container,.note-scroller,.comment-list');"
                    "if(c)c.scrollTop=c.scrollHeight;window.scrollTo(0,document.body.scrollHeight);})()")
                if with_sub:
                    # 点开"展开 N 条回复"，触发 comment/sub/page
                    await tab.execute_script(
                        "(function(){var es=[].slice.call(document.querySelectorAll('*'))"
                        ".filter(function(e){return e.children.length===0&&/展开|条回复/.test(e.textContent||'')"
                        "&&(e.textContent||'').length<20;});es.slice(0,10).forEach(function(e){"
                        "try{e.click();}catch(x){}});})()")
                await asyncio.sleep(scroll_wait)

                cp_count = int(await _eval(
                    tab, "(window.__rbcp_cap&&window.__rbcp_cap.comment_page.length)||0") or 0)
                cs_count = int(await _eval(
                    tab, "(window.__rbcp_cap&&window.__rbcp_cap.comment_sub.length)||0") or 0)
                total = cp_count + cs_count

                latest = await _eval(
                    tab,
                    "window.__rbcp_cap&&window.__rbcp_cap.comment_page.length?"
                    "window.__rbcp_cap.comment_page[window.__rbcp_cap.comment_page.length-1].t:''")
                page_has_more = True
                if latest:
                    obj = json.loads(latest)
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

            page_texts = json.loads(await _eval(
                tab,
                "JSON.stringify((window.__rbcp_cap?window.__rbcp_cap.comment_page:[])"
                ".map(function(x){return x.t;}))") or "[]")
            sub_items = json.loads(await _eval(
                tab,
                "JSON.stringify((window.__rbcp_cap?window.__rbcp_cap.comment_sub:[]))") or "[]")
        finally:
            if chrome is not None:
                try:
                    await chrome.stop()
                except Exception:  # noqa: BLE001
                    pass

        # 一级评论：拼所有页，按 comment_id 去重
        comments: list[Comment] = []
        seen: set[str] = set()
        for text in page_texts:
            try:
                page = parse_comment_page(json.loads(text))
            except Exception:  # noqa: BLE001
                continue
            for c in page.comments:
                if c.comment_id in seen:
                    continue
                seen.add(c.comment_id)
                comments.append(c)

        # 楼中楼续拉：按 URL 里的 root_comment_id 归组
        subs_by_root: dict[str, list[Comment]] = {}
        for item in sub_items:
            url = item.get("u", "")
            rm = _ROOT_ID_RE.search(url)
            if not rm:
                continue
            root_id = rm.group(1)
            try:
                subs, _, _ = parse_sub_comments(json.loads(item["t"]))
            except Exception:  # noqa: BLE001
                continue
            subs_by_root.setdefault(root_id, []).extend(subs)

        return merge_sub_comments(comments, subs_by_root)
