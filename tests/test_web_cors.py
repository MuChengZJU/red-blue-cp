"""桌面模式 CORS 开关测试（Phase 2 传输）。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.web.routes import _maybe_enable_cors


def _has_cors(app: FastAPI) -> bool:
    return any(m.cls is CORSMiddleware for m in app.user_middleware)


def test_cors_enabled_in_desktop_mode(monkeypatch):
    monkeypatch.setenv("RBCP_DESKTOP", "1")
    app = FastAPI()
    assert _maybe_enable_cors(app) is True
    assert _has_cors(app)


def test_cors_off_when_not_desktop(monkeypatch):
    monkeypatch.delenv("RBCP_DESKTOP", raising=False)
    app = FastAPI()
    assert _maybe_enable_cors(app) is False
    assert not _has_cors(app)
