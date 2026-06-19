"""M6c · orchestrator 端到端测试（FakeProvider 脱网，驱动整条 digest）。"""

import json

import pytest

from app.digest.contracts import digest
from app.extract.contracts import Segment, text_fingerprint


class FakeProvider:
    """仅实现 complete_json，证明 digest 只靠鸭子类型、不依赖 DashscopeProvider。"""

    llm_model = "fake-model"

    def __init__(self, json_str: str):
        self._json = json_str

    def complete_json(self, prompt: str, *, operation: str = "digest"):
        return self._json, {"total_tokens": 1}


def test_end_to_end_anchors_three_forms():
    text = "今天天气很好。我们去公园散步。"
    payload = json.dumps({
        "highlights": [{"quote": "今天天气很好。", "importance": 0.9,
                        "context_before": "", "context_after": "我们去公园散步。"}],
        "cards": [{"quote": "我们去公园散步。"}],
        "outline": [{"title": "概述", "quote": "今天天气很好。"}],
    })
    r = digest(text, provider=FakeProvider(payload))

    # 坐标系契约：source_text_sha256 一律重算自 text，不抄入参
    assert r.source_text_sha256 == text_fingerprint(text)
    assert r.coordinate_space == "python_codepoint"
    assert r.model == "fake-model"

    assert len(r.highlights) == 1
    h = r.highlights[0]
    assert text[h.span_start:h.span_end] == "今天天气很好。"
    assert h.weight == 0.9
    assert h.span_start == h.source.char_start  # __post_init__ 不变量

    assert len(r.cards) == 1 and r.cards[0].source is not None
    assert len(r.outline) == 1 and r.outline[0].title == "概述"
    assert r.outline[0].source is not None


def test_unanchorable_highlight_goes_to_diagnostics():
    text = "真实原文内容在这里。"
    payload = json.dumps({"highlights": [
        {"quote": "这句完全不在原文里面出现过的话", "importance": 0.8}]})
    r = digest(text, provider=FakeProvider(payload))
    assert len(r.highlights) == 0
    assert any(d.kind == "unanchored" for d in r.diagnostics)


def test_card_unanchored_source_none_not_diagnostic():
    text = "原文一句话。"
    payload = json.dumps({"cards": [{"quote": "不存在的金句啊啊"}]})
    r = digest(text, provider=FakeProvider(payload))
    assert len(r.cards) == 1 and r.cards[0].source is None
    # card 锚不上 → source=None，不进 diagnostics（diagnostics 只服务 highlight 漏锚）
    assert r.diagnostics == ()


def test_malformed_llm_output_degrades():
    r = digest("原文", provider=FakeProvider("这不是 JSON"))
    assert r.highlights == () and r.cards == () and r.outline == ()
    assert any(d.quote == "<llm_json_parse_failed>" for d in r.diagnostics)


def test_seconds_mapped_via_segments():
    text = "第一句话。第二句话。"
    segs = (
        Segment("第一句话。", None, 0.0, 2.0, 0, 5),
        Segment("第二句话。", None, 2.0, 4.0, 5, 10),
    )
    payload = json.dumps({"highlights": [{"quote": "第二句话。", "importance": 1.0}]})
    r = digest(text, provider=FakeProvider(payload), segments=segs)
    assert len(r.highlights) == 1
    assert r.highlights[0].source.seconds == 2.0  # 落 seg1 → start_sec=2.0


def test_matching_sha_passes_guard_and_runs():
    text = "原文内容很长够锚定"
    fp = text_fingerprint(text)
    r = digest(text, provider=FakeProvider('{"highlights":[]}'), text_sha256=fp)
    assert r.source_text_sha256 == fp


def test_mismatched_sha_rejected_before_llm():
    # provider 会抛，证明 guard 在调 provider 之前就拦下
    class Boom:
        def complete_json(self, *a, **k):
            raise AssertionError("provider 不该被调用")
    with pytest.raises(ValueError):
        digest("原文", provider=Boom(), text_sha256="wrong-fingerprint")
