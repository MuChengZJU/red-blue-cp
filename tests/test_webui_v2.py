"""M5b E6/E7/E8：WebUI v2 — 模板/路由契约。

主页两标签（单条/批量），/batches 重定向回主页；
批次卡片数据：/api/batches 带 items_preview，任务列表可排除批量任务（避免双重显示）。
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


class TestTabsAndRedirect:

    def test_index_has_single_and_batch_tabs(self, client):
        html = client.get("/").text
        assert 'id="tab-single"' in html
        assert 'id="tab-batch"' in html
        # 批量面板的重做后控件
        assert 'id="batch-file-input"' in html
        assert 'id="batch-title-input"' in html
        assert 'id="force-redownload"' in html

    def test_batches_page_redirects_home(self, client):
        resp = client.get("/batches", follow_redirects=False)
        assert resp.status_code in (301, 302, 307, 308)
        assert resp.headers["location"] == "/"


class TestBatchCardsData:

    def _batch_with_items(self, storage, n=7):
        bid = storage.create_batch(source="s", user_id="u", count=n, complete=True, title="名")
        storage.add_batch_items(bid, [
            {"note_id": f"6877baac00000000220{i:05d}", "url": f"https://x/{i}", "title": f"笔记{i}"}
            for i in range(n)
        ])
        return bid

    def test_list_batches_includes_items_preview(self, client, mock_storage):
        self._batch_with_items(mock_storage, n=7)
        batches = client.get("/api/batches").json()["batches"]
        preview = batches[0]["items_preview"]
        assert len(preview) == 5  # 默认只带前几条，全量走 /items
        assert preview[0]["title"] == "笔记0"

    def test_jobs_can_exclude_batched(self, client, mock_storage):
        bid = self._batch_with_items(mock_storage, n=1)
        batch_job = mock_storage.create_job("https://x/0")
        mock_storage.set_batch_item_job(bid, "6877baac0000000022000000", batch_job)
        single_job = mock_storage.create_job("https://b23.tv/single")

        all_jobs = client.get("/api/jobs").json()
        assert {j["id"] for j in all_jobs} == {batch_job, single_job}

        filtered = client.get("/api/jobs?exclude_batched=true").json()
        assert {j["id"] for j in filtered} == {single_job}
