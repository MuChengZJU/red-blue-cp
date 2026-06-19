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
import app.extract.comments as comments_mod
import app.extract.discover as discover
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
    """打桩单篇转录链路：provider/extract/render 全假。

    实现已从 cli 抽到 service.pipeline（M4a），patch 目标随之改到 pipeline.*。
    """
    import app.extract.pipeline as pipeline
    monkeypatch.setattr(pipeline, "_provider_from_env", lambda api_key, **kw: object())
    monkeypatch.setattr(
        pipeline, "extract_url",
        lambda url, provider, **kw: types.SimpleNamespace(
            title="标题X", author="作者X", platform="xiaohongshu",
            content_type="video",
            # 0.6：fetch_single 返回值新增 canonical/指纹/segments，桩需补齐
            text="正文X", text_sha256="sha256X", segments=None,
            readable_text="正文X",
            # ExtractResult.metadata 是带默认 dict 的真实字段，桩须匹配（fetch_single 读 cover_url）
            metadata={},
            **kw,
        ),
    )
    monkeypatch.setattr(
        pipeline, "render_and_write", lambda result, output_dir: output_dir / "out.md"
    )


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


def test_proxy_with_all_warns_browser_leg_not_proxied(monkeypatch):
    # --proxy 撞 --all：抓清单走 pydoll/Chrome 真实 IP，必须警告（Codex P1）
    async def fake(url):
        return _fake_listing(complete=False, reason="x")

    monkeypatch.setattr(discover, "discover_user_posts", fake)
    result = runner.invoke(
        cli.app,
        ["fetch", "https://x/user/profile/u1", "--all", "--yes",
         "--proxy", "http://127.0.0.1:7897"],
    )
    assert "真实 IP" in result.stdout


def test_proxy_with_comments_warns(stub_single, monkeypatch):
    # --proxy 撞 --comments：抓评论走 pydoll 真实 IP，必须警告（Codex P2）
    async def fake_comments(url, *, with_sub):
        return []

    monkeypatch.setattr(discover, "discover_comments", fake_comments)
    monkeypatch.setattr(
        comments_mod, "write_comments_md",
        lambda note_id, comments, output_dir, note_title="": output_dir / "c.md",
    )
    result = runner.invoke(
        cli.app,
        ["fetch", "https://www.xiaohongshu.com/explore/abc", "--comments",
         "--proxy", "http://127.0.0.1:7897"],
    )
    assert "真实 IP" in result.stdout


def test_proxy_single_no_warning(stub_single):
    # 单篇 --proxy：下载全程走代理，不该有误导警告
    result = runner.invoke(
        cli.app,
        ["fetch", "https://www.xiaohongshu.com/explore/abc",
         "--proxy", "http://127.0.0.1:7897"],
    )
    assert "真实 IP" not in result.stdout


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


def _mk_comment(cid, subs=()):
    return discover.Comment(
        comment_id=cid, note_id="note9", content="x", author="u", author_id="uid",
        like_count=0, ip_location="", create_time=0, reply_to=None,
        sub_comments=list(subs),
    )


def test_api_comments(monkeypatch, tmp_path):
    monkeypatch.setenv("RBCP_OUTPUT_DIR", str(tmp_path))

    async def fake_comments(url, *, with_sub):
        # 2 条一级，其中一条带 3 条楼中楼 → total 应是 5
        return [_mk_comment("c1", subs=[_mk_comment("s1"), _mk_comment("s2"), _mk_comment("s3")]),
                _mk_comment("c2")]

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
    assert body["comment_count"] == 2   # 一级
    assert body["total_count"] == 5     # 含楼中楼


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


def test_load_cookies_missing_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("XHS_COOKIE", raising=False)
    monkeypatch.delenv("RBCP_XHS_COOKIE_FILE", raising=False)
    # 把默认文件指到不存在路径，避免本机已有 ~/.config/rbcp/xhs_cookies.json 干扰
    monkeypatch.setattr(discover, "_DEFAULT_COOKIE_FILE", str(tmp_path / "nope.json"))
    with pytest.raises(RuntimeError):
        discover._load_cookies()


def test_load_cookies_from_default_file(monkeypatch, tmp_path):
    monkeypatch.delenv("XHS_COOKIE", raising=False)
    monkeypatch.delenv("RBCP_XHS_COOKIE_FILE", raising=False)
    f = tmp_path / "xhs_cookies.json"
    f.write_text('{"cookies":[{"name":"web_session","value":"v"}]}', encoding="utf-8")
    monkeypatch.setattr(discover, "_DEFAULT_COOKIE_FILE", str(f))
    cookies = discover._load_cookies()
    assert cookies[0]["name"] == "web_session"


# ─── Codex review 修复回归 ─────────────────────────────────────────────────────


def test_discover_user_posts_cookie_error_is_cookie_expired(monkeypatch):
    """没配 cookie 时 _start_chrome 抛 CookieError，要分类成 cookie_expired 而非 network。"""
    async def fake_start():
        raise discover.CookieError("先 rbcp login")

    monkeypatch.setattr(discover, "_start_chrome", fake_start)
    import asyncio
    r = asyncio.run(discover.discover_user_posts("https://x/user/profile/u1"))
    assert r["complete"] is False
    assert r["incomplete_reason"] == "cookie_expired"


def test_fetch_all_json_incomplete(monkeypatch):
    async def fake(url):
        return _fake_listing(complete=False, reason="risk_control")

    monkeypatch.setattr(discover, "discover_user_posts", fake)
    result = runner.invoke(cli.app, ["fetch", "https://x/user/profile/u1", "--all", "--json", "--yes"])
    assert result.exit_code == 1
    assert '"error": "incomplete_list"' in result.stdout
    assert '"risk_control"' in result.stdout


def test_fetch_all_json_needs_yes(monkeypatch):
    async def fake(url):
        return _fake_listing(complete=True)

    monkeypatch.setattr(discover, "discover_user_posts", fake)
    # --json --all 但没 --yes → 不弹确认，报 confirmation_required
    result = runner.invoke(cli.app, ["fetch", "https://x/user/profile/u1", "--all", "--json"])
    assert result.exit_code == 1
    assert '"confirmation_required"' in result.stdout


def test_fetch_all_json_success(monkeypatch):
    async def fake(url):
        return _fake_listing(complete=True)

    monkeypatch.setattr(discover, "discover_user_posts", fake)
    monkeypatch.setattr(cli, "_fetch_single", lambda url, **kw: {"md_path": "x", "title": "t"})
    result = runner.invoke(cli.app, ["fetch", "https://x/user/profile/u1", "--all", "--json", "--yes"])
    assert result.exit_code == 0
    import json as _j
    # 末行是 JSON 汇总
    line = [l for l in result.stdout.strip().splitlines() if l.startswith("{")][-1]
    data = _j.loads(line)
    assert data["ok"] is True and data["downloaded"] == 2 and data["failed"] == 0
