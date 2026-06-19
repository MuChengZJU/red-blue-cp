from __future__ import annotations

from fastapi.testclient import TestClient

from app.web.routes import app
import app.web.auth as auth


def test_api_requires_token_when_active(monkeypatch):
    monkeypatch.setattr(auth, "_ACTIVE_TOKEN", "secret123")
    c = TestClient(app)
    assert c.get("/api/jobs").status_code == 401
    assert c.get("/api/jobs", headers={"Authorization": "Bearer secret123"}).status_code == 200
    assert c.get("/api/jobs", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/").status_code == 200


def test_no_token_means_open_for_webui_compat(monkeypatch):
    monkeypatch.setattr(auth, "_ACTIVE_TOKEN", None)
    c = TestClient(app)
    assert c.get("/api/jobs").status_code == 200


def test_every_api_route_carries_require_token():
    """Guard: every route on the /api router must carry require_token.

    直接内省 `api` 路由器，而非 `app.routes`——新版 fastapi（0.137+/starlette 1.3+）把
    include_router 的路由包进私有 `_IncludedRouter`、不再平铺进 `app.routes`，
    内省 `app.routes` 会落空（曾导致 CI 假阴：找不到 /api 路由）。
    """
    from app.web.routes import api
    from app.web.auth import require_token
    assert api.routes, "No /api routes found -- assertion is meaningless"
    for r in api.routes:
        dep_calls = [d.call for d in r.dependant.dependencies]
        assert require_token in dep_calls, f"{r.path} missing require_token"
