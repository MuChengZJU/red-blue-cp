"""封面缩略图字节缓存（速览/列表封面）。

与 artifacts.py / digest_cache.py 同构：platformdirs user_cache_dir 下 thumbnails/
子目录，原子写（临时文件 + os.replace）。缓存原始图片字节 + content_type。

红线#5：绝不能写进 ~/transcript（知识库目录只放 Markdown + _index.sqlite）。
红线#7：原子写（临时文件 + os.replace）。

content_type 与字节分两个文件存：{job_id}.bin（图片字节）+ {job_id}.type（媒体类型，
纯文本一行）。load 两者都齐才算命中，缺任一返回 None。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import platformdirs

from app.config import APP_NAME

# App 缓存目录（platformdirs 管理），子目录 thumbnails/。
# 绝不用 ~/transcript。
_CACHE_DIR = Path(platformdirs.user_cache_dir(APP_NAME)) / "thumbnails"

_DEFAULT_CONTENT_TYPE = "image/jpeg"


def _data_path(job_id: int) -> Path:
    return _CACHE_DIR / f"{job_id}.bin"


def _type_path(job_id: int) -> Path:
    return _CACHE_DIR / f"{job_id}.type"


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    """原子写 bytes（临时文件 + os.replace），失败清理临时文件。"""
    fd, tmp = tempfile.mkstemp(dir=str(_CACHE_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save(job_id: int, data: bytes, content_type: str) -> None:
    """原子写入图片字节 + content_type sidecar。"""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # 先写 type，再写 data：load 以 data 文件存在为命中判据，保证命中时 type 已就位。
    _atomic_write_bytes(_type_path(job_id), (content_type or _DEFAULT_CONTENT_TYPE).encode("utf-8"))
    _atomic_write_bytes(_data_path(job_id), data)


def load(job_id: int) -> tuple[bytes, str] | None:
    """读取缓存的图片字节 + content_type。任一文件不存在返回 None（不抛异常）。"""
    data_path = _data_path(job_id)
    if not data_path.is_file():
        return None
    try:
        data = data_path.read_bytes()
    except OSError:
        return None
    try:
        content_type = _type_path(job_id).read_text(encoding="utf-8").strip()
    except OSError:
        content_type = ""
    return data, content_type or _DEFAULT_CONTENT_TYPE


def delete(job_id: int) -> None:
    """删除缩略图缓存（字节 + type sidecar），不存在则忽略。"""
    for path in (_data_path(job_id), _type_path(job_id)):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
