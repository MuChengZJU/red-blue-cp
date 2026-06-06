"""M5b E3/E4：批次取名 + 批量逐条建任务 — 契约测试。

E3：batch.title（可自定义/缺省自动生成）+ 旧库迁移。
E4：run_batch 每条建 job（batch_item.job_id 关联），done 带 usage、failed 留痕，
    批次条目从此可进 /jobs/{id} 详情，复用任务体系。
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

import app.service.batch as batch_mod
from app.service.storage import Storage


NOTE_A = "6877baac000000002201e6a7"
NOTE_B = "6a168424000000000803f177"


def _env(note_ids, user_id="5e5b82e6000000000100a846"):
    return {
        "schema_version": 1, "source": "xhs_user_posted", "user_id": user_id,
        "complete": True, "count": len(note_ids),
        "notes": [
            {"note_id": nid, "title": f"笔记{i}", "type": "normal", "xsec_token": "x",
             "url": f"https://www.xiaohongshu.com/explore/{nid}?xsec_token=x"}
            for i, nid in enumerate(note_ids)
        ],
    }


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "_index.sqlite")


# ── E3：批次取名 ──────────────────────────────────────────────

class TestBatchTitle:

    def test_create_batch_title_roundtrip(self, storage):
        bid = storage.create_batch(
            source="xhs_user_posted", user_id="u1", count=2, complete=True,
            title="我的批次",
        )
        assert storage.get_batch(bid)["title"] == "我的批次"

    def test_run_batch_custom_title(self, tmp_path):
        with patch.object(batch_mod, "fetch_single",
                          return_value={"md_path": "/tmp/a.md", "title": "t", "usage": None}):
            summary = batch_mod.run_batch(
                _env([NOTE_A]), api_key="k", output_dir=tmp_path, title="自定义名",
            )
        storage = Storage(tmp_path / "_index.sqlite")
        assert storage.get_batch(summary["batch_id"])["title"] == "自定义名"

    def test_run_batch_auto_title_from_user_and_count(self, tmp_path):
        with patch.object(batch_mod, "fetch_single",
                          return_value={"md_path": "/tmp/a.md", "title": "t", "usage": None}):
            summary = batch_mod.run_batch(_env([NOTE_A, NOTE_B]), api_key="k", output_dir=tmp_path)
        storage = Storage(tmp_path / "_index.sqlite")
        title = storage.get_batch(summary["batch_id"])["title"]
        assert "2 条" in title  # 自动名至少含条数

    def test_old_db_without_batch_columns_migrated(self, tmp_path):
        # 0.4.1 的库：batch 无 title，batch_item 无 title/job_id
        db_path = tmp_path / "_index.sqlite"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE batch (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL, user_id TEXT,
                count INTEGER NOT NULL DEFAULT 0,
                complete INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE batch_item (
                batch_id INTEGER NOT NULL, note_id TEXT NOT NULL,
                url TEXT NOT NULL, status TEXT NOT NULL,
                md_path TEXT, error_message TEXT, finished_at TEXT,
                PRIMARY KEY (batch_id, note_id)
            );
            INSERT INTO batch (source, user_id, count, complete, status, created_at)
            VALUES ('xhs_user_posted', 'u1', 1, 1, 'done', '2026-01-01');
            """
        )
        conn.commit()
        conn.close()

        storage = Storage(db_path)
        old = storage.get_batch(1)
        assert old["title"] is None  # 旧批次没名字，不崩
        bid = storage.create_batch(source="s", user_id="u", count=1, complete=True, title="新")
        assert storage.get_batch(bid)["title"] == "新"


# ── E4：批量逐条建任务 ────────────────────────────────────────

class TestBatchCreatesJobs:

    def test_each_note_becomes_done_job_with_usage(self, tmp_path):
        usage = {"events": [], "total_cost_yuan": 0.01}
        with patch.object(batch_mod, "fetch_single",
                          return_value={"md_path": "/tmp/a.md", "title": "真标题", "usage": usage}):
            summary = batch_mod.run_batch(_env([NOTE_A, NOTE_B]), api_key="k", output_dir=tmp_path)

        storage = Storage(tmp_path / "_index.sqlite")
        jobs = storage.list_jobs()
        assert len(jobs) == 2
        assert all(j["status"] == "done" for j in jobs)
        assert all(j["usage"] == usage for j in jobs)
        assert all(j["title"] == "真标题" for j in jobs)

        items = storage.list_batch_items(summary["batch_id"])
        job_ids = {j["id"] for j in jobs}
        assert all(item["job_id"] in job_ids for item in items)
        assert all(item["title"] for item in items)  # 插件给的笔记标题落了库

    def test_failed_note_leaves_failed_job(self, tmp_path):
        with patch.object(batch_mod, "fetch_single", side_effect=RuntimeError("boom")):
            summary = batch_mod.run_batch(_env([NOTE_A]), api_key="k", output_dir=tmp_path)

        storage = Storage(tmp_path / "_index.sqlite")
        job = storage.list_jobs()[0]
        assert job["status"] == "failed"
        assert job["error_message"]
        assert storage.list_batch_items(summary["batch_id"])[0]["job_id"] == job["id"]

    def test_resume_skipped_note_creates_no_new_job(self, tmp_path):
        with patch.object(batch_mod, "fetch_single",
                          return_value={"md_path": "/tmp/a.md", "title": "t", "usage": None}):
            batch_mod.run_batch(_env([NOTE_A]), api_key="k", output_dir=tmp_path)
            batch_mod.run_batch(_env([NOTE_A]), api_key="k", output_dir=tmp_path)  # 重跑同清单

        storage = Storage(tmp_path / "_index.sqlite")
        assert len(storage.list_jobs()) == 1  # 断点续传跳过，不重复建 job


# ── 批次条目 API ──────────────────────────────────────────────

class TestBatchItemsApi:

    def test_items_endpoint_returns_rows(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient
        from app.web.routes import app, get_storage

        storage = Storage(tmp_path / "_index.sqlite")
        bid = storage.create_batch(source="s", user_id="u", count=1, complete=True, title="名")
        storage.add_batch_items(bid, [{"note_id": NOTE_A, "url": "https://x", "title": "笔记标题"}])

        app.dependency_overrides[get_storage] = lambda: storage
        try:
            client = TestClient(app)
            resp = client.get(f"/api/batches/{bid}/items")
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert items[0]["note_id"] == NOTE_A
            assert items[0]["title"] == "笔记标题"
            assert client.get("/api/batches/99999/items").status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestCodexFindings:
    """Codex review M5b：重试代理 + 重跑孤儿 job。"""

    def test_rerun_failed_note_reuses_same_job(self, tmp_path):
        # P2：批次重跑不新建 job——原地重置同一条，不留孤儿进主列表
        with patch.object(batch_mod, "fetch_single", side_effect=RuntimeError("boom")):
            batch_mod.run_batch(_env([NOTE_A]), api_key="k", output_dir=tmp_path)
        storage = Storage(tmp_path / "_index.sqlite")
        first_job = storage.list_jobs()[0]
        assert first_job["status"] == "failed"

        with patch.object(batch_mod, "fetch_single",
                          return_value={"md_path": "/tmp/a.md", "title": "t", "usage": None}):
            batch_mod.run_batch(_env([NOTE_A]), api_key="k", output_dir=tmp_path)

        jobs = storage.list_jobs()
        assert len(jobs) == 1, "重跑不应新建 job"
        assert jobs[0]["id"] == first_job["id"]
        assert jobs[0]["status"] == "done"
        assert jobs[0]["retry_count"] == 1
        # 主任务列表（排除批量）不应出现孤儿
        assert storage.list_jobs(exclude_batched=True) == []

    def test_web_pipeline_fn_honors_rbcp_proxy(self, monkeypatch, tmp_path):
        # P1：WebUI 单条/重试管道也要吃 RBCP_PROXY，批量任务重试不丢代理
        import app.service.pipeline as pipeline_mod
        from app.web.routes import get_pipeline_fn

        captured = {}

        def fake_fetch_single(url, *, api_key, output_dir, proxy=None, **kw):
            captured["proxy"] = proxy
            return {"md_path": "/tmp/a.md", "title": "t", "usage": None}

        monkeypatch.setattr(pipeline_mod, "fetch_single", fake_fetch_single)
        monkeypatch.setenv("RBCP_PROXY", "http://127.0.0.1:7897")
        monkeypatch.setenv("RBCP_OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("DASHSCOPE_API_KEY", "k")

        get_pipeline_fn()("https://www.bilibili.com/video/BV1x")
        assert captured["proxy"] == "http://127.0.0.1:7897"
