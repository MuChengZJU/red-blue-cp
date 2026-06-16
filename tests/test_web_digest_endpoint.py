"""Task 1.3 · GET /api/jobs/{job_id}/digest 两层信封端点测试（全程脱网，FakeProvider）。"""

from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.extract.contracts import Segment, text_fingerprint
from app.web import artifacts, digest_cache
from app.web.routes import app, get_digest_provider
from tests.test_cli_digest_0_6 import _FakeProvider as FakeProvider


@pytest.fixture
def seeded_job(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "_CACHE_DIR", tmp_path / "extract")
    monkeypatch.setattr(digest_cache, "_CACHE_DIR", tmp_path / "digest")
    canonical = "你好世界\n这是一个测试。"
    segs = (
        Segment("你好世界", None, 0.0, 2.5, 0, 4),
        Segment("这是一个测试。", None, 2.5, 5.0, 5, 11),
    )
    artifacts.save_extract(42, {
        "canonical_text": canonical,
        "text_sha256": text_fingerprint(canonical),
        "segments": [dataclasses.asdict(s) for s in segs],
    })
    app.dependency_overrides[get_digest_provider] = lambda: FakeProvider()
    yield 42
    app.dependency_overrides.clear()


def test_digest_endpoint_nested_envelope(seeded_job):
    r = TestClient(app).get(f"/api/jobs/{seeded_job}/digest")
    assert r.status_code == 200
    body = r.json()
    # 两层信封
    assert "canonical_text" in body["extract"]
    assert body["extract"]["text_sha256"]
    assert "highlights" in body["digest"]
    assert "cards" in body["digest"]
    assert "outline" in body["digest"]


def test_digest_endpoint_cache_hit_second_call(seeded_job):
    c = TestClient(app)
    first = c.get(f"/api/jobs/{seeded_job}/digest").json()
    second = c.get(f"/api/jobs/{seeded_job}/digest").json()
    assert first == second
    assert digest_cache.load(seeded_job) is not None


def test_digest_missing_artifacts_returns_409(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "_CACHE_DIR", tmp_path / "extract")
    monkeypatch.setattr(digest_cache, "_CACHE_DIR", tmp_path / "digest")
    r = TestClient(app).get("/api/jobs/999/digest")
    assert r.status_code == 409
    assert r.json()["detail"] == "need_retranscribe"

