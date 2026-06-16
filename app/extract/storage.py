"""SQLite-backed job storage."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any



# md 文件名形如 {YYYY-MM-DD}-{作者}-{标题}-{笔记ID}（markdown.sanitize_filename）
_MD_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")


def _title_from_md_stem(stem: str, note_id: str) -> str | None:
    """从 md 文件名抠纯标题：剥日期前缀、尾部笔记 ID、作者段。

    标题位本身是 note_id（当年没标题的占位）→ None（显示层退回 note_id，不装有标题）。
    认不出格式 → 原样返回（比没有强）。
    """
    if not _MD_STEM_RE.match(stem):
        return stem or None
    rest = _MD_STEM_RE.sub("", stem)
    if note_id and rest.endswith(f"-{note_id}"):
        rest = rest[: -(len(note_id) + 1)]
    # 剥作者段（作者名含 "-" 的极少数情况会切掉标题开头，可接受）
    rest = rest.split("-", 1)[1] if "-" in rest else rest
    if not rest or rest == note_id:
        return None
    return rest


def _parse_job_row(row: sqlite3.Row) -> dict[str, Any]:
    """行 → dict，usage 列 JSON 反序列化（脏数据回 None，不让一行坏数据崩整页）。"""
    job = dict(row)
    raw_usage = job.get("usage")
    if raw_usage:
        try:
            job["usage"] = json.loads(raw_usage)
        except (json.JSONDecodeError, TypeError):
            job["usage"] = None
    else:
        job["usage"] = None
    return job


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
                    finished_at TEXT,
                    usage TEXT
                )
                """
            )
            # ── 迁移：0.4.0 及以前的库没有 usage 列（M5a/P1h 加），原地补列 ──
            jobs_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
            }
            if "usage" not in jobs_columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN usage TEXT")
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
                    created_at TEXT NOT NULL,
                    title TEXT
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
                    title TEXT,
                    job_id INTEGER,
                    PRIMARY KEY (batch_id, note_id),
                    FOREIGN KEY (batch_id) REFERENCES batch (id)
                )
                """
            )
            # ── 迁移：0.4.1 及以前的库没有这几列（M5b 加），原地补列 ──
            batch_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(batch)").fetchall()
            }
            if "title" not in batch_columns:
                conn.execute("ALTER TABLE batch ADD COLUMN title TEXT")
            item_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(batch_item)").fetchall()
            }
            if "title" not in item_columns:
                conn.execute("ALTER TABLE batch_item ADD COLUMN title TEXT")
            if "job_id" not in item_columns:
                conn.execute("ALTER TABLE batch_item ADD COLUMN job_id INTEGER")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_batch_item_status "
                "ON batch_item (batch_id, status)"
            )
            self._backfill_legacy_batch_jobs(conn)

    @staticmethod
    def _backfill_legacy_batch_jobs(conn: sqlite3.Connection) -> None:
        """0.5.0 之前的批量条目没建 job（没详情/没标题/不参与去重）。
        打开库时给历史 done/failed 条目回填 job 并关联；标题缺失用 md 文件名兜底。
        只处理 job_id IS NULL 的行，天然幂等。"""
        rows = conn.execute(
            "SELECT batch_id, note_id, url, status, md_path, error_message, "
            "finished_at, title FROM batch_item "
            "WHERE job_id IS NULL AND status IN ('done', 'failed')"
        ).fetchall()
        now = datetime.now().isoformat()
        for row in rows:
            title = row["title"] or (
                _title_from_md_stem(Path(row["md_path"]).stem, row["note_id"])
                if row["md_path"] else None
            )
            ts = row["finished_at"] or now
            cursor = conn.execute(
                """
                INSERT INTO jobs (
                    url, platform, status, md_path, title, error_message,
                    retry_count, created_at, updated_at, finished_at
                ) VALUES (?, 'xiaohongshu', ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (row["url"], row["status"], row["md_path"], title,
                 row["error_message"], ts, ts, ts),
            )
            conn.execute(
                "UPDATE batch_item SET job_id = ?, title = COALESCE(title, ?) "
                "WHERE batch_id = ? AND note_id = ?",
                (cursor.lastrowid, title, row["batch_id"], row["note_id"]),
            )
        Storage._reclean_backfilled_titles(conn)

    @staticmethod
    def _reclean_backfilled_titles(conn: sqlite3.Connection) -> None:
        """0.5.1 首版回填把整个 md 文件名当了标题（带日期/作者/ID 渣）。
        识别「日期开头 + note_id 结尾」的脏标题，重抠纯标题，条目和 job 一起洗。"""
        rows = conn.execute(
            "SELECT batch_id, note_id, job_id, title FROM batch_item "
            "WHERE job_id IS NOT NULL AND title LIKE '____-__-__-%'"
        ).fetchall()
        for row in rows:
            title = row["title"] or ""
            if not title.endswith(f"-{row['note_id']}"):
                continue  # 不是文件名形态的标题，别动
            clean = _title_from_md_stem(title, row["note_id"])
            if clean == title:
                continue
            conn.execute(
                "UPDATE batch_item SET title = ? WHERE batch_id = ? AND note_id = ?",
                (clean, row["batch_id"], row["note_id"]),
            )
            conn.execute(
                "UPDATE jobs SET title = ? WHERE id = ? AND title = ?",
                (clean, row["job_id"], title),
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
        usage: dict[str, Any] | None = None,
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
                    usage = ?,
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
                    json.dumps(usage, ensure_ascii=False) if usage else None,
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

    def reset_for_retry(self, job_id: int) -> bool:
        """原地重试：把 job 重置为 pending、清错误、保留 url、retry_count+1。
        返回 job 是否存在。重试不新建一条，避免历史堆积、且能看到这条最终成没成。"""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET status = 'pending', error_message = NULL, log_excerpt = NULL,
                    md_path = NULL, started_at = NULL, finished_at = NULL,
                    usage = NULL,
                    retry_count = retry_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (now, job_id),
            )
            return cursor.rowcount > 0

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return _parse_job_row(row)

    def list_jobs(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        exclude_batched: bool = False,
    ) -> list[dict[str, Any]]:
        # exclude_batched：批量产生的 job 在任务列表里住在批次卡片内，单卡不重复显示（M5b E8）
        query = "SELECT * FROM jobs"
        if exclude_batched:
            query += (
                " WHERE id NOT IN"
                " (SELECT job_id FROM batch_item WHERE job_id IS NOT NULL)"
            )
        query += " ORDER BY created_at DESC, id DESC"
        params: list[int] = []
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            query += " LIMIT -1 OFFSET ?"
            params.append(offset)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_parse_job_row(row) for row in rows]

    def done_jobs_brief(self) -> list[tuple[int, str, str | None]]:
        """成功任务的 (id, url, title) 轻量清单，供去重扫描（M5b E1/E2）。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, url, title FROM jobs WHERE status = 'done' ORDER BY id DESC"
            ).fetchall()
        return [(row["id"], row["url"], row["title"]) for row in rows]

    def total_cost_yuan(self) -> float:
        """全部任务累计估算费用（元）。无 usage / 脏 JSON 的行不参与。"""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(json_extract(usage, '$.total_cost_yuan')), 0)
                FROM jobs
                WHERE usage IS NOT NULL AND json_valid(usage)
                """
            ).fetchone()
        return float(row[0] or 0.0)

    def stats_by_stage(self) -> dict[str, dict]:
        """按环节（stage）聚合费用与时长。与 total_cost_yuan 相同取数方式。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT usage FROM jobs
                WHERE usage IS NOT NULL AND json_valid(usage)
                """
            ).fetchall()
        result: dict[str, dict] = {}
        for row in rows:
            usage = json.loads(row["usage"])
            for event in usage.get("events") or []:
                stage = event.get("stage") or "unknown"
                if stage not in result:
                    result[stage] = {"cost_yuan": 0.0, "elapsed_seconds": 0.0, "count": 0}
                result[stage]["cost_yuan"] += float(event.get("cost_yuan") or 0)
                result[stage]["elapsed_seconds"] += float(event.get("elapsed_seconds") or 0)
                result[stage]["count"] += 1
        for v in result.values():
            v["cost_yuan"] = round(v["cost_yuan"], 6)
            v["elapsed_seconds"] = round(v["elapsed_seconds"], 2)
        return result


    def delete_job(self, job_id: int) -> bool:
        """删除单条 job：查 md_path → 删 DB 行 → 删 .md 文件（安全忽略缺失）。

        返回是否删了行。md_path 从 DB 查出，绝不接受外部传入的路径（红线#1）。
        """
        job = self.get_job(job_id)
        if job is None:
            return False
        md_path = job.get("md_path")
        with self._connect() as conn:
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        if md_path:
            try:
                os.remove(md_path)
            except FileNotFoundError:
                pass
        return True

    # ── 博主批量（M4a-a4） ─────────────────────────────────────

    def create_batch(
        self,
        *,
        source: str,
        user_id: str | None,
        count: int,
        complete: bool,
        title: str | None = None,
    ) -> int:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO batch (source, user_id, count, complete, status, created_at, title)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (source, user_id, count, int(complete), "pending", now, title),
            )
            return int(cursor.lastrowid)

    def get_batch(self, batch_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM batch WHERE id = ?", (batch_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def list_batches(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """批次列表（最新在前），每条附状态计数 + 前 5 条预览（M5b 批次卡片）。
        全量条目走 list_batch_items（展开时才取，列表轮询不背全量）。"""
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
                preview = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT note_id, title, status, job_id FROM batch_item "
                        "WHERE batch_id = ? ORDER BY rowid LIMIT 5",
                        (row["id"],),
                    ).fetchall()
                ]
                cost_row = conn.execute(
                    """
                    SELECT COALESCE(SUM(json_extract(j.usage, '$.total_cost_yuan')), 0)
                    FROM batch_item bi JOIN jobs j ON j.id = bi.job_id
                    WHERE bi.batch_id = ? AND j.usage IS NOT NULL AND json_valid(j.usage)
                    """,
                    (row["id"],),
                ).fetchone()
                out.append({
                    **dict(row), "counts": counts, "items_preview": preview,
                    "cost_yuan": float(cost_row[0] or 0.0),
                })
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
                        "INSERT INTO batch_item (batch_id, note_id, url, status, title) "
                        "VALUES (?, ?, ?, 'pending', ?)",
                        (batch_id, it["note_id"], it["url"], it.get("title")),
                    )
                else:
                    if it.get("title"):
                        # 重新导入时刷新标题（旧条目当年没存标题——0.5.0 用户实测）
                        conn.execute(
                            "UPDATE batch_item SET title = ? "
                            "WHERE batch_id = ? AND note_id = ?",
                            (it["title"], batch_id, it["note_id"]),
                        )
                    if row["status"] == "skipped" and row["url"] != it["url"]:
                        conn.execute(
                            "UPDATE batch_item SET url = ?, status = 'pending', "
                            "error_message = NULL WHERE batch_id = ? AND note_id = ?",
                            (it["url"], batch_id, it["note_id"]),
                        )

    def set_batch_item_job(self, batch_id: int, note_id: str, job_id: int) -> None:
        """条目 ↔ job 关联（M5b E4）：批次条目从此能进 /jobs/{id} 详情。"""
        with self._connect() as conn:
            conn.execute(
                "UPDATE batch_item SET job_id = ? WHERE batch_id = ? AND note_id = ?",
                (job_id, batch_id, note_id),
            )

    def list_batch_items(self, batch_id: int) -> list[dict[str, Any]]:
        """批次全部条目（登记顺序），供任务列表批次卡片渲染。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM batch_item WHERE batch_id = ? ORDER BY rowid",
                (batch_id,),
            ).fetchall()
        return [dict(row) for row in rows]

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
