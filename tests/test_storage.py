"""Storage 测试 — 按 SPEC §5.1 定义 SQLite jobs CRUD 接口契约。"""

import sqlite3
import tempfile
from pathlib import Path

import pytest
from app.service.storage import Storage


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def storage(db_path):
    return Storage(db_path)


class TestSchemaInit:

    def test_creates_jobs_table(self, storage, db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_creates_indexes(self, storage, db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        index_names = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "idx_jobs_status" in index_names
        assert "idx_jobs_created_at" in index_names

    def test_idempotent_init(self, db_path):
        s1 = Storage(db_path)
        s2 = Storage(db_path)  # 不应报错


class TestCreateJob:

    def test_returns_integer_id(self, storage):
        job_id = storage.create_job("https://www.bilibili.com/video/BV1234")
        assert isinstance(job_id, int)
        assert job_id > 0

    def test_initial_status_is_pending(self, storage):
        job_id = storage.create_job("https://www.bilibili.com/video/BV1234")
        job = storage.get_job(job_id)
        assert job["status"] == "pending"

    def test_url_stored(self, storage):
        url = "https://www.xiaohongshu.com/explore/abc123"
        job_id = storage.create_job(url)
        job = storage.get_job(job_id)
        assert job["url"] == url

    def test_created_at_set(self, storage):
        job_id = storage.create_job("https://example.com")
        job = storage.get_job(job_id)
        assert job["created_at"] is not None

    def test_sequential_ids(self, storage):
        id1 = storage.create_job("https://example.com/1")
        id2 = storage.create_job("https://example.com/2")
        assert id2 > id1


class TestMarkRunning:

    def test_status_changes_to_running(self, storage):
        job_id = storage.create_job("https://example.com")
        storage.mark_running(job_id)
        job = storage.get_job(job_id)
        assert job["status"] == "running"

    def test_started_at_set(self, storage):
        job_id = storage.create_job("https://example.com")
        storage.mark_running(job_id)
        job = storage.get_job(job_id)
        assert job["started_at"] is not None


class TestMarkDone:

    def test_status_changes_to_done(self, storage):
        job_id = storage.create_job("https://example.com")
        storage.mark_running(job_id)
        storage.mark_done(
            job_id,
            md_path="/home/user/transcript/bili/test.md",
            title="测试视频",
            author="UP主",
            platform="bilibili",
            content_type="video",
        )
        job = storage.get_job(job_id)
        assert job["status"] == "done"

    def test_fields_persisted(self, storage):
        job_id = storage.create_job("https://example.com")
        storage.mark_running(job_id)
        storage.mark_done(
            job_id,
            md_path="/path/to/file.md",
            title="标题",
            author="作者",
            platform="xiaohongshu",
            content_type="image_note",
        )
        job = storage.get_job(job_id)
        assert job["md_path"] == "/path/to/file.md"
        assert job["title"] == "标题"
        assert job["author"] == "作者"
        assert job["platform"] == "xiaohongshu"
        assert job["content_type"] == "image_note"

    def test_finished_at_set(self, storage):
        job_id = storage.create_job("https://example.com")
        storage.mark_running(job_id)
        storage.mark_done(job_id, md_path="/path.md")
        job = storage.get_job(job_id)
        assert job["finished_at"] is not None


class TestMarkFailed:

    def test_status_changes_to_failed(self, storage):
        job_id = storage.create_job("https://example.com")
        storage.mark_running(job_id)
        storage.mark_failed(job_id, error_message="连接超时")
        job = storage.get_job(job_id)
        assert job["status"] == "failed"

    def test_error_message_persisted(self, storage):
        job_id = storage.create_job("https://example.com")
        storage.mark_running(job_id)
        storage.mark_failed(job_id, error_message="小红书风控 403")
        job = storage.get_job(job_id)
        assert job["error_message"] == "小红书风控 403"

    def test_log_excerpt_persisted(self, storage):
        job_id = storage.create_job("https://example.com")
        storage.mark_running(job_id)
        traceback_text = "Traceback (most recent call last):\n  File ...\nConnectionError: ..."
        storage.mark_failed(
            job_id,
            error_message="连接失败",
            log_excerpt=traceback_text,
        )
        job = storage.get_job(job_id)
        assert job["log_excerpt"] == traceback_text

    def test_finished_at_set(self, storage):
        job_id = storage.create_job("https://example.com")
        storage.mark_running(job_id)
        storage.mark_failed(job_id, error_message="err")
        job = storage.get_job(job_id)
        assert job["finished_at"] is not None


class TestGetJob:

    def test_returns_dict(self, storage):
        job_id = storage.create_job("https://example.com")
        job = storage.get_job(job_id)
        assert isinstance(job, dict)

    def test_nonexistent_returns_none(self, storage):
        assert storage.get_job(99999) is None

    def test_contains_all_fields(self, storage):
        job_id = storage.create_job("https://example.com")
        job = storage.get_job(job_id)
        expected_fields = {
            "id", "url", "platform", "content_type", "status",
            "md_path", "title", "author", "error_message", "log_excerpt",
            "retry_count", "created_at", "updated_at", "started_at", "finished_at",
        }
        assert expected_fields.issubset(job.keys())


class TestListJobs:

    def test_empty_db_returns_empty_list(self, storage):
        jobs = storage.list_jobs()
        assert jobs == []

    def test_returns_jobs(self, storage):
        storage.create_job("https://example.com/1")
        storage.create_job("https://example.com/2")
        jobs = storage.list_jobs()
        assert len(jobs) == 2

    def test_ordered_by_created_at_desc(self, storage):
        id1 = storage.create_job("https://example.com/1")
        id2 = storage.create_job("https://example.com/2")
        jobs = storage.list_jobs()
        assert jobs[0]["id"] == id2
        assert jobs[1]["id"] == id1

    def test_limit(self, storage):
        for i in range(5):
            storage.create_job(f"https://example.com/{i}")
        jobs = storage.list_jobs(limit=3)
        assert len(jobs) == 3

    def test_offset(self, storage):
        for i in range(5):
            storage.create_job(f"https://example.com/{i}")
        jobs = storage.list_jobs(limit=2, offset=2)
        assert len(jobs) == 2


class TestCleanupRunning:

    def test_running_becomes_failed(self, storage):
        job_id = storage.create_job("https://example.com")
        storage.mark_running(job_id)
        count = storage.cleanup_running()
        assert count == 1
        job = storage.get_job(job_id)
        assert job["status"] == "failed"

    def test_pending_untouched(self, storage):
        job_id = storage.create_job("https://example.com")
        storage.cleanup_running()
        job = storage.get_job(job_id)
        assert job["status"] == "pending"

    def test_done_untouched(self, storage):
        job_id = storage.create_job("https://example.com")
        storage.mark_running(job_id)
        storage.mark_done(job_id, md_path="/path.md")
        storage.cleanup_running()
        job = storage.get_job(job_id)
        assert job["status"] == "done"

    def test_returns_count(self, storage):
        for _ in range(3):
            jid = storage.create_job("https://example.com")
            storage.mark_running(jid)
        storage.create_job("https://example.com/pending")  # pending, not cleaned
        count = storage.cleanup_running()
        assert count == 3

    def test_sets_error_message(self, storage):
        job_id = storage.create_job("https://example.com")
        storage.mark_running(job_id)
        storage.cleanup_running()
        job = storage.get_job(job_id)
        assert job["error_message"] is not None
        assert "重启" in job["error_message"] or "restart" in job["error_message"].lower() or len(job["error_message"]) > 0
