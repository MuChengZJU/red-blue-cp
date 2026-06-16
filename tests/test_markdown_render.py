"""render_and_write 测试 — Markdown 模板渲染 + 原子写入。

按 SPEC §6.3 和 §6.4 定义接口契约。
"""

import os
import tempfile
from pathlib import Path

import pytest
from app.extract.markdown import render_and_write


@pytest.fixture
def output_dir(tmp_path):
    bili_dir = tmp_path / "bili"
    bili_dir.mkdir()
    xhs_dir = tmp_path / "xhs"
    xhs_dir.mkdir()
    return tmp_path


class TestRenderAndWrite:

    def test_returns_path(self, output_dir):
        result = _make_result()
        path = render_and_write(result, output_dir=output_dir)
        assert isinstance(path, Path)
        assert path.exists()

    def test_file_has_md_extension(self, output_dir):
        result = _make_result()
        path = render_and_write(result, output_dir=output_dir)
        assert path.suffix == ".md"

    def test_bilibili_goes_to_bili_dir(self, output_dir):
        result = _make_result(platform="bilibili")
        path = render_and_write(result, output_dir=output_dir)
        assert "bili" in str(path)

    def test_xiaohongshu_goes_to_xhs_dir(self, output_dir):
        result = _make_result(platform="xiaohongshu")
        path = render_and_write(result, output_dir=output_dir)
        assert "xhs" in str(path)

    def test_frontmatter_present(self, output_dir):
        result = _make_result()
        path = render_and_write(result, output_dir=output_dir)
        content = path.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "---" in content[3:]  # closing frontmatter

    def test_frontmatter_contains_platform(self, output_dir):
        result = _make_result(platform="bilibili")
        path = render_and_write(result, output_dir=output_dir)
        content = path.read_text(encoding="utf-8")
        assert "platform: bilibili" in content

    def test_frontmatter_contains_title(self, output_dir):
        result = _make_result(title="测试标题")
        path = render_and_write(result, output_dir=output_dir)
        content = path.read_text(encoding="utf-8")
        assert "测试标题" in content

    def test_frontmatter_contains_author(self, output_dir):
        result = _make_result(author="测试作者")
        path = render_and_write(result, output_dir=output_dir)
        content = path.read_text(encoding="utf-8")
        assert "测试作者" in content

    def test_frontmatter_contains_url(self, output_dir):
        result = _make_result(url="https://www.bilibili.com/video/BV1test")
        path = render_and_write(result, output_dir=output_dir)
        content = path.read_text(encoding="utf-8")
        assert "https://www.bilibili.com/video/BV1test" in content

    def test_text_in_body(self, output_dir):
        result = _make_result(text="这是转录的正文内容")
        path = render_and_write(result, output_dir=output_dir)
        content = path.read_text(encoding="utf-8")
        assert "这是转录的正文内容" in content

    def test_no_tmp_file_left(self, output_dir):
        result = _make_result()
        render_and_write(result, output_dir=output_dir)
        tmp_files = list(output_dir.rglob("*.tmp"))
        assert len(tmp_files) == 0

    def test_title_with_jinja2_chars_safe(self, output_dir):
        result = _make_result(title="标题含 {{ 和 }} 字符")
        path = render_and_write(result, output_dir=output_dir)
        content = path.read_text(encoding="utf-8")
        assert "{{" in content or "标题含" in content  # 不能因 Jinja2 崩溃

    def test_creates_subdirectory_if_missing(self, tmp_path):
        result = _make_result(platform="bilibili")
        path = render_and_write(result, output_dir=tmp_path)
        assert path.exists()

    def test_metadata_status_in_frontmatter(self, output_dir):
        result = _make_result(metadata={"status": "subtitle"})
        path = render_and_write(result, output_dir=output_dir)
        content = path.read_text(encoding="utf-8")
        assert "status: subtitle" in content


# ── Helpers ────────────────────────────────────────────────────

def _make_result(
    platform="bilibili",
    content_type="video",
    title="测试视频",
    author="测试UP主",
    author_id="12345",
    published_at="2025-01-15",
    url="https://www.bilibili.com/video/BV1test",
    text="这是正文内容",
    metadata=None,
    raw_info=None,
):
    from app.extract.extractor import ExtractResult
    return ExtractResult(
        platform=platform,
        content_type=content_type,
        title=title,
        author=author,
        author_id=author_id,
        published_at=published_at,
        url=url,
        text=text,
        metadata=metadata or {"status": "subtitle"},
        raw_info=raw_info or {},
    )
