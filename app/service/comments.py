"""comments.py — 评论 Markdown 格式化模块。

公开接口
--------
format_comments_md(note_id, comments, *, note_title="") -> str
    把一级评论列表（每条的 sub_comments 已嵌套好）渲染成 Markdown 字符串。
    纯函数，不落盘。

write_comments_md(note_id, comments, output_dir, *, note_title="") -> Path
    调 format_comments_md 得到内容，原子写到 output_dir/xhs/{note_id}.comments.md。
    遵循 SPEC §6.3 原子写入协议（.tmp + os.replace + 失败清理）。

渲染规范
--------
- 一级评论平铺，楼中楼子评论缩进嵌套在父评论下。
- 每条评论展示：昵称、正文、点赞数、IP 属地（空时省略该行）、时间（UTC 日期）。
- 子评论体现 reply_to（回复了谁）。
- 时区：所有时间统一用 UTC，避免不同机器测试结果差异。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from app.service.discover import Comment


_log = logging.getLogger("rbcp.comments")


def format_comments_md(
    note_id: str,
    comments: list[Comment],
    *,
    note_title: str = "",
) -> str:
    """把评论列表渲染成 Markdown 字符串（纯函数，不落盘）。

    Parameters
    ----------
    note_id     : 笔记 ID，写入文档标题用。
    comments    : 一级评论列表；每条的 sub_comments 已嵌套好。
    note_title  : 笔记标题（可选），用于 Markdown 大标题。
    """
    lines: list[str] = []

    # 文档标题
    if note_title:
        lines.append(f"# {note_title} — 评论")
    else:
        lines.append(f"# 笔记 {note_id} — 评论")
    lines.append("")

    if not comments:
        lines.append("*暂无评论*")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"共 {len(comments)} 条一级评论")
    lines.append("")
    lines.append("---")
    lines.append("")

    for comment in comments:
        lines.extend(_render_comment(comment, indent_level=0))
        lines.append("")

    return "\n".join(lines)


def write_comments_md(
    note_id: str,
    comments: list[Comment],
    output_dir: Path,
    *,
    note_title: str = "",
) -> Path:
    """原子写入评论 Markdown 文件。

    输出路径：output_dir/xhs/{note_id}.comments.md

    遵循 SPEC §6.3：先写 .tmp，再 os.replace，失败时清理 .tmp。
    """
    content = format_comments_md(note_id, comments, note_title=note_title)

    target_dir = Path(output_dir) / "xhs"
    target_dir.mkdir(parents=True, exist_ok=True)

    final_path = target_dir / f"{note_id}.comments.md"
    tmp_path = final_path.with_suffix(".md.tmp")

    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, final_path)
    except Exception:
        _log.error("写评论文件失败：%s", final_path, exc_info=True)
        tmp_path.unlink(missing_ok=True)
        raise

    _log.info("写出评论：%s（%d 条一级）", final_path, len(comments))
    return final_path


# ── 内部渲染辅助 ────────────────────────────────────────────────────────────────

def _render_comment(comment: Comment, indent_level: int) -> list[str]:
    """递归渲染一条评论及其子评论，返回行列表。

    indent_level 对应嵌套深度：
      0 → 一级评论（无缩进）
      1 → 二级子评论（2 个空格缩进）
      2+ → 更深层（4 个空格缩进）
    """
    prefix = "  " * indent_level

    lines: list[str] = []

    # 评论头：昵称 + 回复对象
    if comment.reply_to:
        header = f"{prefix}**{comment.author}** 回复 **{comment.reply_to}**："
    else:
        header = f"{prefix}**{comment.author}**："

    lines.append(header)

    # 正文（可能多行，每行都加缩进前缀）
    content_lines = comment.content.splitlines()
    if content_lines:
        lines.append(f"{prefix}{content_lines[0]}")
        for extra_line in content_lines[1:]:
            lines.append(f"{prefix}{extra_line}")
    else:
        lines.append(f"{prefix}（空）")

    # 元信息行
    meta_parts: list[str] = []
    meta_parts.append(f"👍 {comment.like_count}")
    if comment.ip_location:
        meta_parts.append(f"属地：{comment.ip_location}")
    meta_parts.append(f"🕐 {_format_time_utc(comment.create_time)}")
    lines.append(f"{prefix}<sub>{' · '.join(meta_parts)}</sub>")

    # 子评论递归
    for sub in comment.sub_comments:
        lines.append("")
        lines.extend(_render_comment(sub, indent_level=indent_level + 1))

    return lines


def _format_time_utc(create_time_ms: int) -> str:
    """毫秒 epoch → UTC 日期时间字符串，格式 YYYY-MM-DD HH:MM UTC。

    统一使用 UTC 确保测试结果跨机器一致。
    """
    dt = datetime.fromtimestamp(create_time_ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")
