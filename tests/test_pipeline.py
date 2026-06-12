"""run_pipeline 集成测试 — 验证端到端管道接线正确。

mock 外部依赖（fetcher HTTP + model API），测试内部组件串联。
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def test_provider_from_env_passes_llm_and_vlm_models(monkeypatch):
    monkeypatch.setenv("RBCP_LLM_MODEL", "free-llm-model")
    monkeypatch.setenv("RBCP_VLM_MODEL", "free-vlm-model")

    from app.service.pipeline import _provider_from_env

    provider = _provider_from_env("test-key")

    assert provider.llm_model == "free-llm-model"
    assert provider.vlm_model == "free-vlm-model"


def test_provider_from_env_keeps_default_llm_and_vlm_models(monkeypatch):
    monkeypatch.delenv("RBCP_LLM_MODEL", raising=False)
    monkeypatch.delenv("RBCP_VLM_MODEL", raising=False)

    from app.service.pipeline import _provider_from_env

    provider = _provider_from_env("test-key")

    assert provider.llm_model == "qwen-plus"
    assert provider.vlm_model == "qwen3-vl-flash"


class TestRunPipeline:

    @patch("app.service.extractor.fetcher")
    @patch("app.service.model.requests.post")
    @patch("app.service.model.requests.get")
    @patch("app.service.model.requests.Session")
    def test_bilibili_video_produces_markdown(
        self, mock_session, mock_get, mock_post, mock_fetcher, tmp_path
    ):
        mock_fetcher.fetch_bilibili.return_value = {
            "platform": "bilibili",
            "content_type": "video",
            "title": "测试视频",
            "author": "UP主",
            "author_id": "12345",
            "post_id": "BV1test123",
            "published_at": "2025-01-15",
            "url": "https://www.bilibili.com/video/BV1test123",
            "subtitle_text": "这是字幕内容",
            "audio_url": None,
            "video_url": None,
            "image_urls": [],
            "duration_sec": 300,
            "referer": "https://www.bilibili.com/video/BV1test123",
            "raw": {},
        }

        # LLM clean mock（M5a 起走流式 SSE）
        import json as _json

        llm_resp = MagicMock()
        llm_resp.status_code = 200
        llm_resp.raise_for_status = MagicMock()
        llm_resp.iter_lines.return_value = iter([
            "data: " + _json.dumps(
                {"choices": [{"delta": {"content": "清洗后的字幕内容"}}]}
            ),
            "data: [DONE]",
        ])
        mock_post.return_value = llm_resp

        from app.cli import _create_pipeline_fn
        pipeline = _create_pipeline_fn(
            api_key="test-key",
            output_dir=tmp_path,
        )
        result = pipeline("https://www.bilibili.com/video/BV1test123")

        # pipeline 返回 dict：md_path + 业务元数据
        assert isinstance(result, dict)
        assert "md_path" in result
        assert result["title"] == "测试视频"
        assert result["author"] == "UP主"
        assert result["platform"] == "bilibili"
        assert result["content_type"] == "video"

        result_path = Path(result["md_path"])
        assert result_path.exists()
        assert result_path.suffix == ".md"
        content = result_path.read_text(encoding="utf-8")
        assert "清洗后的字幕内容" in content
        assert "bilibili" in content

    @patch("app.service.extractor.fetcher")
    @patch("app.service.model.requests.post")
    def test_failed_extraction_raises(self, mock_post, mock_fetcher, tmp_path):
        mock_fetcher.fetch_bilibili.side_effect = RuntimeError("API 403")

        from app.cli import _create_pipeline_fn
        pipeline = _create_pipeline_fn(
            api_key="test-key",
            output_dir=tmp_path,
        )
        with pytest.raises(RuntimeError, match="403"):
            pipeline("https://www.bilibili.com/video/BV1test123")

    @patch("app.service.extractor.fetcher")
    @patch("app.service.model.requests.post")
    def test_markdown_uses_actual_provider_vision_model(
        self, mock_post, mock_fetcher, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("RBCP_VLM_MODEL", "env-vlm-model")
        mock_fetcher.fetch_xiaohongshu.return_value = {
            "platform": "xiaohongshu",
            "content_type": "image_note",
            "title": "image note",
            "author": "author",
            "author_id": "u1",
            "post_id": "note1",
            "published_at": "2026-06-07",
            "url": "https://www.xiaohongshu.com/explore/note1",
            "desc": "",
            "image_urls": ["https://example.com/1.jpg"],
            "referer": "https://www.xiaohongshu.com/",
            "raw": {},
        }

        import json as _json

        responses = []
        for text in ["image text", "cleaned image text"]:
            resp = MagicMock()
            resp.status_code = 200
            resp.iter_lines.return_value = iter([
                "data: " + _json.dumps({"choices": [{"delta": {"content": text}}]}),
                "data: [DONE]",
            ])
            responses.append(resp)
        mock_post.side_effect = responses

        from app.service.extractor import extract_url
        from app.service.markdown import render_and_write
        from app.service.model import DashscopeProvider

        provider = DashscopeProvider("test-key", vlm_model="actual-vlm-model")
        result = extract_url("https://www.xiaohongshu.com/explore/note1", provider)
        path = render_and_write(result, tmp_path)

        content = path.read_text(encoding="utf-8")
        assert "vision_model: actual-vlm-model" in content
        assert "vision_model: env-vlm-model" not in content
