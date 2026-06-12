"""python -m app.mcp 入口：加载 .env、日志走 stderr、接线 tools 并起 stdio 循环。"""

from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv

from app.mcp.protocol import serve
from app.mcp.tools import build_tools, create_default_context


def main() -> None:
    load_dotenv()
    # stdout 只许出 JSON-RPC 消息，所有日志一律 stderr
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    ctx = create_default_context()
    # 启动清理（同 web 入口 routes.cleanup_running_jobs）：上次转录中途被杀的 job
    # 会永久卡 running，进而让 read 的「进行中去重」永远拦住同一 URL。
    # 附带语义与 web 同款单进程假设：勿与 rbcp serve 同时跑同一个 _index.sqlite。
    ctx.storage_factory().cleanup_running()
    serve(build_tools(ctx))


if __name__ == "__main__":
    main()
