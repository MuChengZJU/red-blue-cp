"""Task 1.6 · DELETE /api/jobs/{job_id} 单篇删除端点测试。

删 DB 行 + 删 .md 文件 + 清 artifacts/digest 缓存，走 job_id 不走路径。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.extract.storage import Storage
from app.web import artifacts, digest_cache
from app.web.routes import app, get_storage


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "test.db")


@pytest.fixture
def client(storage):
    app.dependency_overrides[get_storage] = lambda: storage
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── 核心场景：删 job 同时清 .md + 缓存 ───────────────────────


def test_delete_job_removes_row_md_and_cache(
    tmp_path, monkeypatch, storage, client,
):
    """建一个 done job（带 .md + artifacts + digest 缓存），DELETE 后全部清掉。"""
    monkeypatch.setattr(artifacts, "_CACHE_DIR", tmp_path / "extract")
    monkeypatch.setattr(digest_cache, "_CACHE_DIR", tmp_path / "digest")

    # 建 job → pending → running → done（带 md_path）
    job_id = storage.create_job("https://www.bilibili.com/video/BV1test")
    storage.mark_running(job_id)
    md_file = tmp_path / "sample.md"
    md_file.write_text("# hello", encoding="utf-8")
    storage.mark_done(job_id, md_path=str(md_file), title="T", author="A")

    # 落缓存
    artifacts.save_extract(job_id, {"canonical_text": "hello", "text_sha256": "abc", "segments": None})
    digest_cache.save(job_id, {"extract": {}, "digest": {}})

    # 确认前置条件
    assert storage.get_job(job_id) is not None
    assert md_file.exists()
    assert (artifacts._CACHE_DIR / f"{job_id}.json").exists()
    assert (digest_cache._CACHE_DIR / f"{job_id}.json").exists()

    # DELETE
    r = client.delete(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json() == {"deleted": job_id}

    # 删后：DB 行没了
    assert storage.get_job(job_id) is None
    assert all(j["id"] != job_id for j in client.get("/api/jobs").json())
    # .md 文件没了
    assert not md_file.exists()
    # 缓存没了
    assert not (artifacts._CACHE_DIR / f"{job_id}.json").exists()
    assert not (digest_cache._CACHE_DIR / f"{job_id}.json").exists()


# ── 404：不存在的 job ─────────────────────────────────────────


def test_delete_nonexistent_returns_404(client):
    assert client.delete("/api/jobs/99999").status_code == 404


# ── 安全：md 文件已手动删掉也不报错 ──────────────────────────


def test_delete_job_md_already_missing(tmp_path, monkeypatch, storage, client):
    """md 文件已被手动删掉，DELETE 仍然成功（不因 FileNotFoundError 炸）。"""
    monkeypatch.setattr(artifacts, "_CACHE_DIR", tmp_path / "extract")
    monkeypatch.setattr(digest_cache, "_CACHE_DIR", tmp_path / "digest")

    job_id = storage.create_job("https://www.bilibili.com/video/BV1x")
    storage.mark_running(job_id)
    storage.mark_done(job_id, md_path=str(tmp_path / "gone.md"), title="X")

    r = client.delete(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    assert storage.get_job(job_id) is None


# ── 路径穿越红线：DELETE 参数只能是 int job_id ────────────────


def test_delete_string_id_rejected(client):
    """路径参数不是 int → FastAPI 直接 422，绝不接受任意字符串做路径。"""
    assert client.delete("/api/jobs/abc").status_code == 422


def test_delete_dotdot_rejected(client):
    assert client.delete("/api/jobs/..%2F..%2Fetc%2Fpasswd").status_code in (404, 422)
