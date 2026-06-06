"""博主批量下载（M4c）。读插件导出的 notes.json → 走代理逐条下 → 断点续传 + 汇总。

数据契约见 docs/blogger-safe-batch-feature.md §四。下载唯一入口是
pipeline.fetch_single；token 过期（AuthError reason=token_expired）跳过继续，
其他失败记 failed 不崩批。proxy 开跑前出口探测确认生效。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.service.errors import AuthError, ConfigError, NetworkError, format_error_for_user
from app.service.pipeline import build_proxies, fetch_single, probe_exit_ip
from app.service.storage import Storage

_log = logging.getLogger("rbcp.batch")

SUPPORTED_SCHEMA_VERSION = 1


def _load_and_validate(
    notes_json: "Path | str | dict[str, Any]", *, allow_partial: bool
) -> dict[str, Any]:
    """读 + 校验 notes.json 信封。接受文件路径或已解析的 dict（WebUI 直接传 envelope）。
    不合规一律抛 ConfigError（拒绝，不猜测）。"""
    if isinstance(notes_json, dict):
        envelope = notes_json
    else:
        path = Path(notes_json)
        if not path.exists():
            raise ConfigError(f"清单文件不存在：{path}")
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ConfigError(f"清单不是合法 JSON：{path}") from exc

    if not isinstance(envelope, dict):
        raise ConfigError("清单顶层必须是对象（带 schema_version/notes 的信封）")

    version = envelope.get("schema_version")
    if version != SUPPORTED_SCHEMA_VERSION:
        raise ConfigError(
            f"清单 schema_version={version!r}，本版只认 {SUPPORTED_SCHEMA_VERSION}。"
            "请用配套插件重新导出。"
        )

    notes = envelope.get("notes")
    if not isinstance(notes, list):
        raise ConfigError("清单缺少 notes 列表")
    for i, note in enumerate(notes):
        if not isinstance(note, dict) or not note.get("note_id") or not note.get("url"):
            raise ConfigError(f"第 {i} 条笔记缺少 note_id 或 url")

    if not envelope.get("complete", False) and not allow_partial:
        raise ConfigError(
            "清单未拉全（complete=false，多半被风控截断）。不在半份上做全量；"
            "确要继续加 --allow-partial。"
        )
    return envelope


def _check_proxy_egress(proxies: dict[str, str]) -> str | None:
    """开跑前出口探测。返回警告字符串（或 None=明确生效）。**代理连不上才硬拦**。

    出口==直连不再硬拦：TUN/系统代理模式下整机流量都走隧道，直连与代理出口
    本就相同（用户其实受保护），硬拦会误伤。改成给警告让用户自己核对——
    若没开 TUN 而出口相同，那才是真的没生效、暴露真实 IP。
    """
    try:
        via_proxy = probe_exit_ip(proxies)
    except Exception as exc:  # noqa: BLE001 - 代理连不上是唯一硬失败
        raise NetworkError(
            f"代理连不上：{exc}",
            user_message="代理连不上，请检查 RBCP_PROXY / Clash 是否在跑、端口对不对。",
        ) from exc
    try:
        direct = probe_exit_ip(None)
    except Exception:  # noqa: BLE001 - 直连探测失败不影响开跑
        direct = None
    if direct is not None and direct == via_proxy:
        return (
            f"代理出口与直连相同（{via_proxy}）：若你开了 TUN/系统代理，这是正常的"
            f"（整机已走代理）；若没开，则当前用的是真实 IP、代理未生效，请核对后再批量下。"
        )
    return None


def run_batch(
    notes_json_path: "Path | str | dict[str, Any]",
    *,
    api_key: str,
    output_dir: Path,
    proxy: str | None = None,
    comments: bool = False,
    sub: bool = True,
    save_media: bool = False,
    text_only: bool = False,
    resume: bool = True,
    allow_partial: bool = False,
) -> dict[str, Any]:
    """批量下载一份清单。返回 {ok, failed, skipped, token_expired, results, batch_id}。"""
    envelope = _load_and_validate(notes_json_path, allow_partial=allow_partial)
    notes = envelope["notes"]

    summary: dict[str, Any] = {
        "ok": 0, "failed": 0, "skipped": 0,
        "token_expired": [], "results": [], "batch_id": None, "proxy_warning": None,
    }
    if not notes:
        _log.info("清单为空，无可下载笔记")
        return summary

    # 开跑前出口探测（仅在配了代理时）。连不上硬拦；出口==直连只警告不拦。
    if proxy:
        warning = _check_proxy_egress(build_proxies(proxy))
        if warning:
            summary["proxy_warning"] = warning
            _log.warning(warning)

    output_dir = Path(output_dir)
    storage = Storage(output_dir / "_index.sqlite")
    source = str(envelope.get("source") or "xhs_user_posted")
    user_id = envelope.get("user_id")

    # 断点续传：复用同 (source, user_id) 的批次，没有才新建
    batch_id = storage.find_active_batch(source, user_id) if resume else None
    if batch_id is None:
        batch_id = storage.create_batch(
            source=source, user_id=user_id,
            count=len(notes), complete=bool(envelope.get("complete", False)),
        )
    summary["batch_id"] = batch_id
    storage.mark_batch_status(batch_id, "running")
    storage.add_batch_items(
        batch_id, [{"note_id": n["note_id"], "url": n["url"]} for n in notes]
    )
    done_before = storage.get_batch_item_statuses(batch_id)

    for note in notes:
        note_id, url = note["note_id"], note["url"]
        if resume and done_before.get(note_id) in ("done", "skipped"):
            # done=已下过；skipped=token 过期（同 url 重跑别再试死 token，
            # add_batch_items 已把"换了新 token"的 skipped 重置成 pending）
            continue
        try:
            result = fetch_single(
                url, api_key=api_key, output_dir=output_dir,
                comments=comments, sub=sub, save_media=save_media,
                text_only=text_only, proxy=proxy,
            )
            storage.mark_batch_item_done(batch_id, note_id, md_path=result["md_path"])
            summary["ok"] += 1
            summary["results"].append({"note_id": note_id, "ok": True, **result})
        except AuthError as exc:
            if getattr(exc, "reason", None) == "token_expired":
                storage.mark_batch_item_failed(
                    batch_id, note_id, error_message="token_expired", skipped=True
                )
                summary["skipped"] += 1
                summary["token_expired"].append(note_id)
                summary["results"].append(
                    {"note_id": note_id, "ok": False, "skipped": True,
                     "error": "token_expired"}
                )
                _log.warning("第 %s 条 token 过期，已跳过", note_id)
            else:
                _record_failure(storage, summary, batch_id, note_id, exc)
        except Exception as exc:  # noqa: BLE001 - 单条失败不中断整批
            _record_failure(storage, summary, batch_id, note_id, exc)

    storage.mark_batch_status(batch_id, "done")
    return summary


def _record_failure(storage, summary, batch_id, note_id, exc) -> None:
    msg = format_error_for_user(exc)
    storage.mark_batch_item_failed(batch_id, note_id, error_message=msg)
    summary["failed"] += 1
    summary["results"].append({"note_id": note_id, "ok": False, "error": msg})
    _log.warning("第 %s 条失败：%s", note_id, exc)
