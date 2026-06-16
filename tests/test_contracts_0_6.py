"""0.6 契约桩守护测试（§A/§B/§C 锁定）。

两类断言：
1. import-lint：digest 只许 import ``app.extract.contracts``，不碰 extract 内部模块
   （extractor/model/fetcher/...）。这条纪律保证 Extract↔Digest 隔离，是并行 fan out 的前提。
2. 形状/默认值冻结：契约的字段、frozen、坐标系默认值不许被悄悄改。
"""

import ast
import dataclasses
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DIGEST_DIR = REPO_ROOT / "app" / "digest"
EXTRACT_DIR = REPO_ROOT / "app" / "extract"


def _package_of(py_file: Path) -> str:
    """文件所属包（其所在目录的点路径），用于把相对 import 解析成绝对。"""
    parts = py_file.relative_to(REPO_ROOT).parts
    return ".".join(parts[:-1])  # 去掉文件名；__init__.py 同样归到其目录包


def _cross_package_offenders(
    source: str, package: str, forbidden_prefix: str, allowed_exact: set[str]
) -> list[str]:
    """source 里跨包越界 import 的目标模块名列表。

    同时覆盖**绝对 import** 与 **相对 import**（相对按 package 解析成绝对），
    杜绝 `from ..extract.model import X` 这种之前能绕过 lint 的写法。
    """
    tree = ast.parse(source)
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                module = node.module or ""
            else:
                base = package.split(".")
                base = base[: len(base) - (node.level - 1)]
                module = ".".join(base + ([node.module] if node.module else []))
            if module == forbidden_prefix:
                # `from <pkg> import <sub>` —— 每个名字都是潜在子模块
                targets.extend(f"{module}.{alias.name}" for alias in node.names)
            else:
                targets.append(module)
    return [
        t
        for t in targets
        if (t == forbidden_prefix or t.startswith(forbidden_prefix + "."))
        and t not in allowed_exact
    ]


def _iter_py(root: Path):
    for p in root.rglob("*.py"):
        if "__pycache__" not in p.parts:
            yield p


def test_digest_only_imports_extract_contracts():
    """digest 包（含未来子包，rglob）对 app.extract.* 的 import 必须恰好是 app.extract.contracts。"""
    offenders: list[str] = []
    for py_file in _iter_py(DIGEST_DIR):
        for t in _cross_package_offenders(
            py_file.read_text(encoding="utf-8"),
            _package_of(py_file),
            forbidden_prefix="app.extract",
            allowed_exact={"app.extract.contracts"},
        ):
            offenders.append(f"{py_file.relative_to(REPO_ROOT)}: {t}")
    assert not offenders, "digest 只许依赖 app.extract.contracts，越界：" + "; ".join(offenders)


def test_extract_must_not_import_digest():
    """对称纪律：extract 不许 import app.digest.*（防反向耦合，保隔离双向）。"""
    offenders: list[str] = []
    for py_file in _iter_py(EXTRACT_DIR):
        for t in _cross_package_offenders(
            py_file.read_text(encoding="utf-8"),
            _package_of(py_file),
            forbidden_prefix="app.digest",
            allowed_exact=set(),
        ):
            offenders.append(f"{py_file.relative_to(REPO_ROOT)}: {t}")
    assert not offenders, "extract 不许依赖 digest，越界：" + "; ".join(offenders)


def test_import_lint_catches_relative_and_absolute_violations():
    """守 lint 本身：相对/绝对越界都要抓，合规两种写法都不误报（之前相对 import 能绕过）。"""
    pkg, fp, ok = "app.digest", "app.extract", {"app.extract.contracts"}
    # 相对 import 越界 —— 正是之前能 100% 绕过的洞
    assert _cross_package_offenders("from ..extract.model import P", pkg, fp, ok) == ["app.extract.model"]
    # 绝对 import 越界
    assert _cross_package_offenders("import app.extract.fetcher", pkg, fp, ok) == ["app.extract.fetcher"]
    # from app.extract import model（子模块名形式）越界
    assert _cross_package_offenders("from app.extract import model", pkg, fp, ok) == ["app.extract.model"]
    # 更深子包的相对 import 也要解析对
    assert _cross_package_offenders("from ...extract.model import X", "app.digest.render", fp, ok) == ["app.extract.model"]
    # 合规：只引 contracts，两种写法都不报
    assert _cross_package_offenders("from app.extract.contracts import Segment", pkg, fp, ok) == []
    assert _cross_package_offenders("from app.extract import contracts", pkg, fp, ok) == []
    assert _cross_package_offenders("from app.digest.contracts import Card", pkg, fp, ok) == []


# ---------------- §B ExtractResult / Segment ----------------

def test_extract_result_shape_frozen():
    from app.extract.contracts import ExtractResult, Segment

    assert dataclasses.is_dataclass(ExtractResult)
    field_names = {f.name for f in dataclasses.fields(ExtractResult)}
    # 决策 C：canonical text + 清洗版两份都存 + 指纹 + 句级 segments
    for required in {"text", "readable_text", "text_sha256", "segments", "metadata", "usage", "md_path"}:
        assert required in field_names, f"ExtractResult 缺字段 {required}"

    seg = Segment(text="你好", speaker_id=None, start_sec=0.0, end_sec=1.0, char_start=0, char_end=2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        seg.text = "改不了"  # type: ignore[misc]


def test_segment_has_char_offsets():
    from app.extract.contracts import Segment

    field_names = {f.name for f in dataclasses.fields(Segment)}
    assert {"char_start", "char_end", "start_sec", "end_sec", "speaker_id"} <= field_names


def test_text_fingerprint_deterministic_and_sha256():
    import hashlib

    from app.extract.contracts import text_fingerprint

    s = "说话人1：你好\n\n说话人2：再见"
    assert text_fingerprint(s) == hashlib.sha256(s.encode("utf-8")).hexdigest()
    assert text_fingerprint(s) == text_fingerprint(s)  # 确定性


def test_build_canonical_is_stub():
    from app.extract.contracts import build_canonical_text_and_segments

    with pytest.raises(NotImplementedError):
        build_canonical_text_and_segments({})


# ---------------- §B facade verbs are stubs ----------------

def test_facade_verbs_are_stubs():
    from app.extract import facade

    with pytest.raises(NotImplementedError):
        facade.extract("http://x", output_dir=Path("/tmp"))
    with pytest.raises(NotImplementedError):
        facade.search("q", output_dir=Path("/tmp"))
    with pytest.raises(NotImplementedError):
        facade.list_blogger("http://x")
    with pytest.raises(NotImplementedError):
        facade.Jobs().total_cost_yuan()


# ---------------- §C Digest contract ----------------

def test_digest_result_defaults_and_coordinate_space():
    from app.digest.contracts import DigestResult

    r = DigestResult(
        highlights=(), cards=(), outline=(), model="qwen-plus",
        source_text_sha256="deadbeef",
    )
    assert r.coordinate_space == "python_codepoint"
    assert r.normalization_version == "v1"
    assert r.diagnostics == ()


def test_coordinate_space_shared_between_extract_and_digest():
    from app.digest.contracts import DigestResult
    from app.extract.contracts import COORDINATE_SPACE

    r = DigestResult(highlights=(), cards=(), outline=(), model="m", source_text_sha256="x")
    assert r.coordinate_space == COORDINATE_SPACE


def test_source_ref_defaults():
    from app.digest.contracts import SourceRef

    ref = SourceRef()
    assert ref.anchoring_status == "exact"
    assert ref.confidence == 1.0
    assert ref.char_start is None and ref.char_end is None


def test_highlight_span_binds_to_source():
    from app.digest.contracts import Highlight, SourceRef

    h = Highlight(span_start=3, span_end=9, weight=0.8, source=SourceRef(char_start=3, char_end=9))
    assert dataclasses.is_dataclass(h)
    with pytest.raises(dataclasses.FrozenInstanceError):
        h.weight = 0.1  # type: ignore[misc]
    # 自执行不变量：span 与 source.char 不一致直接拒绝构造
    with pytest.raises(ValueError):
        Highlight(span_start=3, span_end=9, weight=0.8, source=SourceRef(char_start=3, char_end=10))
    with pytest.raises(ValueError):
        Highlight(span_start=3, span_end=9, weight=0.8, source=SourceRef())  # char 为 None


def test_diagnostic_shape():
    from app.digest.contracts import Diagnostic

    d = Diagnostic(kind="unanchored", quote="某句原话")
    assert d.confidence == 0.0 and d.suggested is None
    assert dataclasses.is_dataclass(d)


def test_digest_fingerprint_guard_is_live():
    from app.digest.contracts import digest
    from app.extract.contracts import text_fingerprint

    # 没传 sha：跳过校验，直接到未实现
    with pytest.raises(NotImplementedError):
        digest("text", provider=object())
    # 传对的 sha：校验过，到未实现
    with pytest.raises(NotImplementedError):
        digest("text", provider=object(), text_sha256=text_fingerprint("text"))
    # 传错的 sha：防漂 guard 先 raise ValueError（即使桩未实现）
    with pytest.raises(ValueError):
        digest("text", provider=object(), text_sha256="not-the-fingerprint")
