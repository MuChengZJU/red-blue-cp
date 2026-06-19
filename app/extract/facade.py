"""0.6 §B · rbcp-extract 公共门面（动词的稳定签名）。

CLI / Desktop / Digest 调用 Extract 一律走这层，不直接调 extractor/fetcher/discover 内部。
本层只做**薄包装**：把现有 service 实现（pipeline/extractor/discover/batch/storage）整理成
契约里的稳定返回形状（ExtractResult / PostBrief / BatchResult / SearchHit / Jobs）。
重活的 import 放函数体内（lazy），保持本模块 import 轻、不引入循环依赖。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from app.extract.contracts import BatchResult, ExtractResult, PostBrief, SearchHit

__all__ = ["extract", "search", "list_blogger", "run_batch", "Jobs", "BatchResult"]


def extract(
    url: str,
    *,
    output_dir: Path,
    comments: bool = False,
    text_only: bool = False,
    save_media: bool = False,
    proxy: str | None = None,
) -> ExtractResult:
    """单条 URL → 结构化 ExtractResult（canonical text + segments），并落盘 .md。

    包装 extract_url（拿结构化结果）+ render_and_write（落盘），返回带 md_path 的 ExtractResult。
    评论默认不抓；comments=True 时抓评论并写独立 .md（路径进 metadata["comments_path"]）。
    """
    from app.extract.extractor import extract_url
    from app.extract.markdown import render_and_write
    from app.extract.pipeline import _provider_from_env, build_proxies

    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    proxies = build_proxies(proxy)
    provider = _provider_from_env(api_key, proxies=proxies)
    result = extract_url(
        url, provider, text_only=text_only, save_media=save_media, proxies=proxies
    )
    md_path = render_and_write(result, output_dir=output_dir)

    metadata = dict(result.metadata)
    if comments:
        from app.extract import discover
        from app.extract.comments import write_comments_md
        from app.extract.discover import note_id_from_url

        note_comments = asyncio.run(discover.discover_comments(url))
        comments_path = write_comments_md(
            note_id_from_url(url), note_comments, output_dir, note_title=result.title
        )
        metadata["comments_path"] = str(comments_path)
        metadata["comment_count"] = len(note_comments)

    # ExtractResult 是 frozen dataclass：md_path / 补充 metadata 用 replace 回填，不原地改。
    import dataclasses

    return dataclasses.replace(result, md_path=str(md_path), metadata=metadata)


def search(query: str, *, output_dir: Path, limit: int = 8) -> list[SearchHit]:
    """本地知识库标题/路径扫描检索（无全文索引 → 最简子串匹配，命中即返）。

    0.6 暂不引入全文检索（FTS5 是 P2 红线禁项）。这里扫 output_dir 下 .md 文件名/路径，
    对 query 做不区分大小写的子串匹配，按命中位置粗排，返回前 limit 条 SearchHit。
    正文/frontmatter 解析留待未来需求再补，现在 snippet 给文件名、score 给 1.0/位置反比。
    """
    output_dir = Path(output_dir)
    if not output_dir.exists():
        return []
    q = query.strip().lower()
    hits: list[SearchHit] = []
    for path in sorted(output_dir.rglob("*.md")):
        name = path.name
        if name.startswith("_"):
            continue  # 跳过 _index 等内部文件
        idx = name.lower().find(q) if q else 0
        if q and idx < 0:
            continue
        # 命中越靠前分越高（粗排）；空 query 全收，score=1.0
        score = 1.0 if not q else 1.0 / (1.0 + idx)
        hits.append(SearchHit(
            title=path.stem,
            author="",
            platform="",
            url="",
            path=str(path),
            snippet=name,
            score=score,
        ))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def list_blogger(url: str, *, proxy: str | None = None) -> list[PostBrief]:
    """列博主全量笔记清单（现 discover，不下载）。撞风控/半份清单返回已抓到的部分。"""
    from app.extract import discover

    listing = asyncio.run(discover.discover_user_posts(url))
    briefs: list[PostBrief] = []
    for note in listing.get("notes", []):
        note_id = note["note_id"]
        token = note.get("xsec_token") or ""
        note_url = (
            f"https://www.xiaohongshu.com/explore/{note_id}"
            f"?xsec_token={token}&xsec_source=pc_user"
        )
        briefs.append(PostBrief(note_id=note_id, url=note_url, title=note.get("title")))
    return briefs


def run_batch(items: list[str] | Path, *, output_dir: Path, **opts: object) -> BatchResult:
    """批量抓取（现 batch.run_batch 的整理版）。返回锁定计数语义的 BatchResult。

    items：插件导出的 notes.json 路径（Path）或已解析的 envelope dict / 清单。
    透传 comments/sub/save_media/text_only/proxy/allow_partial 等 opts 给底层。
    """
    from app.extract.batch import run_batch as _run_batch

    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    summary = _run_batch(
        items,  # type: ignore[arg-type]
        api_key=api_key,
        output_dir=Path(output_dir),
        **opts,  # type: ignore[arg-type]
    )
    return BatchResult(
        ok=int(summary.get("ok", 0)),
        failed=int(summary.get("failed", 0)),
        skipped=int(summary.get("skipped", 0)),
    )


class Jobs:
    """任务/状态门面（Storage 的薄包装；GUI/CLI 看进度用）。

    db 默认落在 output_dir/_index.sqlite（红线#4 唯一允许写进知识库目录的非 .md 文件）。
    """

    def __init__(self, output_dir: Path | None = None) -> None:
        if output_dir is None:
            from app.config import resolve_output_dir
            output_dir = resolve_output_dir()
        self._db_path = Path(output_dir) / "_index.sqlite"

    def _storage(self):
        from app.extract.storage import Storage

        return Storage(self._db_path)

    def create(self, url: str) -> int:
        return self._storage().create_job(url)

    def get(self, job_id: int) -> dict | None:
        return self._storage().get_job(job_id)

    def list(self, limit: int = 20) -> list[dict]:
        return self._storage().list_jobs(limit=limit)

    def total_cost_yuan(self) -> float:
        return self._storage().total_cost_yuan()
