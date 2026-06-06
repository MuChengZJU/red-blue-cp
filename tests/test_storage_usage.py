"""M5a：jobs.usage 字段（JSON）落库 + 累计费用 — 契约测试。

usage 结构（pipeline 汇总后传入）：
{"events": [{"stage": "asr", "audio_seconds": 10, ...}], "total_cost_yuan": 0.012}
"""

import json
import sqlite3

import pytest

from app.service.storage import Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "_index.sqlite")


_USAGE = {
    "events": [
        {"stage": "asr", "model": "paraformer-v2", "audio_seconds": 600,
         "elapsed_seconds": 45.2, "cost_yuan": 0.048},
        {"stage": "llm_clean", "model": "qwen-plus", "input_tokens": 12000,
         "output_tokens": 11000, "elapsed_seconds": 80.1, "cost_yuan": 0.031},
    ],
    "total_cost_yuan": 0.079,
}


class TestUsagePersistence:

    def test_mark_done_stores_usage_roundtrip(self, storage):
        job_id = storage.create_job("https://b23.tv/x")
        storage.mark_done(job_id, md_path="/tmp/a.md", usage=_USAGE)
        job = storage.get_job(job_id)
        assert job["usage"] == _USAGE

    def test_mark_done_without_usage_is_none(self, storage):
        job_id = storage.create_job("https://b23.tv/x")
        storage.mark_done(job_id, md_path="/tmp/a.md")
        assert storage.get_job(job_id)["usage"] is None

    def test_list_jobs_parses_usage(self, storage):
        job_id = storage.create_job("https://b23.tv/x")
        storage.mark_done(job_id, md_path="/tmp/a.md", usage=_USAGE)
        jobs = storage.list_jobs()
        assert jobs[0]["usage"]["total_cost_yuan"] == pytest.approx(0.079)

    def test_corrupt_usage_json_returns_none_not_crash(self, storage):
        job_id = storage.create_job("https://b23.tv/x")
        with storage._connect() as conn:
            conn.execute("UPDATE jobs SET usage = '不是json' WHERE id = ?", (job_id,))
        assert storage.get_job(job_id)["usage"] is None


class TestTotalCost:

    def test_sums_total_cost_over_jobs(self, storage):
        j1 = storage.create_job("https://b23.tv/1")
        storage.mark_done(j1, md_path="/tmp/1.md", usage=_USAGE)
        j2 = storage.create_job("https://b23.tv/2")
        storage.mark_done(
            j2, md_path="/tmp/2.md",
            usage={"events": [], "total_cost_yuan": 0.021},
        )
        # 无 usage 的旧任务不参与求和、不崩
        j3 = storage.create_job("https://b23.tv/3")
        storage.mark_done(j3, md_path="/tmp/3.md")
        assert storage.total_cost_yuan() == pytest.approx(0.1)

    def test_empty_db_returns_zero(self, storage):
        assert storage.total_cost_yuan() == 0.0


class TestMigration:

    def test_old_db_without_usage_column_gets_migrated(self, tmp_path):
        # 0.4.0 的库没有 usage 列；打开时必须原地补列，旧数据不丢
        db_path = tmp_path / "_index.sqlite"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                platform TEXT, content_type TEXT,
                status TEXT NOT NULL,
                md_path TEXT, title TEXT, author TEXT,
                error_message TEXT, log_excerpt TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                started_at TEXT, finished_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO jobs (url, status, created_at, updated_at) "
            "VALUES ('https://b23.tv/old', 'done', '2026-01-01', '2026-01-01')"
        )
        conn.commit()
        conn.close()

        storage = Storage(db_path)
        old_job = storage.list_jobs()[0]
        assert old_job["url"] == "https://b23.tv/old"
        assert old_job["usage"] is None

        new_id = storage.create_job("https://b23.tv/new")
        storage.mark_done(new_id, md_path="/tmp/n.md", usage=_USAGE)
        assert storage.get_job(new_id)["usage"] == _USAGE
