"""0.6 §C · rbcp-digest 数据契约（最关键的接缝）。

Render（Desktop）与 CLI ``rbcp digest --json`` 共同消费这层。锁死它，三形态 UI 才能并行做。

依赖纪律：digest 只 import ``app.extract.contracts``（公共类型），不碰 extract 的内部模块
（extractor/fetcher/model/...）。这条由 test_contracts_0_6 的 import-lint 守。

锚定方案（eng + Codex#3/#4 锁定）：
- LLM **不返字符 offset**（数不准），返回 quote + 前后文 + 可选 segment_id。
- 后端 **exact-first → normalized-second** 确定性锚定，产出 span + anchoring_status + confidence。
- **低置信不进 highlights，只进 diagnostics**（靠前后文消歧唯一处，不"多次出现全标"）。
- 所有 span / SourceRef 针对 canonical text 的 Python codepoint index；``source_text_sha256``
  必须等于 ``ExtractResult.text_sha256`` 才有效。前端 UTF-16 用后端切好的 span，别自己数字符。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.extract.contracts import COORDINATE_SPACE, Segment, text_fingerprint

__all__ = [
    "SourceRef",
    "Highlight",
    "Card",
    "OutlineNode",
    "Diagnostic",
    "DigestResult",
    "digest",
]


@dataclass(frozen=True)
class SourceRef:
    """回原文出处。坐标系 = canonical text 的 codepoint 区间（左闭右开）。

    ``seconds`` 不变量：
    - 视频（ExtractResult.segments 非 None）：由 [char_start, char_end) 落到**覆盖 char_start 的那个
      segment** → 取其 start_sec；char_start 落在 segment 间隙（缝隙字符）上时取右侧/下一个 segment，
      无右侧则 None；跨多 segment 时取起点所在 segment。
    - 图文（segments 为 None）：``seconds`` 恒为 None，``char_start/char_end`` 亦无意义，改用 ``image_index``。
    """

    char_start: int | None = None
    char_end: int | None = None
    seconds: float | None = None      # 由 char 区间映射 segment 的时间戳；图文恒 None
    image_index: int | None = None    # 图文第几张
    anchoring_status: str = "exact"   # exact | normalized | unanchored
    confidence: float = 1.0           # 低置信不进高亮，只进 diagnostics


@dataclass(frozen=True)
class Highlight:
    """全文重点高亮（跳读用）。span 是 canonical text 的 codepoint 区间（左闭右开）。

    硬不变量：``span_start == source.char_start`` 且 ``span_end == source.char_end``。
    span_* 是**必填渲染区间**（前端高亮哪段），source 是**同区间的锚定出处**（带 seconds /
    anchoring_status / confidence）。两者必须指向同一区间——对 Highlight 而言 source 的
    char_start/char_end 必非 None。M6c 须用同一对值填两处，并由测试锁死。
    """

    span_start: int
    span_end: int
    weight: float          # 0-1，排序 / "只看高亮"阈值
    source: SourceRef

    def __post_init__(self) -> None:
        # 自执行不变量：span 与 source.char 区间必须一致（防 fan out 后两处由不同代码填岔了）。
        if self.source.char_start != self.span_start or self.source.char_end != self.span_end:
            raise ValueError(
                "Highlight.span 必须与 source.char 区间一致："
                f"span=({self.span_start},{self.span_end}) "
                f"source=({self.source.char_start},{self.source.char_end})"
            )


@dataclass(frozen=True)
class Card:
    """卡片 / 金句。"""

    quote: str
    source: SourceRef | None = None


@dataclass(frozen=True)
class OutlineNode:
    """脉络大纲节点（可嵌套）。"""

    title: str
    source: SourceRef | None = None
    children: tuple["OutlineNode", ...] = ()


@dataclass(frozen=True)
class Diagnostic:
    """未锚定 / 低置信项：不进 highlights、不渲染，但可查（CLI --json / Render 调试面）。

    形状暂定（0.6 provisional）：UI 在 0.6 把它当**不透明诊断列表**，勿据具体字段做核心渲染。
    M6c 落地后若 UI 要正式消费再升级为正式契约。
    """

    kind: str                       # unanchored | low_confidence | ambiguous
    quote: str                      # LLM 返回的原话（锚定失败/可疑的那句）
    reason: str = ""
    confidence: float = 0.0
    suggested: SourceRef | None = None   # 后端尝试锚定的（低置信）结果，可能为 None


@dataclass(frozen=True)
class DigestResult:
    """三形态结构化产出 + 坐标系契约。"""

    highlights: tuple[Highlight, ...]
    cards: tuple[Card, ...]
    outline: tuple[OutlineNode, ...]
    model: str
    # 坐标系契约（Codex#4）：所有 span/SourceRef 针对的就是带此指纹的那份 canonical text。
    # 必须 == 产出时 canonical text 的 text_fingerprint()（见 digest 不变量）。
    source_text_sha256: str
    coordinate_space: str = COORDINATE_SPACE      # "python_codepoint"
    normalization_version: str = "v1"
    diagnostics: tuple[Diagnostic, ...] = ()      # 未锚定 / 低置信项，不渲染但可查


def digest(
    text: str,
    *,
    provider: Any,
    text_sha256: str | None = None,
    segments: tuple[Segment, ...] | None = None,
) -> DigestResult:
    """对 canonical text 调 LLM 产出 高亮 / 卡片金句 / 脉络 三形态。

    定位是**确定性服务端锚定**（exact→normalized），不是让 LLM 报位置。
    时间戳由 char 区间落到覆盖它的 segment → 取 start_sec（规则见 SourceRef.seconds）。

    指纹防漂不变量（M6c 须实现，对抗审查补强）：
    - ``DigestResult.source_text_sha256`` **一律 = text_fingerprint(text)**（text 的纯函数），
      绝不照抄外部传入值——否则坐标已漂仍校验放行。
    - ``text_sha256`` 是**可选的调用方断言**：若提供且 != text_fingerprint(text)，立即 raise ValueError
      （调用方传的 text 与它以为的 ExtractResult 对不上）；不提供则跳过断言。

    ``provider``：digest 需要的 LLM 方法签名由 M6c 锁定（暂 Any）；Extract↔Digest 隔离由
    import-lint（含相对 import）保证，不靠类型——故这里不从 app.extract.model 引 ModelProvider。
    """
    # 防漂自校验（live，即使桩未实现也先守）：调用方传了 sha 就必须和 text 真指纹一致。
    if text_sha256 is not None and text_fingerprint(text) != text_sha256:
        raise ValueError("text_sha256 与 text 的指纹不符——坐标系不匹配，拒绝 digest")
    raise NotImplementedError("M6c: LLM 三形态 + 确定性服务端锚定")
