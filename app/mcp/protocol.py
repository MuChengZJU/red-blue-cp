"""MCP stdio 协议层：JSON-RPC 2.0 逐行读写 + 方法分发，不含业务。

工具通过参数注入（list[ToolDef]，鸭子类型访问 name/description/input_schema/handler），
本模块不 import tools。协议行为依据 docs/devlog/2026-06-12-mcp-protocol-spec-notes.md。
"""

from __future__ import annotations

import json
import logging
import sys

logger = logging.getLogger(__name__)

SERVER_INFO = {"name": "rbcp-mcp-demo", "version": "0.1.0"}
SUPPORTED_PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
LATEST_PROTOCOL_VERSION = "2025-11-25"

# JSON-RPC 2.0 标准错误码
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _result(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_message(msg: dict, tools: list) -> dict | None:
    """处理一条已解析的 JSON-RPC 消息，返回响应 dict；notification 返回 None。

    纯函数（不读写 IO），便于单测。handler 抛任意异常在此兜底成 isError 结果。
    """
    method = msg.get("method")
    params = msg.get("params")
    if not isinstance(params, dict):
        params = {}

    # notifications/* 一律忽略；其余无 id 的消息按 JSON-RPC notification 处理，不响应
    if isinstance(method, str) and method.startswith("notifications/"):
        logger.debug("忽略 notification: %s", method)
        return None
    if "id" not in msg:
        logger.debug("忽略无 id 消息: %s", method)
        return None

    req_id = msg["id"]

    if method == "initialize":
        client_version = params.get("protocolVersion")
        version = (
            client_version
            if client_version in SUPPORTED_PROTOCOL_VERSIONS
            else LATEST_PROTOCOL_VERSION
        )
        return _result(req_id, {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })

    if method == "ping":
        return _result(req_id, {})

    if method == "tools/list":
        return _result(req_id, {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.input_schema,
                }
                for t in tools
            ]
        })

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        tool = next((t for t in tools if t.name == name), None)
        if tool is None:
            return _error(req_id, INVALID_PARAMS, f"Unknown tool: {name}")
        try:
            result = tool.handler(arguments)
            blocks, is_error = list(result.blocks), bool(result.is_error)
        except Exception as exc:  # 兜底：handler 抛什么都不许打断循环
            logger.exception("工具 %s 执行异常", name)
            blocks, is_error = [f"工具执行失败：{exc}"], True
        return _result(req_id, {
            "content": [{"type": "text", "text": b} for b in blocks],
            "isError": is_error,
        })

    return _error(req_id, METHOD_NOT_FOUND, f"Method not found: {method}")


def _write(stdout, msg: dict) -> None:
    # 单行 JSON + 换行（消息内禁止内嵌裸换行），写完即 flush
    stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    stdout.flush()


def serve(tools: list, stdin=None, stdout=None) -> None:
    """stdio 主循环：逐行读 stdin -> handle_message -> 写 stdout。EOF 干净退出。"""
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            _write(stdout, _error(None, PARSE_ERROR, "Parse error"))
            continue
        if not isinstance(msg, dict):
            _write(stdout, _error(None, INVALID_REQUEST, "Invalid Request"))
            continue
        try:
            response = handle_message(msg, tools)
        except Exception:  # 最后防线：协议层自身异常也不许崩循环
            logger.exception("handle_message 异常")
            _write(stdout, _error(msg.get("id"), INTERNAL_ERROR, "Internal error"))
            continue
        if response is not None:
            _write(stdout, response)
