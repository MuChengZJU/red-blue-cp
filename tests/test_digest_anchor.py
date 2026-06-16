"""M6c · anchor.py 纯锚定核心测试。锁 judge 方案的 must-test 不变量。"""

import pytest

from app.digest import anchor
from app.extract.contracts import Segment


def _seg(text, cs, ce, start=None, end=None, sid="0"):
    return Segment(text=text, speaker_id=sid, start_sec=start, end_sec=end, char_start=cs, char_end=ce)


def _anchor(canonical, quote, before="", after="", seg_id=None, segments=None):
    norm, back = anchor.build_norm_index(canonical)
    return anchor.anchor_one(canonical, norm, back, quote, before, after, seg_id, segments)


# ── 归一化可逆 ───────────────────────────────────────────────
def test_norm_back_map_reversible_fullwidth():
    canonical = "全角ＡＢＣＤ结尾"
    norm, back = anchor.build_norm_index(canonical)
    assert "abcd" in norm
    ns = norm.index("abcd")
    cs, ce = back[ns], back[ns + 3] + 1
    assert canonical[cs:ce] == "ＡＢＣＤ"


def test_norm_folds_whitespace_run_to_single_space():
    canonical = "你好\n\n　世界"  # 含全角空格 + 双换行
    norm, _ = anchor.build_norm_index(canonical)
    assert norm == "你好 世界"  # 连续空白折成单空格


def test_norm_maps_pairs_and_nfkc_folds_cjk_punct():
    norm, _ = anchor.build_norm_index("“引号”和，逗号")
    assert '"引号"和' in norm  # 成对引号 → ASCII（_PUNCT_MAP）
    assert "," in norm and "，" not in norm  # 全角逗号 → 半角（NFKC，接受这层折叠）


# ── anchor_one 各分支 ────────────────────────────────────────
def test_exact_unique():
    o = _anchor("这是一句话。", "一句话")
    assert o.status == "exact" and o.confidence == 1.0
    assert (o.char_start, o.char_end) == (2, 5)
    assert o.diagnostic_kind is None


def test_normalized_unique():
    o = _anchor("全角ＡＢＣＤ结尾", "abcd")
    assert o.status == "normalized" and o.confidence == 0.8
    assert "全角ＡＢＣＤ结尾"[o.char_start:o.char_end] == "ＡＢＣＤ"
    assert o.diagnostic_kind is None


def test_multi_candidate_disambiguated_by_context():
    canonical = "甲说我喜欢猫。乙说我喜欢猫。"
    o = _anchor(canonical, "我喜欢猫。", before="乙说")
    assert o.diagnostic_kind is None
    assert o.status == "exact" and o.confidence == 0.9  # 消歧档
    assert (o.char_start, o.char_end) == (9, 14)  # 选了第二处（乙说后）


def test_ambiguous_goes_to_diagnostics():
    o = _anchor("我喜欢猫。我喜欢猫。", "我喜欢猫。")  # 无 context，两处全等
    assert o.diagnostic_kind == "ambiguous"
    assert o.confidence <= 0.5  # 不进 highlights


def test_zero_match_unanchored():
    o = _anchor("毫不相关的内容", "完全不存在的另一句")
    assert o.status == "unanchored" and o.confidence == 0.0
    assert o.diagnostic_kind == "unanchored"


def test_short_normalized_quote_low_confidence():
    # exact 失败（全角），normalized quote 太短（<4）→ low_confidence 不锚
    o = _anchor("ＡＢ结尾", "ab")
    assert o.status == "unanchored" and o.diagnostic_kind == "low_confidence"
    assert o.char_start is None


def test_segment_id_soft_bonus_breaks_tie():
    canonical = "我喜欢猫。我喜欢猫。"
    segs = (_seg("我喜欢猫。", 0, 5), _seg("我喜欢猫。", 5, 10))
    o = _anchor(canonical, "我喜欢猫。", seg_id=1, segments=segs)  # 提示第二段
    assert o.diagnostic_kind is None
    assert (o.char_start, o.char_end) == (5, 10)


# ── seconds_for_char 全分支 ──────────────────────────────────
def test_seconds_covering_and_gap_and_beyond():
    segs = (_seg("你好", 0, 5, start=0.0), _seg("再见", 7, 12, start=5.0))  # 缝隙 [5,7)
    assert anchor.seconds_for_char(0, segs) == 0.0     # 覆盖 seg0
    assert anchor.seconds_for_char(4, segs) == 0.0     # seg0 末字符前
    assert anchor.seconds_for_char(5, segs) == 5.0     # 缝隙→右邻 seg1
    assert anchor.seconds_for_char(7, segs) == 5.0     # 覆盖 seg1
    assert anchor.seconds_for_char(12, segs) is None   # 超末段


def test_seconds_none_cases():
    assert anchor.seconds_for_char(0, None) is None        # 图文
    assert anchor.seconds_for_char(0, ()) is None          # 空 segments
    assert anchor.seconds_for_char(None, (_seg("x", 0, 1, start=1.0),)) is None
    # 命中但 segment 没 start_sec → None（不瞎补）
    assert anchor.seconds_for_char(0, (_seg("x", 0, 3, start=None),)) is None


# ── 单一构造点满足 Highlight.__post_init__ ───────────────────
def test_make_highlight_span_binds_source():
    segs = (_seg("一句话", 0, 5, start=1.0),)
    h = anchor.make_highlight(0, 5, 0.9, segs, "exact", 1.0)
    assert h.span_start == h.source.char_start == 0
    assert h.span_end == h.source.char_end == 5
    assert h.source.seconds == 1.0


def test_make_source_ref_seconds_wired():
    segs = (_seg("一句话", 0, 5, start=2.5),)
    ref = anchor.make_source_ref(2, 4, segs, "normalized", 0.8)
    assert ref.anchoring_status == "normalized" and ref.confidence == 0.8
    assert ref.seconds == 2.5
