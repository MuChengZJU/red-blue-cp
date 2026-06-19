"""run_pipeline 集成测试 — 验证端到端管道接线正确。

mock 外部依赖（fetcher HTTP + model API），测试内部组件串联。
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestRunPipeline:

    @patch("app.extract.extractor.fetcher")
    @patch("app.extract.model.requests.post")
    @patch("app.extract.model.requests.get")
    @patch("app.extract.model.requests.Session")
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

    @patch("app.extract.extractor.fetcher")
    @patch("app.extract.model.requests.post")
    def test_failed_extraction_raises(self, mock_post, mock_fetcher, tmp_path):
        mock_fetcher.fetch_bilibili.side_effect = RuntimeError("API 403")

        from app.cli import _create_pipeline_fn
        pipeline = _create_pipeline_fn(
            api_key="test-key",
            output_dir=tmp_path,
        )
        with pytest.raises(RuntimeError, match="403"):
            pipeline("https://www.bilibili.com/video/BV1test123")


class TestProviderModelDefaults:
    """设置页存空串后 RBCP_*_MODEL="" 会让 model="" 发给 DashScope → HTTP 400。
    空串必须回退默认模型名，否则无法转录（实测根因）。"""

    def test_empty_model_envs_fall_back_to_defaults(self, monkeypatch):
        from app.extract.pipeline import _provider_from_env

        monkeypatch.setenv("RBCP_ASR_MODEL", "")
        monkeypatch.setenv("RBCP_VLM_MODEL", "")
        monkeypatch.setenv("RBCP_LLM_MODEL", "")
        p = _provider_from_env("sk-test")
        assert p.asr_model == "paraformer-v2"
        assert p.vlm_model == "qwen3-vl-flash"
        assert p.llm_model == "qwen-plus"

    def test_explicit_model_envs_still_honored(self, monkeypatch):
        from app.extract.pipeline import _provider_from_env

        monkeypatch.setenv("RBCP_LLM_MODEL", "qwen-max")
        assert _provider_from_env("sk-test").llm_model == "qwen-max"
