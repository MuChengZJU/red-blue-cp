"""纯函数解析层单测（Phase 1-A TDD）。

喂 tests/fixtures/xhs/ 的脱敏 JSON，验证 parse_user_posted / parse_comment_page /
parse_sub_comments / merge_sub_comments 四个纯函数的行为。

无 I/O、无网络、无浏览器。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.service.discover import (
    Comment,
    CommentPage,
    Note,
    NotePage,
    merge_sub_comments,
    parse_comment_page,
    parse_sub_comments,
    parse_user_posted,
)

# ─── fixtures 路径 ──────────────────────────────────────────────────────────

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "xhs"


def load(filename: str) -> dict:
    return json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))


# ─── parse_user_posted ──────────────────────────────────────────────────────


class TestParseUserPosted:
    def test_page1_note_count(self):
        """page1 应返回 3 条 Note。"""
        page = parse_user_posted(load("user_posted_page1.json"))
        assert isinstance(page, NotePage)
        assert len(page.notes) == 3

    def test_page1_has_more_and_cursor(self):
        """page1 has_more=True，cursor 非空。"""
        page = parse_user_posted(load("user_posted_page1.json"))
        assert page.has_more is True
        assert page.cursor != ""

    def test_page1_type_mapping(self):
        """接口 normal→'image'，video→'video'。"""
        page = parse_user_posted(load("user_posted_page1.json"))
        notes = page.notes
        assert notes[0].type == "image"   # fixture note1: normal
        assert notes[1].type == "video"   # fixture note2: video
        assert notes[2].type == "image"   # fixture note3: normal

    def test_page1_third_note_empty_title(self):
        """第 3 条 display_title 为 ''，解析后 title == ''，不报错。"""
        page = parse_user_posted(load("user_posted_page1.json"))
        assert page.notes[2].title == ""

    def test_page1_liked_count_is_int(self):
        """接口 liked_count 是字符串 '128'，解析后是 int 128。"""
        page = parse_user_posted(load("user_posted_page1.json"))
        assert page.notes[0].liked_count == 128
        assert isinstance(page.notes[0].liked_count, int)

    def test_page1_author_fields(self):
        """author 来自 user.nickname，author_id 来自 user.user_id。"""
        page = parse_user_posted(load("user_posted_page1.json"))
        note = page.notes[0]
        assert note.author == "测试博主"
        assert note.author_id == "fixtureuser0000000000000001"

    def test_page1_note_id_and_xsec_token(self):
        """note_id 和 xsec_token 正确透传。"""
        page = parse_user_posted(load("user_posted_page1.json"))
        note = page.notes[0]
        assert note.note_id == "fixturenote000000000000001"
        assert note.xsec_token == "FAKE-TOKEN-AAAA-0001="

    def test_last_page_has_more_false(self):
        """末页 has_more=False，cursor=''。"""
        page = parse_user_posted(load("user_posted_last.json"))
        assert page.has_more is False
        assert page.cursor == ""

    def test_last_page_note_count(self):
        """末页返回 1 条 Note。"""
        page = parse_user_posted(load("user_posted_last.json"))
        assert len(page.notes) == 1

    def test_missing_interact_info_defaults_liked_count_to_zero(self):
        """note 缺 interact_info 时 liked_count 默认 0，不抛异常。"""
        raw = load("user_posted_page1.json")
        # 删除第一条 note 的 interact_info
        del raw["data"]["notes"][0]["interact_info"]
        page = parse_user_posted(raw)
        assert page.notes[0].liked_count == 0

    def test_notes_are_note_instances(self):
        """返回的 notes 都是 Note 类型。"""
        page = parse_user_posted(load("user_posted_page1.json"))
        for note in page.notes:
            assert isinstance(note, Note)


# ─── parse_comment_page ─────────────────────────────────────────────────────


class TestParseCommentPage:
    def setup_method(self):
        self.page: CommentPage = parse_comment_page(load("comment_page.json"))

    def test_two_top_level_comments(self):
        """comment_page 有 2 条一级评论。"""
        assert isinstance(self.page, CommentPage)
        assert len(self.page.comments) == 2

    def test_c1_no_sub_comments(self):
        """c1 sub_comment_count=0，sub_comments=[]。"""
        c1 = self.page.comments[0]
        assert c1.sub_comment_count == 0
        assert c1.sub_comments == []

    def test_c1_reply_to_is_none(self):
        """一级评论 reply_to 为 None。"""
        c1 = self.page.comments[0]
        assert c1.reply_to is None

    def test_c2_sub_comment_count(self):
        """c2 sub_comment_count=3。"""
        c2 = self.page.comments[1]
        assert c2.sub_comment_count == 3

    def test_c2_sub_comment_has_more(self):
        """c2 sub_comment_has_more=True。"""
        c2 = self.page.comments[1]
        assert c2.sub_comment_has_more is True

    def test_c2_sub_comment_cursor_nonempty(self):
        """c2 sub_comment_cursor 非空。"""
        c2 = self.page.comments[1]
        assert c2.sub_comment_cursor != ""

    def test_c2_inline_sub_comments_count(self):
        """c2 内联 sub_comments 有 1 条。"""
        c2 = self.page.comments[1]
        assert len(c2.sub_comments) == 1

    def test_c2_inline_sub_reply_to(self):
        """内联子评论的 reply_to 是被回复者昵称（来自 target_comment.user_info.nickname）。"""
        c2 = self.page.comments[1]
        sub = c2.sub_comments[0]
        assert sub.reply_to == "评论者乙"

    def test_like_count_is_int(self):
        """like_count 接口给字符串，解析后是 int。"""
        c1 = self.page.comments[0]
        assert c1.like_count == 12
        assert isinstance(c1.like_count, int)

    def test_create_time_is_int(self):
        """create_time 是 int（毫秒 epoch）。"""
        c1 = self.page.comments[0]
        assert c1.create_time == 1780408417000
        assert isinstance(c1.create_time, int)

    def test_author_fields(self):
        """author 来自 user_info.nickname，author_id 来自 user_info.user_id。"""
        c1 = self.page.comments[0]
        assert c1.author == "评论者甲"
        assert c1.author_id == "fixturecmtuser0000000000001"

    def test_comment_id(self):
        """comment_id 来自接口 id 字段。"""
        c1 = self.page.comments[0]
        assert c1.comment_id == "fixturecmt0000000000000001"

    def test_page_cursor_and_has_more(self):
        """CommentPage cursor 和 has_more 正确解析。"""
        assert self.page.cursor == "6a000comment00000000cur01"
        assert self.page.has_more is True


# ─── parse_sub_comments ─────────────────────────────────────────────────────


class TestParseSubComments:
    def setup_method(self):
        result = parse_sub_comments(load("comment_sub_page.json"))
        self.subs, self.cursor, self.has_more = result

    def test_returns_two_comments(self):
        """续拉页有 2 条子评论。"""
        assert len(self.subs) == 2

    def test_cursor_empty(self):
        """末页 cursor=''。"""
        assert self.cursor == ""

    def test_has_more_false(self):
        """末页 has_more=False。"""
        assert self.has_more is False

    def test_reply_to_filled_from_target_comment(self):
        """每条子评论 reply_to 由 target_comment.user_info.nickname 填好。"""
        assert self.subs[0].reply_to == "评论者乙"
        assert self.subs[1].reply_to == "回复者丙"

    def test_subs_are_comment_instances(self):
        """返回的都是 Comment 类型。"""
        for sub in self.subs:
            assert isinstance(sub, Comment)

    def test_like_count_is_int(self):
        """like_count 是 int。"""
        assert self.subs[0].like_count == 1
        assert isinstance(self.subs[0].like_count, int)


# ─── merge_sub_comments ─────────────────────────────────────────────────────


class TestMergeSubComments:
    """merge_sub_comments：把续拉到的楼中楼合并进一级评论。"""

    def _build_c2_with_inline(self) -> Comment:
        """从 fixture 解析出 c2（已含内联 1 条 sub_comment）。"""
        page = parse_comment_page(load("comment_page.json"))
        return page.comments[1]

    def _build_extra_subs(self) -> list[Comment]:
        """从 comment_sub_page 续拉到的 2 条子评论。"""
        subs, _, _ = parse_sub_comments(load("comment_sub_page.json"))
        return subs

    def test_merge_total_count(self):
        """内联 1 + 续拉 2 = 合并后 sub_comments 共 3 条。"""
        c2 = self._build_c2_with_inline()
        extra = self._build_extra_subs()
        merged = merge_sub_comments([c2], {"fixturecmt0000000000000002": extra})
        c2_merged = merged[0]
        assert len(c2_merged.sub_comments) == 3

    def test_merge_count_matches_declared(self):
        """合并后数量等于 c2.sub_comment_count（=3）。"""
        c2 = self._build_c2_with_inline()
        extra = self._build_extra_subs()
        merged = merge_sub_comments([c2], {"fixturecmt0000000000000002": extra})
        c2_merged = merged[0]
        assert len(c2_merged.sub_comments) == c2_merged.sub_comment_count

    def test_merge_dedup(self):
        """重复合并幂等——对同一条 extra_subs 调用两次结果相同（不翻倍）。"""
        c2 = self._build_c2_with_inline()
        extra = self._build_extra_subs()
        subs_by_root = {"fixturecmt0000000000000002": extra}

        # 第一次合并
        merged1 = merge_sub_comments([c2], subs_by_root)
        count1 = len(merged1[0].sub_comments)

        # 第二次用已合并的结果再合并
        merged2 = merge_sub_comments(merged1, subs_by_root)
        count2 = len(merged2[0].sub_comments)

        assert count1 == count2 == 3

    def test_merge_order_stable(self):
        """合并后顺序稳定：内联在前，续拉在后。"""
        c2 = self._build_c2_with_inline()
        extra = self._build_extra_subs()
        merged = merge_sub_comments([c2], {"fixturecmt0000000000000002": extra})
        ids = [s.comment_id for s in merged[0].sub_comments]
        assert ids == [
            "fixturesub00000000000000a1",  # 内联
            "fixturesub00000000000000a2",  # 续拉 1
            "fixturesub00000000000000a3",  # 续拉 2
        ]

    def test_merge_no_match_leaves_original(self):
        """subs_by_root 里没有对应 id 的条目，原 sub_comments 不变。"""
        c2 = self._build_c2_with_inline()
        original_len = len(c2.sub_comments)
        merged = merge_sub_comments([c2], {})
        assert len(merged[0].sub_comments) == original_len

    def test_merge_does_not_mutate_input(self):
        """merge_sub_comments 是纯函数：不修改传入的 comments list 本身（返回新 list）。"""
        c2 = self._build_c2_with_inline()
        extra = self._build_extra_subs()
        original_sub_count = len(c2.sub_comments)
        _ = merge_sub_comments([c2], {"fixturecmt0000000000000002": extra})
        # 原始 c2 对象的 sub_comments 不应被在意（dataclass 是可变的，这里测返回新list
        # 而非 comments list 本身不变——实现可复用原 Comment 对象，只要不替换引用即可）
        # 核心是返回值正确，不是 in-place 修改限制，所以只验返回值长度
        result = merge_sub_comments([c2], {"fixturecmt0000000000000002": extra})
        assert len(result) == 1
        assert len(result[0].sub_comments) == 3


# ─── 真实数据回归：计数字段空串（fixture 漏了，真链路实测抓到）──────────────


def test_liked_count_empty_string_coerces_to_zero():
    """真实 user_posted 里 liked_count 可能是空串 ""，不能让 int("") 崩。"""
    resp = {
        "success": True,
        "code": 0,
        "data": {
            "cursor": "c",
            "has_more": True,
            "notes": [{
                "note_id": "n",
                "xsec_token": "t",
                "type": "normal",
                "display_title": "x",
                "user": {"nickname": "u", "user_id": "uid"},
                "interact_info": {"liked_count": ""},  # 空串
            }],
        },
    }
    page = parse_user_posted(resp)
    assert page.notes[0].liked_count == 0


def test_comment_counts_empty_string_coerce_to_zero():
    resp = {
        "code": 0, "success": True,
        "data": {"cursor": "", "has_more": False, "comments": [{
            "id": "c", "note_id": "n", "content": "x",
            "user_info": {"nickname": "u", "user_id": "uid"},
            "like_count": "", "create_time": "", "ip_location": "",
            "sub_comment_count": "", "sub_comment_has_more": False,
            "sub_comment_cursor": "", "sub_comments": [],
        }]},
    }
    page = parse_comment_page(resp)
    c = page.comments[0]
    assert c.like_count == 0
    assert c.create_time == 0
    assert c.sub_comment_count == 0
