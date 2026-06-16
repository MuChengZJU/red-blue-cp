"""M5a：WebUI 用量/费用展示 — API + 模板契约。

详情页：每任务用量明细（语音 x 秒 / token 数 / 估算费用）。
列表页：累计估算费用（/api/stats）。
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.extract.storage import Storage
from app.web.routes import app, get_pipeline_fn, get_storage


@pytest.fixture
def mock_storage(tmp_path):
    return Storage(tmp_path / "test.db")


@pytest.fixture
def client(mock_storage):
    app.dependency_overrides[get_storage] = lambda: mock_storage
    app.dependency_overrides[get_pipeline_fn] = lambda: MagicMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


_USAGE = {
    "events": [
        {"stage": "asr", "model": "paraformer-v2", "audio_seconds": 600,
         "elapsed_seconds": 45.0, "cost_yuan": 0.048},
    ],
    "total_cost_yuan": 0.048,
}


class TestStatsApi:

    def test_empty_db_total_zero(self, client):
        body = client.get("/api/stats").json()
        assert body["total_cost_yuan"] == 0.0

    def test_total_sums_job_usage(self, client, mock_storage):
        job_id = mock_storage.create_job("https://b23.tv/x")
        mock_storage.mark_done(job_id, md_path="/tmp/a.md", usage=_USAGE)
        body = client.get("/api/stats").json()
        assert body["total_cost_yuan"] == pytest.approx(0.048)


class TestJobApiExposesUsage:

    def test_job_detail_includes_usage(self, client, mock_storage):
        job_id = mock_storage.create_job("https://b23.tv/x")
        mock_storage.mark_done(job_id, md_path="/tmp/a.md", usage=_USAGE)
        body = client.get(f"/api/jobs/{job_id}").json()
        assert body["usage"]["total_cost_yuan"] == pytest.approx(0.048)

    def test_old_job_usage_null_not_crash(self, client, mock_storage):
        job_id = mock_storage.create_job("https://b23.tv/x")
        mock_storage.mark_done(job_id, md_path="/tmp/a.md")
        body = client.get(f"/api/jobs/{job_id}").json()
        assert body["usage"] is None


class TestTemplates:

    def test_detail_page_has_usage_panel(self, client, mock_storage):
        job_id = mock_storage.create_job("https://b23.tv/x")
        mock_storage.mark_done(job_id, md_path="/tmp/a.md", usage=_USAGE)
        html = client.get(f"/jobs/{job_id}").text
        assert 'id="usage-panel"' in html

    def test_index_page_has_total_cost(self, client):
        html = client.get("/").text
        assert 'id="total-cost"' in html
