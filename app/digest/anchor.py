"""M6c · 确定性服务端锚定（纯函数核心，零 IO / LLM / provider）。

把 LLM 返回的 quote + 前后文 锚回 canonical text 的 codepoint 区间：exact → normalized 两层，
context 消歧，低置信/歧义只产 diagnostics 不进 highlights。所有区间左闭右开、针对 canonical text。

只依赖 app.extract.contracts（Segment）+ app.digest.contracts（SourceRef/Highlight/Diagnostic），
不碰 llm/provider/网络 → 可独立单测。设计见 devlog M6c judge 方案。
"""

from __future__ import annotations

import unicodedata
from bisect import bisect_right
from dataclasses import dataclass

from app.digest.contracts import Diagnostic, Highlight, SourceRef
from app.extract.contracts import Segment

# ── 旋钮（集中一处，改这里调行为）─────────────────────────────────
NORMALIZATION_VERSION = "v1"
HIGHLIGHT_MIN_CONFIDENCE = 0.7   # 进 highlights 硬门槛（唯一旋钮）
W = 32                           # context 消歧窗口（codepoint）
MIN_NORM_QUOTE_LEN = 4           # 短于此的 normalized 命中不锚（防短句误配）
_CTX_BEST_MIN = 0.6              # 多候选消歧：最高分须 >= 此
_CTX_MARGIN = 0.2               # 且最高分须比次高分高出此间隔
# confidence 阶梯
_CONF_EXACT_UNIQUE = 1.0
_CONF_EXACT_DISAMBIG = 0.9
_CONF_NORM_UNIQUE = 0.8
_CONF_NORM_DISAMBIG = 0.7
_CONF_AMBIGUOUS = 0.4            # 歧义/未过间隔：只进 diagnostics

# 标点白名单（v1 的一部分，改表必升 NORMALIZATION_VERSION）：只统一明显成对同义符号。
# 中文逗号句号等一律保留不折叠（避免短 quote 在 normalized 层误配）。
_PUNCT_MAP = {
    "“": '"', "”": '"', "‘": "'", "’": "'",  # 成对引号
    "—": "-", "–": "-",                                  # 破折号
    "…": "...",                                               # 省略号
}


@dataclass(frozen=True)
class AnchorOutcome:
    """anchor_one 的产出。orchestrator 据此分流 highlights vs diagnostics。"""

    status: str                  # exact | normalized | unanchored
    confidence: float
    char_start: int | None
    char_end: int | None
    diagnostic_kind: str | None  # None=干净锚定；否则 unanchored|ambiguous|low_confidence


# ── 归一化（可逆，带 back-map）─────────────────────────────────
def build_norm_index(canonical: str) -> tuple[str, list[int]]:
    """canonical → (norm, back)。norm[k] 来自 canonical[back[k]]。

    规则（v1，按顺序逐字符）：空白 run 折成单空格(back 指 run 首字符) → NFKC(仅结果长度==1才换)
    → casefold → 标点白名单。norm 命中区间 [ns,ne) 反查 canonical：cs=back[ns], ce=back[ne-1]+1。
    """
    norm_chars: list[str] = []
    back: list[int] = []
    i, n = 0, len(canonical)
    while i < n:
        ch = canonical[i]
        if ch.isspace():
            norm_chars.append(" ")
            back.append(i)
            j = i + 1
            while j < n and canonical[j].isspace():
                j += 1
            i = j
            continue
        # NFKC 把全角折半角（含全角 CJK 标点 ，。？！：； → ,.?!:;）。接受这层折叠：
        # exact 命中处理逐字复制(spike 实证 LLM 逐字)；normalized 仅 ≥4 字才用，短句误配风险低。
        nfkc = unicodedata.normalize("NFKC", ch)
        base = nfkc if len(nfkc) == 1 else ch
        for folded in base.casefold():
            mapped = _PUNCT_MAP.get(folded, folded)
            for mc in mapped:
                norm_chars.append(mc)
                back.append(i)
        i += 1
    return "".join(norm_chars), back


def _find_all(haystack: str, needle: str) -> list[tuple[int, int]]:
    """needle 在 haystack 的全部出现 [start,end)，按位置升序（含重叠，确定性）。"""
    if not needle:
        return []
    out: list[tuple[int, int]] = []
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx < 0:
            break
        out.append((idx, idx + len(needle)))
        start = idx + 1
    return out


def _shrink(canonical: str, cs: int, ce: int) -> tuple[int, int]:
    """端点收缩：span 两端不含空白/缝隙字符。"""
    while cs < ce and canonical[cs].isspace():
        cs += 1
    while ce > cs and canonical[ce - 1].isspace():
        ce -= 1
    return cs, ce


def find_all_exact(canonical: str, quote: str) -> list[tuple[int, int]]:
    q = quote.strip()
    if not q:
        return []
    return _find_all(canonical, q)


def find_all_normalized(
    canonical: str, norm: str, back: list[int], quote: str
) -> list[tuple[int, int]]:
    """normalized 层命中，映射回 canonical + 端点收缩 + 去重。短 quote 返回 []（调用方据此降级）。"""
    nq = build_norm_index(quote)[0].strip()
    if len(nq) < MIN_NORM_QUOTE_LEN:
        return []
    out: list[tuple[int, int]] = []
    for ns, ne in _find_all(norm, nq):
        cs, ce = _shrink(canonical, back[ns], back[ne - 1] + 1)
        if cs < ce:
            out.append((cs, ce))
    return list(dict.fromkeys(out))


def _common_prefix_len(a: str, b: str) -> int:
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    return i


def _common_suffix_len(a: str, b: str) -> int:
    i = 0
    while i < len(a) and i < len(b) and a[-1 - i] == b[-1 - i]:
        i += 1
    return i


def _context_score(
    canonical: str, norm_ctx_before: str, norm_ctx_after: str, cs: int, ce: int
) -> float:
    """候选 (cs,ce) 与 LLM ctx 的归一空间匹配分 ∈ [0,1]。"""
    left = build_norm_index(canonical[max(0, cs - W):cs])[0]
    right = build_norm_index(canonical[ce:ce + W])[0]
    lcs_b = _common_suffix_len(left, norm_ctx_before)
    lcs_a = _common_prefix_len(right, norm_ctx_after)
    denom = len(norm_ctx_before) + len(norm_ctx_after)
    if denom == 0:
        return 0.0
    return (lcs_b + lcs_a) / denom


def anchor_one(
    canonical: str,
    norm: str,
    back: list[int],
    quote: str,
    ctx_before: str,
    ctx_after: str,
    segment_id: int | None,
    segments: tuple[Segment, ...] | None,
) -> AnchorOutcome:
    """把一条 quote 锚到 canonical。确定性：同输入恒同输出。"""
    exact = find_all_exact(canonical, quote)
    if exact:
        candidates, status = exact, "exact"
        conf_unique, conf_disambig = _CONF_EXACT_UNIQUE, _CONF_EXACT_DISAMBIG
    else:
        nq = build_norm_index(quote)[0].strip()
        if 0 < len(nq) < MIN_NORM_QUOTE_LEN:
            # 太短只能 normalized 命中 → 不锚，记 low_confidence
            return AnchorOutcome("unanchored", 0.0, None, None, "low_confidence")
        candidates = find_all_normalized(canonical, norm, back, quote)
        status = "normalized"
        conf_unique, conf_disambig = _CONF_NORM_UNIQUE, _CONF_NORM_DISAMBIG

    if not candidates:
        return AnchorOutcome("unanchored", 0.0, None, None, "unanchored")

    if len(candidates) == 1:
        cs, ce = candidates[0]
        return AnchorOutcome(status, conf_unique, cs, ce, None)

    # ≥2 候选。先用 segment_id 硬收窄：若恰好一个候选落在提示段内 → 直接锚定（强信号）。
    seg_bounds = None
    if segment_id is not None and segments and 0 <= segment_id < len(segments):
        seg = segments[segment_id]
        seg_bounds = (seg.char_start, seg.char_end)
        in_seg = [(cs, ce) for cs, ce in candidates if seg.char_start <= cs < seg.char_end]
        if len(in_seg) == 1:
            return AnchorOutcome(status, conf_disambig, in_seg[0][0], in_seg[0][1], None)

    # 否则 context 消歧（归一空间）+ segment_id 软加分（用于段内多候选/段提示不唯一时）
    nb = build_norm_index(ctx_before)[0]
    na = build_norm_index(ctx_after)[0]

    scored: list[tuple[float, int, int, int]] = []  # (score, idx, cs, ce)
    for idx, (cs, ce) in enumerate(candidates):
        score = _context_score(canonical, nb, na, cs, ce)
        if seg_bounds and seg_bounds[0] <= cs < seg_bounds[1]:
            score += 0.3
        score += 1e-6 / (cs + 1)  # 极弱 tie-break，保确定性
        scored.append((score, idx, cs, ce))
    scored.sort(key=lambda t: (-t[0], t[2]))  # 高分优先，并列取靠前

    best = scored[0]
    second = scored[1]
    if best[0] >= _CTX_BEST_MIN and (best[0] - second[0]) >= _CTX_MARGIN:
        return AnchorOutcome(status, conf_disambig, best[2], best[3], None)
    # 未过明显间隔 / 都低 / 并列 → 歧义，进 diagnostics（suggested=最高分候选）
    return AnchorOutcome(status, _CONF_AMBIGUOUS, best[2], best[3], "ambiguous")


# ── char → 时间映射 ────────────────────────────────────────────
def seconds_for_char(
    char_start: int | None, segments: tuple[Segment, ...] | None
) -> float | None:
    """char_start → 覆盖它的 segment.start_sec；缝隙取右邻；图文/越界/无时间戳 → None。"""
    if char_start is None or not segments:
        return None
    starts = [s.char_start for s in segments]
    i = bisect_right(starts, char_start) - 1
    if i >= 0 and segments[i].char_start <= char_start < segments[i].char_end:
        return segments[i].start_sec
    j = bisect_right(starts, char_start)  # 缝隙 → 右邻 segment
    return segments[j].start_sec if j < len(segments) else None


# ── 单一构造点（满足 Highlight.__post_init__：span 与 source.char 同源）──
def make_source_ref(
    char_start: int, char_end: int, segments: tuple[Segment, ...] | None,
    status: str, confidence: float,
) -> SourceRef:
    return SourceRef(
        char_start=char_start, char_end=char_end,
        seconds=seconds_for_char(char_start, segments),
        image_index=None, anchoring_status=status, confidence=confidence,
    )


def make_highlight(
    char_start: int, char_end: int, weight: float,
    segments: tuple[Segment, ...] | None, status: str, confidence: float,
) -> Highlight:
    src = make_source_ref(char_start, char_end, segments, status, confidence)
    return Highlight(span_start=char_start, span_end=char_end, weight=weight, source=src)


def diagnostic_from(outcome: AnchorOutcome, quote: str, segments) -> Diagnostic:
    """歧义/未锚定 → Diagnostic。suggested 带（若有）最佳候选的低置信 SourceRef。"""
    suggested = None
    if outcome.char_start is not None and outcome.char_end is not None:
        suggested = make_source_ref(
            outcome.char_start, outcome.char_end, segments,
            outcome.status, outcome.confidence,
        )
    return Diagnostic(
        kind=outcome.diagnostic_kind or "unanchored",
        quote=quote, confidence=outcome.confidence, suggested=suggested,
    )
