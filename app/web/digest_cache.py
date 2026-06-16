"""digest 产物缓存（两层信封 JSON）。

与 artifacts.py 同构：platformdirs user_cache_dir 下 digest/ 子目录，
原子写（临时文件 + os.replace），load 不存在返回 None（不抛异常）。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import platformdirs

from app.config import APP_NAME

# App 缓存目录（platformdirs 管理），子目录 digest/。
_CACHE_DIR = Path(platformdirs.user_cache_dir(APP_NAME)) / "digest"


def _cache_path(job_id: int) -> Path:
    return _CACHE_DIR / f"{job_id}.json"


def save(job_id: int, envelope: dict[str, Any]) -> None:
    """原子写入 JSON sidecar（临时文件 + os.replace）。"""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = _cache_path(job_id)
    fd, tmp = tempfile.mkstemp(dir=_CACHE_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(envelope, f, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load(job_id: int) -> dict[str, Any] | None:
    """读取缓存的 digest JSON。文件不存在返回 None。"""
    path = _cache_path(job_id)
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)

