"""转录产物 App 缓存（速览数据地基）。

将 canonical_text / text_sha256 / segments 持久化到 platformdirs 的 user_cache_dir，
供后续速览①③和 digest 锚定消费。

红线#5：绝不能写进 ~/transcript（知识库目录只放 Markdown + _index.sqlite）。
红线#7：原子写（临时文件 + os.replace）。
"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import platformdirs

from app.config import APP_NAME

# App 缓存目录（platformdirs 管理），子目录 extract/。
# 绝不用 ~/transcript。
_CACHE_DIR = Path(platformdirs.user_cache_dir(APP_NAME)) / "extract"


def _cache_path(job_id: int) -> Path:
    return _CACHE_DIR / f"{job_id}.json"


def save_extract(job_id: int, data: dict[str, Any]) -> None:
    """原子写入 JSON sidecar（临时文件 + os.replace）。"""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = _cache_path(job_id)
    fd, tmp = tempfile.mkstemp(dir=_CACHE_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_extract(job_id: int) -> dict[str, Any]:
    """读取缓存的 JSON sidecar。文件不存在则抛 FileNotFoundError。"""
    path = _cache_path(job_id)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def delete(job_id: int) -> None:
    """删除 artifacts 缓存文件，不存在则忽略。"""
    try:
        _cache_path(job_id).unlink()
    except FileNotFoundError:
        pass


def _serialize_segments(segments: Any) -> list[dict[str, Any]] | None:
    """将 Segment dataclass 序列化为 list[dict]。None -> None。"""
    if segments is None:
        return None
    return [dataclasses.asdict(seg) for seg in segments]


def _get_field(obj: Any, dict_key: str, attr_name: str) -> Any:
    """兼容 dict（_run_job 传入）和 ExtractResult（测试直接传入）。"""
    if isinstance(obj, dict):
        return obj.get(dict_key)
    return getattr(obj, attr_name, None)


def on_job_success(job_id: int, result: Any) -> None:
    """转录成功后，从 pipeline dict 或 ExtractResult 提取关键字段并落盘。"""
    canonical_text = _get_field(result, "canonical_text", "text")
    text_sha256 = _get_field(result, "text_sha256", "text_sha256")
    segments = _get_field(result, "segments", "segments")
    readable_text = _get_field(result, "readable_text", "readable_text")
    cover_url = _get_field(result, "cover_url", "cover_url")
    if canonical_text is None and text_sha256 is None:
        return  # mock 环境下无实际数据，跳过
    data = {
        "canonical_text": canonical_text,
        "text_sha256": text_sha256,
        "segments": _serialize_segments(segments),
        "readable_text": readable_text,
        "cover_url": cover_url,
    }
    save_extract(job_id, data)
