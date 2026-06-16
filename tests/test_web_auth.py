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
    """Guard: every route whose path starts with /api/ must have require_token in its deps."""
    from app.web.auth import require_token
    api_routes = [r for r in app.routes if getattr(r, "path", "").startswith("/api/")]
    assert api_routes, "No /api routes found -- assertion is meaningless"
    for r in api_routes:
        dep_calls = [d.call for d in r.dependant.dependencies]
        assert require_token in dep_calls, f"{r.path} missing require_token"
