"""rbcp-digest：原文 → 高亮 / 卡片金句 / 脉络（有损 LLM，与 Extract 隔离）。

公共契约见 ``app.digest.contracts``。digest 只依赖 ``app.extract.contracts`` 的公共类型，
不碰 extract 内部模块（由 test_contracts_0_6 的 import-lint 守）。
"""

from app.digest.contracts import (
    Card,
    Diagnostic,
    DigestResult,
    Highlight,
    OutlineNode,
    SourceRef,
    digest,
)

__all__ = [
    "SourceRef",
    "Highlight",
    "Card",
    "OutlineNode",
    "Diagnostic",
    "DigestResult",
    "digest",
]
