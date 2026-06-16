"""storage 的 batch / batch_item 表 + CRUD 测试（M4a-a4 锁定 schema）。

M4c batch 断点续传依赖这些方法。表用 IF NOT EXISTS 模式，老 DB 自动补表不丢数据。
"""

import sqlite3

import pytest

from app.extract.storage import Storage


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "_index.sqlite"


# ── 建表 / 迁移 ─────────────────────────────────────────────────

class TestSchema:

    def test_new_db_has_batch_tables(self, db_path):
        Storage(db_path)
        with sqlite3.connect(db_path) as conn:
            names = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        assert "batch" in names
        assert "batch_item" in names

    def test_old_db_gets_tables_without_losing_jobs(self, db_path):
        # 模拟老库：只有 jobs 表 + 一行
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE jobs (id INTEGER PRIMARY KEY, url TEXT, status TEXT, "
                "created_at TEXT, updated_at TEXT)"
            )
            conn.execute(
                "INSERT INTO jobs (url, status, created_at, updated_at) "
                "VALUES ('u', 'done', 'now', 'now')"
            )
        Storage(db_path)  # 应自动补 batch 表，不动 jobs 数据
        with sqlite3.connect(db_path) as conn:
            names = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            jobs_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        assert "batch" in names and "batch_item" in names
        assert jobs_count == 1


# ── batch CRUD ──────────────────────────────────────────────────

class TestBatchCrud:

    def test_create_batch_returns_id_and_get_batch_reads_back(self, db_path):
        st = Storage(db_path)
        bid = st.create_batch(source="xhs_user_posted", user_id="u123",
                              count=326, complete=True)
        assert isinstance(bid, int)
        row = st.get_batch(bid)
        assert row["source"] == "xhs_user_posted"
        assert row["user_id"] == "u123"
        assert row["count"] == 326
        assert row["status"] == "pending"

    def test_complete_bool_stored_as_int(self, db_path):
        st = Storage(db_path)
        bid = st.create_batch(source="s", user_id="u", count=1, complete=False)
        assert st.get_batch(bid)["complete"] == 0

    def test_get_batch_missing_returns_none(self, db_path):
        st = Storage(db_path)
        assert st.get_batch(999) is None

    def test_mark_batch_status(self, db_path):
        st = Storage(db_path)
        bid = st.create_batch(source="s", user_id="u", count=1, complete=True)
        st.mark_batch_status(bid, "running")
        assert st.get_batch(bid)["status"] == "running"


# ── batch_item CRUD + 断点续传查询 ──────────────────────────────

class TestBatchItemCrud:

    def _batch(self, db_path):
        st = Storage(db_path)
        bid = st.create_batch(source="s", user_id="u", count=2, complete=True)
        return st, bid

    def test_add_items_default_pending(self, db_path):
        st, bid = self._batch(db_path)
        st.add_batch_items(bid, [
            {"note_id": "n1", "url": "http://a"},
            {"note_id": "n2", "url": "http://b"},
        ])
        statuses = st.get_batch_item_statuses(bid)
        assert statuses == {"n1": "pending", "n2": "pending"}

    def test_mark_item_done_sets_md_path(self, db_path):
        st, bid = self._batch(db_path)
        st.add_batch_items(bid, [{"note_id": "n1", "url": "http://a"}])
        st.mark_batch_item_done(bid, "n1", md_path="/x/n1.md")
        assert st.get_batch_item_statuses(bid)["n1"] == "done"

    def test_mark_item_failed(self, db_path):
        st, bid = self._batch(db_path)
        st.add_batch_items(bid, [{"note_id": "n1", "url": "http://a"}])
        st.mark_batch_item_failed(bid, "n1", error_message="boom")
        assert st.get_batch_item_statuses(bid)["n1"] == "failed"

    def test_mark_item_skipped(self, db_path):
        st, bid = self._batch(db_path)
        st.add_batch_items(bid, [{"note_id": "n1", "url": "http://a"}])
        st.mark_batch_item_failed(bid, "n1", error_message="token_expired", skipped=True)
        assert st.get_batch_item_statuses(bid)["n1"] == "skipped"

    def test_re_add_same_item_is_idempotent(self, db_path):
        # 断点续传：重跑可能重复 add 已有 note_id，不能报错也不能覆盖已完成状态
        st, bid = self._batch(db_path)
        st.add_batch_items(bid, [{"note_id": "n1", "url": "http://a"}])
        st.mark_batch_item_done(bid, "n1", md_path="/x/n1.md")
        st.add_batch_items(bid, [{"note_id": "n1", "url": "http://a"}])  # 重复 add
        assert st.get_batch_item_statuses(bid)["n1"] == "done"  # 仍是 done，没被重置
