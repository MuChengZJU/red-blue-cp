#!/usr/bin/env python3
"""RBCP Desktop sidecar — PyInstaller spike entry.

职责（最小）：读 stdin / argv 的纯文本 → 走真实 app.digest.digest 引擎 →
按 0.6-digest-json 契约打印 {"extract": ..., "digest": ...} 到 stdout。

为什么是这个形状：这是 Desktop 与引擎之间唯一的接缝（见
docs/contracts/0.6-digest-json-contract.md）。联调期 Tauri 壳 spawn 本二进制，
喂原文，拿契约 JSON 渲染三形态。

spike 约束：
- 不需要真 API key。digest 的 LLM 部分用 FakeProvider（确定性、离线）替代。
- 引擎源码 vendored 在同目录 _engine/（只含 digest + extract.contracts，纯标准库依赖），
  保证二进制自包含、可复现，不依赖任何具体分支被 checkout。
"""
from __future__ import annotations

import json
import os
import sys

# 让 vendored 引擎可 import（PyInstaller 打包后 _engine 随包，sys._MEIPASS 指向解包目录）。
_BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
_ENGINE = os.path.join(_BASE, "_engine")
if _ENGINE not in sys.path:
    sys.path.insert(0, _ENGINE)

from app.digest import digest  # noqa: E402
from app.extract.contracts import (  # noqa: E402
    Segment,
    build_canonical_text_and_segments,
    text_fingerprint,
)


class FakeProvider:
    """确定性离线 provider：从原文挑句子充当 highlights / cards / outline。

    实现 DigestProvider 协议的 complete_json(prompt, *, operation)。
    解析 prompt 末尾的「完整原文」/「原文：」块拿回 text，按中文句号切句，
    造一份合法的 digest LLM JSON（逐字 quote，保证后端锚定能 exact 命中）。
    """

    def complete_json(self, prompt: str, *, operation: str = "digest"):
        text = _extract_source_from_prompt(prompt)
        sentences = _split_sentences(text)
        highlights = [
            {"quote": s, "importance": round(0.95 - 0.05 * i, 2),
             "context_before": "", "context_after": "", "segment_id": i}
            for i, s in enumerate(sentences[:3])
        ]
        cards = []
        if sentences:
            cards.append({"quote": sentences[0], "context_before": "",
                          "context_after": "", "segment_id": 0})
        cards.append({"quote": "（FakeProvider 自由生成的金句，锚不回原文）",
                      "context_before": "", "context_after": "", "segment_id": None})
        outline = [{
            "title": "全文脉络",
            "quote": sentences[0] if sentences else None,
            "context_before": "", "context_after": "", "segment_id": 0,
            "children": [
                {"title": f"要点 {i + 1}", "quote": s, "context_before": "",
                 "context_after": "", "segment_id": i, "children": []}
                for i, s in enumerate(sentences[1:3])
            ],
        }]
        payload = {"highlights": highlights, "cards": cards, "outline": outline}
        return json.dumps(payload, ensure_ascii=False), None


def _extract_source_from_prompt(prompt: str) -> str:
    for marker in ("\n完整原文：\n", "\n原文：\n"):
        idx = prompt.rfind(marker)
        if idx >= 0:
            return prompt[idx + len(marker):].strip()
    return prompt.strip()


def _split_sentences(text: str) -> list[str]:
    out: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in "。！？":
            out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return [s for s in out if s]


def _build_extract(text: str) -> tuple[str, str, tuple[Segment, ...] | None]:
    """造一份 canonical text + segments（每句一个 segment，等距分配时间戳）。

    这是 sidecar spike 的桩 extract：真链路里换成 facade.extract(url)。
    canonical 与 segments 同源对齐（codepoint 区间）。
    """
    sentences = _split_sentences(text)
    if not sentences:
        sha = text_fingerprint(text)
        return text, sha, None
    # ASR payload 形状（DashScope 风格）：begin_time/end_time 单位毫秒。
    per_ms = 3500
    asr_sentences = [
        {
            "text": s,
            "speaker_id": "0",
            "begin_time": i * per_ms,
            "end_time": (i + 1) * per_ms,
        }
        for i, s in enumerate(sentences)
    ]
    payload = {"transcripts": [{"sentences": asr_sentences}]}
    # build_canonical_text_and_segments 原子产出 canonical text + 对齐的 char 区间
    canonical, segments = build_canonical_text_and_segments(payload)
    return canonical, text_fingerprint(canonical), segments


def _segment_to_dict(seg: Segment) -> dict:
    return {
        "text": seg.text,
        "speaker_id": seg.speaker_id,
        "start_sec": seg.start_sec,
        "end_sec": seg.end_sec,
        "char_start": seg.char_start,
        "char_end": seg.char_end,
    }


def _source_to_dict(src) -> dict | None:
    if src is None:
        return None
    return {
        "char_start": src.char_start,
        "char_end": src.char_end,
        "seconds": src.seconds,
        "image_index": src.image_index,
        "anchoring_status": src.anchoring_status,
        "confidence": src.confidence,
    }


def _outline_to_dict(node) -> dict:
    return {
        "title": node.title,
        "source": _source_to_dict(node.source),
        "children": [_outline_to_dict(c) for c in node.children],
    }


def run(text: str) -> dict:
    canonical, sha, segments = _build_extract(text)
    result = digest(canonical, provider=FakeProvider(),
                    text_sha256=sha, segments=segments)
    return {
        "extract": {
            "canonical_text": canonical,
            "text_sha256": sha,
            "segments": ([_segment_to_dict(s) for s in segments]
                         if segments is not None else None),
        },
        "digest": {
            "highlights": [
                {"span_start": h.span_start, "span_end": h.span_end,
                 "weight": h.weight, "source": _source_to_dict(h.source)}
                for h in result.highlights
            ],
            "cards": [
                {"quote": c.quote, "source": _source_to_dict(c.source)}
                for c in result.cards
            ],
            "outline": [_outline_to_dict(n) for n in result.outline],
            "model": result.model,
            "source_text_sha256": result.source_text_sha256,
            "coordinate_space": result.coordinate_space,
            "normalization_version": result.normalization_version,
            "diagnostics": [
                {"kind": d.kind, "quote": d.quote, "reason": d.reason,
                 "confidence": d.confidence, "suggested": _source_to_dict(d.suggested)}
                for d in result.diagnostics
            ],
        },
    }


def _read_input(argv: list[str]) -> str:
    if len(argv) > 1:
        return argv[1]
    data = sys.stdin.read()
    return data


def main() -> int:
    text = _read_input(sys.argv).strip()
    if not text:
        text = "今天聊大模型推理加速。核心瓶颈是显存带宽。投机解码能提速两到三倍。"
    out = run(text)
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
