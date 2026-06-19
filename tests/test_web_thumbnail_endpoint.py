"""GET /api/jobs/{job_id}/thumbnail 封面缩略图端点测试（全程脱网，mock requests）。

契约（前端已依赖，路径/语义不可变）：
- 路径：/api/jobs/{job_id}/thumbnail（int job_id，挂 authed api router）
- 命中：200 + 图片字节 + media_type
- 无缩略图（无 job / 无 artifact / 无 cover_url / 上游失败）：404，绝不 500
- 缓存命中第二次不再发网络请求
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.extract.storage import Storage
from app.web import artifacts, thumbnail_cache
from app.web.routes import app, get_storage
import app.web.routes as routes


_FAKE_JPEG = b"\xff\xd8\xff\xe0FAKEJPEGBYTES\xff\xd9"


class _FakeResponse:
    def __init__(self, status_code: int, content: bytes, content_type: str = "image/jpeg"):
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type}


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "test.db")


@pytest.fixture
def client(tmp_path, monkeypatch, storage):
    # 隔离缓存目录（artifacts + thumbnail），绝不碰真 user_cache_dir
    monkeypatch.setattr(artifacts, "_CACHE_DIR", tmp_path / "extract")
    monkeypatch.setattr(thumbnail_cache, "_CACHE_DIR", tmp_path / "thumbnails")
    app.dependency_overrides[get_storage] = lambda: storage
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_job(storage, *, cover_url, platform="bilibili"):
    """建一个 done job + artifact（带/不带 cover_url）。返回 job_id。"""
    job_id = storage.create_job("https://www.bilibili.com/video/BV1test")
    storage.mark_running(job_id)
    storage.mark_done(job_id, md_path="/tmp/x.md", title="T", author="A", platform=platform)
    artifacts.save_extract(job_id, {
        "canonical_text": "hello",
        "text_sha256": "abc",
        "segments": None,
        "readable_text": "hello",
        "cover_url": cover_url,
    })
    return job_id


# ── (a) 有 cover_url + 上游 200 → 200 字节 + 落缓存 ──────────────


def test_thumbnail_fetches_and_caches(monkeypatch, storage, client):
    job_id = _seed_job(storage, cover_url="https://i.bili.com/cover.jpg")

    calls = {"n": 0}

    def fake_get(url, **kwargs):
        calls["n"] += 1
        return _FakeResponse(200, _FAKE_JPEG, "image/jpeg")

    monkeypatch.setattr(routes.requests, "get", fake_get)

    r = client.get(f"/api/jobs/{job_id}/thumbnail")
    assert r.status_code == 200
    assert r.content == _FAKE_JPEG
    assert r.headers["content-type"] == "image/jpeg"
    assert "max-age=86400" in r.headers.get("cache-control", "")
    assert calls["n"] == 1
    # 落了缓存
    cached = thumbnail_cache.load(job_id)
    assert cached is not None
    assert cached[0] == _FAKE_JPEG
    assert cached[1] == "image/jpeg"


# ── (b) 无 cover_url / 无 artifact → 404 ─────────────────────────


def test_thumbnail_no_cover_url_returns_404(monkeypatch, storage, client):
    job_id = _seed_job(storage, cover_url=None)

    def fail_get(url, **kwargs):  # pragma: no cover - 不该被调用
        raise AssertionError("无 cover_url 不应发起网络请求")

    monkeypatch.setattr(routes.requests, "get", fail_get)

    r = client.get(f"/api/jobs/{job_id}/thumbnail")
    assert r.status_code == 404


def test_thumbnail_no_artifact_returns_404(monkeypatch, storage, client):
    """job 存在但没有 artifact sidecar → 404（无缩略图）。"""
    job_id = storage.create_job("https://www.bilibili.com/video/BV1none")
    storage.mark_running(job_id)
    storage.mark_done(job_id, md_path="/tmp/x.md", title="T", platform="bilibili")

    def fail_get(url, **kwargs):  # pragma: no cover
        raise AssertionError("无 artifact 不应发起网络请求")

    monkeypatch.setattr(routes.requests, "get", fail_get)

    r = client.get(f"/api/jobs/{job_id}/thumbnail")
    assert r.status_code == 404


def test_thumbnail_no_job_returns_404(monkeypatch, client):
    def fail_get(url, **kwargs):  # pragma: no cover
        raise AssertionError("无 job 不应发起网络请求")

    monkeypatch.setattr(routes.requests, "get", fail_get)

    r = client.get("/api/jobs/999999/thumbnail")
    assert r.status_code == 404


# ── (c) 第二次请求命中缓存，不再发网络请求 ──────────────────────


def test_thumbnail_cache_hit_no_second_network_call(monkeypatch, storage, client):
    job_id = _seed_job(storage, cover_url="https://i.bili.com/cover.jpg")

    calls = {"n": 0}

    def fake_get(url, **kwargs):
        calls["n"] += 1
        return _FakeResponse(200, _FAKE_JPEG, "image/png")

    monkeypatch.setattr(routes.requests, "get", fake_get)

    first = client.get(f"/api/jobs/{job_id}/thumbnail")
    second = client.get(f"/api/jobs/{job_id}/thumbnail")
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.content == _FAKE_JPEG
    assert second.headers["content-type"] == "image/png"  # 缓存回带 content_type
    # 只发起一次网络请求
    assert calls["n"] == 1


# ── (d) 上游非 200 → 404（绝不 500） ────────────────────────────


def test_thumbnail_upstream_non_200_returns_404(monkeypatch, storage, client):
    job_id = _seed_job(storage, cover_url="https://i.bili.com/cover.jpg")

    def fake_get(url, **kwargs):
        return _FakeResponse(403, b"forbidden", "text/html")

    monkeypatch.setattr(routes.requests, "get", fake_get)

    r = client.get(f"/api/jobs/{job_id}/thumbnail")
    assert r.status_code == 404
    # 失败不落缓存
    assert thumbnail_cache.load(job_id) is None


def test_thumbnail_upstream_raises_returns_404(monkeypatch, storage, client):
    """网络层抛异常（超时/连接错误）也降级 404，绝不 500。"""
    import requests as _requests

    job_id = _seed_job(storage, cover_url="https://i.bili.com/cover.jpg")

    def fake_get(url, **kwargs):
        raise _requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(routes.requests, "get", fake_get)

    r = client.get(f"/api/jobs/{job_id}/thumbnail")
    assert r.status_code == 404


# ── 红线#11：小红书封面必须带 referer ───────────────────────────


def test_thumbnail_xhs_sends_referer(monkeypatch, storage, client):
    job_id = _seed_job(
        storage, cover_url="https://sns-img.xhscdn.com/cover.jpg", platform="xiaohongshu"
    )

    captured = {}

    def fake_get(url, **kwargs):
        captured["headers"] = kwargs.get("headers") or {}
        return _FakeResponse(200, _FAKE_JPEG, "image/jpeg")

    monkeypatch.setattr(routes.requests, "get", fake_get)

    r = client.get(f"/api/jobs/{job_id}/thumbnail")
    assert r.status_code == 200
    assert captured["headers"].get("Referer") == "https://www.xiaohongshu.com/"
