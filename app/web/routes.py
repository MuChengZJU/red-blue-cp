"""FastAPI routes for the Red Blue CP web UI."""

from __future__ import annotations

import asyncio
import logging
import os
import traceback
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.service.errors import RbcpError, format_error_for_user
from app.service.extractor import detect_platform
from app.service.storage import Storage
from app.service.urls import clean_url


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


def _safe_error_detail(error: BaseException, *, max_levels: int = 5) -> str:
    """给用户看的「技术详情」：异常链的 类型: 信息，**不含 traceback/文件路径**。

    完整 traceback 只进服务器日志（logger）。绝不把 /home/用户名、.venv 路径、
    源码行号这些泄漏到 WebUI——那会暴露服务器文件系统和用户名。
    """
    parts: list[str] = []
    seen = 0
    exc: BaseException | None = error
    while exc is not None and seen < max_levels:
        msg = str(exc).strip()
        parts.append(f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__)
        exc = exc.__cause__ or exc.__context__
        seen += 1
    return "\n".join(parts)


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
        # error_message 存「人话」；log_excerpt 存**脱敏的异常链摘要**（不含 traceback/
        # 文件路径/用户名）。完整 traceback 只进服务器日志，绝不上 WebUI。
        storage.mark_failed(
            job_id,
            error_message=format_error_for_user(error),
            log_excerpt=_safe_error_detail(error),
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
    # 分享文案抽 URL + 去追踪参数（小红书保 token）。粘贴带标题的分享串也能用。
    url = clean_url(payload.url)
    # audit #4：建 job 前先校验平台，非 B站/小红书立即 400 + 人话，
    # 别让用户等异步任务跑到 detect_platform 才报错（白等一轮）。
    try:
        detect_platform(url)
    except RbcpError as exc:
        raise HTTPException(status_code=400, detail=format_error_for_user(exc)) from None

    job_id = storage.create_job(url)
    asyncio.create_task(
        asyncio.to_thread(_run_job, job_id, url, storage, pipeline_fn)
    )
    return {"job_id": job_id}


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(
    job_id: int,
    storage: Storage = Depends(get_storage),
    pipeline_fn: Callable[[str], str] = Depends(get_pipeline_fn),
) -> dict[str, int]:
    """原地重试：复用同一条 job（不新建），重置为 pending 后再后台跑。
    避免重试堆出一堆新任务，且这条记录能反映最终成没成。"""
    job = storage.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    storage.reset_for_retry(job_id)
    asyncio.create_task(
        asyncio.to_thread(_run_job, job_id, job["url"], storage, pipeline_fn)
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


@app.post("/api/import-list")
async def import_list(
    payload: dict = Body(...),
    allow_partial: bool = False,
) -> dict:
    """导入插件导出的 notes.json，后台跑 batch（走代理 / 断点续传 / token 跳过 / 汇总）。

    早校验 schema：不合规立即 400，不开后台任务。开跑后到 /batches 看进度。
    """
    from app.service import batch as batch_mod

    try:
        batch_mod._load_and_validate(payload, allow_partial=allow_partial)
    except RbcpError as exc:
        raise HTTPException(status_code=400, detail=format_error_for_user(exc)) from None

    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    output_dir = Path(os.getenv("RBCP_OUTPUT_DIR", "~/transcript")).expanduser()
    proxy = os.getenv("RBCP_PROXY") or None
    asyncio.create_task(
        asyncio.to_thread(
            batch_mod.run_batch,
            payload,
            api_key=api_key,
            output_dir=output_dir,
            proxy=proxy,
            allow_partial=allow_partial,
        )
    )
    return {"ok": True, "count": len(payload.get("notes") or [])}


@app.get("/api/batches")
def api_list_batches(storage: Storage = Depends(get_storage)) -> dict:
    """批次列表 + 每批的状态计数，供批量状态页轮询。"""
    return {"batches": storage.list_batches(limit=50)}


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


@app.get("/batches")
def batches_page(request: Request):
    """批量导入 + 状态页：上传 notes.json，轮询看每批进度。"""
    return templates.TemplateResponse(request, "batches.html", {"request": request})


@app.get("/jobs/{job_id}")
def job_detail(
    request: Request,
    job_id: int,
    storage: Storage = Depends(get_storage),
):
    job = storage.get_job(job_id)
    if job is None:
        # 返回带样式的 404 页（仍是 404 状态），而不是裸 JSON。
        # 前端 JS fetch /api/jobs/{id} 拿到 404 后会显示「任务不存在」空状态。
        return templates.TemplateResponse(
            request,
            "detail.html",
            {"request": request, "job_id": job_id, "job": None},
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "detail.html",
        {"request": request, "job_id": job_id, "job": job},
    )
