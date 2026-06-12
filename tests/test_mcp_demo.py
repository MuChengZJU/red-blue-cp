"""MCP demo 测试 — 按 app/mcp/CONTRACT.md「测试契约」逐条覆盖。
风格仿 tests/test_routes.py：真 Storage 落 tmp_path + MagicMock pipeline +
job_runner=lambda fn: fn()（同步内联）。fixture 的 md 保留真产物特征：完整
frontmatter（照 note.md.j2 字段）+ CJK 标题正文 + 「说话人1：」行 + 原链接。
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.mcp.protocol import (LATEST_PROTOCOL_VERSION, SERVER_INFO,
                              SUPPORTED_PROTOCOL_VERSIONS, handle_message, serve)
from app.mcp.tools import ToolContext, ToolDef, build_tools
from app.service.errors import NetworkError
from app.service.storage import Storage

BILI_URL = "https://www.bilibili.com/video/BV1GJ411x7h7/"
XHS_URL = "https://www.xiaohongshu.com/explore/65f1a2b3c4d5e6f7a8b9c0d1"
TITLE = "大模型推理加速实战分享"
AUTHOR = "测试UP主"
BODY = ("说话人1：大家好，今天聊聊大模型推理加速，重点是 KV 缓存优化。\n\n"
        "说话人2：好的，先从显存占用说起，KV 缓存是推理时的大头。\n")
_INIT = {"capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}


def write_note_md(path: Path, *, title=TITLE, author=AUTHOR, url=BILI_URL, body=BODY):
    """照 app/service/templates/note.md.j2 写一篇像真产物的 md。"""
    path.write_text(
        f"""---
platform: bilibili
type: video
url: {url}
author: {author}
author_id: 12345
title: {title}
published_at: 2026-05-01
fetched_at: 2026-06-01T12:00:00
duration_sec: 613
asr_model: paraformer-v2
speaker_count: 2
status: ok
tags: []
---

# {title}

> [{author}](https://space.bilibili.com/12345) · 2026-05-01 · [原链接]({url})

## 转录文本 / 图文 OCR

{body}
""", encoding="utf-8")


@pytest.fixture
def output_dir(tmp_path):
    (tmp_path / "transcript").mkdir()
    return tmp_path / "transcript"


@pytest.fixture
def storage(output_dir):
    return Storage(output_dir / "_index.sqlite")


@pytest.fixture
def mock_pipeline(output_dir):
    """副作用真写出 md 文件（mark_done 后 read 二次调用要能真读到）。"""
    pipe = MagicMock()

    def _run(url):
        md_path = output_dir / "2026-06-01-测试UP主-大模型推理加速实战分享-BV1GJ411x7h7.md"
        write_note_md(md_path, url=url)
        return {"md_path": str(md_path), "title": TITLE, "author": AUTHOR,
                "platform": "bilibili", "content_type": "video", "usage": None}

    pipe.side_effect = _run
    return pipe


@pytest.fixture
def ctx(output_dir, storage, mock_pipeline):
    return ToolContext(output_dir=output_dir, storage_factory=lambda: storage,
                       pipeline_fn=mock_pipeline, job_runner=lambda fn: fn())


@pytest.fixture
def tools(ctx):
    return build_tools(ctx)


def call_tool(tools, name, arguments):
    return next(t for t in tools if t.name == name).handler(arguments)


def rpc(method, id=None, params=None):
    msg = {"jsonrpc": "2.0", "method": method}
    msg.update({k: v for k, v in (("id", id), ("params", params)) if v is not None})
    return msg


class TestProtocol:
    """协议层：直调 handle_message（纯函数）。"""

    def test_initialize_echoes_supported_version(self, tools):
        resp = handle_message(rpc("initialize", 1, {"protocolVersion": "2024-11-05", **_INIT}), tools)
        result = resp["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert result["serverInfo"] == SERVER_INFO
        assert result["capabilities"] == {"tools": {}}

    def test_initialize_unsupported_version_falls_back_to_latest(self, tools):
        resp = handle_message(rpc("initialize", 1, {"protocolVersion": "2010-01-01", **_INIT}), tools)
        assert resp["result"]["protocolVersion"] == LATEST_PROTOCOL_VERSION
        assert LATEST_PROTOCOL_VERSION in SUPPORTED_PROTOCOL_VERSIONS

    def test_tools_list_has_4_tools_with_camel_input_schema(self, tools):
        listed = handle_message(rpc("tools/list", 2), tools)["result"]["tools"]
        assert {t["name"] for t in listed} == {"read", "search", "list_recent", "get_status"}
        for t in listed:
            assert "inputSchema" in t and "input_schema" not in t
            assert t["description"]

    def test_ping_returns_empty_result(self, tools):
        assert handle_message(rpc("ping", 3), tools)["result"] == {}

    def test_unknown_method_returns_32601(self, tools):
        assert handle_message(rpc("resources/list", 4), tools)["error"]["code"] == -32601

    def test_notification_returns_none(self, tools):
        assert handle_message(rpc("notifications/initialized"), tools) is None
        assert handle_message(rpc("notifications/cancelled"), tools) is None

    def test_tools_call_unknown_tool_returns_32602(self, tools):
        resp = handle_message(rpc("tools/call", 5, {"name": "no_such_tool", "arguments": {}}), tools)
        assert resp["error"]["code"] == -32602

    def test_tools_call_result_shape(self, tools):
        resp = handle_message(rpc("tools/call", 6, {"name": "list_recent", "arguments": {}}), tools)
        result = resp["result"]
        assert result["isError"] is False
        assert result["content"][0]["type"] == "text"
        json.loads(result["content"][0]["text"])  # block 是合法 JSON 文本

    def test_handler_exception_caught_as_is_error(self):
        boom = ToolDef(name="boom", description="炸", input_schema={"type": "object"},
                       handler=lambda args: 1 / 0)
        result = handle_message(rpc("tools/call", 7, {"name": "boom", "arguments": {}}), [boom])["result"]
        assert result["isError"] is True
        assert "Traceback" not in result["content"][0]["text"]  # 人话，不是 traceback


class TestServe:
    def test_bad_json_line_does_not_crash_loop(self, tools):
        lines = [
            json.dumps(rpc("initialize", 1, {"protocolVersion": LATEST_PROTOCOL_VERSION, **_INIT})),
            json.dumps(rpc("notifications/initialized")),
            "{这不是合法 JSON",
            json.dumps(rpc("tools/list", 2)),
            json.dumps(rpc("ping", 3)),
        ]
        stdout = io.StringIO()
        serve(tools, stdin=io.StringIO("\n".join(lines) + "\n"), stdout=stdout)  # EOF 干净退出
        out_lines = [ln for ln in stdout.getvalue().splitlines() if ln.strip()]
        assert len(out_lines) == 4  # notification 不响应；坏行回 -32700；单行 JSON 无内嵌换行
        by_id = {r.get("id"): r for r in map(json.loads, out_lines)}
        assert by_id[1]["result"]["serverInfo"]["name"] == "rbcp-mcp-demo"
        assert by_id[None]["error"]["code"] == -32700
        assert len(by_id[2]["result"]["tools"]) == 4
        assert by_id[3]["result"] == {}


class TestRead:
    def test_cold_start_then_cache_hit(self, tools, storage, mock_pipeline):
        res1 = call_tool(tools, "read", {"url": BILI_URL})
        meta1 = json.loads(res1.blocks[0])
        assert res1.is_error is False
        assert meta1["status"] == "started" and "get_status" in meta1["hint"]
        assert mock_pipeline.called
        assert storage.get_job(meta1["job_id"])["status"] == "done"  # 同步 runner 已内联跑完

        res2 = call_tool(tools, "read", {"url": BILI_URL})
        meta2 = json.loads(res2.blocks[0])
        assert meta2["status"] == "ready" and meta2["title"] == TITLE
        for key in ("job_id", "author", "platform", "url", "md_path"):
            assert key in meta2
        assert len(res2.blocks) == 2 and "说话人1：" in res2.blocks[1] and "原链接" in res2.blocks[1]
        assert len(storage.list_jobs()) == 1  # 命中不建新 job

    def test_in_progress_dedup_no_new_job(self, tools, storage, mock_pipeline):
        job_id = storage.create_job(BILI_URL)
        storage.mark_running(job_id)
        meta = json.loads(call_tool(tools, "read", {"url": BILI_URL}).blocks[0])
        assert meta["status"] == "transcribing" and meta["job_id"] == job_id
        assert len(storage.list_jobs()) == 1
        assert not mock_pipeline.called

    def test_done_but_md_deleted_retranscribes(self, tools, storage):
        call_tool(tools, "read", {"url": BILI_URL})
        Path(storage.list_jobs()[0]["md_path"]).unlink()
        res = call_tool(tools, "read", {"url": BILI_URL})
        assert json.loads(res.blocks[0])["status"] == "started"  # 视为未命中 → 重新转录
        assert len(storage.list_jobs()) == 2
        res3 = call_tool(tools, "read", {"url": BILI_URL})
        assert json.loads(res3.blocks[0])["status"] == "ready"  # md 已重建，再读命中

    def test_invalid_url_is_error(self, tools, storage):
        res = call_tool(tools, "read", {"url": "https://www.youtube.com/watch?v=abc"})
        assert res.is_error is True and "不支持" in res.blocks[0]
        assert storage.list_jobs() == []  # 不建 job

    def test_pipeline_failure_persists_sanitized_excerpt(self, tools, storage, mock_pipeline):
        mock_pipeline.side_effect = NetworkError("DashScope llm_clean 网络重试 3 次仍失败")
        res = call_tool(tools, "read", {"url": BILI_URL})
        job = storage.get_job(json.loads(res.blocks[0])["job_id"])
        assert job["status"] == "failed"
        assert job["error_message"] and job["log_excerpt"]
        for leak in ("/Users/", "/home/", ".py", 'File "', "site-packages", ".venv"):
            assert leak not in job["log_excerpt"], f"log_excerpt 泄漏了 {leak!r}"

    def test_share_text_url_extracted(self, tools, storage):
        raw = f"【{TITLE}】 {BILI_URL}?share_source=copy_web&vd_source=abc 复制打开哔哩哔哩"
        call_tool(tools, "read", {"url": raw})
        assert storage.list_jobs()[0]["url"] == BILI_URL


class TestSearch:
    def test_hit_returns_frontmatter_fields_and_snippet(self, tools, output_dir):
        write_note_md(output_dir / "a.md")
        res = call_tool(tools, "search", {"query": "推理加速"})
        assert res.is_error is False
        data = json.loads(res.blocks[0])
        assert data["total_matched"] == 1
        hit = data["results"][0]
        assert hit["title"] == TITLE and hit["url"] == BILI_URL  # 来自 frontmatter
        assert hit["author"] == AUTHOR
        assert "推理加速" in hit["snippet"]
        assert "\n" not in hit["snippet"]  # 换行折叠为空格

    def test_multi_word_and_semantics(self, tools, output_dir):
        write_note_md(output_dir / "a.md")  # 含「推理」+「显存」
        write_note_md(output_dir / "b.md", title="纯优化笔记", body="说话人1：只聊显存。\n")
        data = json.loads(call_tool(tools, "search", {"query": "显存 推理"}).blocks[0])
        assert data["total_matched"] == 1
        assert data["results"][0]["title"] == TITLE

    def test_no_match_returns_zero(self, tools, output_dir):
        write_note_md(output_dir / "a.md")
        data = json.loads(call_tool(tools, "search", {"query": "量子纠缠"}).blocks[0])
        assert data["total_matched"] == 0 and data["results"] == []

    def test_blank_query_is_error(self, tools):
        assert call_tool(tools, "search", {"query": "   "}).is_error is True

    def test_file_without_frontmatter_does_not_crash(self, tools, output_dir):
        (output_dir / "broken.md").write_text("没有 frontmatter，但提到了推理。", encoding="utf-8")
        write_note_md(output_dir / "a.md")
        data = json.loads(call_tool(tools, "search", {"query": "推理"}).blocks[0])
        assert data["total_matched"] == 2
        assert "broken" in {r["title"] for r in data["results"]}  # 缺 frontmatter 退化用文件名 stem


class TestListRecentAndGetStatus:
    def test_list_recent_happy_path(self, tools, storage, output_dir):
        md = output_dir / "a.md"
        write_note_md(md)
        done_id = storage.create_job(BILI_URL)
        storage.mark_running(done_id)
        storage.mark_done(done_id, md_path=str(md), title=TITLE, author=AUTHOR,
                          platform="bilibili", content_type="video",
                          usage={"total_cost_yuan": 0.05})
        pending_id = storage.create_job(XHS_URL)
        data = json.loads(call_tool(tools, "list_recent", {"limit": 10}).blocks[0])
        assert {j["job_id"] for j in data["jobs"]} == {done_id, pending_id}
        for j in data["jobs"]:
            for key in ("job_id", "status", "title", "author", "platform", "url", "created_at"):
                assert key in j
        assert data["library_total_cost_yuan"] == pytest.approx(0.05)

    def test_get_status_done_has_hint(self, tools, storage, output_dir):
        md = output_dir / "a.md"
        write_note_md(md)
        job_id = storage.create_job(BILI_URL)
        storage.mark_running(job_id)
        storage.mark_done(job_id, md_path=str(md), title=TITLE)
        data = json.loads(call_tool(tools, "get_status", {"job_id": job_id}).blocks[0])
        assert data["job_id"] == job_id and data["status"] == "done"
        for key in ("title", "url", "error_message", "log_excerpt"):
            assert key in data
        assert "read" in data["hint"]

    def test_get_status_missing_job_is_error(self, tools):
        res = call_tool(tools, "get_status", {"job_id": 99999})
        assert res.is_error is True and "不存在" in res.blocks[0]
