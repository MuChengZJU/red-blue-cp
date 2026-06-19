"""测试：批量成功分支也应持久化 artifacts（Task 1.4）。

验证 run_batch 成功后，artifacts.load_extract 能拿到
fetch_single 返回的 canonical_text / text_sha256 / segments。
"""

from __future__ import annotations

import json

import pytest

from app.extract import batch as batch_mod
from app.extract.contracts import Segment
from app.extract.batch import run_batch
from app.web import artifacts


# -- helpers --

def _envelope(notes, *, complete=True, user_id="u999"):
    return {
        "schema_version": 1,
        "source": "xhs_user_posted",
        "user_id": user_id,
        "user_name": "博主",
        "captured_at": "2026-06-05T12:00:00+08:00",
        "complete": complete,
        "count": len(notes),
        "notes": notes,
    }


def _note(note_id, **extra):
    base = {
        "note_id": note_id,
        "title": f"标题{note_id}",
        "type": "normal",
        "xsec_token": "tok",
        "url": f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token=tok",
    }
    base.update(extra)
    return base


# -- test --


class TestBatchArtifactsPersistence:
    """批量成功后 artifacts 应落盘，速览可用。"""

    def test_single_item_batch_persists_artifacts(
        self, tmp_path, monkeypatch
    ):
        # monkeypatch _CACHE_DIR 到 tmp 以免写真缓存
        monkeypatch.setattr(artifacts, "_CACHE_DIR", tmp_path / "cache")

        fake_result = {
            "md_path": str(tmp_path / "kb" / "n1.md"),
            "title": "批量标题",
            "canonical_text": "批量正文内容 hello",
            "text_sha256": "aaa111bbb222",
            "segments": None,
        }
        monkeypatch.setattr(
            batch_mod, "fetch_single", lambda url, **kw: fake_result,
        )
        # 无代理，跳过出口探测
        monkeypatch.setattr(batch_mod, "probe_exit_ip", lambda p: "1.1.1.1")

        envelope = _envelope([_note("n1")])
        p = tmp_path / "notes.json"
        p.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")

        output_dir = tmp_path / "kb"
        summary = run_batch(
            p,
            api_key="test-key",
            output_dir=output_dir,
            proxy=None,
        )
        assert summary["ok"] == 1

        # 拿到 job_id
        from app.extract.storage import Storage

        st = Storage(output_dir / "_index.sqlite")
        items = st.list_batch_items(summary["batch_id"])
        assert len(items) == 1
        job_id = items[0]["job_id"]

        # 核心断言：artifacts 落盘了
        cached = artifacts.load_extract(job_id)
        assert cached["canonical_text"] == "批量正文内容 hello"
        assert cached["text_sha256"] == "aaa111bbb222"

    def test_batch_with_segments_persists_artifacts(
        self, tmp_path, monkeypatch
    ):
        """segments 有值时也能正确序列化落盘。"""
        monkeypatch.setattr(artifacts, "_CACHE_DIR", tmp_path / "cache")

        fake_result = {
            "md_path": str(tmp_path / "kb" / "n1.md"),
            "title": "带 segments",
            "canonical_text": "全文",
            "text_sha256": "sha_xxx",
            "segments": [
                Segment(text="hello", speaker_id=None,
                        start_sec=0.0, end_sec=1.0,
                        char_start=0, char_end=5),
                Segment(text="world", speaker_id=None,
                        start_sec=1.0, end_sec=2.0,
                        char_start=5, char_end=10),
            ],
        }
        monkeypatch.setattr(
            batch_mod, "fetch_single", lambda url, **kw: fake_result,
        )

        envelope = _envelope([_note("n1")])
        p = tmp_path / "notes.json"
        p.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")

        output_dir = tmp_path / "kb"
        summary = run_batch(
            p,
            api_key="test-key",
            output_dir=output_dir,
            proxy=None,
        )
        assert summary["ok"] == 1

        from app.extract.storage import Storage

        st = Storage(output_dir / "_index.sqlite")
        items = st.list_batch_items(summary["batch_id"])
        job_id = items[0]["job_id"]

        cached = artifacts.load_extract(job_id)
        assert cached["canonical_text"] == "全文"
        assert len(cached["segments"]) == 2
        assert cached["segments"][0]["text"] == "hello"
