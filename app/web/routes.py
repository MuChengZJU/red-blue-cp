"""FastAPI routes for the Red Blue CP web UI."""

from __future__ import annotations

import asyncio
import logging
import os
import traceback
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.service.storage import Storage


load_dotenv()  # 防御性：直接 uvicorn 启动时也保证 .env 已加载

logger = logging.getLogger("rbcp")
if not logger.handlers:
    logger.setLevel(logging.INFO)


class _PollNoiseFilter(logging.Filter):
    """屏蔽前端 2 秒一次轮询 /api/jobs 的 access log 噪音。"""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not (' "GET /api/jobs' in message or ' "GET /api/jobs?' in message)


logging.getLogger("uvicorn.access").addFilter(_PollNoiseFilter())


app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


class CreateJobRequest(BaseModel):
    url: str = Field(..., min_length=1)


class UploaderPostsRequest(BaseModel):
    user_url: str = Field(..., min_length=1)


class CommentsRequest(BaseModel):
    url: str = Field(..., min_length=1)
    sub: bool = True


def get_storage() -> Storage:
    db_path = Path(os.getenv("RBCP_OUTPUT_DIR", "~/transcript")).expanduser()
    return Storage(db_path / "_index.sqlite")


def get_pipeline_fn() -> Callable[[str], str]:
    from app.cli import _create_pipeline_fn

    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    output_dir = Path(os.getenv("RBCP_OUTPUT_DIR", "~/transcript")).expanduser()
    return _create_pipeline_fn(api_key=api_key, output_dir=output_dir)


def _run_job(
    job_id: int,
    url: str,
    storage: Storage,
    pipeline_fn: Callable[[str], dict],
) -> None:
    storage.mark_running(job_id)
    logger.info("[job %s] start: %s", job_id, url)
    try:
        result = pipeline_fn(url)
        storage.mark_done(
            job_id,
            md_path=result["md_path"],
            title=result.get("title"),
            author=result.get("author"),
            platform=result.get("platform"),
            content_type=result.get("content_type"),
        )
        logger.info("[job %s] done: %s", job_id, result["md_path"])
    except Exception as error:
        tb = traceback.format_exc()
        storage.mark_failed(
            job_id,
            error_message=str(error),
            log_excerpt=tb,
        )
        logger.error("[job %s] FAILED: %s\n%s", job_id, error, tb)


def _markdown_path_for_job(storage: Storage, job_id: int) -> Path:
    job = storage.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    md_path = job.get("md_path")
    if not md_path:
        raise HTTPException(status_code=404, detail="Markdown not found")

    path = Path(md_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Markdown not found")
    return path


@app.on_event("startup")
def cleanup_running_jobs() -> None:
    get_storage().cleanup_running()


@app.post("/api/jobs")
async def create_job(
    payload: CreateJobRequest,
    storage: Storage = Depends(get_storage),
    pipeline_fn: Callable[[str], str] = Depends(get_pipeline_fn),
) -> dict[str, int]:
    job_id = storage.create_job(payload.url)
    asyncio.create_task(
        asyncio.to_thread(_run_job, job_id, payload.url, storage, pipeline_fn)
    )
    return {"job_id": job_id}


@app.get("/api/jobs")
def list_jobs(
    limit: int = 20,
    offset: int = 0,
    storage: Storage = Depends(get_storage),
) -> list[dict]:
    return storage.list_jobs(limit=limit, offset=offset)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, storage: Storage = Depends(get_storage)) -> dict:
    job = storage.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs/{job_id}/markdown")
def get_markdown(
    job_id: int,
    storage: Storage = Depends(get_storage),
) -> PlainTextResponse:
    path = _markdown_path_for_job(storage, job_id)
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(status_code=404, detail="Markdown not found") from None
    return PlainTextResponse(content, media_type="text/markdown")


@app.get("/api/jobs/{job_id}/download")
def download_markdown(
    job_id: int,
    storage: Storage = Depends(get_storage),
) -> FileResponse:
    path = _markdown_path_for_job(storage, job_id)
    return FileResponse(
        path,
        media_type="text/markdown",
        filename=path.name,
    )


@app.post("/api/uploaders/posts")
async def uploader_posts(payload: UploaderPostsRequest) -> dict:
    """列博主全量笔记清单。返回 SPEC §4.3 契约（含 complete 硬字段）。

    浏览器抓取较慢且全局串行，这里直接 await（单用户 MVP 可接受）。
    """
    from app.service import discover

    return await discover.discover_user_posts(payload.user_url)


@app.post("/api/comments")
async def fetch_comments(payload: CommentsRequest) -> dict:
    """抓单篇笔记评论，写出 {note_id}.comments.md，返回路径 + 条数。"""
    from app.service import discover
    from app.service.comments import write_comments_md

    output_dir = Path(os.getenv("RBCP_OUTPUT_DIR", "~/transcript")).expanduser()
    note_id = discover.note_id_from_url(payload.url)
    try:
        comments = await discover.discover_comments(payload.url, with_sub=payload.sub)
    except discover.RiskControlError as error:
        raise HTTPException(status_code=503, detail=str(error)) from None

    path = write_comments_md(note_id, comments, output_dir, note_title="")
    sub_count = sum(len(c.sub_comments) for c in comments)
    return {
        "note_id": note_id,
        "comments_path": str(path),
        "comment_count": len(comments),          # 一级评论数
        "total_count": len(comments) + sub_count,  # 含楼中楼，= 写入文件的评论总数
    }


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


@app.get("/jobs/{job_id}")
def job_detail(
    request: Request,
    job_id: int,
    storage: Storage = Depends(get_storage),
):
    job = storage.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse(
        request,
        "detail.html",
        {"request": request, "job_id": job_id, "job": job},
    )
