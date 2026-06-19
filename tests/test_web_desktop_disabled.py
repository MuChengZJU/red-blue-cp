import os

from fastapi.testclient import TestClient

from app.web.routes import app


def test_pydoll_endpoints_404_in_desktop_mode(monkeypatch):
    monkeypatch.setenv("RBCP_DESKTOP", "1")
    c = TestClient(app)
    # 桌面模式：这俩端点不可用（404），不触发 discover/pydoll
    assert c.post("/api/uploaders/posts", json={"url": "https://x"}).status_code == 404
    assert c.post("/api/comments", json={"url": "https://x"}).status_code == 404


def test_pydoll_endpoints_available_when_not_desktop(monkeypatch):
    monkeypatch.delenv("RBCP_DESKTOP", raising=False)
    c = TestClient(app)
    # 非桌面：不是 404（可能 400/422/500 等业务码，但不能是被我们禁用的 404）
    assert c.post("/api/uploaders/posts", json={}).status_code != 404
