"""sanitize_filename 测试 — 按 SPEC §6.2 定义接口契约。

输入：title, author, date, suffix_id
输出："{date}-{safe_author}-{safe_title}-{suffix_id}" 格式的文件名（不含 .md）
"""

import pytest
from app.extract.markdown import sanitize_filename


class TestSanitizeFilename:

    def test_normal_case(self):
        result = sanitize_filename(
            title="如何学习深度学习",
            author="张三",
            date="2025-01-15",
            suffix_id="BV1234567890",
        )
        assert result == "2025-01-15-张三-如何学习深度学习-BV1234567890"

    def test_special_chars_removed(self):
        result = sanitize_filename(
            title='标题/含\\特:殊*字?符"和<尖>括|号',
            author="up主",
            date="2025-03-01",
            suffix_id="BV9999",
        )
        assert "/" not in result
        assert "\\" not in result
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result
        assert '"' not in result
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result
        assert "BV9999" in result
        assert "up主" in result

    def test_emoji_removed(self):
        result = sanitize_filename(
            title="今天吃了🍕好开心😊",
            author="美食博主",
            date="2025-06-01",
            suffix_id="note123",
        )
        assert "🍕" not in result
        assert "😊" not in result
        assert "今天吃了" in result
        assert "好开心" in result

    def test_title_truncated_to_60_chars(self):
        long_title = "这是一个" * 20  # 80 chars
        result = sanitize_filename(
            title=long_title,
            author="作者",
            date="2025-01-01",
            suffix_id="BV1",
        )
        # 提取 title 部分: date-author-TITLE-suffix
        parts = result.split("-", 3)  # ['2025', '01', '01', 'author-title-suffix']
        after_date = parts[3]  # "作者-truncated_title-BV1"
        title_part = after_date.split("-", 1)[1].rsplit("-", 1)[0]
        assert len(title_part) <= 60

    def test_empty_author_becomes_unknown(self):
        result = sanitize_filename(
            title="测试视频",
            author="",
            date="2025-02-28",
            suffix_id="BV1111",
        )
        assert "unknown_author" in result

    def test_none_author_becomes_unknown(self):
        result = sanitize_filename(
            title="测试视频",
            author=None,
            date="2025-02-28",
            suffix_id="BV1111",
        )
        assert "unknown_author" in result

    def test_empty_title_uses_suffix_id(self):
        result = sanitize_filename(
            title="",
            author="某博主",
            date="2025-04-01",
            suffix_id="note_abc123",
        )
        # title 为空时，title 部分应该用 suffix_id 填充
        assert "note_abc123" in result

    def test_consecutive_whitespace_compressed(self):
        result = sanitize_filename(
            title="标题   有   很多   空格",
            author="作者",
            date="2025-01-01",
            suffix_id="BV1",
        )
        assert "   " not in result
        assert "标题 有 很多 空格" in result or "标题 有 很多 空格" in result

    def test_fullwidth_space_unified(self):
        # 　 是全角空格
        result = sanitize_filename(
            title="全角　空格　测试",
            author="作者",
            date="2025-01-01",
            suffix_id="BV1",
        )
        assert "　" not in result
        assert "全角 空格 测试" in result or "全角空格测试" in result

    def test_control_chars_removed(self):
        result = sanitize_filename(
            title="含有\x00控制\x1f字符",
            author="作者",
            date="2025-01-01",
            suffix_id="BV1",
        )
        assert "\x00" not in result
        assert "\x1f" not in result
        assert "含有" in result

    def test_suffix_always_present(self):
        result = sanitize_filename(
            title="任意标题",
            author="任意作者",
            date="2025-01-01",
            suffix_id="BV_unique_123",
        )
        assert result.endswith("BV_unique_123")

    def test_same_title_different_suffix_no_collision(self):
        r1 = sanitize_filename("相同标题", "同一作者", "2025-01-01", "BV001")
        r2 = sanitize_filename("相同标题", "同一作者", "2025-01-01", "BV002")
        assert r1 != r2

    def test_date_preserved_as_prefix(self):
        result = sanitize_filename(
            title="视频",
            author="作者",
            date="2026-05-09",
            suffix_id="BV1",
        )
        assert result.startswith("2026-05-09")
