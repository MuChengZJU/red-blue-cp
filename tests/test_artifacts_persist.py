"""app.web.artifacts 持久化测试（TDD Step 1）。

验证 on_job_success 将 canonical_text / text_sha256 / segments 落到 App 缓存，
而不触碰 ~/transcript（红线#5）。
"""

from __future__ import annotations

import pytest

from app.extract.contracts import ExtractResult, Segment, text_fingerprint
from app.web import artifacts


@pytest.fixture()
def fake_extract_result() -> ExtractResult:
    """最小 ExtractResult，含 segments（ASR 句级）。"""
    canonical = "你好世界\n这是一个测试。"
    return ExtractResult(
        platform="bilibili",
        content_type="video",
        title="测试视频",
        author="测试作者",
        author_id=None,
        published_at=None,
        url="https://www.bilibili.com/video/BV_test",
        text=canonical,
        readable_text=canonical,
        text_sha256=text_fingerprint(canonical),
        metadata={},
        segments=(
            Segment(
                text="你好世界",
                speaker_id=None,
                start_sec=0.0,
                end_sec=2.5,
                char_start=0,
                char_end=4,
            ),
            Segment(
                text="这是一个测试。",
                speaker_id=None,
                start_sec=2.5,
                end_sec=5.0,
                char_start=5,
                char_end=11,
            ),
        ),
    )


def test_on_job_success_persists_canonical_and_segments(
    tmp_path, monkeypatch, fake_extract_result
):
    monkeypatch.setattr(artifacts, "_CACHE_DIR", tmp_path)  # App 缓存，非 ~/transcript
    artifacts.on_job_success(job_id=7, result=fake_extract_result)
    art = artifacts.load_extract(7)
    assert art["canonical_text"] == fake_extract_result.text
    assert art["text_sha256"] == fake_extract_result.text_sha256
    assert len(art["segments"]) == len(fake_extract_result.segments)
    # segments 序列化后是 dict 列表
    assert art["segments"][0]["text"] == "你好世界"
    assert art["segments"][0]["char_start"] == 0
