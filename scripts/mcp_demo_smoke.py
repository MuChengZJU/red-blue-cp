#!/usr/bin/env python3
"""rbcp MCP demo 冒烟脚本（纯标准库）。

起 `python -m app.mcp` 子进程，按 NDJSON 走一遍最小握手 + 只读动词：
initialize → notifications/initialized → tools/list → search → list_recent。
全程不调 read——冒烟不触发转录、不花钱。

用法：
    python scripts/mcp_demo_smoke.py [--output-dir ~/transcript] [--query 关键词]

全部断言通过打 "SMOKE OK" 退出码 0，任一失败退出码非 0。
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

TIMEOUT_SECONDS = 10  # 单条响应等待上限，防挂死
PRINT_LIMIT = 800     # 响应行打印截断长度，避免刷屏


class SmokeFailure(Exception):
    """断言失败 / 超时 / 协议错误，统一走非 0 退出。"""


def _pump(stream, q: queue.Queue) -> None:
    # 后台线程逐行搬运子进程 stdout，主线程用带超时的 Queue.get 读，防挂死
    for line in stream:
        q.put(line)


def _send(proc: subprocess.Popen, msg: dict, label: str) -> None:
    print(f"-> {label}")
    proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
    proc.stdin.flush()


def _recv(q: queue.Queue, proc: subprocess.Popen, label: str) -> dict:
    try:
        line = q.get(timeout=TIMEOUT_SECONDS)
    except queue.Empty:
        code = proc.poll()
        extra = f"（子进程已退出，returncode={code}）" if code is not None else ""
        raise SmokeFailure(f"{label}: {TIMEOUT_SECONDS}s 内未收到响应{extra}")
    shown = line.rstrip("\n")
    if len(shown) > PRINT_LIMIT:
        shown = shown[:PRINT_LIMIT] + f"...（截断，全长 {len(shown)} 字符）"
    print(f"<- {label}: {shown}")
    try:
        return json.loads(line)
    except json.JSONDecodeError as e:
        raise SmokeFailure(f"{label}: 响应不是合法 JSON：{e}")


def _result_of(resp: dict, label: str) -> dict:
    if "error" in resp:
        raise SmokeFailure(f"{label}: 返回 JSON-RPC error：{resp['error']}")
    if "result" not in resp:
        raise SmokeFailure(f"{label}: 响应缺 result 字段")
    return resp["result"]


def run_smoke(args: argparse.Namespace) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    if args.output_dir:
        env["RBCP_OUTPUT_DIR"] = str(Path(args.output_dir).expanduser())

    proc = subprocess.Popen(
        [sys.executable, "-m", "app.mcp"],
        cwd=repo_root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        # stderr 不接管：server 日志直接透传到终端，便于排查
        text=True,
        encoding="utf-8",
        env=env,
    )
    q: queue.Queue = queue.Queue()
    threading.Thread(target=_pump, args=(proc.stdout, q), daemon=True).start()

    try:
        # 1. initialize：result 必须带 serverInfo
        _send(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "mcp-demo-smoke", "version": "0.1.0"},
            },
        }, "initialize")
        result = _result_of(_recv(q, proc, "initialize"), "initialize")
        if "serverInfo" not in result:
            raise SmokeFailure("initialize: result 缺 serverInfo")

        # 2. initialized 通知：协议规定不响应，不等回包
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"},
              "notifications/initialized")

        # 3. tools/list：恰好 4 个工具
        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, "tools/list")
        result = _result_of(_recv(q, proc, "tools/list"), "tools/list")
        tools = result.get("tools", [])
        if len(tools) != 4:
            names = [t.get("name") for t in tools]
            raise SmokeFailure(f"tools/list: 期望 4 个工具，实际 {len(tools)} 个：{names}")

        # 4./5. 两个只读动词：result 必须有 content（绝不调 read，不花钱）
        calls = [
            (3, "search", {"query": args.query}),
            (4, "list_recent", {}),
        ]
        for call_id, name, arguments in calls:
            label = f"tools/call {name}"
            _send(proc, {
                "jsonrpc": "2.0", "id": call_id, "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }, label)
            result = _result_of(_recv(q, proc, label), label)
            if not result.get("content"):
                raise SmokeFailure(f"{label}: result 缺 content")
    finally:
        try:
            proc.stdin.close()  # EOF → server 干净退出
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="rbcp MCP demo 冒烟：只走只读动词（search / list_recent），不花钱")
    parser.add_argument("--output-dir", default=None,
                        help="知识库目录，覆盖 RBCP_OUTPUT_DIR（默认沿用现有环境 / ~/transcript）")
    parser.add_argument("--query", default="的",
                        help="search 关键词（默认「的」，中文库里几乎必命中）")
    args = parser.parse_args()
    try:
        run_smoke(args)
    except SmokeFailure as e:
        print(f"SMOKE FAIL: {e}", file=sys.stderr)
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
