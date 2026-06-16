#!/usr/bin/env python3
"""RBCP Desktop sidecar：跑常驻 `rbcp serve`（桌面模式）。

Tauri 壳 spawn 本二进制 → serve 绑 127.0.0.1 + 随机端口 + 启动 token →
stdout 首行回吐 ``{"port": ..., "token": ...}`` 给壳，壳转给前端调本地 HTTP API。

约束：
- **绝不用 vendored 拷贝**，直接用仓库真实 ``app/``（单一真相源）。frozen(PyInstaller) 时
  ``app/`` 随包(_MEIPASS)；开发期把仓库根加进 sys.path。
- ``RBCP_DESKTOP=1`` 必须在 import ``app.web.routes`` 之前设好——它决定是否开 CORS、禁 pydoll 端点。
"""
from __future__ import annotations

import asyncio
import os
import sys

# 真实引擎 = 仓库 app/。frozen 时随包，开发期加仓库根。
if hasattr(sys, "_MEIPASS"):
    sys.path.insert(0, sys._MEIPASS)
else:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# 必须在任何 app.web 导入之前设：开 CORS + 禁 pydoll 端点。
os.environ["RBCP_DESKTOP"] = "1"

from app.config import load_config  # noqa: E402
from app.web import auth  # noqa: E402
from app.cli import _DesktopServer, _build_serve_config  # noqa: E402


def main() -> int:
    load_config()  # 桌面端 .env / 配置发现
    auth.new_token()  # 设进程级启动 token；_DesktopServer 会把它随 port 一起回吐
    cfg = _build_serve_config(desktop=True)  # 127.0.0.1 + port 0（内核分配）
    asyncio.run(_DesktopServer(cfg).serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
