"""service/batch.py 测试（M4c 博主批量流）。

覆盖：schema 校验 / 必填字段 / 半份拒绝 / 空清单 / 出口探测 /
断点续传 / token 过期跳过 / 通用失败兜底 / 汇总。

策略：probe_exit_ip、fetch_single 都 mock（避免真网络/烧 API），
Storage 用 tmp_path 下真 SQLite 验证断点状态真写入。
"""

from __future__ import annotations

import json

import pytest

from app.extract import batch as batch_mod
from app.extract.batch import run_batch
from app.extract.errors import AuthError, ConfigError, NetworkError
from app.extract.storage import Storage


# ── fixtures ────────────────────────────────────────────────────


def _envelope(notes, *, schema_version=1, complete=True, user_id="u123"):
    return {
        "schema_version": schema_version,
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


@pytest.fixture
def write_notes(tmp_path):
    def _write(envelope, name="notes.json"):
        p = tmp_path / name
        p.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
        return p

    return _write


@pytest.fixture
def run_kwargs(tmp_path):
    """默认调用参数：无代理（跳过出口探测），output_dir 指向 tmp。"""
    return {
        "api_key": "test-key",
        "output_dir": tmp_path / "kb",
        "proxy": None,
    }


@pytest.fixture
def patch_probe(monkeypatch):
    """默认让出口探测返回 (直连=1.1.1.1, 代理=2.2.2.2)，即代理生效。"""
    calls = {"args": []}

    def fake_probe(proxies):
        calls["args"].append(proxies)
        return "2.2.2.2" if proxies else "1.1.1.1"

    monkeypatch.setattr(batch_mod, "probe_exit_ip", fake_probe)
    return calls


# ── schema / 必填字段校验 ────────────────────────────────────────


class TestSchemaValidation:

    def test_schema_version_mismatch_rejected(self, write_notes, run_kwargs):
        p = write_notes(_envelope([_note("n1")], schema_version=2))
        with pytest.raises(ConfigError):
            run_batch(p, **run_kwargs)

    def test_missing_schema_version_rejected(self, write_notes, run_kwargs, tmp_path):
        env = _envelope([_note("n1")])
        del env["schema_version"]
        p = tmp_path / "x.json"
        p.write_text(json.dumps(env), encoding="utf-8")
        with pytest.raises(ConfigError):
            run_batch(p, **run_kwargs)

    def test_missing_note_url_rejected(self, write_notes, run_kwargs):
        bad = _note("n1")
        del bad["url"]
        p = write_notes(_envelope([bad]))
        with pytest.raises(ConfigError):
            run_batch(p, **run_kwargs)

    def test_missing_note_id_rejected(self, write_notes, run_kwargs):
        bad = _note("n1")
        del bad["note_id"]
        p = write_notes(_envelope([bad]))
        with pytest.raises(ConfigError):
            run_batch(p, **run_kwargs)

    def test_file_not_found_rejected(self, run_kwargs, tmp_path):
        with pytest.raises(ConfigError):
            run_batch(tmp_path / "nope.json", **run_kwargs)


# ── 半份 / 空清单 ───────────────────────────────────────────────


class TestPartialAndEmpty:

    def test_incomplete_rejected_by_default(self, write_notes, run_kwargs):
        p = write_notes(_envelope([_note("n1")], complete=False))
        with pytest.raises(ConfigError):
            run_batch(p, **run_kwargs)

    def test_incomplete_allowed_with_flag(
        self, write_notes, run_kwargs, monkeypatch
    ):
        monkeypatch.setattr(
            batch_mod, "fetch_single",
            lambda url, **kw: {"md_path": "/x/n1.md", "title": "t"},
        )
        p = write_notes(_envelope([_note("n1")], complete=False))
        summary = run_batch(p, allow_partial=True, **run_kwargs)
        assert summary["ok"] == 1

    def test_empty_notes_friendly_exit(self, write_notes, run_kwargs):
        p = write_notes(_envelope([]))
        summary = run_batch(p, **run_kwargs)
        assert summary["ok"] == 0
        assert summary["failed"] == 0
        assert summary["results"] == []


# ── 出口探测 ────────────────────────────────────────────────────


class TestExitProbe:

    def test_proxy_same_egress_warns_not_raises(
        self, write_notes, tmp_path, monkeypatch
    ):
        # 直连==代理出口（TUN/系统代理常态）→ 不硬拦，给警告继续下
        monkeypatch.setattr(batch_mod, "probe_exit_ip", lambda proxies: "9.9.9.9")
        monkeypatch.setattr(
            batch_mod, "fetch_single",
            lambda url, **kw: {"md_path": "/x/n1.md", "title": "t"},
        )
        p = write_notes(_envelope([_note("n1")]))
        summary = run_batch(p, api_key="k", output_dir=tmp_path / "kb",
                            proxy="http://127.0.0.1:7897")
        assert summary["ok"] == 1               # 继续下了
        assert summary["proxy_warning"]         # 但给了核对警告

    def test_proxy_unreachable_raises(self, write_notes, tmp_path, monkeypatch):
        # 代理连不上是唯一硬失败 → 不开跑
        def probe(proxies):
            if proxies:
                raise ConnectionError("Connection refused")
            return "1.1.1.1"

        monkeypatch.setattr(batch_mod, "probe_exit_ip", probe)
        called = {"n": 0}
        monkeypatch.setattr(
            batch_mod, "fetch_single",
            lambda url, **kw: called.__setitem__("n", called["n"] + 1)
            or {"md_path": "/x.md", "title": "t"},
        )
        p = write_notes(_envelope([_note("n1")]))
        with pytest.raises(NetworkError):
            run_batch(p, api_key="k", output_dir=tmp_path / "kb",
                      proxy="http://127.0.0.1:7897")
        assert called["n"] == 0

    def test_proxy_effective_proceeds(
        self, write_notes, tmp_path, monkeypatch, patch_probe
    ):
        monkeypatch.setattr(
            batch_mod, "fetch_single",
            lambda url, **kw: {"md_path": "/x/n1.md", "title": "t"},
        )
        p = write_notes(_envelope([_note("n1")]))
        summary = run_batch(p, api_key="k", output_dir=tmp_path / "kb",
                            proxy="http://127.0.0.1:7897")
        assert summary["ok"] == 1
        # 探测过直连 + 代理两次
        assert len(patch_probe["args"]) == 2

    def test_no_proxy_skips_probe(self, write_notes, run_kwargs, monkeypatch):
        probed = {"n": 0}
        monkeypatch.setattr(
            batch_mod, "probe_exit_ip",
            lambda proxies: probed.__setitem__("n", probed["n"] + 1) or "x",
        )
        monkeypatch.setattr(
            batch_mod, "fetch_single",
            lambda url, **kw: {"md_path": "/x/n1.md", "title": "t"},
        )
        p = write_notes(_envelope([_note("n1")]))
        run_batch(p, **run_kwargs)
        assert probed["n"] == 0  # 无代理不探测


# ── 逐条下载 / 断点 / 失败分类 ──────────────────────────────────


class TestDownloadLoop:

    def test_happy_path_marks_items_done(
        self, write_notes, run_kwargs, monkeypatch
    ):
        seen = []
        monkeypatch.setattr(
            batch_mod, "fetch_single",
            lambda url, **kw: (seen.append(url), {"md_path": f"/x/{len(seen)}.md",
                                                  "title": "t"})[1],
        )
        p = write_notes(_envelope([_note("n1"), _note("n2")]))
        summary = run_batch(p, **run_kwargs)
        assert summary["ok"] == 2
        assert summary["failed"] == 0
        assert len(seen) == 2
        # batch_item 真写入 done
        st = Storage(run_kwargs["output_dir"] / "_index.sqlite")
        statuses = st.get_batch_item_statuses(summary["batch_id"])
        assert statuses == {"n1": "done", "n2": "done"}

    def test_token_expired_skipped_and_collected(
        self, write_notes, run_kwargs, monkeypatch
    ):
        def fake(url, **kw):
            if "n2" in url:
                raise AuthError("空壳", reason="token_expired")
            return {"md_path": "/x/ok.md", "title": "t"}

        monkeypatch.setattr(batch_mod, "fetch_single", fake)
        p = write_notes(_envelope([_note("n1"), _note("n2")]))
        summary = run_batch(p, **run_kwargs)
        assert summary["ok"] == 1
        assert summary["skipped"] == 1
        assert summary["token_expired"] == ["n2"]
        st = Storage(run_kwargs["output_dir"] / "_index.sqlite")
        statuses = st.get_batch_item_statuses(summary["batch_id"])
        assert statuses["n2"] == "skipped"

    def test_generic_failure_does_not_crash_batch(
        self, write_notes, run_kwargs, monkeypatch
    ):
        # M4b 未合并：fetch_single 还不会抛 AuthError(token_expired)，
        # 过期表现为通用异常 → 走通用 failed 兜底，不崩批
        def fake(url, **kw):
            if "n2" in url:
                raise RuntimeError("抠不到 initial_state")
            return {"md_path": "/x/ok.md", "title": "t"}

        monkeypatch.setattr(batch_mod, "fetch_single", fake)
        p = write_notes(_envelope([_note("n1"), _note("n2")]))
        summary = run_batch(p, **run_kwargs)
        assert summary["ok"] == 1
        assert summary["failed"] == 1
        st = Storage(run_kwargs["output_dir"] / "_index.sqlite")
        statuses = st.get_batch_item_statuses(summary["batch_id"])
        assert statuses["n2"] == "failed"

    def test_resume_skips_already_done(
        self, write_notes, run_kwargs, monkeypatch
    ):
        # 预先建一个 batch 并把 n1 标 done，再跑应只下 n2
        st = Storage(run_kwargs["output_dir"] / "_index.sqlite")
        seen = []
        monkeypatch.setattr(
            batch_mod, "fetch_single",
            lambda url, **kw: (seen.append(url),
                               {"md_path": "/x/n2.md", "title": "t"})[1],
        )
        p = write_notes(_envelope([_note("n1"), _note("n2")]))

        # 第一次跑：让 n2 失败，n1 成功
        def fake_first(url, **kw):
            if "n2" in url:
                raise RuntimeError("boom")
            return {"md_path": "/x/n1.md", "title": "t"}

        monkeypatch.setattr(batch_mod, "fetch_single", fake_first)
        first = run_batch(p, **run_kwargs)
        assert first["ok"] == 1 and first["failed"] == 1

        # 第二次跑（同一份清单）：n1 已 done 应跳过，只重试 n2
        seen.clear()
        monkeypatch.setattr(
            batch_mod, "fetch_single",
            lambda url, **kw: (seen.append(url),
                               {"md_path": "/x/n2.md", "title": "t"})[1],
        )
        second = run_batch(p, **run_kwargs)
        assert all("n1" not in u for u in seen)  # n1 没再下
        assert any("n2" in u for u in seen)      # n2 重试了
        assert second["ok"] == 1


class TestResumeSkipped:
    """Codex P2：token 过期(skipped)的断点续传——同清单别重试死 token，
    重新抓清单(新 token=新 url)要重试。"""

    def test_same_manifest_rerun_does_not_retry_expired(
        self, write_notes, run_kwargs, monkeypatch
    ):
        def fake(url, **kw):
            if "n1" in url:
                raise AuthError("空壳", reason="token_expired")
            return {"md_path": "/x/ok.md", "title": "t"}

        monkeypatch.setattr(batch_mod, "fetch_single", fake)
        p = write_notes(_envelope([_note("n1"), _note("n2")]))
        first = run_batch(p, **run_kwargs)
        assert first["skipped"] == 1

        calls = []
        monkeypatch.setattr(
            batch_mod, "fetch_single",
            lambda url, **kw: calls.append(url) or {"md_path": "/x.md", "title": "t"},
        )
        run_batch(p, **run_kwargs)  # 同一份清单重跑
        assert all("n1" not in u for u in calls)  # 死 token 不再重试

    def test_recapture_new_token_retries_expired(self, write_notes, run_kwargs, monkeypatch):
        monkeypatch.setattr(
            batch_mod, "fetch_single",
            lambda url, **kw: (_ for _ in ()).throw(AuthError("空壳", reason="token_expired")),
        )
        old = _note("n1", url="https://www.xiaohongshu.com/explore/n1?xsec_token=OLD")
        run_batch(write_notes(_envelope([old]), name="cap1.json"), **run_kwargs)

        calls = []
        monkeypatch.setattr(
            batch_mod, "fetch_single",
            lambda url, **kw: calls.append(url) or {"md_path": "/x/n1.md", "title": "t"},
        )
        new = _note("n1", url="https://www.xiaohongshu.com/explore/n1?xsec_token=NEW")
        second = run_batch(write_notes(_envelope([new]), name="cap2.json"), **run_kwargs)
        assert any("NEW" in u for u in calls)  # 新 token 重试了
        assert second["ok"] == 1
