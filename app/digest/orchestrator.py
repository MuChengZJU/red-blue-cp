"""M6c · 编排层：run_digest 把 LLM 产物经确定性锚定组装成 DigestResult。

流程：build_prompt → call_digest_llm → parse_digest_json → 逐条 anchor_one
→ 按门槛分流 highlights / diagnostics（cards/outline 锚不上则 source=None）
→ 组装 DigestResult（source_text_sha256 一律 = text_fingerprint(text)，纯函数算、不抄入参）。
"""

from __future__ import annotations

from typing import Any

from app.digest import anchor, llm
from app.digest.contracts import Card, DigestResult, OutlineNode
from app.extract.contracts import Segment, text_fingerprint


def _anchor_item(text, norm, back, segments, item) -> anchor.AnchorOutcome:
    return anchor.anchor_one(
        text, norm, back, item.quote, item.context_before, item.context_after,
        item.segment_id, segments,
    )


def _is_clean_highlight(o: anchor.AnchorOutcome) -> bool:
    return (
        o.diagnostic_kind is None
        and o.status in ("exact", "normalized")
        and o.confidence >= anchor.HIGHLIGHT_MIN_CONFIDENCE
        and o.char_start is not None
    )


def _build_outline(text, norm, back, segments, nodes) -> tuple[OutlineNode, ...]:
    out = []
    for node in nodes:
        source = None
        if node.quote:
            o = _anchor_item(text, norm, back, segments, _as_item(node))
            if o.diagnostic_kind is None and o.char_start is not None:
                source = anchor.make_source_ref(
                    o.char_start, o.char_end, segments, o.status, o.confidence)
        out.append(OutlineNode(
            title=node.title, source=source,
            children=_build_outline(text, norm, back, segments, node.children),
        ))
    return tuple(out)


def _as_item(node) -> llm.ParsedItem:
    return llm.ParsedItem(
        quote=node.quote or "", context_before=node.context_before,
        context_after=node.context_after, segment_id=node.segment_id,
    )


def run_digest(
    text: str, *, provider: Any, segments: tuple[Segment, ...] | None = None
) -> DigestResult:
    fingerprint = text_fingerprint(text)
    norm, back = anchor.build_norm_index(text)

    raw, _usage = llm.call_digest_llm(provider, llm.build_prompt(text, segments))
    parsed = llm.parse_digest_json(raw)

    highlights = []
    diagnostics = list(parsed.diagnostics)
    for item in parsed.highlights:
        o = _anchor_item(text, norm, back, segments, item)
        if _is_clean_highlight(o):
            highlights.append(anchor.make_highlight(
                o.char_start, o.char_end, item.weight, segments, o.status, o.confidence))
        else:
            diagnostics.append(anchor.diagnostic_from(o, item.quote, segments))

    cards = []
    for item in parsed.cards:
        o = _anchor_item(text, norm, back, segments, item)
        source = None
        if o.diagnostic_kind is None and o.char_start is not None:
            source = anchor.make_source_ref(
                o.char_start, o.char_end, segments, o.status, o.confidence)
        cards.append(Card(quote=item.quote, source=source))

    outline = _build_outline(text, norm, back, segments, parsed.outline)

    return DigestResult(
        highlights=tuple(highlights),
        cards=tuple(cards),
        outline=outline,
        model=getattr(provider, "llm_model", "unknown"),
        source_text_sha256=fingerprint,
        diagnostics=tuple(diagnostics),
    )
