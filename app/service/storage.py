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
