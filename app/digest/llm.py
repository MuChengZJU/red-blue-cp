"""M6c · LLM 调用 + 解析层（纯 str↔结构，唯一碰 provider 的地方）。

digest 不 import app.extract.model（隔离）。provider 走窄 Protocol + 鸭子类型注入。
parse 层鲁棒降级：LLM 输出畸形也不抛，返回空三形态 + 一条 diagnostic。

只依赖 app.digest.contracts（Diagnostic）+ 标准库。不碰 char offset（那是 anchor.py 的事）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.digest.contracts import Diagnostic

_MAX_OUTLINE_DEPTH = 5
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


@runtime_checkable
class DigestProvider(Protocol):
    """digest 需要的最小 LLM 能力。壳层注入实现（如 DashscopeProvider）。"""

    def complete_json(
        self, prompt: str, *, operation: str = "digest"
    ) -> tuple[str, dict | None]:
        """调 LLM 产 JSON（response_format=json_object）。返回 (raw_json_text, usage)。"""
        ...


@dataclass(frozen=True)
class ParsedItem:
    quote: str
    context_before: str = ""
    context_after: str = ""
    segment_id: int | None = None
    weight: float = 0.5


@dataclass(frozen=True)
class ParsedOutline:
    title: str
    quote: str | None = None
    context_before: str = ""
    context_after: str = ""
    segment_id: int | None = None
    children: tuple["ParsedOutline", ...] = ()


@dataclass(frozen=True)
class ParsedDigest:
    highlights: tuple[ParsedItem, ...] = ()
    cards: tuple[ParsedItem, ...] = ()
    outline: tuple[ParsedOutline, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()  # parse 失败的降级记录


DIGEST_PROMPT_HEADER = (
    "你是中文内容速览分析器。基于下面的原文，产出三种速览结构，**只输出 JSON**"
    "（不要解释、不要 markdown 代码块包裹）。\n\n"
    "严格要求：highlights/cards/outline 里的 quote、context_before、context_after 必须是"
    "**从原文逐字复制的片段，一字不改、不补标点、不翻译、不改简繁**——我会用你给的 quote"
    "在原文里精确查找定位，改了就定位不到。context_before/after 各取 quote 前后约 15-30 字原文。\n\n"
    "JSON schema：\n"
    '{\n'
    '  "highlights": [{"quote": "逐字原文重点句", "importance": 0.0到1.0,\n'
    '                  "context_before": "前文逐字", "context_after": "后文逐字",\n'
    '                  "segment_id": 整数或null}],\n'
    '  "cards": [{"quote": "金句原话逐字", "context_before": "...", "context_after": "...",\n'
    '             "segment_id": 整数或null}],\n'
    '  "outline": [{"title": "自拟小节标题", "quote": "该节点对应原文一句逐字或null",\n'
    '               "context_before": "...", "context_after": "...", "segment_id": 整数或null,\n'
    '               "children": [递归同结构]}]\n'
    "}\n"
    "说明：highlights=跳读时该高亮的重点句(importance 给重要度)；cards=可独立成卡的金句；"
    "outline=层级脉络(title 可自拟不必是原文，quote 是该节点对应的一句原文、没有就 null)。\n"
)


def build_prompt(text: str, segments: tuple | None = None) -> str:
    """拼 digest 的 LLM prompt。有 segments 时附 segN 列表供模型引用 0-based segment_id。"""
    parts = [DIGEST_PROMPT_HEADER]
    if segments:
        parts.append("\n原文分段（segment_id 用这里的 0-based 序号，不确定填 null）：\n")
        for i, seg in enumerate(segments):
            parts.append(f"seg{i}: {seg.text}\n")
        parts.append("\n完整原文：\n")
    else:
        parts.append("\n原文：\n")
    parts.append(text)
    return "".join(parts)


def call_digest_llm(provider: Any, prompt: str) -> tuple[str, dict | None]:
    """调注入 provider 的 complete_json（鸭子类型，不依赖具体实现）。"""
    return provider.complete_json(prompt, operation="digest")


def _loads_lenient(raw: str) -> dict | None:
    """剥 code fence → json.loads；失败则截首 { 到末 } 重试；再失败返回 None。"""
    s = _FENCE_RE.sub("", raw.strip())
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except (ValueError, TypeError):
        pass
    lo, hi = s.find("{"), s.rfind("}")
    if 0 <= lo < hi:
        try:
            obj = json.loads(s[lo:hi + 1])
            return obj if isinstance(obj, dict) else None
        except (ValueError, TypeError):
            return None
    return None


def _clamp01(value: Any, default: float = 0.5) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _opt_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _parse_items(raw_list: Any, *, with_weight: bool) -> list[ParsedItem]:
    out: list[ParsedItem] = []
    if not isinstance(raw_list, list):
        return out
    for it in raw_list:
        if not isinstance(it, dict):
            continue
        quote = it.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            continue
        out.append(ParsedItem(
            quote=quote,
            context_before=it.get("context_before") if isinstance(it.get("context_before"), str) else "",
            context_after=it.get("context_after") if isinstance(it.get("context_after"), str) else "",
            segment_id=_opt_int(it.get("segment_id")),
            weight=_clamp01(it.get("importance")) if with_weight else 0.5,
        ))
    return out


def _parse_outline(raw_list: Any, *, depth: int) -> list[ParsedOutline]:
    out: list[ParsedOutline] = []
    if depth >= _MAX_OUTLINE_DEPTH or not isinstance(raw_list, list):
        return out
    for it in raw_list:
        if not isinstance(it, dict):
            continue
        title = it.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        q = it.get("quote")
        out.append(ParsedOutline(
            title=title,
            quote=q if isinstance(q, str) and q.strip() else None,
            context_before=it.get("context_before") if isinstance(it.get("context_before"), str) else "",
            context_after=it.get("context_after") if isinstance(it.get("context_after"), str) else "",
            segment_id=_opt_int(it.get("segment_id")),
            children=tuple(_parse_outline(it.get("children"), depth=depth + 1)),
        ))
    return out


def parse_digest_json(raw: str) -> ParsedDigest:
    """LLM 原始输出 → ParsedDigest。永不抛：畸形输出降级为空三形态 + 一条 diagnostic。"""
    obj = _loads_lenient(raw)
    if obj is None:
        return ParsedDigest(diagnostics=(Diagnostic(
            kind="unanchored", quote="<llm_json_parse_failed>",
            reason=(raw or "")[:200],
        ),))
    return ParsedDigest(
        highlights=tuple(_parse_items(obj.get("highlights"), with_weight=True)),
        cards=tuple(_parse_items(obj.get("cards"), with_weight=False)),
        outline=tuple(_parse_outline(obj.get("outline"), depth=0)),
    )
