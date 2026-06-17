"""设置配置端点测试：设置界面 ↔ 后端 os.environ + 配置 .env。"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

import app.web.config_api as config_api
from app.web.routes import app

_KEYS = [
    "DASHSCOPE_API_KEY", "RBCP_OUTPUT_DIR", "RBCP_PROXY",
    "RBCP_ASR_MODEL", "RBCP_VLM_MODEL", "RBCP_LLM_MODEL",
]


@pytest.fixture
def clean(tmp_path, monkeypatch):
    monkeypatch.setattr(config_api, "config_dir", lambda: tmp_path)
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)  # monkeypatch 接管 → teardown 自动清
    return tmp_path


def test_set_then_get_config(clean):
    c = TestClient(app)
    assert c.get("/api/config").json()["dashscope_key_set"] is False

    r = c.post("/api/config", json={
        "dashscope_key": "sk-test1234567890",
        "proxy": "http://127.0.0.1:7897",
        "asr_model": "paraformer-v2",
    })
    assert r.status_code == 200
    assert "DASHSCOPE_API_KEY" in r.json()["applied"]

    # 即时生效（_provider_from_env 每次读 env）
    assert os.environ["DASHSCOPE_API_KEY"] == "sk-test1234567890"
    # 持久化到配置 .env
    assert "DASHSCOPE_API_KEY=sk-test1234567890" in (clean / ".env").read_text(encoding="utf-8")

    g = c.get("/api/config").json()
    assert g["dashscope_key_set"] is True
    assert "sk-test1234567890" not in str(g)   # 打码，绝不回明文
    assert g["proxy"] == "http://127.0.0.1:7897"
    assert g["asr_model"] == "paraformer-v2"


def test_empty_key_does_not_overwrite(clean, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-existing99999")
    c = TestClient(app)
    c.post("/api/config", json={"dashscope_key": "", "vlm_model": "qwen3-vl-flash"})
    assert os.environ["DASHSCOPE_API_KEY"] == "sk-existing99999"  # 空 key 不误清
    assert os.environ["RBCP_VLM_MODEL"] == "qwen3-vl-flash"


def test_persist_merges_existing(clean):
    c = TestClient(app)
    c.post("/api/config", json={"dashscope_key": "sk-aaa1111bbbb"})
    c.post("/api/config", json={"proxy": "http://127.0.0.1:1080"})
    body = (clean / ".env").read_text(encoding="utf-8")
    assert "DASHSCOPE_API_KEY=sk-aaa1111bbbb" in body  # 第一次的没被第二次覆盖掉
    assert "RBCP_PROXY=http://127.0.0.1:1080" in body
