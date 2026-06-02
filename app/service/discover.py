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

from dataclasses import dataclass, field


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

        # liked_count 接口给字符串，转 int；缺 interact_info 时默认 0
        interact = raw.get("interact_info") or {}
        liked_count = int(interact.get("liked_count", 0))

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
        like_count=int(raw.get("like_count", 0)),
        ip_location=raw.get("ip_location", ""),
        create_time=int(raw.get("create_time", 0)),
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
        comment.sub_comment_count = int(raw.get("sub_comment_count", 0))
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
# 浏览器壳层（async）—— Phase 2 实现。pydoll 在函数内部懒加载。
# ─────────────────────────────────────────────────────────────────────────────


async def discover_user_posts(user_url: str) -> dict:
    """列博主全量笔记清单。返回 SPEC §4.3 的 list 输出契约（含 complete 字段）。"""
    raise NotImplementedError  # Phase 2


async def discover_comments(note_url: str, *, with_sub: bool = True) -> list[Comment]:
    """抓单篇笔记评论（默认含楼中楼）。返回一级评论 list（sub_comments 已嵌套）。"""
    raise NotImplementedError  # Phase 2
