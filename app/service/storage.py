"""SQLite-backed job storage."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


class Storage:
    """Persistence layer for transcript jobs."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    platform TEXT,
                    content_type TEXT,
                    status TEXT NOT NULL,
                    md_path TEXT,
                    title TEXT,
                    author TEXT,
                    error_message TEXT,
                    log_excerpt TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs (created_at DESC)"
            )
            # ── 博主批量（M4a-a4，断点续传用）。阶段 1 不建 inbox 表 ──
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS batch (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    user_id TEXT,
                    count INTEGER NOT NULL DEFAULT 0,
                    complete INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS batch_item (
                    batch_id INTEGER NOT NULL,
                    note_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    md_path TEXT,
                    error_message TEXT,
                    finished_at TEXT,
                    PRIMARY KEY (batch_id, note_id),
                    FOREIGN KEY (batch_id) REFERENCES batch (id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_batch_item_status "
                "ON batch_item (batch_id, status)"
            )

    def create_job(
        self,
        url: str,
        *,
        platform: str | None = None,
        content_type: str | None = None,
    ) -> int:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO jobs (
                    url, platform, content_type, status, retry_count,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (url, platform, content_type, "pending", 0, now, now),
            )
            return int(cursor.lastrowid)

    def mark_running(self, job_id: int) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, updated_at = ?, started_at = ?
                WHERE id = ?
                """,
                ("running", now, now, job_id),
            )

    def mark_done(
        self,
        job_id: int,
        *,
        md_path: str,
        title: str | None = None,
        author: str | None = None,
        platform: str | None = None,
        content_type: str | None = None,
    ) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?,
                    md_path = ?,
                    title = ?,
                    author = ?,
                    platform = ?,
                    content_type = ?,
                    error_message = NULL,
                    log_excerpt = NULL,
                    updated_at = ?,
                    finished_at = ?
                WHERE id = ?
                """,
                (
                    "done",
                    md_path,
                    title,
                    author,
                    platform,
                    content_type,
                    now,
                    now,
                    job_id,
                ),
            )

    def mark_failed(
        self,
        job_id: int,
        *,
        error_message: str,
        log_excerpt: str | None = None,
    ) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?,
                    error_message = ?,
                    log_excerpt = ?,
                    updated_at = ?,
                    finished_at = ?
                WHERE id = ?
                """,
                ("failed", error_message, log_excerpt, now, now, job_id),
            )

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_jobs(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM jobs ORDER BY created_at DESC, id DESC"
        params: list[int] = []
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            query += " LIMIT -1 OFFSET ?"
            params.append(offset)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    # ── 博主批量（M4a-a4） ─────────────────────────────────────

    def create_batch(
        self,
        *,
        source: str,
        user_id: str | None,
        count: int,
        complete: bool,
    ) -> int:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO batch (source, user_id, count, complete, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (source, user_id, count, int(complete), "pending", now),
            )
            return int(cursor.lastrowid)

    def get_batch(self, batch_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM batch WHERE id = ?", (batch_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def list_batches(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """批次列表（最新在前），每条附 done/failed/skipped/pending 计数。供 WebUI 批量状态页。"""
        query = "SELECT * FROM batch ORDER BY id DESC"
        params: list[Any] = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            out = []
            for row in rows:
                counts = {
                    r["status"]: r["c"]
                    for r in conn.execute(
                        "SELECT status, COUNT(*) AS c FROM batch_item "
                        "WHERE batch_id = ? GROUP BY status",
                        (row["id"],),
                    ).fetchall()
                }
                out.append({**dict(row), "counts": counts})
        return out

    def find_active_batch(self, source: str, user_id: str | None) -> int | None:
        """按 (source, user_id) 找回最近一个批次 id，供 batch 断点续传复用。无则 None。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM batch WHERE source = ? "
                "AND (user_id = ? OR (user_id IS NULL AND ? IS NULL)) "
                "ORDER BY id DESC LIMIT 1",
                (source, user_id, user_id),
            ).fetchone()
        return int(row["id"]) if row is not None else None

    def mark_batch_status(self, batch_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE batch SET status = ? WHERE id = ?", (status, batch_id)
            )

    def add_batch_items(self, batch_id: int, items: list[dict[str, Any]]) -> None:
        """登记待下条目（断点续传幂等）。

        - 新 note_id → 插入 pending。
        - 已存在：默认保持原状态（done/failed/skipped 不动）。
        - **例外**：原状态是 skipped（token 过期跳过）且 url 变了（重新抓清单换了
          新 xsec_token）→ 重置 pending，让新 token 重试。同 url 的 skipped 不动
          （死 token 重跑不必再试）。
        """
        with self._connect() as conn:
            for it in items:
                row = conn.execute(
                    "SELECT status, url FROM batch_item WHERE batch_id = ? AND note_id = ?",
                    (batch_id, it["note_id"]),
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO batch_item (batch_id, note_id, url, status) "
                        "VALUES (?, ?, ?, 'pending')",
                        (batch_id, it["note_id"], it["url"]),
                    )
                elif row["status"] == "skipped" and row["url"] != it["url"]:
                    conn.execute(
                        "UPDATE batch_item SET url = ?, status = 'pending', "
                        "error_message = NULL WHERE batch_id = ? AND note_id = ?",
                        (it["url"], batch_id, it["note_id"]),
                    )

    def get_batch_item_statuses(self, batch_id: int) -> dict[str, str]:
        """{note_id: status}，断点续传查这个跳过 done/skipped。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT note_id, status FROM batch_item WHERE batch_id = ?",
                (batch_id,),
            ).fetchall()
        return {row["note_id"]: row["status"] for row in rows}

    def mark_batch_item_done(self, batch_id: int, note_id: str, *, md_path: str) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE batch_item
                SET status = 'done', md_path = ?, error_message = NULL, finished_at = ?
                WHERE batch_id = ? AND note_id = ?
                """,
                (md_path, now, batch_id, note_id),
            )

    def mark_batch_item_failed(
        self,
        batch_id: int,
        note_id: str,
        *,
        error_message: str,
        skipped: bool = False,
    ) -> None:
        now = datetime.now().isoformat()
        status = "skipped" if skipped else "failed"
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE batch_item
                SET status = ?, error_message = ?, finished_at = ?
                WHERE batch_id = ? AND note_id = ?
                """,
                (status, error_message, now, batch_id, note_id),
            )

    def cleanup_running(self) -> int:
        now = datetime.now().isoformat()
        error_message = "Job was running before restart"
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET status = ?,
                    error_message = ?,
                    updated_at = ?,
                    finished_at = ?
                WHERE status = ?
                """,
                ("failed", error_message, now, now, "running"),
            )
            return int(cursor.rowcount)
