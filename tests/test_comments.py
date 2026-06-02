"""tests/test_comments.py — TDD for app/service/comments.py

覆盖场景：
① 一条带 2 层楼中楼的笔记 → markdown 里父评论在前、子评论缩进在后、字段都在
② 空列表 [] → 输出含"暂无评论"
③ ip_location == "" → 不报错也不留空字段行
④ write_comments_md 写出正确文件名、写完无残留 .tmp 文件
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.service.discover import Comment
from app.service.comments import format_comments_md, write_comments_md


# ── 测试数据构造 ────────────────────────────────────────────────────────────────

def _make_comment(
    comment_id="c1",
    author="用户A",
    author_id="uid_a",
    content="这是一条评论",
    like_count=10,
    ip_location="广东",
    create_time=1_717_200_000_000,  # 2024-06-01 04:00:00 UTC
    reply_to=None,
    sub_comments=None,
) -> Comment:
    return Comment(
        comment_id=comment_id,
        author=author,
        author_id=author_id,
        content=content,
        like_count=like_count,
        ip_location=ip_location,
        create_time=create_time,
        reply_to=reply_to,
        sub_comments=sub_comments or [],
    )


def _make_nested_comments() -> list[Comment]:
    """构造一条带 2 层楼中楼的评论树：
    一级评论 c1 → 子评论 c1_1 → 子评论 c1_2
    """
    sub2 = _make_comment(
        comment_id="c1_2",
        author="用户C",
        content="二级回复内容",
        like_count=2,
        ip_location="北京",
        create_time=1_717_286_400_000,  # 2024-06-02 04:00:00 UTC
        reply_to="用户B",
    )
    sub1 = _make_comment(
        comment_id="c1_1",
        author="用户B",
        content="子评论内容",
        like_count=5,
        ip_location="上海",
        create_time=1_717_243_200_000,  # 2024-06-01 16:00:00 UTC
        reply_to="用户A",
        sub_comments=[sub2],
    )
    parent = _make_comment(
        comment_id="c1",
        author="用户A",
        content="父评论内容",
        like_count=10,
        ip_location="广东",
        create_time=1_717_200_000_000,
        reply_to=None,
        sub_comments=[sub1],
    )
    return [parent]


# ── 测试：format_comments_md 纯函数 ─────────────────────────────────────────────

class TestFormatCommentsMd:

    def test_empty_list_contains_no_comments_message(self):
        md = format_comments_md("note123", [])
        assert "暂无评论" in md

    def test_empty_list_no_crash(self):
        """空列表不报错。"""
        md = format_comments_md("note123", [])
        assert isinstance(md, str)
        assert len(md) > 0

    def test_parent_comment_appears_before_sub(self):
        comments = _make_nested_comments()
        md = format_comments_md("note123", comments)
        parent_pos = md.index("父评论内容")
        child_pos = md.index("子评论内容")
        assert parent_pos < child_pos

    def test_sub_comment_indented(self):
        """子评论的行必须有缩进（相对父评论更深的层级）。"""
        comments = _make_nested_comments()
        md = format_comments_md("note123", comments)
        lines = md.splitlines()
        child_lines = [l for l in lines if "子评论内容" in l]
        assert len(child_lines) >= 1
        # 子评论行必须以空格或 > 开头（缩进或引用）
        for line in child_lines:
            assert line.startswith("  ") or line.startswith(">"), (
                f"子评论行未缩进：{line!r}"
            )

    def test_parent_author_in_output(self):
        comments = _make_nested_comments()
        md = format_comments_md("note123", comments)
        assert "用户A" in md

    def test_child_author_in_output(self):
        comments = _make_nested_comments()
        md = format_comments_md("note123", comments)
        assert "用户B" in md

    def test_like_count_in_output(self):
        comments = _make_nested_comments()
        md = format_comments_md("note123", comments)
        assert "10" in md  # 父评论点赞数

    def test_ip_location_in_output(self):
        comments = _make_nested_comments()
        md = format_comments_md("note123", comments)
        assert "广东" in md

    def test_create_time_rendered_as_date(self):
        """毫秒 epoch 1717200000000 → 2024-06-01（UTC）"""
        comments = _make_nested_comments()
        md = format_comments_md("note123", comments)
        assert "2024-06-01" in md

    def test_empty_ip_location_no_crash(self):
        """ip_location == "" 时不报错，也不出现空字段行（如 '属地：'）。"""
        comment = _make_comment(ip_location="")
        md = format_comments_md("note123", [comment])
        # 不应报错，且不留裸着的"属地："字符串（后面没有值）
        assert isinstance(md, str)
        # 不应该出现形如 "属地：\n" 的空值行
        for line in md.splitlines():
            stripped = line.strip()
            if "属地" in stripped:
                # 有"属地"字样时，后面不能是空的（末尾不能只有冒号/冒号+空格）
                assert not stripped.endswith("：") and not stripped.endswith(":"), (
                    f"ip_location 为空时留了空字段行：{line!r}"
                )

    def test_reply_to_in_sub_comment(self):
        """子评论体现回复对象。"""
        comments = _make_nested_comments()
        md = format_comments_md("note123", comments)
        # 子评论应体现"回复 用户A"
        assert "用户A" in md  # 被回复者出现在输出中

    def test_note_title_in_output(self):
        comments = _make_nested_comments()
        md = format_comments_md("note123", comments, note_title="测试笔记标题")
        assert "测试笔记标题" in md

    def test_second_level_sub_comment_in_output(self):
        """二级子评论（楼中楼的第二层）也出现在输出中。"""
        comments = _make_nested_comments()
        md = format_comments_md("note123", comments)
        assert "二级回复内容" in md

    def test_second_level_sub_comment_indented(self):
        """二级子评论缩进比一级子评论更深，或至少有缩进。"""
        comments = _make_nested_comments()
        md = format_comments_md("note123", comments)
        lines = md.splitlines()
        second_level_lines = [l for l in lines if "二级回复内容" in l]
        assert len(second_level_lines) >= 1
        for line in second_level_lines:
            assert line.startswith("  ") or line.startswith(">"), (
                f"二级子评论行未缩进：{line!r}"
            )

    def test_multiple_top_level_comments(self):
        """多条一级评论都出现在输出中。"""
        c1 = _make_comment(comment_id="x1", author="用户X", content="第一条评论")
        c2 = _make_comment(comment_id="x2", author="用户Y", content="第二条评论")
        md = format_comments_md("note123", [c1, c2])
        assert "第一条评论" in md
        assert "第二条评论" in md


# ── 测试：write_comments_md 文件落盘 ────────────────────────────────────────────

class TestWriteCommentsMd:

    def test_creates_file(self, tmp_path):
        comments = [_make_comment()]
        path = write_comments_md("note_abc", comments, tmp_path)
        assert path.exists()

    def test_filename_contains_note_id(self, tmp_path):
        comments = [_make_comment()]
        path = write_comments_md("note_abc", comments, tmp_path)
        assert "note_abc" in path.name

    def test_filename_ends_with_comments_md(self, tmp_path):
        comments = [_make_comment()]
        path = write_comments_md("note_abc", comments, tmp_path)
        assert path.name.endswith(".comments.md")

    def test_file_in_xhs_subdir(self, tmp_path):
        comments = [_make_comment()]
        path = write_comments_md("note_abc", comments, tmp_path)
        assert path.parent.name == "xhs"

    def test_no_tmp_file_left(self, tmp_path):
        """写完后没有残留 .tmp 文件。"""
        comments = [_make_comment()]
        write_comments_md("note_abc", comments, tmp_path)
        tmp_files = list(tmp_path.rglob("*.tmp"))
        assert len(tmp_files) == 0

    def test_file_content_correct(self, tmp_path):
        comment = _make_comment(author="测试作者", content="测试内容")
        path = write_comments_md("note_xyz", [comment], tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "测试作者" in content
        assert "测试内容" in content

    def test_returns_path_object(self, tmp_path):
        comments = [_make_comment()]
        result = write_comments_md("note_abc", comments, tmp_path)
        assert isinstance(result, Path)

    def test_creates_xhs_dir_if_missing(self, tmp_path):
        """xhs 子目录不存在时自动创建。"""
        assert not (tmp_path / "xhs").exists()
        comments = [_make_comment()]
        write_comments_md("note_abc", comments, tmp_path)
        assert (tmp_path / "xhs").exists()
