"""0.6 §B · rbcp-extract 公共数据契约（锁定的接缝，先于实现）。

这里只放**冻结的数据形状**和坐标系约定，不放行为（行为在 facade.py / 各 service 模块）。
CLI / Desktop / Digest 三方都依赖这层；digest 只许 import 本模块（见 test_contracts_0_6）。

坐标系契约（Codex#4 锁定 + 桩对抗审查补强）：
- ``ExtractResult.text`` 是 **canonical 原始原文**，是唯一锚定坐标系。
- 所有 span / char offset 一律针对 ``text`` 的 **Python codepoint index**（不是 UTF-16，不是字节）。
- **区间一律左闭右开 [start, end)**（与 Python 切片一致，空区间 start==end）——Segment /
  Highlight / SourceRef 三处共用此语义，杜绝 off-by-one。
- ``text_sha256`` 是 ``text`` 的指纹；两侧（Extract / Digest）**必须统一调 ``text_fingerprint()``**
  生成，不得各自手搓 ``.encode()``，否则编码差异会误判坐标漂移。DigestResult 须带相同指纹。
- 字段顺序**不构成契约**：frozen dataclass 把有默认值字段排后是必要重排，下游一律用关键字构造，
  不得按位置 new。测试只断言字段集合。

迁移说明（strangler）：现 ``app.extract.extractor.ExtractResult`` 是 0.5.x 遗留的可变版、
且把 llm_clean 后的清洗版当唯一 text（extractor.py 硬伤，Codex#1）。M6b 把 extractor 迁到
本模块这份冻结版（text=canonical + readable_text=清洗版，两份都存）。在 M6b 落地前两者并存。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Segment",
    "ExtractResult",
    "PostBrief",
    "SearchHit",
    "BatchResult",
    "text_fingerprint",
    "build_canonical_text_and_segments",
    "COORDINATE_SPACE",
]

# 坐标系标识：所有 char offset 都是 canonical text 的 Python codepoint 下标。
COORDINATE_SPACE = "python_codepoint"


@dataclass(frozen=True)
class Segment:
    """ASR 句级片段。``char_start/char_end`` 是该句在 canonical text 里的 codepoint 区间（左闭右开）。

    硬不变量：``char_start/char_end`` **只索引 ExtractResult.text（canonical），与 readable_text
    无任何对齐关系**——readable_text（清洗版）上没有可用 offset。
    char 区间与 canonical text 由 ``build_canonical_text_and_segments`` 原子产出、同源保证对齐
    （speaker 前缀「说话人N：」/ 换行 / 句间分隔符等「缝隙字符」不属于任何 segment 区间）。
    图文内容无 segments（ExtractResult.segments 为 None）。
    """

    text: str
    speaker_id: str | None
    start_sec: float | None
    end_sec: float | None
    char_start: int
    char_end: int


@dataclass(frozen=True)
class ExtractResult:
    """采集+转录的结构化结果。三方共享、冻结。

    ``text`` = canonical 原始原文（锚定坐标系）；``readable_text`` = llm_clean 后可读版（展示用）。
    两份都存（决策 C）。知识库 .md body 存哪份在 M6b 落地时定（建议 canonical，需用户拍板）。

    硬不变量（M6b 落地须守）：
    - ``text`` 必须**就是** ``build_canonical_text_and_segments(asr_payload)`` 返回的第一个值；
      ``segments`` 必须就是其返回的第二个值（同源，保证 ``text[seg.char_start:seg.char_end] == seg.text``）。
    - ``readable_text`` 由 ``text`` 再 llm_clean 得到，**不得反向**（不能先 clean 再当 text）。
    - 文本归一化（换行统一 / NFC 等，若有）必须在 ``build_canonical_text_and_segments`` 内、
      产出 ``text`` 之前完成；之后 ``text`` 视为不可变，落盘亦不得被写入层二次改写（呼应红线#7 原子写）。
    """

    platform: str            # bilibili | xiaohongshu
    content_type: str        # video | image_note
    title: str
    author: str
    author_id: str | None
    published_at: str | None
    url: str
    text: str                # canonical 原始原文 = 唯一锚定坐标系
    readable_text: str       # llm_clean 后的可读版
    text_sha256: str         # text 的指纹，DigestResult 据此校验坐标系未漂
    metadata: dict[str, Any] = field(default_factory=dict)  # speaker_count / duration_sec 等
    usage: dict[str, Any] | None = None    # token / 音频秒 / 各阶段耗时
    md_path: str | None = None             # 落盘路径（None = 未写盘）
    segments: tuple[Segment, ...] | None = None  # ASR 句级；图文为 None


@dataclass(frozen=True)
class PostBrief:
    """博主清单中的一条（list_blogger 产出，不含正文）。"""

    note_id: str
    url: str
    title: str | None = None


@dataclass(frozen=True)
class SearchHit:
    """本地知识库全文检索命中一条。"""

    title: str
    author: str
    platform: str
    url: str
    path: str
    snippet: str
    score: float


@dataclass(frozen=True)
class BatchResult:
    """run_batch 的汇总结果。明细字段（每条 ok/failed/skipped 及原因）M6b 落地时补，
    届时只增字段、不改已锁的计数语义。"""

    ok: int = 0
    failed: int = 0
    skipped: int = 0


def text_fingerprint(text: str) -> str:
    """canonical text 的指纹算法（契约的一部分，Extract 与 Digest 两侧必须用同一个）。

    UTF-8 编码后取 sha256 hex。算法锁死，换它就是破坏坐标系兼容。
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _speaker_id_str(speaker_id: Any) -> str | None:
    return None if speaker_id is None else str(speaker_id)


def _ms_to_sec(value: Any) -> float | None:
    """DashScope ASR sentence 的 begin_time/end_time 是**毫秒** → 转秒。

    注意：毫秒这一单位需在 M6b 真链路实测核对一次（外部 API 细节，别只信引用代码）。
    单位若变只改这一处。
    """
    if value is None:
        return None
    try:
        return float(value) / 1000.0
    except (TypeError, ValueError):
        return None


def _collect_sentences(transcripts: list[dict[str, Any]]) -> list[tuple[Any, str, Any, Any]]:
    out: list[tuple[Any, str, Any, Any]] = []
    for transcript in transcripts:
        for sentence in transcript.get("sentences") or []:
            if not isinstance(sentence, dict):
                continue
            text = (sentence.get("text") or "").strip()
            if text:
                out.append(
                    (sentence.get("speaker_id"), text,
                     sentence.get("begin_time"), sentence.get("end_time"))
                )
    return out


def build_canonical_text_and_segments(
    asr_payload: dict[str, Any],
) -> tuple[str, tuple[Segment, ...]]:
    """从 ASR payload **原子产出** canonical text + segments，char offset 与 text 严格对齐。

    产出的 ``text`` 与历史 ``model._format_transcription(payload)`` **逐字一致**（行为不回归，
    由现有 _format_transcription 测试守），并附带 segments。不变量：每个 segment 满足
    ``text[seg.char_start:seg.char_end] == seg.text``（缝隙字符：speaker 前缀「说话人N：」/
    换行不属于任何 segment）。区间左闭右开。

    三种装配（与 _format_transcription 同构）：
    - 多说话人（≥2 个非 None speaker_id）：连续同人合并为一轮「说话人N：句…」，轮间「\\n\\n」。
    - 单说话人且有 transcript 级 text：按「\\n」拼 transcript text；segments 用前向扫描尽力对齐。
    - 单说话人且无 transcript 级 text：按「\\n」拼句子文本。
    """
    transcripts = [t for t in (asr_payload.get("transcripts") or []) if isinstance(t, dict)]
    sentences = _collect_sentences(transcripts)
    speakers = {sid for sid, _, _, _ in sentences if sid is not None}

    parts: list[str] = []
    segments: list[Segment] = []
    pos = 0

    def emit(piece: str) -> tuple[int, int]:
        nonlocal pos
        start = pos
        parts.append(piece)
        pos += len(piece)
        return start, pos

    if len(speakers) >= 2:
        groups: list[tuple[Any, list[tuple[Any, str, Any, Any]]]] = []
        for rec in sentences:
            sid = rec[0]
            if groups and groups[-1][0] == sid:
                groups[-1][1].append(rec)
            else:
                groups.append((sid, [rec]))
        for gi, (sid, recs) in enumerate(groups):
            if gi > 0:
                emit("\n\n")
            label = f"说话人{int(sid) + 1}：" if isinstance(sid, int) else "说话人："
            emit(label)
            for _sid, txt, begin, end in recs:
                cs, ce = emit(txt)
                segments.append(Segment(
                    text=txt, speaker_id=_speaker_id_str(sid),
                    start_sec=_ms_to_sec(begin), end_sec=_ms_to_sec(end),
                    char_start=cs, char_end=ce,
                ))
        return "".join(parts), tuple(segments)

    transcript_texts = [
        (t.get("text") or "").strip() for t in transcripts if (t.get("text") or "").strip()
    ]
    if transcript_texts:
        for ti, ttext in enumerate(transcript_texts):
            if ti > 0:
                emit("\n")
            emit(ttext)
        text = "".join(parts)
        # 前向扫描尽力对齐句子（text 来自 transcript 级文本，可能与句子拼接有标点差异）。
        # 只在 find 命中时产 segment → 不变量 text[cs:ce]==seg.text 恒成立；找不到则跳过该句。
        cursor = 0
        for sid, txt, begin, end in sentences:
            idx = text.find(txt, cursor)
            if idx < 0:
                continue
            segments.append(Segment(
                text=txt, speaker_id=_speaker_id_str(sid),
                start_sec=_ms_to_sec(begin), end_sec=_ms_to_sec(end),
                char_start=idx, char_end=idx + len(txt),
            ))
            cursor = idx + len(txt)
        return text, tuple(segments)

    for si, (sid, txt, begin, end) in enumerate(sentences):
        if si > 0:
            emit("\n")
        cs, ce = emit(txt)
        segments.append(Segment(
            text=txt, speaker_id=_speaker_id_str(sid),
            start_sec=_ms_to_sec(begin), end_sec=_ms_to_sec(end),
            char_start=cs, char_end=ce,
        ))
    return "".join(parts), tuple(segments)
