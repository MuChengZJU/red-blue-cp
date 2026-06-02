"""Phase 2c 接线层测试：CLI list/fetch + routes 两个 API。

浏览器抓取（discover_*）与媒体转录（extract_url）全部 mock，
只验证编排逻辑：list 的 complete 退出码、fetch --comments 调用链、
--all 的预览/确认/半份清单拒绝、API 形状。
"""

from __future__ import annotations

import types

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import app.cli as cli
import app.service.comments as comments_mod
import app.service.discover as discover
from app.web.routes import app as web_app


runner = CliRunner()


def _fake_listing(*, complete=True, notes=None, reason=None):
    notes = notes if notes is not None else [
        {"note_id": "n1", "title": "笔记一", "type": "image", "liked_count": 5, "xsec_token": "t1"},
        {"note_id": "n2", "title": "笔记二", "type": "video", "liked_count": 9, "xsec_token": "t2"},
    ]
    return {
        "user_id": "u1",
        "complete": complete,
        "incomplete_reason": reason,
        "captured": len(notes),
        "estimated_total": None,
        "estimate": {"image_notes": 1, "video_notes": 1, "vlm_calls": 1, "asr_minutes": None},
        "notes": notes,
    }


# ─── CLI list ────────────────────────────────────────────────────────────────


def test_list_json_complete(monkeypatch):
    async def fake(url):
        return _fake_listing(complete=True)

    monkeypatch.setattr(discover, "discover_user_posts", fake)
    result = runner.invoke(cli.app, ["list", "https://x/user/profile/u1", "--json"])
    assert result.exit_code == 0
    assert '"complete": true' in result.stdout


def test_list_incomplete_exits_nonzero(monkeypatch):
    async def fake(url):
        return _fake_listing(complete=False, reason="risk_control")

    monkeypatch.setattr(discover, "discover_user_posts", fake)
    result = runner.invoke(cli.app, ["list", "https://x/user/profile/u1"])
    assert result.exit_code == 1
    assert "未拉全" in result.stdout
    assert "risk_control" in result.stdout


# ─── CLI fetch 单篇 ────────────────────────────────────────────────────────────


@pytest.fixture
def stub_single(monkeypatch):
    """打桩单篇转录链路：provider/extract/render 全假。"""
    monkeypatch.setattr(cli, "_provider_from_env", lambda api_key: object())
    monkeypatch.setattr(
        cli, "extract_url",
        lambda url, provider, **kw: types.SimpleNamespace(title="标题X", **kw),
    )
    monkeypatch.setattr(cli, "render_and_write", lambda result, output_dir: output_dir / "out.md")


def test_fetch_single_plain(stub_single):
    result = runner.invoke(cli.app, ["fetch", "https://www.xiaohongshu.com/explore/abc"])
    assert result.exit_code == 0
    assert "Done:" in result.stdout


def test_fetch_single_with_comments(stub_single, monkeypatch):
    calls = {}

    async def fake_comments(url, *, with_sub):
        calls["with_sub"] = with_sub
        return ["c1", "c2", "c3"]  # 占位，write 被 mock

    monkeypatch.setattr(discover, "discover_comments", fake_comments)
    monkeypatch.setattr(
        comments_mod, "write_comments_md",
        lambda note_id, comments, output_dir, note_title="": output_dir / f"{note_id}.comments.md",
    )

    result = runner.invoke(
        cli.app, ["fetch", "https://www.xiaohongshu.com/explore/abc123", "--comments"]
    )
    assert result.exit_code == 0
    assert calls["with_sub"] is True
    assert "Comments:" in result.stdout
    assert "3 条" in result.stdout


def test_fetch_comments_no_sub_passes_flag(stub_single, monkeypatch):
    calls = {}

    async def fake_comments(url, *, with_sub):
        calls["with_sub"] = with_sub
        return []

    monkeypatch.setattr(discover, "discover_comments", fake_comments)
    monkeypatch.setattr(
        comments_mod, "write_comments_md",
        lambda *a, **k: a[2] / "x.comments.md",
    )
    result = runner.invoke(
        cli.app,
        ["fetch", "https://www.xiaohongshu.com/explore/abc", "--comments", "--no-sub"],
    )
    assert result.exit_code == 0
    assert calls["with_sub"] is False


# ─── CLI fetch --all ──────────────────────────────────────────────────────────


def test_fetch_all_incomplete_refuses(monkeypatch):
    async def fake(url):
        return _fake_listing(complete=False, reason="risk_control")

    monkeypatch.setattr(discover, "discover_user_posts", fake)
    result = runner.invoke(cli.app, ["fetch", "https://x/user/profile/u1", "--all", "--yes"])
    assert result.exit_code == 1
    assert "不在半份清单上做全量下载" in result.stdout


def test_fetch_all_downloads_each(monkeypatch):
    async def fake(url):
        return _fake_listing(complete=True)

    monkeypatch.setattr(discover, "discover_user_posts", fake)
    fetched = []
    monkeypatch.setattr(
        cli, "_fetch_single",
        lambda url, **kw: fetched.append(url) or {"md_path": "x", "title": "t"},
    )
    result = runner.invoke(cli.app, ["fetch", "https://x/user/profile/u1", "--all", "--yes"])
    assert result.exit_code == 0
    assert len(fetched) == 2  # 两条 note 各抓一次
    assert "成功 2，失败 0" in result.stdout


def test_fetch_all_one_failure_continues(monkeypatch):
    async def fake(url):
        return _fake_listing(complete=True)

    monkeypatch.setattr(discover, "discover_user_posts", fake)

    def flaky(url, **kw):
        if "n1" in url:
            raise RuntimeError("boom")
        return {"md_path": "x", "title": "t"}

    monkeypatch.setattr(cli, "_fetch_single", flaky)
    result = runner.invoke(cli.app, ["fetch", "https://x/user/profile/u1", "--all", "--yes"])
    assert result.exit_code == 0
    assert "成功 1，失败 1" in result.stdout


# ─── routes ───────────────────────────────────────────────────────────────────


def test_api_uploaders_posts(monkeypatch):
    async def fake(user_url):
        return _fake_listing(complete=True)

    monkeypatch.setattr(discover, "discover_user_posts", fake)
    client = TestClient(web_app)
    resp = client.post("/api/uploaders/posts", json={"user_url": "https://x/user/profile/u1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["complete"] is True
    assert body["captured"] == 2


def test_api_comments(monkeypatch, tmp_path):
    monkeypatch.setenv("RBCP_OUTPUT_DIR", str(tmp_path))

    async def fake_comments(url, *, with_sub):
        return ["c1", "c2"]

    monkeypatch.setattr(discover, "discover_comments", fake_comments)
    monkeypatch.setattr(
        comments_mod, "write_comments_md",
        lambda note_id, comments, output_dir, note_title="": output_dir / f"{note_id}.comments.md",
    )
    client = TestClient(web_app)
    resp = client.post(
        "/api/comments", json={"url": "https://www.xiaohongshu.com/explore/note9"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["note_id"] == "note9"
    assert body["comment_count"] == 2


def test_api_comments_risk_control_503(monkeypatch, tmp_path):
    monkeypatch.setenv("RBCP_OUTPUT_DIR", str(tmp_path))

    async def fake_comments(url, *, with_sub):
        raise discover.RiskControlError("撞验证墙")

    monkeypatch.setattr(discover, "discover_comments", fake_comments)
    client = TestClient(web_app)
    resp = client.post("/api/comments", json={"url": "https://www.xiaohongshu.com/explore/n"})
    assert resp.status_code == 503


# ─── cookie 来源解析（生产 .env 串 / dev 文件回退）─────────────────────────────


def test_load_cookies_from_env_string(monkeypatch):
    monkeypatch.setenv("XHS_COOKIE", "web_session=abc; a1=xyz")
    monkeypatch.delenv("RBCP_XHS_COOKIE_FILE", raising=False)
    cookies = discover._load_cookies()
    names = {c["name"]: c["value"] for c in cookies}
    assert names == {"web_session": "abc", "a1": "xyz"}
    assert all(c["domain"] == ".xiaohongshu.com" for c in cookies)


def test_load_cookies_from_file(monkeypatch, tmp_path):
    monkeypatch.delenv("XHS_COOKIE", raising=False)
    f = tmp_path / "ck.json"
    f.write_text(
        '{"cookies":[{"name":"a1","value":"v","domain":".xiaohongshu.com",'
        '"path":"/","secure":true,"sameSite":"Lax"}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("RBCP_XHS_COOKIE_FILE", str(f))
    cookies = discover._load_cookies()
    assert cookies[0]["name"] == "a1"
    assert cookies[0]["sameSite"] == "Lax"


def test_load_cookies_env_string_wins_over_file(monkeypatch, tmp_path):
    f = tmp_path / "ck.json"
    f.write_text('[{"name":"fromfile","value":"x"}]', encoding="utf-8")
    monkeypatch.setenv("RBCP_XHS_COOKIE_FILE", str(f))
    monkeypatch.setenv("XHS_COOKIE", "fromenv=1")
    cookies = discover._load_cookies()
    assert cookies[0]["name"] == "fromenv"  # .env 串优先


def test_load_cookies_missing_raises(monkeypatch):
    monkeypatch.delenv("XHS_COOKIE", raising=False)
    monkeypatch.delenv("RBCP_XHS_COOKIE_FILE", raising=False)
    with pytest.raises(RuntimeError):
        discover._load_cookies()
