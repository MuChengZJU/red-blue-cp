"""M5b E1/E2：去重检测 — 契约测试。

dedup_key：同内容不同参数（token/追踪参数）归一到同一个键；
短链（b23.tv/xhslink）解析不了内容 id，老实返回 None 不猜。
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.service.storage import Storage
from app.service.urls import dedup_key
from app.web.routes import app, get_pipeline_fn, get_storage


# ── dedup_key 纯函数 ──────────────────────────────────────────

class TestDedupKey:

    def test_bilibili_same_bv_different_params(self):
        a = dedup_key("https://www.bilibili.com/video/BV1xSGq6mE9Y/?share_source=copy_web&vd_source=8bd8")
        b = dedup_key("https://www.bilibili.com/video/BV1xSGq6mE9Y")
        assert a == b == "bili:BV1xSGq6mE9Y"

    def test_xhs_same_note_different_tokens(self):
        a = dedup_key("https://www.xiaohongshu.com/discovery/item/6877baac000000002201e6a7?xsec_token=AAA")
        b = dedup_key("https://www.xiaohongshu.com/explore/6877baac000000002201e6a7?xsec_token=BBB&xsec_source=pc_share")
        assert a == b == "xhs:6877baac000000002201e6a7"

    def test_short_links_return_none(self):
        # 短链不解析就不知道内容 id，不猜
        assert dedup_key("https://b23.tv/T2ObAMT") is None
        assert dedup_key("http://xhslink.com/o/AAM7Ua2aehc") is None

    def test_non_platform_returns_none(self):
        assert dedup_key("https://example.com/video/BV1xSGq6mE9Y") is None
        assert dedup_key("") is None


# ── E1：单条提交去重 ──────────────────────────────────────────

@pytest.fixture
def mock_storage(tmp_path):
    return Storage(tmp_path / "test.db")


@pytest.fixture
def client(mock_storage):
    app.dependency_overrides[get_storage] = lambda: mock_storage
    app.dependency_overrides[get_pipeline_fn] = lambda: MagicMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestCreateJobDedup:

    def _make_done_job(self, storage, url="https://www.bilibili.com/video/BV1xSGq6mE9Y"):
        job_id = storage.create_job(url)
        storage.mark_done(job_id, md_path="/tmp/a.md", title="旧任务")
        return job_id

    def test_duplicate_url_returns_409_with_existing(self, client, mock_storage):
        existing = self._make_done_job(mock_storage)
        resp = client.post("/api/jobs", json={
            "url": "https://www.bilibili.com/video/BV1xSGq6mE9Y/?share_source=copy_web"
        })
        assert resp.status_code == 409
        body = resp.json()["detail"]
        assert body["duplicate"] is True
        assert body["existing_job_id"] == existing
        assert body["title"] == "旧任务"

    def test_force_true_creates_new_job(self, client, mock_storage):
        self._make_done_job(mock_storage)
        resp = client.post("/api/jobs", json={
            "url": "https://www.bilibili.com/video/BV1xSGq6mE9Y", "force": True
        })
        assert resp.status_code == 200
        assert "job_id" in resp.json()

    def test_failed_old_job_does_not_block(self, client, mock_storage):
        # 只有「成功保存过」才算已下过；失败的旧任务不拦
        job_id = mock_storage.create_job("https://www.bilibili.com/video/BV1xSGq6mE9Y")
        mock_storage.mark_failed(job_id, error_message="boom")
        resp = client.post("/api/jobs", json={
            "url": "https://www.bilibili.com/video/BV1xSGq6mE9Y"
        })
        assert resp.status_code == 200

    def test_short_link_skips_dedup(self, client, mock_storage):
        # 短链 dedup_key=None → 不做去重检测，正常提交
        self._make_done_job(mock_storage, url="https://b23.tv/T2ObAMT")
        resp = client.post("/api/jobs", json={"url": "https://b23.tv/T2ObAMT"})
        assert resp.status_code == 200

    def test_fresh_url_passes(self, client, mock_storage):
        resp = client.post("/api/jobs", json={
            "url": "https://www.bilibili.com/video/BV1newone"
        })
        assert resp.status_code == 200


# ── E2：批量导入去重 ──────────────────────────────────────────

class TestImportListDedup:
    """note_id 用真实形态（24 位 hex），短 id 是合成数据陷阱。"""

    NOTE_A = "6877baac000000002201e6a7"
    NOTE_B = "6a168424000000000803f177"

    def _env(self, note_ids):
        return {
            "schema_version": 1, "source": "xhs_user_posted", "user_id": "u1",
            "complete": True, "count": len(note_ids),
            "notes": [
                {"note_id": nid, "title": "t", "type": "normal", "xsec_token": "x",
                 "url": f"https://www.xiaohongshu.com/explore/{nid}?xsec_token=x"}
                for nid in note_ids
            ],
        }

    def test_skips_already_done_notes(self, client, mock_storage, monkeypatch):
        import app.service.batch as batch_mod
        captured = {}
        monkeypatch.setattr(
            batch_mod, "run_batch",
            lambda payload, **kw: captured.setdefault("notes", payload["notes"]),
        )
        done = mock_storage.create_job(
            f"https://www.xiaohongshu.com/explore/{self.NOTE_A}?xsec_token=old"
        )
        mock_storage.mark_done(done, md_path="/tmp/a.md")

        resp = client.post("/api/import-list", json=self._env([self.NOTE_A, self.NOTE_B]))
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["skipped_duplicates"] == 1

    def test_all_duplicates_returns_zero_without_batch(self, client, mock_storage, monkeypatch):
        import app.service.batch as batch_mod
        called = {}
        monkeypatch.setattr(batch_mod, "run_batch", lambda *a, **k: called.setdefault("yes", True))
        done = mock_storage.create_job(
            f"https://www.xiaohongshu.com/explore/{self.NOTE_A}"
        )
        mock_storage.mark_done(done, md_path="/tmp/a.md")

        resp = client.post("/api/import-list", json=self._env([self.NOTE_A]))
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert resp.json()["skipped_duplicates"] == 1

    def test_force_keeps_all(self, client, mock_storage, monkeypatch):
        import app.service.batch as batch_mod
        monkeypatch.setattr(batch_mod, "run_batch", lambda *a, **k: None)
        done = mock_storage.create_job(
            f"https://www.xiaohongshu.com/explore/{self.NOTE_A}"
        )
        mock_storage.mark_done(done, md_path="/tmp/a.md")

        resp = client.post("/api/import-list?force=true", json=self._env([self.NOTE_A, self.NOTE_B]))
        assert resp.status_code == 200
        assert resp.json()["count"] == 2
        assert resp.json()["skipped_duplicates"] == 0
