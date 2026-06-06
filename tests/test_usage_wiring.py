"""M5a：usage 从 provider 账本流到 SQLite 的接线 — 契约测试。

链路：provider.usage_events → summarize_usage → pipeline dict["usage"]
      → routes._run_job → storage.mark_done(usage=)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.service.extractor import ExtractResult
from app.service.storage import Storage


def _fake_result(url: str = "https://b23.tv/x") -> ExtractResult:
    return ExtractResult(
        platform="bilibili", content_type="video", title="t", author="a",
        author_id=None, published_at=None, url=url, text="正文",
        metadata={}, raw_info={},
    )


def _fake_provider() -> MagicMock:
    provider = MagicMock()
    provider.usage_events = [
        {"stage": "asr", "model": "paraformer-v2",
         "audio_seconds": 600, "elapsed_seconds": 45.0},
    ]
    return provider


class TestCliPipelineUsage:

    @patch("app.cli.render_and_write", return_value=Path("/tmp/t.md"))
    @patch("app.cli.extract_url")
    @patch("app.cli._provider_from_env")
    def test_pipeline_dict_contains_usage_summary(
        self, mock_provider_fn, mock_extract, _mock_render
    ):
        mock_provider_fn.return_value = _fake_provider()
        mock_extract.return_value = _fake_result()
        from app.cli import _create_pipeline_fn

        out = _create_pipeline_fn(api_key="k", output_dir=Path("/tmp"))("https://b23.tv/x")
        assert out["usage"]["total_cost_yuan"] == pytest.approx(0.048)
        assert out["usage"]["events"][0]["stage"] == "asr"

    @patch("app.cli.render_and_write", return_value=Path("/tmp/t.md"))
    @patch("app.cli.extract_url")
    @patch("app.cli._provider_from_env")
    def test_no_model_calls_usage_is_none(
        self, mock_provider_fn, mock_extract, _mock_render
    ):
        provider = MagicMock()
        provider.usage_events = []
        mock_provider_fn.return_value = provider
        mock_extract.return_value = _fake_result()
        from app.cli import _create_pipeline_fn

        out = _create_pipeline_fn(api_key="k", output_dir=Path("/tmp"))("https://b23.tv/x")
        assert out["usage"] is None


class TestFetchSingleUsage:

    @patch("app.service.pipeline.render_and_write", return_value=Path("/tmp/t.md"))
    @patch("app.service.pipeline.extract_url")
    @patch("app.service.pipeline._provider_from_env")
    def test_fetch_single_returns_usage(
        self, mock_provider_fn, mock_extract, _mock_render, tmp_path
    ):
        mock_provider_fn.return_value = _fake_provider()
        mock_extract.return_value = _fake_result()
        from app.service.pipeline import fetch_single

        out = fetch_single("https://b23.tv/x", api_key="k", output_dir=tmp_path)
        assert out["usage"]["total_cost_yuan"] == pytest.approx(0.048)


class TestRunJobPersistsUsage:

    def test_run_job_passes_usage_to_mark_done(self, tmp_path):
        from app.web.routes import _run_job

        storage = Storage(tmp_path / "_index.sqlite")
        job_id = storage.create_job("https://b23.tv/x")
        usage = {"events": [{"stage": "llm_clean", "model": "qwen-plus",
                             "input_tokens": 100, "output_tokens": 50,
                             "elapsed_seconds": 2.0, "cost_yuan": 0.00018}],
                 "total_cost_yuan": 0.00018}
        pipeline_fn = MagicMock(return_value={
            "md_path": "/tmp/t.md", "title": "t", "usage": usage,
        })
        _run_job(job_id, "https://b23.tv/x", storage, pipeline_fn)
        assert storage.get_job(job_id)["usage"] == usage
