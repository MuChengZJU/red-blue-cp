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
    "RBCP_ASR_BASE_URL", "RBCP_ASR_API_KEY",
    "RBCP_VLM_BASE_URL", "RBCP_VLM_API_KEY",
    "RBCP_LLM_BASE_URL", "RBCP_LLM_API_KEY",
    "RBCP_VLM_IMAGE_MODE",
    "RBCP_LLM_THINKING", "RBCP_VLM_THINKING",
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


def test_empty_output_dir_does_not_persist(clean, monkeypatch):
    """空 output_dir 不能写入：否则 Path("") 会把知识库落到当前工作目录。"""
    monkeypatch.setenv("RBCP_OUTPUT_DIR", "/home/u/transcript")
    c = TestClient(app)
    r = c.post("/api/config", json={"output_dir": "", "proxy": "http://127.0.0.1:1"})
    assert "RBCP_OUTPUT_DIR" not in r.json()["applied"]  # 跳过，未写
    assert os.environ["RBCP_OUTPUT_DIR"] == "/home/u/transcript"  # 原值保留
    body = (clean / ".env").read_text(encoding="utf-8")
    assert "RBCP_OUTPUT_DIR=\n" not in body and "RBCP_OUTPUT_DIR=" not in body


def test_empty_model_fields_do_not_persist(clean, monkeypatch):
    """空模型字段不能写入：否则 RBCP_LLM_MODEL="" 会让 model="" 发给 DashScope → 400。"""
    monkeypatch.setenv("RBCP_LLM_MODEL", "qwen-plus")
    c = TestClient(app)
    r = c.post("/api/config", json={
        "asr_model": "", "vlm_model": "", "llm_model": "", "proxy": "http://127.0.0.1:1",
    })
    applied = r.json()["applied"]
    assert "RBCP_LLM_MODEL" not in applied
    assert "RBCP_ASR_MODEL" not in applied
    assert "RBCP_VLM_MODEL" not in applied
    assert os.environ["RBCP_LLM_MODEL"] == "qwen-plus"  # 原值保留，没被空串清掉
    assert "RBCP_PROXY" in applied  # proxy 仍可写（含清空）


def test_persist_merges_existing(clean):
    c = TestClient(app)
    c.post("/api/config", json={"dashscope_key": "sk-aaa1111bbbb"})
    c.post("/api/config", json={"proxy": "http://127.0.0.1:1080"})
    body = (clean / ".env").read_text(encoding="utf-8")
    assert "DASHSCOPE_API_KEY=sk-aaa1111bbbb" in body  # 第一次的没被第二次覆盖掉
    assert "RBCP_PROXY=http://127.0.0.1:1080" in body


# ── 0.7 自定义模型服务商 ──────────────────────────────────────

def test_get_config_returns_effective_defaults_and_presets(clean):
    g = TestClient(app).get("/api/config").json()
    assert g["provider_preset"] == "qianwen"
    assert g["asr_base_url"].startswith("https://cn-beijing.maas.qianwenaiapi.com/")
    assert g["llm_base_url"].endswith("/compatible-mode/v1")
    assert g["vlm_model"] == "qwen3.7-flash"
    assert g["llm_thinking"] is False and g["vlm_thinking"] is False
    assert g["image_mode"] == "auto"
    assert {p["id"] for p in g["presets"]} == {"qianwen", "custom"}


def test_set_custom_provider_persists_and_masks(clean):
    c = TestClient(app)
    r = c.post("/api/config", json={
        "asr_base_url": "https://asr.example.com/api/v1",
        "asr_api_key": "asr-secret-1234",
        "asr_model": "fun-asr",
        "llm_base_url": "https://llm.example.com/v1",
        "llm_api_key": "llm-secret-5678",
        "llm_model": "my-llm",
        "vlm_base_url": "https://vlm.example.com/v1",
        "vlm_model": "my-vlm",
        "image_mode": "base64",
    })
    assert r.status_code == 200, r.text
    assert os.environ["RBCP_LLM_BASE_URL"] == "https://llm.example.com/v1"
    body = (clean / ".env").read_text(encoding="utf-8")
    assert "RBCP_LLM_API_KEY=llm-secret-5678" in body
    assert "RBCP_VLM_IMAGE_MODE=base64" in body

    g = c.get("/api/config").json()
    assert g["provider_preset"] == "custom"
    assert g["asr_model"] == "fun-asr"
    assert g["llm_model"] == "my-llm"
    assert g["vlm_model"] == "my-vlm"
    assert g["image_mode"] == "base64"
    assert g["llm_api_key_set"] is True
    assert "llm-secret-5678" not in str(g)  # 绝不明文回传


def test_base_url_without_scheme_gets_http(clean):
    r = TestClient(app).post("/api/config", json={"proxy": "", "llm_base_url": "127.0.0.1:8080/v1"})
    assert r.status_code == 200
    assert os.environ["RBCP_LLM_BASE_URL"] == "http://127.0.0.1:8080/v1"


def test_invalid_base_url_and_image_mode_rejected(clean):
    c = TestClient(app)
    r = c.post("/api/config", json={"llm_base_url": "ftp://example.com/v1"})
    assert r.status_code == 400
    r = c.post("/api/config", json={"image_mode": "bogus"})
    assert r.status_code == 400


def test_config_test_endpoint_reports_failure(clean, monkeypatch):
    from unittest.mock import patch

    c = TestClient(app)
    with patch("app.web.config_api.test_connection",
               return_value={"ok": True, "target": "llm", "model": "qwen-plus"}):
        assert c.post("/api/config/test", json={"target": "llm"}).json()["ok"] is True
    with patch("app.web.config_api.test_connection", side_effect=RuntimeError("boom")):
        body = c.post("/api/config/test", json={"target": "llm"}).json()
    assert body["ok"] is False
    assert "boom" in body["error"]


def test_thinking_flags_roundtrip(clean):
    c = TestClient(app)
    r = c.post("/api/config", json={"llm_thinking": True, "vlm_thinking": False})
    assert r.status_code == 200, r.text
    assert os.environ["RBCP_LLM_THINKING"] == "true"
    assert os.environ["RBCP_VLM_THINKING"] == "false"
    g = c.get("/api/config").json()
    assert g["llm_thinking"] is True
    assert g["vlm_thinking"] is False
