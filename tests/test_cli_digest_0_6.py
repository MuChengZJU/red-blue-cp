"""M6f · rbcp digest 命令 + Extract 门面动词测试（全程脱网，mock provider）。

验证：
1. `rbcp digest <url> --json` 输出符合 0.6 digest-json 契约（顶层 extract/digest 信封、
   坐标系字段、highlight span==source.char、source_text_sha256==extract.text_sha256）。
2. 非 --json 给人看的精简渲染含高亮/金句/脉络。
3. Extract 门面动词（extract / list_blogger / Jobs / search）接线正确（不再 NotImplementedError）。
禁止真实 API：provider.complete_json 与 extract_url 全 mock。
"""

from __future__ import annotations

import json

from typer.testing import CliRunner
from unittest.mock import patch

from app.cli import app
from app.extract.contracts import (
    ExtractResult,
    Segment,
    text_fingerprint,
)

runner = CliRunner()


# 与契约样例同形：三句单说话人 ASR，char 区间与 canonical text 对齐。
_CANONICAL = "今天聊大模型推理加速。核心瓶颈是显存带宽。投机解码能提速两到三倍。"
_SEGMENTS = (
    Segment(text="今天聊大模型推理加速。", speaker_id="0", start_sec=0.0, end_sec=3.2,
            char_start=0, char_end=11),
    Segment(text="核心瓶颈是显存带宽。", speaker_id="0", start_sec=3.2, end_sec=7.0,
            char_start=11, char_end=21),
    Segment(text="投机解码能提速两到三倍。", speaker_id="0", start_sec=7.0, end_sec=11.5,
            char_start=21, char_end=33),
)


class _FakeProvider:
    """只实现 digest 需要的 complete_json（鸭子类型）。llm_model 进 DigestResult.model。"""

    llm_model = "qwen-plus"

    def complete_json(self, prompt: str, *, operation: str = "digest"):
        payload = json.dumps({
            "highlights": [
                {"quote": "核心瓶颈是显存带宽。", "importance": 0.95,
                 "context_before": "今天聊大模型推理加速。", "context_after": "投机解码能提速两到三倍。"},
                {"quote": "投机解码能提速两到三倍。", "importance": 0.9,
                 "context_before": "核心瓶颈是显存带宽。", "context_after": ""},
            ],
            "cards": [
                {"quote": "核心瓶颈是显存带宽。", "context_before": "今天聊大模型推理加速。",
                 "context_after": "投机解码能提速两到三倍。"},
                {"quote": "原文没有的金句"},  # 锚不回 → source 为 null
            ],
            "outline": [
                {"title": "推理加速要点", "quote": "今天聊大模型推理加速。", "children": [
                    {"title": "瓶颈", "quote": "核心瓶颈是显存带宽。"},
                    {"title": "优化", "quote": "投机解码能提速两到三倍。"},
                ]},
            ],
        }, ensure_ascii=False)
        return payload, {"total_tokens": 42}


def _fake_extract_result() -> ExtractResult:
    return ExtractResult(
        platform="bilibili",
        content_type="video",
        title="推理加速分享",
        author="某up",
        author_id=None,
        published_at=None,
        url="https://www.bilibili.com/video/BV1xx",
        text=_CANONICAL,
        readable_text=_CANONICAL,
        text_sha256=text_fingerprint(_CANONICAL),
        metadata={},
        segments=_SEGMENTS,
    )


def _patch_engine():
    """mock 掉 provider 构造 + extract_url，全程脱网。"""
    prov = patch("app.extract.pipeline._provider_from_env", return_value=_FakeProvider())
    ext = patch("app.cli.extract_url", return_value=_fake_extract_result())
    return prov, ext


def test_digest_json_matches_contract():
    prov, ext = _patch_engine()
    with prov, ext:
        result = runner.invoke(app, ["digest", "https://www.bilibili.com/video/BV1xx", "--json"])
    assert result.exit_code == 0, result.stdout
    envelope = json.loads(result.stdout)

    # 顶层信封
    assert set(envelope.keys()) == {"extract", "digest"}
    extract = envelope["extract"]
    digest = envelope["digest"]

    # extract 子集
    assert extract["canonical_text"] == _CANONICAL
    assert extract["text_sha256"] == text_fingerprint(_CANONICAL)
    assert isinstance(extract["segments"], list) and len(extract["segments"]) == 3
    seg0 = extract["segments"][0]
    assert {"text", "speaker_id", "start_sec", "end_sec", "char_start", "char_end"} <= set(seg0)

    # digest 坐标系契约
    assert digest["coordinate_space"] == "python_codepoint"
    assert digest["normalization_version"] == "v1"
    # source_text_sha256 必须 == extract.text_sha256（坐标未漂）
    assert digest["source_text_sha256"] == extract["text_sha256"]

    # highlight：span == source.char，且区间切出来是原文
    assert len(digest["highlights"]) == 2
    for h in digest["highlights"]:
        assert h["span_start"] == h["source"]["char_start"]
        assert h["span_end"] == h["source"]["char_end"]
        piece = _CANONICAL[h["span_start"]:h["span_end"]]
        assert piece  # 非空
    # 第一条命中「核心瓶颈是显存带宽。」→ seconds 取该 segment 的 start_sec
    h0 = digest["highlights"][0]
    assert _CANONICAL[h0["span_start"]:h0["span_end"]] == "核心瓶颈是显存带宽。"
    assert h0["source"]["seconds"] == 3.2

    # cards：一条锚回原文（source 非 null），一条锚不回（source == null 但 quote 保留）
    assert len(digest["cards"]) == 2
    assert digest["cards"][0]["source"] is not None
    assert digest["cards"][1]["source"] is None
    assert digest["cards"][1]["quote"] == "原文没有的金句"

    # outline 递归节点
    assert len(digest["outline"]) == 1
    root = digest["outline"][0]
    assert root["title"] == "推理加速要点"
    assert len(root["children"]) == 2
    assert root["children"][0]["title"] == "瓶颈"

    # model 来自 provider.llm_model
    assert digest["model"] == "qwen-plus"


def test_digest_human_readable_render():
    prov, ext = _patch_engine()
    with prov, ext:
        result = runner.invoke(app, ["digest", "https://www.bilibili.com/video/BV1xx"])
    assert result.exit_code == 0, result.stdout
    out = result.stdout
    assert "高亮" in out and "金句" in out and "脉络" in out
    assert "核心瓶颈是显存带宽。" in out  # 高亮句渲染出来
    assert "推理加速要点" in out          # 脉络标题渲染出来


def test_digest_failure_nonzero_exit():
    """extract_url 抛错 → 退出码非 0，--json 给 ok:false。"""
    prov = patch("app.extract.pipeline._provider_from_env", return_value=_FakeProvider())
    ext = patch("app.cli.extract_url", side_effect=RuntimeError("连接超时"))
    with prov, ext:
        result = runner.invoke(app, ["digest", "https://www.bilibili.com/video/BV1xx", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False


def test_digest_help_lists_command():
    result = runner.invoke(app, ["digest", "--help"])
    assert result.exit_code == 0
    assert "--json" in result.stdout


# ---------------- Extract 门面动词 ----------------

def test_facade_extract_wires_pipeline(tmp_path):
    """facade.extract → extract_url + render_and_write，返回带 md_path 的 ExtractResult。"""
    from app.extract import facade

    with patch("app.extract.pipeline._provider_from_env", return_value=_FakeProvider()), \
         patch("app.extract.extractor.extract_url", return_value=_fake_extract_result()), \
         patch("app.extract.markdown.render_and_write", return_value=tmp_path / "x.md"):
        out = facade.extract("https://www.bilibili.com/video/BV1xx", output_dir=tmp_path)
    assert out.text == _CANONICAL
    assert out.md_path == str(tmp_path / "x.md")
    assert out.text_sha256 == text_fingerprint(_CANONICAL)


def test_facade_list_blogger_maps_to_postbrief():
    from app.extract import facade

    listing = {
        "notes": [
            {"note_id": "n1", "title": "标题一", "type": "image", "xsec_token": "tok1"},
            {"note_id": "n2", "title": None, "type": "video", "xsec_token": "tok2"},
        ],
    }
    with patch("app.extract.discover.discover_user_posts", new=_async_value(listing)):
        briefs = facade.list_blogger("https://www.xiaohongshu.com/user/profile/abc")
    assert len(briefs) == 2
    assert briefs[0].note_id == "n1" and briefs[0].title == "标题一"
    assert "n1" in briefs[0].url and "xsec_token=tok1" in briefs[0].url
    assert briefs[1].title is None


def test_facade_jobs_wraps_storage(tmp_path):
    from app.extract import facade

    jobs = facade.Jobs(output_dir=tmp_path)
    job_id = jobs.create("https://www.bilibili.com/video/BV1xx")
    assert isinstance(job_id, int)
    got = jobs.get(job_id)
    assert got is not None and got["url"].endswith("BV1xx")
    assert any(r["id"] == job_id for r in jobs.list(limit=10))
    assert jobs.total_cost_yuan() == 0.0  # 新建 job 无 usage


def test_facade_search_scans_markdown(tmp_path):
    from app.extract import facade

    (tmp_path / "推理加速分享.md").write_text("body", encoding="utf-8")
    (tmp_path / "无关笔记.md").write_text("body", encoding="utf-8")
    (tmp_path / "_index.sqlite").write_text("", encoding="utf-8")  # 内部文件应被跳过
    hits = facade.search("推理", output_dir=tmp_path)
    assert len(hits) == 1
    assert hits[0].title == "推理加速分享"


def _async_value(value):
    """把同步值包成可被 asyncio.run 跑的 coroutine（mock async 函数用）。"""
    async def _coro(*args, **kwargs):
        return value
    return _coro
