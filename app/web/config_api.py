"""设置界面 ↔ 后端配置：读当前生效配置 + 把用户配置即时设进 os.environ 并持久化。

桌面端痛点：设置界面填的 key 只存前端 localStorage，serve 从不读它 → 转录 401。
本模块让设置真正配置 serve：set_config 即时 os.environ（运行中下一次请求就生效，
_provider_from_env 每次读 env）+ 落 platformdirs 配置目录的 .env（重启仍在）。

0.7 起支持「自定义模型服务商」：ASR / VLM / LLM 可分别配置 base_url、api_key、model。
未单独配置的能力回退共享 key（DASHSCOPE_API_KEY）和默认端点（千问AI平台）。

安全：配置 .env 写在用户配置目录（`~/Library/Application Support/rbcp/.env` 等），
**不在仓库、不进 git**（守红线#2）。key 读出时打码，绝不回明文。
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import config_dir
from app.model_endpoints import (
    IMAGE_MODES,
    PROVIDER_PRESETS,
    asr_endpoint,
    detect_preset,
    llm_endpoint,
    shared_api_key,
    vlm_endpoint,
    vlm_image_mode,
)

# UI 字段名 → 环境变量名（非密钥类）
_FIELDS = {
    "output_dir": "RBCP_OUTPUT_DIR",
    "proxy": "RBCP_PROXY",
    "asr_base_url": "RBCP_ASR_BASE_URL",
    "asr_model": "RBCP_ASR_MODEL",
    "vlm_base_url": "RBCP_VLM_BASE_URL",
    "vlm_model": "RBCP_VLM_MODEL",
    "llm_base_url": "RBCP_LLM_BASE_URL",
    "llm_model": "RBCP_LLM_MODEL",
    "image_mode": "RBCP_VLM_IMAGE_MODE",
}

# 密钥类字段：读出打码，写入时留空=不改
_SECRET_FIELDS = {
    "dashscope_key": "DASHSCOPE_API_KEY",
    "asr_api_key": "RBCP_ASR_API_KEY",
    "vlm_api_key": "RBCP_VLM_API_KEY",
    "llm_api_key": "RBCP_LLM_API_KEY",
}

_ALL_UI_FIELDS = {**_FIELDS, **_SECRET_FIELDS}

# 空串无意义且有害：key 会被误清、output_dir 会落 cwd、model/base_url 会让请求 400。
# 设置页字段没预填时点保存会提交空串，必须跳过。proxy 例外（清空代理是合法操作）。
_SKIP_IF_EMPTY = (set(_FIELDS) | set(_SECRET_FIELDS)) - {"proxy"}


def _env_path() -> Path:
    return config_dir() / ".env"


def _mask(k: str) -> str:
    if not k:
        return ""
    if len(k) <= 8:
        return "***"
    return k[:4] + "***" + k[-4:]


def _secret_view(name: str, shared: str) -> dict[str, Any]:
    """单个密钥字段的展示信息：是否已配、打码值、来源（own/shared/none）。"""
    own = (os.getenv(_SECRET_FIELDS[name]) or "").strip()
    value = own or (shared if name != "dashscope_key" else "")
    source = "own" if own else ("shared" if value else "none")
    return {
        f"{name}_set": bool(value),
        f"{name}_masked": _mask(value),
        f"{name}_source": source,
    }


def get_config() -> dict[str, Any]:
    """读当前生效配置（来自 os.environ / 默认端点）。key 打码。

    base_url / model 返回**生效值**（含默认），方便设置页直接回显；保存时会显式落盘。
    output_dir / proxy 返回原始值（空=用默认），避免把默认路径误写进配置。
    """
    shared = shared_api_key()
    asr = asr_endpoint()
    llm = llm_endpoint()
    vlm = vlm_endpoint()

    out: dict[str, Any] = {
        "output_dir": os.getenv("RBCP_OUTPUT_DIR") or "",
        "proxy": os.getenv("RBCP_PROXY") or "",
        "asr_base_url": asr.base_url,
        "asr_model": asr.model,
        "llm_base_url": llm.base_url,
        "llm_model": llm.model,
        "vlm_base_url": vlm.base_url,
        "vlm_model": vlm.model,
        "image_mode": vlm_image_mode(),
        "provider_preset": detect_preset(asr.base_url, llm.base_url),
        "presets": [dict(p) for p in PROVIDER_PRESETS],
    }
    for name in _SECRET_FIELDS:
        out.update(_secret_view(name, shared))
    return out


def _normalize_base_url(value: str, *, field: str) -> str:
    """base_url 校验/补全：无 scheme 自动补 http://；只接受 http/https。"""
    value = value.strip()
    if "://" not in value:
        value = "http://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field} 不是合法的 http(s) 地址：{value}")
    return value.rstrip("/")


def set_config(updates: dict[str, Any]) -> list[str]:
    """更新提供的字段：设进 os.environ（即时生效）+ 持久化到配置 .env。

    - 只处理已知字段，其余忽略。
    - 空串跳过（见 _SKIP_IF_EMPTY 注释）；proxy 允许置空。
    - base_url 自动补 http:// 并校验；image_mode 只接受 auto/url/base64。
    返回实际写入的环境变量名列表。
    """
    applied: dict[str, str] = {}
    for ui, env in _ALL_UI_FIELDS.items():
        if ui not in updates or updates[ui] is None:
            continue
        val = str(updates[ui]).strip()
        if ui in _SKIP_IF_EMPTY and val == "":
            continue
        if ui.endswith("_base_url") and val:
            val = _normalize_base_url(val, field=ui)
        if ui == "image_mode" and val not in IMAGE_MODES:
            raise ValueError(f"image_mode 只支持 {', '.join(IMAGE_MODES)}，收到：{val}")
        os.environ[env] = val
        applied[env] = val
    if applied:
        _persist(applied)
    return list(applied.keys())


def test_connection(target: str) -> dict[str, Any]:
    """用当前生效配置探测某个能力是否可用（设置页「测试连接」按钮）。

    - asr：只调上传凭证接口（不产生转写费用）
    - vlm / llm：发一条极短 chat（最多 8 token）
    失败抛 RbcpError，由 route 层翻成人话 + 附服务端响应。
    """
    from app.extract.pipeline import _provider_from_env, build_proxies

    provider = _provider_from_env(
        shared_api_key(), proxies=build_proxies(os.getenv("RBCP_PROXY"))
    )
    return provider.probe(target)


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
