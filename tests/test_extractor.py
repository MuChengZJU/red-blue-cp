"""extractor + fetcher 测试 — 定义编排层接口契约。

测试策略：mock fetcher 函数和 ModelProvider，测编排逻辑。
不测 HTTP 细节（那是 fetcher 的事），测"给了什么数据 → 调了什么模型 → 输出什么结果"。
"""

from dataclasses import fields
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from app.extract.extractor import extract_url, detect_platform, ExtractResult
from app.extract.errors import UnsupportedUrlError


# ── URL 检测 ───────────────────────────────────────────────────

class TestDetectPlatform:

    def test_bilibili_full_url(self):
        assert detect_platform("https://www.bilibili.com/video/BV1xx411c7mD") == "bilibili"

    def test_bilibili_short_url(self):
        assert detect_platform("https://b23.tv/abc123") == "bilibili"

    def test_xiaohongshu_full_url(self):
        assert detect_platform("https://www.xiaohongshu.com/explore/abc123") == "xiaohongshu"

    def test_xiaohongshu_short_url(self):
        assert detect_platform("https://xhslink.com/abc123") == "xiaohongshu"

    def test_unknown_url_raises(self):
        with pytest.raises(UnsupportedUrlError):
            detect_platform("https://www.youtube.com/watch?v=xxx")

    def test_bilibili_mobile_url(self):
        assert detect_platform("https://m.bilibili.com/video/BV1xx411c7mD") == "bilibili"

    def test_xiaohongshu_discovery_url(self):
        assert detect_platform("https://www.xiaohongshu.com/discovery/item/abc123") == "xiaohongshu"


# ── ExtractResult 结构 ─────────────────────────────────────────

class TestExtractResult:

    def test_is_dataclass(self):
        field_names = {f.name for f in fields(ExtractResult)}
        expected = {
            "platform", "content_type", "title", "author", "author_id",
            "published_at", "url", "text", "readable_text", "text_sha256", "metadata", "segments",
        }
        assert expected.issubset(field_names)


# ── B 站视频提取 ──────────────────────────────────────────────

class TestBilibiliVideoExtraction:

    @patch("app.extract.extractor.fetcher")
    def test_with_subtitle_skips_asr(self, mock_fetcher):
        mock_fetcher.fetch_bilibili.return_value = _bili_video_info(
            subtitle_text="字幕内容在这里",
        )
        provider = _mock_provider(llm_clean_result="清洗后的字幕")

        result = extract_url("https://www.bilibili.com/video/BV1test", provider)

        assert result.platform == "bilibili"
        assert result.content_type == "video"
        assert result.readable_text == "清洗后的字幕"
        assert result.title == "测试视频标题"
        assert result.author == "测试UP主"
        # 有字幕时不应该调 ASR
        provider.asr.assert_not_called()
        provider.llm_clean.assert_called_once()

    @patch("app.extract.extractor.fetcher")
    def test_without_subtitle_uses_asr(self, mock_fetcher):
        mock_fetcher.fetch_bilibili.return_value = _bili_video_info(
            subtitle_text=None,
            audio_url="https://example.com/audio.m4s",
        )
        provider = _mock_provider(
            asr_result="ASR转写文本",
            llm_clean_result="清洗后的ASR文本",
        )

        result = extract_url("https://www.bilibili.com/video/BV1test", provider)

        assert result.readable_text == "清洗后的ASR文本"
        provider.asr.assert_called_once()
        provider.llm_clean.assert_called_once()

    @patch("app.extract.extractor.fetcher")
    def test_result_fields_populated(self, mock_fetcher):
        mock_fetcher.fetch_bilibili.return_value = _bili_video_info(
            subtitle_text="有字幕",
        )
        provider = _mock_provider(llm_clean_result="文本")

        result = extract_url("https://www.bilibili.com/video/BV1test", provider)

        assert result.author_id == "12345"
        assert result.url == "https://www.bilibili.com/video/BV1test"
        assert result.published_at is not None
        assert isinstance(result.metadata, dict)

    @patch("app.extract.extractor.fetcher")
    def test_subtitle_status_in_metadata(self, mock_fetcher):
        mock_fetcher.fetch_bilibili.return_value = _bili_video_info(
            subtitle_text="有字幕",
        )
        provider = _mock_provider(llm_clean_result="文本")

        result = extract_url("https://www.bilibili.com/video/BV1test", provider)
        assert result.metadata.get("status") == "subtitle"

    @patch("app.extract.extractor.fetcher")
    def test_asr_status_when_no_subtitle(self, mock_fetcher):
        mock_fetcher.fetch_bilibili.return_value = _bili_video_info(
            subtitle_text=None,
            audio_url="https://example.com/audio.m4s",
        )
        provider = _mock_provider(asr_result="asr", llm_clean_result="文本")

        result = extract_url("https://www.bilibili.com/video/BV1test", provider)
        assert result.metadata.get("status") == "asr"


# ── 小红书视频提取 ────────────────────────────────────────────

class TestXhsVideoExtraction:

    @patch("app.extract.extractor.fetcher")
    def test_video_uses_asr(self, mock_fetcher):
        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_video_info()
        provider = _mock_provider(
            asr_result="小红书视频ASR文本",
            llm_clean_result="清洗后文本",
        )

        result = extract_url("https://www.xiaohongshu.com/explore/vid123", provider)

        assert result.platform == "xiaohongshu"
        assert result.content_type == "video"
        assert result.readable_text == "清洗后文本"
        provider.asr.assert_called_once()

    @patch("app.extract.extractor.fetcher")
    def test_passes_referer_to_asr(self, mock_fetcher):
        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_video_info()
        provider = _mock_provider(asr_result="text", llm_clean_result="clean")

        extract_url("https://www.xiaohongshu.com/explore/vid123", provider)

        call_kwargs = provider.asr.call_args
        # referer 应该包含 xiaohongshu
        args = call_kwargs[0] if call_kwargs[0] else ()
        kwargs = call_kwargs[1] if call_kwargs[1] else {}
        referer = kwargs.get("referer", args[1] if len(args) > 1 else None)
        assert referer is not None and "xiaohongshu" in referer


# ── 小红书图文提取 ────────────────────────────────────────────

class TestXhsImageNoteExtraction:

    @patch("app.extract.extractor.fetcher")
    def test_image_note_uses_vlm(self, mock_fetcher):
        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_image_note_info(
            image_urls=["https://img.xhs.com/1.jpg", "https://img.xhs.com/2.jpg"],
        )
        provider = _mock_provider(
            vlm_result="图片文字内容",
            llm_clean_result="清洗后的图文",
        )

        result = extract_url("https://www.xiaohongshu.com/explore/note123", provider)

        assert result.platform == "xiaohongshu"
        assert result.content_type == "image_note"
        assert result.readable_text == "清洗后的图文"
        assert provider.vlm.call_count == 2  # 每张图调一次

    @patch("app.extract.extractor.fetcher")
    def test_image_count_in_metadata(self, mock_fetcher):
        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_image_note_info(
            image_urls=["https://img.xhs.com/1.jpg", "https://img.xhs.com/2.jpg", "https://img.xhs.com/3.jpg"],
        )
        provider = _mock_provider(vlm_result="text", llm_clean_result="clean")

        result = extract_url("https://www.xiaohongshu.com/explore/note123", provider)
        assert result.metadata.get("image_count") == 3

    @patch("app.extract.extractor.fetcher")
    def test_vision_status_in_metadata(self, mock_fetcher):
        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_image_note_info(
            image_urls=["https://img.xhs.com/1.jpg"],
        )
        provider = _mock_provider(vlm_result="text", llm_clean_result="clean")

        result = extract_url("https://www.xiaohongshu.com/explore/note123", provider)
        assert result.metadata.get("status") == "vision"


# ── 错误处理 ──────────────────────────────────────────────────

class TestErrorHandling:

    def test_invalid_url_raises_unsupported_url_error(self):
        provider = _mock_provider()
        with pytest.raises(UnsupportedUrlError):
            extract_url("https://www.youtube.com/watch?v=xxx", provider)

    @patch("app.extract.extractor.fetcher")
    def test_fetcher_error_propagates(self, mock_fetcher):
        mock_fetcher.fetch_bilibili.side_effect = RuntimeError("B站 API 返回异常")
        provider = _mock_provider()
        with pytest.raises(RuntimeError):
            extract_url("https://www.bilibili.com/video/BV1test", provider)


# ── Test Fixtures ─────────────────────────────────────────────

def _mock_provider(
    asr_result="",
    vlm_result="",
    llm_clean_result="",
):
    provider = MagicMock()
    provider.asr.return_value = (asr_result, ())
    provider.vlm.return_value = vlm_result
    provider.llm_clean.return_value = llm_clean_result
    return provider


def _bili_video_info(
    subtitle_text=None,
    audio_url=None,
):
    return {
        "platform": "bilibili",
        "content_type": "video",
        "title": "测试视频标题",
        "author": "测试UP主",
        "author_id": "12345",
        "post_id": "BV1test",
        "published_at": "2025-01-15",
        "url": "https://www.bilibili.com/video/BV1test",
        "subtitle_text": subtitle_text,
        "audio_url": audio_url,
        "video_url": None,
        "image_urls": [],
        "duration_sec": 600,
        "referer": "https://www.bilibili.com/video/BV1test",
        "raw": {},
    }


def _xhs_video_info():
    return {
        "platform": "xiaohongshu",
        "content_type": "video",
        "title": "小红书视频标题",
        "author": "小红书博主",
        "author_id": "xhs_uid_001",
        "post_id": "vid123",
        "published_at": "2025-03-01",
        "url": "https://www.xiaohongshu.com/explore/vid123",
        "subtitle_text": None,
        "audio_url": "https://sns-video.xhscdn.com/video.mp4",
        "video_url": "https://sns-video.xhscdn.com/video.mp4",
        "image_urls": [],
        "duration_sec": 120,
        "referer": "https://www.xiaohongshu.com/explore/vid123",
        "raw": {},
    }


def _xhs_image_note_info(image_urls=None):
    return {
        "platform": "xiaohongshu",
        "content_type": "image_note",
        "title": "小红书图文标题",
        "author": "图文博主",
        "author_id": "xhs_uid_002",
        "post_id": "note123",
        "published_at": "2025-04-01",
        "url": "https://www.xiaohongshu.com/explore/note123",
        "subtitle_text": None,
        "audio_url": None,
        "video_url": None,
        "image_urls": image_urls or [],
        "duration_sec": None,
        "referer": "https://www.xiaohongshu.com/explore/note123",
        "raw": {},
    }
