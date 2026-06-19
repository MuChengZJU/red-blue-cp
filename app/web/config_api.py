"""设置界面 ↔ 后端配置：读当前生效配置 + 把用户配置即时设进 os.environ 并持久化。

桌面端痛点：设置界面填的 key 只存前端 localStorage，serve 从不读它 → 转录 401。
本模块让设置真正配置 serve：set_config 即时 os.environ（运行中下一次请求就生效，
_provider_from_env 每次读 env）+ 落 platformdirs 配置目录的 .env（重启仍在）。

安全：配置 .env 写在用户配置目录（`~/Library/Application Support/rbcp/.env` 等），
**不在仓库、不进 git**（守红线#2）。key 读出时打码。
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from app.config import config_dir

# UI 字段名 → 环境变量名
_FIELDS = {
    "dashscope_key": "DASHSCOPE_API_KEY",
    "output_dir": "RBCP_OUTPUT_DIR",
    "proxy": "RBCP_PROXY",
    "asr_model": "RBCP_ASR_MODEL",
    "vlm_model": "RBCP_VLM_MODEL",
    "llm_model": "RBCP_LLM_MODEL",
}


def _env_path() -> Path:
    return config_dir() / ".env"


def _mask(k: str) -> str:
    if not k:
        return ""
    if len(k) <= 8:
        return "***"
    return k[:4] + "***" + k[-4:]


def get_config() -> dict[str, Any]:
    """读当前生效配置（来自 os.environ）。key 打码，另给 dashscope_key_set 布尔。"""
    out: dict[str, Any] = {}
    for ui, env in _FIELDS.items():
        val = os.getenv(env) or ""
        if ui == "dashscope_key":
            out["dashscope_key_set"] = bool(val)
            out["dashscope_key_masked"] = _mask(val)
        else:
            out[ui] = val
    return out


def set_config(updates: dict[str, Any]) -> list[str]:
    """更新提供的字段：设进 os.environ（即时生效）+ 持久化到配置 .env。

    - 只处理 _FIELDS 里的已知字段，其余忽略。
    - 这些字段空串无意义且有害，跳过（置空=保持原值，不写不持久化）：
      key（不误清已有）/ output_dir（空串 → Path("") 落 cwd，知识库写进启动目录）/
      asr|vlm|llm_model（空串 → model="" 发给 DashScope → HTTP 400，无法转录）。
      设置页这些字段没预填时点保存会提交空串，正是这条把 model 清空导致转录 400 的根因。
    - 只有 proxy 允许置空（清空代理是合法操作）。
    返回实际写入的环境变量名列表。
    """
    _SKIP_IF_EMPTY = {
        "dashscope_key", "output_dir", "asr_model", "vlm_model", "llm_model",
    }
    applied: dict[str, str] = {}
    for ui, env in _FIELDS.items():
        if ui not in updates or updates[ui] is None:
            continue
        val = str(updates[ui]).strip()
        if ui in _SKIP_IF_EMPTY and val == "":
            continue
        os.environ[env] = val
        applied[env] = val
    if applied:
        _persist(applied)
    return list(applied.keys())


def _persist(applied: dict[str, str]) -> None:
    """合并写配置 .env（保留未涉及的已有行），原子替换。"""
    path = _env_path()
    existing: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k = line.split("=", 1)[0].strip()
                existing[k] = line.rstrip("\n")
    for k, v in applied.items():
        existing[k] = f"{k}={v}"
    body = "\n".join(existing[k] for k in existing) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
