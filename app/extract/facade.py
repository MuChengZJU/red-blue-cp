"""0.6 §B · rbcp-extract 公共门面（动词的稳定签名）。

CLI / Desktop / Digest 调用 Extract 一律走这层，不直接调 extractor/fetcher/discover 内部。
本文件在契约锁定阶段只锁**签名**；函数体是 NotImplementedError 桩，M6b 接到现有 service 实现
（``pipeline.fetch_single`` 整理为返回 ``ExtractResult`` 等）。重活的 import 放函数体内（lazy），
保持本模块 import 轻、不引入循环依赖。
"""

from __future__ import annotations

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
    """单条 URL → 结构化 ExtractResult（现 pipeline.fetch_single 的整理版，返回结构而非裸 dict）。"""
    raise NotImplementedError("M6b: 接 pipeline.fetch_single，返回 ExtractResult")


def search(query: str, *, output_dir: Path, limit: int = 8) -> list[SearchHit]:
    """本地知识库全文检索（原 MCP 工具里的检索，上提为门面一等公民）。"""
    raise NotImplementedError("M6b: 本地全文检索 → list[SearchHit]")


def list_blogger(url: str, *, proxy: str | None = None) -> list[PostBrief]:
    """列博主全量笔记清单（现 discover，不下载）。"""
    raise NotImplementedError("M6b: 接 discover，返回 list[PostBrief]")


def run_batch(items: list[str] | Path, *, output_dir: Path, **opts: object) -> BatchResult:
    """批量抓取（现 batch.run_batch 的整理版）。"""
    raise NotImplementedError("M6b: 接 batch.run_batch")


class Jobs:
    """任务/状态门面（Storage 的薄包装；GUI/CLI 看进度用）。M6b 接 Storage。"""

    def create(self, url: str) -> int:
        raise NotImplementedError("M6b")

    def get(self, job_id: int) -> dict | None:
        raise NotImplementedError("M6b")

    def list(self, limit: int = 20) -> list[dict]:
        raise NotImplementedError("M6b")

    def total_cost_yuan(self) -> float:
        raise NotImplementedError("M6b")
