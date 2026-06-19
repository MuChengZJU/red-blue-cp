"""FastAPI routes for the Red Blue CP web UI."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import traceback
from pathlib import Path
from typing import Callable

import requests

from app.config import load_config, resolve_output_dir
from app.extract import model
from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.extract.errors import RbcpError, format_error_for_user
from app.extract.extractor import detect_platform
from app.extract.storage import Storage
from app.web import artifacts
from app.web import digest_cache
from app.web import thumbnail_cache
from app.extract.urls import clean_url, dedup_key
from app.web.auth import require_token


load_config()  # 防御性：直接 uvicorn 启动时也保证 .env 已加载

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


def _maybe_enable_cors(target_app: FastAPI) -> bool:
    """桌面模式下放宽 CORS：前端从 tauri://localhost 跨源调本地 serve。

    serve 仅绑 127.0.0.1（外部够不着）+ Bearer token 鉴权，不用 cookie，
    故 allow_origins=["*"] 安全。非桌面（WebUI 同源）不加，保持原行为。
    """
    if os.getenv("RBCP_DESKTOP") == "1":
        from fastapi.middleware.cors import CORSMiddleware

        target_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        return True
    return False


_maybe_enable_cors(app)

# 静态托管桌面前端：浏览器/QA 开 /app/ 同源加载、调本地 API（dev/QA 便利；Tauri 打包走 frontendDist）。
_DESKTOP_FRONTEND = Path(__file__).resolve().parent.parent.parent / "desktop" / "frontend"
if _DESKTOP_FRONTEND.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/app", StaticFiles(directory=str(_DESKTOP_FRONTEND), html=True), name="desktop-frontend")

api = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


class CreateJobRequest(BaseModel):
    url: str = Field(..., min_length=1)
    force: bool = False  # 已下过仍强制重下（M5b 去重）


class UploaderPostsRequest(BaseModel):
    user_url: str = Field(..., min_length=1)


class CommentsRequest(BaseModel):
    url: str = Field(..., min_length=1)
    sub: bool = True


def get_storage() -> Storage:
    db_path = resolve_output_dir()
    return Storage(db_path / "_index.sqlite")


def get_pipeline_fn() -> Callable[[str], dict]:
    """WebUI 单条/重试的下载管道。走 pipeline.fetch_single 并吃 RBCP_PROXY——
    批量产生的 job 在 UI 点重试也不会丢代理护 IP（Codex review P1）。"""
    from app.extract import pipeline as pipeline_mod

    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    output_dir = resolve_output_dir()
    proxy = os.getenv("RBCP_PROXY") or None
    return lambda url: pipeline_mod.fetch_single(
        url, api_key=api_key, output_dir=output_dir, proxy=proxy
    )


def get_digest_provider():
    from app.extract.pipeline import _provider_from_env, build_proxies

    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    return _provider_from_env(api_key, proxies=build_proxies(os.getenv("RBCP_PROXY")))


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
        # 外部 API 的真实报错体（如 DashScope「模型不存在 / 参数非法」的 JSON）才是
        # 可定位的信息——之前只进服务器日志，GUI 看不到，用户「没日志」就是指这个。
        # 这类响应体是服务商的 JSON 错误，不含本机路径/用户名，可安全展示给用户。
        excerpt = (getattr(exc, "payload_excerpt", None) or "").strip()
        if excerpt:
            parts.append(f"  ↳ 服务端响应：{excerpt[:800]}")
        exc = exc.__cause__ or exc.__context__
        seen += 1
    return "\n".join(parts)


def _find_done_duplicate(storage: Storage, url: str) -> dict | None:
    """同内容（dedup_key 相同）的已成功任务；没有 / 解析不出 key → None。"""
    key = dedup_key(url)
    if key is None:
        return None
    for job_id, job_url, title in storage.done_jobs_brief():
        if dedup_key(job_url) == key:
            return {"job_id": job_id, "title": title}
    return None


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
            usage=result.get("usage"),
        )
        logger.info("[job %s] done: %s", job_id, result["md_path"])
        artifacts.on_job_success(job_id, result)
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


@api.post("/jobs")
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

    # M5b 去重（E1）：同内容已成功保存过 → 409 给前端弹「是否重下」；force 才放行。
    # 只拦 done（失败的旧任务不拦）；短链 dedup_key=None 不猜、不拦。
    if not payload.force:
        dup = _find_done_duplicate(storage, url)
        if dup is not None:
            raise HTTPException(status_code=409, detail={
                "duplicate": True,
                "existing_job_id": dup["job_id"],
                "title": dup["title"],
            })

    job_id = storage.create_job(url)
    asyncio.create_task(
        asyncio.to_thread(_run_job, job_id, url, storage, pipeline_fn)
    )
    return {"job_id": job_id}


@api.post("/jobs/{job_id}/retry")
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


@api.get("/jobs")
def list_jobs(
    limit: int = 20,
    offset: int = 0,
    exclude_batched: bool = False,
    storage: Storage = Depends(get_storage),
) -> list[dict]:
    return storage.list_jobs(limit=limit, offset=offset, exclude_batched=exclude_batched)


@api.get("/stats")
def get_stats(storage: Storage = Depends(get_storage)) -> dict:
    """全局统计（P1h）：累计估算费用 + 按环节聚合。"""
    return {
        "total_cost_yuan": storage.total_cost_yuan(),
        "by_stage": storage.stats_by_stage(),
    }


@api.get("/config")
def get_config() -> dict:
    """读当前生效配置（API key 打码）。设置界面加载时拉。"""
    from app.web import config_api

    return config_api.get_config()


@api.post("/config")
def set_config(payload: dict = Body(...)) -> dict:
    """保存设置：即时设进 os.environ（运行中下次请求生效）+ 落配置 .env（重启仍在）。"""
    from app.web import config_api

    applied = config_api.set_config(payload)
    return {"ok": True, "applied": applied}


@api.get("/jobs/{job_id}")
def get_job(job_id: int, storage: Storage = Depends(get_storage)) -> dict:
    job = storage.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@api.get("/jobs/{job_id}/markdown")
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


@api.get("/jobs/{job_id}/download")
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


def _reject_in_desktop() -> None:
    if os.getenv("RBCP_DESKTOP") == "1":
        raise HTTPException(status_code=404, detail="disabled_in_desktop")


@api.post("/uploaders/posts", dependencies=[Depends(_reject_in_desktop)])
async def uploader_posts(payload: UploaderPostsRequest) -> dict:
    """列博主全量笔记清单。返回 SPEC §4.3 契约（含 complete 硬字段）。

    浏览器抓取较慢且全局串行，这里直接 await（单用户 MVP 可接受）。
    """
    from app.extract import discover

    return await discover.discover_user_posts(payload.user_url)


@api.post("/comments", dependencies=[Depends(_reject_in_desktop)])
async def fetch_comments(payload: CommentsRequest) -> dict:
    """抓单篇笔记评论，写出 {note_id}.comments.md，返回路径 + 条数。"""
    from app.extract import discover
    from app.extract.comments import write_comments_md

    output_dir = resolve_output_dir()
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


@api.post("/import-list")
async def import_list(
    payload: dict = Body(...),
    allow_partial: bool = False,
    force: bool = False,
    title: str | None = None,
    storage: Storage = Depends(get_storage),
) -> dict:
    """导入插件导出的 notes.json，后台跑 batch（走代理 / 断点续传 / token 跳过 / 汇总）。

    早校验 schema：不合规立即 400，不开后台任务。
    M5b 去重（E2）：默认跳过已成功下过的笔记（按 note_id 对 dedup_key），force=true 全量重下。
    """
    from app.extract import batch as batch_mod

    try:
        batch_mod._load_and_validate(payload, allow_partial=allow_partial)
    except RbcpError as exc:
        raise HTTPException(status_code=400, detail=format_error_for_user(exc)) from None

    notes = payload.get("notes") or []
    skipped_duplicates = 0
    if not force:
        done_keys = {dedup_key(job_url) for _, job_url, _ in storage.done_jobs_brief()}
        done_keys.discard(None)
        fresh = [
            n for n in notes
            if f"xhs:{str(n.get('note_id', '')).lower()}" not in done_keys
        ]
        skipped_duplicates = len(notes) - len(fresh)
        notes = fresh
        payload = {**payload, "notes": notes, "count": len(notes)}

    if not notes:
        # 全是已下过的：不开后台任务，直接报数
        return {"ok": True, "count": 0, "skipped_duplicates": skipped_duplicates}

    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    output_dir = resolve_output_dir()
    proxy = os.getenv("RBCP_PROXY") or None
    asyncio.create_task(
        asyncio.to_thread(
            batch_mod.run_batch,
            payload,
            api_key=api_key,
            output_dir=output_dir,
            proxy=proxy,
            allow_partial=allow_partial,
            title=title,
        )
    )
    return {"ok": True, "count": len(notes), "skipped_duplicates": skipped_duplicates}


@api.get("/batches")
def api_list_batches(storage: Storage = Depends(get_storage)) -> dict:
    """批次列表 + 每批的状态计数，供任务列表批次卡片轮询。"""
    return {"batches": storage.list_batches(limit=50)}


@api.get("/batches/{batch_id}/items")
def api_batch_items(batch_id: int, storage: Storage = Depends(get_storage)) -> dict:
    """批次全部条目（含 job_id，可点进 /jobs/{id} 详情）。"""
    if storage.get_batch(batch_id) is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return {"items": storage.list_batch_items(batch_id)}


@api.get("/jobs/{job_id}/digest")
def get_digest(
    job_id: int,
    provider=Depends(get_digest_provider),
):
    try:
        art = artifacts.load_extract(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=409, detail="need_retranscribe") from None
    # 同一 job_id 复跑（retry / 批量重跑）会用新内容覆盖 artifact，但 digest 缓存
    # 还是旧的——只有当缓存里的 text_sha256 与当前 artifact 一致才复用，否则重算。
    cached = digest_cache.load(job_id)
    if cached is not None and cached.get("extract", {}).get("text_sha256") == art["text_sha256"]:
        return cached
    from app.digest.contracts import digest as run_digest
    from app.extract.contracts import Segment

    segs = tuple(Segment(**d) for d in art["segments"]) if art["segments"] is not None else None
    dr = run_digest(art["canonical_text"], provider=provider, text_sha256=art["text_sha256"], segments=segs)
    envelope = {
        "extract": {
            "canonical_text": art["canonical_text"],
            "text_sha256": art["text_sha256"],
            "segments": art["segments"],
            "readable_text": art.get("readable_text"),
        },
        "digest": dataclasses.asdict(dr),
    }
    digest_cache.save(job_id, envelope)
    return envelope


_XHS_REFERER = "https://www.xiaohongshu.com/"
_BILI_REFERER = "https://www.bilibili.com/"


def _thumbnail_referer(platform: str | None) -> str:
    """封面图防盗链 Referer：小红书必须带（红线#11），B 站亦带；其余给 B 站默认。"""
    if platform == "xiaohongshu":
        return _XHS_REFERER
    return _BILI_REFERER


@api.get("/jobs/{job_id}/thumbnail")
def get_thumbnail(
    job_id: int,
    storage: Storage = Depends(get_storage),
) -> Response:
    """封面缩略图：按 job_id 取 cover_url，命中缓存直返，否则按需抓取 + 缓存。

    红线#1：只走 job_id，不接受任意路径。
    无 job / 无 artifact / 无 cover_url / 上游抓取失败 → 404（语义：「无缩略图」，绝不 500）。
    """
    job = storage.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        art = artifacts.load_extract(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No thumbnail") from None
    cover_url = art.get("cover_url")
    if not cover_url:
        raise HTTPException(status_code=404, detail="No thumbnail")

    cached = thumbnail_cache.load(job_id)
    if cached is not None:
        data, content_type = cached
        return Response(
            content=data,
            media_type=content_type,
            headers={"Cache-Control": "max-age=86400"},
        )

    from app.extract.pipeline import build_proxies

    platform = art.get("platform") or job.get("platform")
    headers = {
        **model.DEFAULT_MEDIA_HEADERS,
        "Referer": _thumbnail_referer(platform),
    }
    try:
        resp = requests.get(
            cover_url,
            headers=headers,
            timeout=(5, 15),
            proxies=build_proxies(os.getenv("RBCP_PROXY")),
        )
    except Exception as error:  # noqa: BLE001 - 抓封面失败一律降级 404，绝不 500
        logger.warning("[thumbnail %s] fetch failed: %s", job_id, error)
        raise HTTPException(status_code=404, detail="No thumbnail") from None
    if resp.status_code != 200:
        logger.warning("[thumbnail %s] upstream HTTP %s for %s", job_id, resp.status_code, cover_url)
        raise HTTPException(status_code=404, detail="No thumbnail")

    content_type = resp.headers.get("content-type", "image/jpeg")
    thumbnail_cache.save(job_id, resp.content, content_type)
    return Response(
        content=resp.content,
        media_type=content_type,
        headers={"Cache-Control": "max-age=86400"},
    )


@api.delete("/jobs/{job_id}")
def delete_job(
    job_id: int, storage: Storage = Depends(get_storage),
) -> dict:
    if not storage.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    artifacts.delete(job_id)
    digest_cache.delete(job_id)
    thumbnail_cache.delete(job_id)
    return {"deleted": job_id}


app.include_router(api)


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


@app.get("/batches")
def batches_page():
    """M5b：批量已整合进主页（批量标签 + 批次卡片），旧入口重定向回主页。"""
    return RedirectResponse(url="/", status_code=301)


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
