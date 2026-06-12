"""4 个 Agent 动词的实现（read / search / list_recent / get_status）。

实验 demo（exp/agent-interface-demo 分支），契约见 app/mcp/CONTRACT.md。
本文件不含任何协议逻辑；协议层（protocol.py）只依赖这里导出的
ToolResult / ToolDef / ToolContext / create_default_context / build_tools。
业务全部走现有 service 接口，不重写。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.service.errors import RbcpError, format_error_for_user
from app.service.extractor import detect_platform
from app.service.storage import Storage
from app.service.urls import clean_url, dedup_key

logger = logging.getLogger("rbcp.mcp")

_MAX_SEARCH_FILE_BYTES = 5 * 1024 * 1024  # search 跳过 >5MB 的文件
_SNIPPET_RADIUS = 60  # snippet 取命中词前后各 60 字符

# 给 Agent 看的工具说明（CONTRACT.md 锁死的文案）
_READ_DESC = (
    "读取一条 B 站/小红书内容的完整转录文本（Markdown）。已转录过的立即返回；"
    "未转录的会启动转录（耗时约 1-5 分钟、消耗少量 API 费用），"
    "届时请稍后用 get_status 查询、完成后再次调用 read。接受分享文案（自动抽 URL）。"
)
_SEARCH_DESC = (
    "在本地知识库（已转录的全部内容）里全文检索。多个关键词空格分隔，"
    "须全部命中（AND，不分大小写）。返回标题/作者/原链接/文件路径/上下文摘录。"
)
_LIST_RECENT_DESC = "列出最近的转录任务（含状态/标题/作者/链接），用于了解库里有什么、转录进展如何。"
_GET_STATUS_DESC = "按 job_id 查询转录任务状态。done 后调用 read 取全文（缓存命中，立即返回）。"


@dataclass(frozen=True)
class ToolResult:
    blocks: list[str]  # 依次作为 content 里的多个 text block 输出
    is_error: bool = False


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict  # JSON Schema（协议层序列化为 inputSchema）
    handler: Callable[[dict], "ToolResult"]  # 入参 = tools/call 的 arguments dict


@dataclass
class ToolContext:
    output_dir: Path  # 知识库目录（RBCP_OUTPUT_DIR，默认 ~/transcript）
    storage_factory: Callable[[], Storage]  # 每次调用新建 Storage（仿 web 层 get_storage）
    pipeline_fn: Callable[[str], dict]  # url -> fetch_single 结果 dict（吃 RBCP_PROXY）
    job_runner: Callable[[Callable[[], None]], None] = field(
        default=lambda fn: threading.Thread(target=fn, daemon=True).start()
    )  # 测试注入 lambda fn: fn()（同步内联，确定性）


def create_default_context() -> ToolContext:
    """默认接线，仿 app/web/routes.py 的 get_storage / get_pipeline_fn。"""
    output_dir = Path(os.getenv("RBCP_OUTPUT_DIR", "~/transcript")).expanduser()
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    proxy = os.getenv("RBCP_PROXY") or None

    def pipeline_fn(url: str) -> dict:
        from app.service import pipeline as pipeline_mod

        return pipeline_mod.fetch_single(url, api_key=api_key, output_dir=output_dir, proxy=proxy)

    return ToolContext(
        output_dir=output_dir,
        storage_factory=lambda: Storage(output_dir / "_index.sqlite"),
        pipeline_fn=pipeline_fn,
    )


def _json_block(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _schema(props: dict, required: list[str] | None = None) -> dict:
    """object 型 JSON Schema 的省行写法（协议层序列化为 inputSchema）。"""
    schema: dict = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


def _safe_error_detail(error: BaseException, *, max_levels: int = 5) -> str:
    """异常链的 类型: 信息 摘要，**不含 traceback/文件路径**。
    复制自 web 壳（app/web/routes.py），转正时上提 service/。"""
    parts: list[str] = []
    seen = 0
    exc: BaseException | None = error
    while exc is not None and seen < max_levels:
        msg = str(exc).strip()
        parts.append(f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__)
        exc = exc.__cause__ or exc.__context__
        seen += 1
    return "\n".join(parts)


def _run_job(job_id: int, url: str, storage: Storage, pipeline_fn: Callable[[str], dict]) -> None:
    """跑一条转录任务并落库。复制自 web 壳（app/web/routes.py），转正时上提 service/。"""
    storage.mark_running(job_id)
    logger.info("[job %s] start: %s", job_id, url)
    try:
        result = pipeline_fn(url)
        storage.mark_done(
            job_id, md_path=result["md_path"], title=result.get("title"),
            author=result.get("author"), platform=result.get("platform"),
            content_type=result.get("content_type"), usage=result.get("usage"),
        )
        logger.info("[job %s] done: %s", job_id, result["md_path"])
    except Exception as error:
        tb = traceback.format_exc()
        # error_message 存「人话」；log_excerpt 存脱敏的异常链摘要。
        # 完整 traceback 只进 stderr 日志，绝不外显。
        storage.mark_failed(
            job_id, error_message=format_error_for_user(error), log_excerpt=_safe_error_detail(error)
        )
        logger.error("[job %s] FAILED: %s\n%s", job_id, error, tb)


def _parse_frontmatter(text: str) -> dict:
    """note.md.j2 frontmatter 的手工解析（无 yaml 依赖）。

    只认首个 ---…--- 块内的 key: value 行；'  - ' 开头的列表续行
    （media_paths）忽略；没闭合 / 任意异常 → 空 dict，不让坏文件崩检索。
    """
    try:
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}
        fm: dict = {}
        for line in lines[1:]:
            if line.strip() == "---":
                return fm
            if line.startswith("  - "):
                continue
            key, sep, value = line.partition(":")
            if sep:
                fm[key.strip()] = value.strip()
        return {}  # 没找到闭合 --- → 视为解析失败
    except Exception:
        return {}


def build_tools(ctx: ToolContext) -> list[ToolDef]:
    def read(arguments: dict) -> ToolResult:
        try:
            url = clean_url(str(arguments.get("url", "")))
            detect_platform(url)
        except RbcpError as error:
            return ToolResult(blocks=[format_error_for_user(error)], is_error=True)
        force = bool(arguments.get("force", False))
        storage = ctx.storage_factory()
        key = dedup_key(url)

        # 缓存命中：done 且 md 文件还在 → 元数据 + 全文两个 block 秒回
        if not force and key is not None:
            for job_id, job_url, _title in storage.done_jobs_brief():
                if dedup_key(job_url) != key:
                    continue
                job = storage.get_job(job_id)
                if job is None:
                    continue
                md_path = job.get("md_path")
                if not md_path:
                    continue
                try:
                    markdown = Path(md_path).read_text(encoding="utf-8")
                except OSError:
                    continue  # md 文件已被删 → 视为未命中，继续往下
                meta = {"status": "ready", "job_id": job_id, "md_path": md_path}
                meta.update({k: job.get(k) for k in ("title", "author", "platform", "url")})
                return ToolResult(blocks=[_json_block(meta), markdown])

        # 进行中去重：同内容已有 pending/running 任务 → 绝不重复建任务。
        # 已知竞态（评审 P1，demo 接受）：两次 read 并发通过此扫描会各自建任务；
        # 转正时应在 DB 层加唯一约束兜底。limit=100 窗口外的积压任务也可能漏检（P2）。
        if key is not None:
            for job in storage.list_jobs(limit=100):
                if job.get("status") not in ("pending", "running"):
                    continue
                if dedup_key(job.get("url") or "") != key:
                    continue
                payload = {
                    "status": "transcribing", "job_id": job["id"], "url": job.get("url"),
                    "hint": "已有同内容任务在转录，勿重复提交；用 get_status 查询",
                }
                return ToolResult(blocks=[_json_block(payload)])

        # 冷启动：建 job 丢给 runner（默认后台线程），立即返回
        job_id = storage.create_job(url)
        ctx.job_runner(lambda: _run_job(job_id, url, storage, ctx.pipeline_fn))
        payload = {
            "status": "started", "job_id": job_id, "url": url,
            "hint": "转录已启动（约 1-5 分钟）。先做别的，稍后用 get_status 查询；"
                    "done 后再调 read 即缓存命中秒回。",
        }
        return ToolResult(blocks=[_json_block(payload)])

    def search(arguments: dict) -> ToolResult:
        query = str(arguments.get("query", ""))
        limit = int(arguments.get("limit", 8))
        words = [w.lower() for w in query.split()]
        if not words:
            return ToolResult(blocks=["检索词为空：请提供至少一个关键词。"], is_error=True)
        matches: list[dict] = []
        for path in sorted(ctx.output_dir.rglob("*.md")):
            try:
                if path.stat().st_size > _MAX_SEARCH_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            lowered = text.lower()
            counts = [lowered.count(w) for w in words]
            if not all(counts):
                continue  # 多词 AND：全部命中才算
            fm = _parse_frontmatter(text)
            pos = lowered.find(words[0])
            start = max(0, pos - _SNIPPET_RADIUS)
            snippet = " ".join(text[start : pos + len(words[0]) + _SNIPPET_RADIUS].split())
            matches.append({
                "title": fm.get("title") or path.stem, "author": fm.get("author"),
                "platform": fm.get("platform"), "url": fm.get("url"), "path": str(path),
                "snippet": snippet, "score": sum(counts),
            })
        matches.sort(key=lambda r: r["score"], reverse=True)
        payload = {"query": query, "total_matched": len(matches), "results": matches[:limit]}
        return ToolResult(blocks=[_json_block(payload)])

    def list_recent(arguments: dict) -> ToolResult:
        limit = int(arguments.get("limit", 10))
        storage = ctx.storage_factory()
        fields = ("status", "title", "author", "platform", "url", "created_at")
        jobs = [
            {"job_id": job["id"], **{k: job.get(k) for k in fields}}
            for job in storage.list_jobs(limit=limit)
        ]
        payload = {"jobs": jobs, "library_total_cost_yuan": storage.total_cost_yuan()}
        return ToolResult(blocks=[_json_block(payload)])

    def get_status(arguments: dict) -> ToolResult:
        raw_id = arguments.get("job_id")
        try:
            job_id = int(raw_id)
        except (TypeError, ValueError):
            return ToolResult(blocks=[f"任务不存在：job_id={raw_id}"], is_error=True)
        job = ctx.storage_factory().get_job(job_id)
        if job is None:
            return ToolResult(blocks=[f"任务不存在：job_id={job_id}"], is_error=True)
        # log_excerpt 本就脱敏（不含 traceback/路径），可安全外显
        fields = ("status", "title", "url", "error_message", "log_excerpt")
        payload = {"job_id": job["id"], **{k: job.get(k) for k in fields}}
        if job.get("status") == "done":
            payload["hint"] = "调用 read(url) 取全文"
        return ToolResult(blocks=[_json_block(payload)])

    return [
        ToolDef(
            name="read", description=_READ_DESC, handler=read,
            input_schema=_schema(
                {"url": {"type": "string"}, "force": {"type": "boolean", "default": False}}, ["url"]
            ),
        ),
        ToolDef(
            name="search", description=_SEARCH_DESC, handler=search,
            input_schema=_schema(
                {"query": {"type": "string"}, "limit": {"type": "integer", "default": 8}}, ["query"]
            ),
        ),
        ToolDef(
            name="list_recent", description=_LIST_RECENT_DESC, handler=list_recent,
            input_schema=_schema({"limit": {"type": "integer", "default": 10}}),
        ),
        ToolDef(
            name="get_status", description=_GET_STATUS_DESC, handler=get_status,
            input_schema=_schema({"job_id": {"type": "integer"}}, ["job_id"]),
        ),
    ]
