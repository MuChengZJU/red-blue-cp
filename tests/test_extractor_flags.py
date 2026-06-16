"""test_extractor_flags.py — 测试 extract_url 的 text_only / save_media 开关。

策略：mock fetcher + mock requests，不打真实网络，不调真实 provider。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.extract.extractor import extract_url


# ─── 辅助工厂 ────────────────────────────────────────────────────────────────


def _exploding_provider():
    """一旦调 vlm 或 asr 就抛，用来证明 text_only=True 时完全绕过。"""
    provider = MagicMock()
    provider.asr.side_effect = AssertionError("asr should not be called in text_only mode")
    provider.vlm.side_effect = AssertionError("vlm should not be called in text_only mode")
    provider.llm_clean.side_effect = lambda text: text  # 透传，不抛
    return provider


def _silent_provider():
    """正常返回空字符串的 provider，用于 save_media 测试（不需要 ASR/VLM）。"""
    provider = MagicMock()
    provider.asr.return_value = ("", ())
    provider.vlm.return_value = ""
    provider.llm_clean.side_effect = lambda text: text
    return provider


def _bili_video_info(
    subtitle_text=None,
    audio_url=None,
    video_url=None,
    desc=None,
):
    return {
        "platform": "bilibili",
        "content_type": "video",
        "title": "测试B站视频",
        "author": "测试UP主",
        "author_id": "12345",
        "post_id": "BV1test",
        "published_at": "2025-01-15",
        "url": "https://www.bilibili.com/video/BV1test",
        "subtitle_text": subtitle_text,
        "audio_url": audio_url or "https://cn-bili-cdn.example.com/audio.m4s",
        "video_url": video_url or "https://cn-bili-cdn.example.com/video.m4s",
        "image_urls": [],
        "duration_sec": 600,
        "referer": "https://www.bilibili.com/video/BV1test",
        "desc": desc or "这是视频的简介描述",
        "raw": {},
    }


def _xhs_video_info(desc=None):
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
        "desc": desc or "小红书视频的正文描述",
        "raw": {},
    }


def _xhs_image_note_info(image_urls=None, desc=None):
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
        "image_urls": image_urls or ["https://sns-img.xhscdn.com/1.jpg"],
        "duration_sec": None,
        "referer": "https://www.xiaohongshu.com/explore/note123",
        "desc": desc or "图文笔记的正文描述",
        "raw": {},
    }


# ─── text_only 测试 ───────────────────────────────────────────────────────────


class TestTextOnly:

    @patch("app.extract.extractor.fetcher")
    def test_bilibili_subtitle_no_asr_called(self, mock_fetcher):
        """B站有字幕时 text_only=True → 直接用字幕，不调 asr/vlm。"""
        mock_fetcher.fetch_bilibili.return_value = _bili_video_info(
            subtitle_text="字幕内容在这里",
        )
        provider = _exploding_provider()

        result = extract_url(
            "https://www.bilibili.com/video/BV1test",
            provider,
            text_only=True,
        )

        assert result.text == "字幕内容在这里"
        assert result.metadata.get("status") == "text_only"
        provider.asr.assert_not_called()
        provider.vlm.assert_not_called()

    @patch("app.extract.extractor.fetcher")
    def test_bilibili_no_subtitle_uses_desc(self, mock_fetcher):
        """B站无字幕时 text_only=True → 用 desc 字段，不调 asr。"""
        mock_fetcher.fetch_bilibili.return_value = _bili_video_info(
            subtitle_text=None,
            desc="视频简介描述文字",
        )
        provider = _exploding_provider()

        result = extract_url(
            "https://www.bilibili.com/video/BV1test",
            provider,
            text_only=True,
        )

        assert result.text == "视频简介描述文字"
        assert result.metadata.get("status") == "text_only"
        provider.asr.assert_not_called()

    @patch("app.extract.extractor.fetcher")
    def test_bilibili_no_subtitle_no_desc_uses_title(self, mock_fetcher):
        """B站无字幕无 desc 时 text_only=True → 退回用 title。"""
        info = _bili_video_info(subtitle_text=None, desc=None)
        info["desc"] = None  # 明确置 None
        mock_fetcher.fetch_bilibili.return_value = info
        provider = _exploding_provider()

        result = extract_url(
            "https://www.bilibili.com/video/BV1test",
            provider,
            text_only=True,
        )

        assert result.text == "测试B站视频"  # 退回用 title
        assert result.metadata.get("status") == "text_only"

    @patch("app.extract.extractor.fetcher")
    def test_xhs_video_text_only_no_asr(self, mock_fetcher):
        """小红书视频 text_only=True → 用 desc，不调 asr。"""
        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_video_info(
            desc="小红书视频正文描述"
        )
        provider = _exploding_provider()

        result = extract_url(
            "https://www.xiaohongshu.com/explore/vid123",
            provider,
            text_only=True,
        )

        assert result.text == "小红书视频正文描述"
        assert result.metadata.get("status") == "text_only"
        provider.asr.assert_not_called()

    @patch("app.extract.extractor.fetcher")
    def test_xhs_image_note_text_only_no_vlm(self, mock_fetcher):
        """小红书图文 text_only=True → 用 desc，不调 vlm。"""
        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_image_note_info(
            desc="图文笔记的正文内容"
        )
        provider = _exploding_provider()

        result = extract_url(
            "https://www.xiaohongshu.com/explore/note123",
            provider,
            text_only=True,
        )

        assert result.text == "图文笔记的正文内容"
        assert result.metadata.get("status") == "text_only"
        provider.vlm.assert_not_called()

    @patch("app.extract.extractor.fetcher")
    def test_xhs_image_note_no_desc_uses_title(self, mock_fetcher):
        """小红书图文无 desc 时 text_only=True → 退回用 title。"""
        info = _xhs_image_note_info(desc=None)
        info["desc"] = None
        mock_fetcher.fetch_xiaohongshu.return_value = info
        provider = _exploding_provider()

        result = extract_url(
            "https://www.xiaohongshu.com/explore/note123",
            provider,
            text_only=True,
        )

        assert result.text == "小红书图文标题"
        assert result.metadata.get("status") == "text_only"

    @patch("app.extract.extractor.fetcher")
    def test_text_only_still_calls_llm_clean(self, mock_fetcher):
        """text_only=True 时仍然走 llm_clean（清理正文质量）。"""
        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_image_note_info(
            desc="原始正文"
        )
        provider = MagicMock()
        provider.asr.side_effect = AssertionError("should not call asr")
        provider.vlm.side_effect = AssertionError("should not call vlm")
        provider.llm_clean.return_value = "清洗后正文"

        result = extract_url(
            "https://www.xiaohongshu.com/explore/note123",
            provider,
            text_only=True,
        )

        provider.llm_clean.assert_called_once()
        assert result.readable_text == "清洗后正文"  # .md 正文=清洗版；canonical 原文在 result.text


# ─── save_media 测试 ──────────────────────────────────────────────────────────


class TestSaveMedia:

    @patch("app.extract.extractor.fetcher")
    def test_xhs_image_note_downloads_images(self, mock_fetcher, tmp_path, monkeypatch):
        """小红书图文 save_media=True → 下载图片到 media_dir/{note_id}/。"""
        monkeypatch.setenv("RBCP_MEDIA_DIR", str(tmp_path))
        monkeypatch.setenv("RBCP_OUTPUT_DIR", str(tmp_path / "transcript"))
        (tmp_path / "transcript").mkdir()

        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_image_note_info(
            image_urls=[
                "https://sns-img.xhscdn.com/1.jpg",
                "https://sns-img.xhscdn.com/2.jpg",
            ]
        )
        provider = _silent_provider()

        fake_response = MagicMock()
        fake_response.content = b"fake_image_bytes"
        fake_response.raise_for_status.return_value = None

        with patch("requests.get", return_value=fake_response) as mock_get:
            result = extract_url(
                "https://www.xiaohongshu.com/explore/note123",
                provider,
                save_media=True,
            )

        # 媒体路径写进了 metadata
        assert "media_paths" in result.metadata
        media_paths = result.metadata["media_paths"]
        assert len(media_paths) == 2

        # 文件确实写到了 media_dir 下的 note_id 子目录
        media_dir = tmp_path / "note123"
        assert media_dir.is_dir()
        saved_files = list(media_dir.iterdir())
        assert len(saved_files) == 2

    @patch("app.extract.extractor.fetcher")
    def test_media_not_in_output_dir(self, mock_fetcher, tmp_path, monkeypatch):
        """红线 #5：媒体文件绝不能出现在知识库（RBCP_OUTPUT_DIR）目录下。"""
        output_dir = tmp_path / "transcript"
        output_dir.mkdir()
        media_dir = tmp_path / "media"
        media_dir.mkdir()

        monkeypatch.setenv("RBCP_OUTPUT_DIR", str(output_dir))
        monkeypatch.setenv("RBCP_MEDIA_DIR", str(media_dir))

        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_image_note_info(
            image_urls=["https://sns-img.xhscdn.com/photo.jpg"]
        )
        provider = _silent_provider()

        fake_response = MagicMock()
        fake_response.content = b"fake_image_bytes"
        fake_response.raise_for_status.return_value = None

        with patch("requests.get", return_value=fake_response):
            extract_url(
                "https://www.xiaohongshu.com/explore/note123",
                provider,
                save_media=True,
            )

        # 知识库目录里不能有任何媒体文件
        all_output_files = list(output_dir.rglob("*"))
        assert all_output_files == [], (
            f"知识库目录里出现了不该有的文件: {all_output_files}"
        )

    @patch("app.extract.extractor.fetcher")
    def test_save_media_idempotent(self, mock_fetcher, tmp_path, monkeypatch):
        """幂等：同 note_id 第二次调用，已存在的文件直接跳过，不重新下载。"""
        monkeypatch.setenv("RBCP_MEDIA_DIR", str(tmp_path))

        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_image_note_info(
            image_urls=["https://sns-img.xhscdn.com/1.jpg"]
        )
        provider = _silent_provider()

        fake_response = MagicMock()
        fake_response.content = b"fake_image_bytes"
        fake_response.raise_for_status.return_value = None

        with patch("requests.get", return_value=fake_response) as mock_get:
            extract_url(
                "https://www.xiaohongshu.com/explore/note123",
                provider,
                save_media=True,
            )
            first_call_count = mock_get.call_count

            # 第二次调用——已存在的文件不应再下载
            extract_url(
                "https://www.xiaohongshu.com/explore/note123",
                provider,
                save_media=True,
            )
            second_call_count = mock_get.call_count

        # 两次 extract_url 都调了 fetch_xiaohongshu，但 requests.get 下载
        # 不应在第二次额外增加（只有第一次下载）
        assert second_call_count == first_call_count, (
            f"第二次调用仍触发了 requests.get: 第一次 {first_call_count} 次，"
            f"第二次累计 {second_call_count} 次"
        )

    @patch("app.extract.extractor.fetcher")
    def test_save_media_requests_with_referer(self, mock_fetcher, tmp_path, monkeypatch):
        """下载图片时必须带 referer header（防盗链）。"""
        monkeypatch.setenv("RBCP_MEDIA_DIR", str(tmp_path))

        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_image_note_info(
            image_urls=["https://sns-img.xhscdn.com/photo.jpg"]
        )
        provider = _silent_provider()

        fake_response = MagicMock()
        fake_response.content = b"fake_bytes"
        fake_response.raise_for_status.return_value = None

        with patch("requests.get", return_value=fake_response) as mock_get:
            extract_url(
                "https://www.xiaohongshu.com/explore/note123",
                provider,
                save_media=True,
            )

        # 至少有一次 requests.get 是带了 headers 且包含 Referer 的
        called_with_referer = False
        for call in mock_get.call_args_list:
            kwargs = call[1] if call[1] else {}
            headers = kwargs.get("headers") or {}
            if "Referer" in headers or "referer" in headers:
                called_with_referer = True
                break
        assert called_with_referer, "下载图片时未带 Referer header"

    @patch("app.extract.extractor.fetcher")
    def test_save_media_uses_atomic_write(self, mock_fetcher, tmp_path, monkeypatch):
        """原子写：下载完成后不留 .part 临时文件。"""
        monkeypatch.setenv("RBCP_MEDIA_DIR", str(tmp_path))

        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_image_note_info(
            image_urls=["https://sns-img.xhscdn.com/photo.jpg"]
        )
        provider = _silent_provider()

        fake_response = MagicMock()
        fake_response.content = b"fake_bytes"
        fake_response.raise_for_status.return_value = None

        with patch("requests.get", return_value=fake_response):
            extract_url(
                "https://www.xiaohongshu.com/explore/note123",
                provider,
                save_media=True,
            )

        # 不能有 .part 临时文件残留
        part_files = list(tmp_path.rglob("*.part"))
        assert part_files == [], f"发现残留临时文件: {part_files}"

    @patch("app.extract.extractor.fetcher")
    def test_xhs_video_saves_video_url(self, mock_fetcher, tmp_path, monkeypatch):
        """小红书视频 save_media=True → 下载 video_url（完整视频，非仅音频）。"""
        monkeypatch.setenv("RBCP_MEDIA_DIR", str(tmp_path))

        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_video_info()
        provider = _silent_provider()

        fake_response = MagicMock()
        fake_response.content = b"fake_video_bytes"
        fake_response.raise_for_status.return_value = None

        with patch("requests.get", return_value=fake_response) as mock_get:
            result = extract_url(
                "https://www.xiaohongshu.com/explore/vid123",
                provider,
                save_media=True,
            )

        assert "media_paths" in result.metadata
        assert len(result.metadata["media_paths"]) >= 1

        # 验证下载的是 video_url（sns-video.xhscdn.com/video.mp4）
        downloaded_urls = [str(call[0][0]) for call in mock_get.call_args_list]
        assert any("video.mp4" in u for u in downloaded_urls), (
            f"没有下载 video_url，实际下载了: {downloaded_urls}"
        )

    @patch("app.extract.extractor.fetcher")
    def test_metadata_media_paths_set(self, mock_fetcher, tmp_path, monkeypatch):
        """save_media=True 时 metadata['media_paths'] 是非空列表。"""
        monkeypatch.setenv("RBCP_MEDIA_DIR", str(tmp_path))

        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_image_note_info(
            image_urls=["https://sns-img.xhscdn.com/1.jpg"]
        )
        provider = _silent_provider()

        fake_response = MagicMock()
        fake_response.content = b"data"
        fake_response.raise_for_status.return_value = None

        with patch("requests.get", return_value=fake_response):
            result = extract_url(
                "https://www.xiaohongshu.com/explore/note123",
                provider,
                save_media=True,
            )

        assert isinstance(result.metadata.get("media_paths"), list)
        assert len(result.metadata["media_paths"]) > 0

    @patch("app.extract.extractor.fetcher")
    def test_save_media_false_no_media_downloaded(self, mock_fetcher, tmp_path, monkeypatch):
        """save_media=False（默认）时不触发任何媒体下载。"""
        monkeypatch.setenv("RBCP_MEDIA_DIR", str(tmp_path))

        mock_fetcher.fetch_xiaohongshu.return_value = _xhs_image_note_info(
            image_urls=["https://sns-img.xhscdn.com/1.jpg"]
        )
        provider = MagicMock()
        provider.vlm.return_value = "vlm result"
        provider.llm_clean.side_effect = lambda t: t

        with patch("requests.get") as mock_get:
            result = extract_url(
                "https://www.xiaohongshu.com/explore/note123",
                provider,
            )

        assert "media_paths" not in result.metadata
        # requests.get 可能被 fetcher 本身调用，但不应该下载媒体文件
        # （这里我们 mock 了 fetcher，所以 requests.get 不应该被调用）
        mock_get.assert_not_called()


# ─── 回归：默认调用仍然兼容 ──────────────────────────────────────────────────


class TestBackwardCompatibility:
    """确保现有的 extract_url(url, provider) 调用方式不破。"""

    @patch("app.extract.extractor.fetcher")
    def test_default_bilibili_still_works(self, mock_fetcher):
        mock_fetcher.fetch_bilibili.return_value = {
            "platform": "bilibili",
            "content_type": "video",
            "title": "测试视频",
            "author": "UP主",
            "author_id": "111",
            "post_id": "BV1aaa",
            "published_at": "2025-01-01",
            "url": "https://www.bilibili.com/video/BV1aaa",
            "subtitle_text": "字幕",
            "audio_url": None,
            "video_url": None,
            "image_urls": [],
            "duration_sec": 300,
            "referer": "https://www.bilibili.com/video/BV1aaa",
            "raw": {},
        }
        provider = MagicMock()
        provider.llm_clean.return_value = "final"

        result = extract_url("https://www.bilibili.com/video/BV1aaa", provider)

        assert result.platform == "bilibili"
        assert result.readable_text == "final"

    @patch("app.extract.extractor.fetcher")
    def test_default_xhs_image_note_still_works(self, mock_fetcher):
        mock_fetcher.fetch_xiaohongshu.return_value = {
            "platform": "xiaohongshu",
            "content_type": "image_note",
            "title": "图文",
            "author": "作者",
            "author_id": "uid",
            "post_id": "note_abc",
            "published_at": "2025-01-01",
            "url": "https://www.xiaohongshu.com/explore/note_abc",
            "subtitle_text": None,
            "audio_url": None,
            "video_url": None,
            "image_urls": ["https://img.xhs.com/img.jpg"],
            "duration_sec": None,
            "referer": "https://www.xiaohongshu.com/explore/note_abc",
            "raw": {},
        }
        provider = MagicMock()
        provider.vlm.return_value = "vlm text"
        provider.llm_clean.return_value = "clean text"

        result = extract_url("https://www.xiaohongshu.com/explore/note_abc", provider)

        assert result.platform == "xiaohongshu"
        assert result.readable_text == "clean text"
