"""WebUI 批量导入 + 批次状态接口测试（M4 WebUI 入口）。run_batch 全 mock，不真下载。"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.extract.batch as batch_mod
from app.extract.storage import Storage
from app.web.routes import app

client = TestClient(app)


def _env(n=2, **over):
    e = {
        "schema_version": 1, "source": "xhs_user_posted", "user_id": "u1",
        "complete": True, "count": n,
        "notes": [
            {"note_id": f"n{i}", "title": "t", "type": "normal",
             "xsec_token": "x", "url": f"https://www.xiaohongshu.com/explore/n{i}"}
            for i in range(n)
        ],
    }
    e.update(over)
    return e


def test_import_rejects_bad_schema(monkeypatch, tmp_path):
    monkeypatch.setenv("RBCP_OUTPUT_DIR", str(tmp_path))
    r = client.post("/api/import-list", json={"schema_version": 2, "notes": []})
    assert r.status_code == 400
    assert "schema_version" in r.json()["detail"] or "清单" in r.json()["detail"]


def test_import_valid_starts_background(monkeypatch, tmp_path):
    monkeypatch.setenv("RBCP_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(batch_mod, "run_batch", lambda *a, **k: {"ok": 0})
    r = client.post("/api/import-list", json=_env(3))
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["count"] == 3


def test_import_half_list_rejected_unless_allow_partial(monkeypatch, tmp_path):
    monkeypatch.setenv("RBCP_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(batch_mod, "run_batch", lambda *a, **k: {})
    r = client.post("/api/import-list", json=_env(1, complete=False))
    assert r.status_code == 400
    r2 = client.post("/api/import-list?allow_partial=true", json=_env(1, complete=False))
    assert r2.status_code == 200


def test_list_batches_returns_counts(monkeypatch, tmp_path):
    monkeypatch.setenv("RBCP_OUTPUT_DIR", str(tmp_path))
    st = Storage(tmp_path / "_index.sqlite")
    bid = st.create_batch(source="xhs_user_posted", user_id="u1", count=2, complete=True)
    st.add_batch_items(bid, [{"note_id": "n1", "url": "u"}, {"note_id": "n2", "url": "u"}])
    st.mark_batch_item_done(bid, "n1", md_path="/x.md")
    r = client.get("/api/batches")
    assert r.status_code == 200
    batches = r.json()["batches"]
    assert batches and batches[0]["counts"].get("done") == 1
    assert batches[0]["counts"].get("pending") == 1


def test_batches_page_redirects_home(monkeypatch, tmp_path):
    # M5b：批量整合进主页，旧 /batches 入口 301 回主页
    monkeypatch.setenv("RBCP_OUTPUT_DIR", str(tmp_path))
    r = client.get("/batches", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/"
