"""M6c · llm.py 解析鲁棒性测试（纯 str→结构，脱网）。"""

import json

from app.digest import llm
from app.extract.contracts import Segment


def test_parse_valid_json():
    raw = json.dumps({
        "highlights": [{"quote": "重点句", "importance": 0.9, "context_before": "前", "context_after": "后", "segment_id": 1}],
        "cards": [{"quote": "金句"}],
        "outline": [{"title": "小节", "quote": "原文句", "children": [{"title": "子节"}]}],
    })
    p = llm.parse_digest_json(raw)
    assert len(p.highlights) == 1 and p.highlights[0].weight == 0.9
    assert p.highlights[0].segment_id == 1
    assert len(p.cards) == 1 and p.cards[0].weight == 0.5  # cards 无 weight 默认 0.5
    assert p.outline[0].title == "小节" and p.outline[0].quote == "原文句"
    assert p.outline[0].children[0].title == "子节"
    assert p.diagnostics == ()


def test_parse_strips_code_fence():
    raw = '```json\n{"highlights":[{"quote":"x重点"}]}\n```'
    p = llm.parse_digest_json(raw)
    assert len(p.highlights) == 1 and p.highlights[0].quote == "x重点"


def test_parse_truncates_surrounding_garbage():
    raw = '模型废话开头 {"cards":[{"quote":"金句来了"}]} 结尾废话'
    p = llm.parse_digest_json(raw)
    assert len(p.cards) == 1


def test_parse_malformed_degrades_to_diagnostic():
    p = llm.parse_digest_json("完全不是 JSON 啊啊啊")
    assert p.highlights == () and p.cards == () and p.outline == ()
    assert len(p.diagnostics) == 1
    assert p.diagnostics[0].quote == "<llm_json_parse_failed>"


def test_parse_drops_items_without_quote():
    raw = json.dumps({"highlights": [{"quote": ""}, {"importance": 0.5}, {"quote": "有效句"}]})
    p = llm.parse_digest_json(raw)
    assert len(p.highlights) == 1 and p.highlights[0].quote == "有效句"


def test_parse_clamps_and_defaults_importance():
    raw = json.dumps({"highlights": [
        {"quote": "超界", "importance": 5.0},
        {"quote": "负的", "importance": -1},
        {"quote": "非数", "importance": "abc"},
    ]})
    p = llm.parse_digest_json(raw)
    weights = [h.weight for h in p.highlights]
    assert weights == [1.0, 0.0, 0.5]


def test_parse_bool_importance_uses_default():
    # bool 是 int 子类：true/false 不当权重，走默认 0.5（对抗审查 nit）。
    raw = json.dumps({"highlights": [{"quote": "句子内容", "importance": True}]})
    assert llm.parse_digest_json(raw).highlights[0].weight == 0.5


def test_parse_outline_depth_capped():
    # 构造超过 5 层的嵌套，超出被截
    node: dict = {"title": "L6"}
    for i in range(6):
        node = {"title": f"L{5 - i}", "children": [node]}
    p = llm.parse_digest_json(json.dumps({"outline": [node]}))
    # 数实际深度
    depth, cur = 1, p.outline
    while cur and cur[0].children:
        depth += 1
        cur = cur[0].children
    assert depth <= 5


def test_build_prompt_includes_segments():
    segs = (Segment("第一段", None, None, None, 0, 3), Segment("第二段", None, None, None, 3, 6))
    prompt = llm.build_prompt("第一段第二段", segs)
    assert "seg0: 第一段" in prompt and "seg1: 第二段" in prompt
    assert "只输出 JSON" in prompt
    # 无 segments 时不附分段
    assert "seg0:" not in llm.build_prompt("纯文本", None)
