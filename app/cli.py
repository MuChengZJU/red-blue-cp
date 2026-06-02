"""Command-line entry points for Red Blue CP."""

from __future__ import annotations

import asyncio
import json as _json
import os
from pathlib import Path
from typing import Callable

import typer
import uvicorn
from dotenv import load_dotenv

from app.service.discover import note_id_from_url as _note_id_from_url
from app.service.extractor import extract_url
from app.service.markdown import render_and_write
from app.service.model import DashscopeProvider


app = typer.Typer()


def _provider_from_env(api_key: str) -> DashscopeProvider:
    asr_model = os.getenv("RBCP_ASR_MODEL", "paraformer-v2")
    diarization_enabled = os.getenv("RBCP_ASR_DIARIZATION", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    speaker_count_raw = os.getenv("RBCP_ASR_SPEAKER_COUNT", "").strip()
    speaker_count = int(speaker_count_raw) if speaker_count_raw.isdigit() else None
    return DashscopeProvider(
        api_key=api_key,
        asr_model=asr_model,
        diarization_enabled=diarization_enabled,
        speaker_count=speaker_count,
    )


def _create_pipeline_fn(api_key: str, output_dir: Path) -> Callable[[str], dict]:
    """Create a URL-to-Markdown pipeline bound to runtime configuration.

    Returns a dict with md_path + 业务元数据，供 storage.mark_done 持久化。
    """

    def pipeline(url: str) -> dict:
        provider = _provider_from_env(api_key)
        result = extract_url(url, provider)
        md_path = render_and_write(result, output_dir=output_dir)
        return {
            "md_path": str(md_path),
            "title": result.title,
            "author": result.author,
            "platform": result.platform,
            "content_type": result.content_type,
        }

    return pipeline


def run_pipeline(url: str) -> str:
    """Run the URL-to-Markdown pipeline and return the generated file path."""
    load_dotenv()
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    output_dir = Path(os.getenv("RBCP_OUTPUT_DIR", "~/transcript")).expanduser()
    pipeline = _create_pipeline_fn(api_key=api_key, output_dir=output_dir)
    return pipeline(url)["md_path"]


@app.command("run")
def run(url: str) -> None:
    try:
        md_path = run_pipeline(url)
    except Exception as error:
        typer.echo(f"Failed: {error}")
        return

    typer.echo(f"Done: {md_path}")


@app.command("serve")
def serve() -> None:
    load_dotenv()
    uvicorn.run("app.web.routes:app", host="0.0.0.0", port=8000, workers=1)


def _fetch_single(
    url: str,
    *,
    api_key: str,
    output_dir: Path,
    comments: bool = False,
    sub: bool = True,
    save_media: bool = False,
    text_only: bool = False,
) -> dict:
    """抓单篇笔记：正文转录（+可选媒体落盘/纯文本）+ 可选评论。返回结果摘要。"""
    provider = _provider_from_env(api_key)
    result = extract_url(url, provider, text_only=text_only, save_media=save_media)
    md_path = render_and_write(result, output_dir=output_dir)
    out: dict = {"md_path": str(md_path), "title": result.title}

    if comments:
        from app.service import discover
        from app.service.comments import write_comments_md

        note_comments = asyncio.run(discover.discover_comments(url, with_sub=sub))
        comments_path = write_comments_md(
            _note_id_from_url(url), note_comments, output_dir, note_title=result.title
        )
        out["comments_path"] = str(comments_path)
        out["comment_count"] = len(note_comments)

    return out


def _build_note_url(note_id: str, xsec_token: str) -> str:
    return (
        f"https://www.xiaohongshu.com/explore/{note_id}"
        f"?xsec_token={xsec_token}&xsec_source=pc_user"
    )


@app.command("list")
def list_uploader(
    url: str,
    json_out: bool = typer.Option(False, "--json", help="输出机器可读 JSON"),
) -> None:
    """列博主全量笔记清单（不下载）。撞风控/半份时退出码非 0。"""
    load_dotenv()
    from app.service import discover

    result = asyncio.run(discover.discover_user_posts(url))

    if json_out:
        typer.echo(_json.dumps(result, ensure_ascii=False))
    else:
        est = result["estimate"]
        typer.echo(
            f"博主 {result['user_id']}：共 {result['captured']} 篇"
            f"（图文 {est['image_notes']} / 视频 {est['video_notes']}）"
        )
        if result["complete"]:
            typer.echo("清单完整 ✓")
        else:
            typer.secho(
                f"⚠ 未拉全（{result['incomplete_reason']}）：以上是半份清单，勿当全量",
                fg=typer.colors.RED,
            )

    if not result["complete"]:
        raise typer.Exit(code=1)


@app.command("fetch")
def fetch(
    url: str,
    all_: bool = typer.Option(False, "--all", help="整博主全量下载"),
    comments: bool = typer.Option(False, "--comments", help="附带抓评论"),
    no_sub: bool = typer.Option(False, "--no-sub", help="评论只要一级，不要楼中楼"),
    save_media: bool = typer.Option(False, "--save-media", help="额外存原始媒体到独立目录"),
    text_only: bool = typer.Option(False, "--text-only", help="跳过 VLM/ASR，只取现成正文"),
    json_out: bool = typer.Option(False, "--json", help="输出机器可读 JSON"),
    yes: bool = typer.Option(False, "--yes", help="--all 时跳过确认"),
) -> None:
    """抓单篇笔记，或用 --all 抓整个博主。"""
    load_dotenv()
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    output_dir = Path(os.getenv("RBCP_OUTPUT_DIR", "~/transcript")).expanduser()

    if all_:
        _fetch_all(
            url,
            api_key=api_key,
            output_dir=output_dir,
            comments=comments,
            sub=not no_sub,
            save_media=save_media,
            text_only=text_only,
            yes=yes,
        )
        return

    try:
        out = _fetch_single(
            url,
            api_key=api_key,
            output_dir=output_dir,
            comments=comments,
            sub=not no_sub,
            save_media=save_media,
            text_only=text_only,
        )
    except Exception as error:  # noqa: BLE001
        if json_out:
            typer.echo(_json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        else:
            typer.echo(f"Failed: {error}")
        raise typer.Exit(code=1) from None

    if json_out:
        typer.echo(_json.dumps({"ok": True, **out}, ensure_ascii=False))
    else:
        typer.echo(f"Done: {out['md_path']}")
        if "comments_path" in out:
            typer.echo(f"Comments: {out['comments_path']}（{out.get('comment_count', 0)} 条一级）")


def _fetch_all(
    url: str,
    *,
    api_key: str,
    output_dir: Path,
    comments: bool,
    sub: bool,
    save_media: bool,
    text_only: bool,
    yes: bool,
) -> None:
    """博主全量：列清单 → 预览 → 确认 → 逐条下载。半份清单默认拒绝继续。"""
    from app.service import discover

    listing = asyncio.run(discover.discover_user_posts(url))
    est = listing["estimate"]
    typer.echo(
        f"博主 {listing['user_id']}：共 {listing['captured']} 篇"
        f"（图文 {est['image_notes']} / 视频 {est['video_notes']}）"
    )

    if not listing["complete"]:
        typer.secho(
            f"⚠ 清单未拉全（{listing['incomplete_reason']}）。不在半份清单上做全量下载。"
            "请稍后重试或刷新 cookie。",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    if not listing["notes"]:
        typer.echo("这个博主没有可下载的笔记。")
        return

    if not yes:
        confirmed = typer.confirm(f"确认下载这 {listing['captured']} 篇？")
        if not confirmed:
            typer.echo("已取消。")
            raise typer.Exit(code=0)

    ok, failed = 0, 0
    for note in listing["notes"]:
        note_url = _build_note_url(note["note_id"], note["xsec_token"])
        try:
            _fetch_single(
                note_url,
                api_key=api_key,
                output_dir=output_dir,
                comments=comments,
                sub=sub,
                save_media=save_media,
                text_only=text_only,
            )
            ok += 1
            typer.echo(f"  [{ok + failed}/{listing['captured']}] ✓ {note['title'][:30]}")
        except Exception as error:  # noqa: BLE001 - 单篇失败不中断整批
            failed += 1
            typer.secho(
                f"  [{ok + failed}/{listing['captured']}] ✗ {note['note_id']}: {error}",
                fg=typer.colors.YELLOW,
            )

    typer.echo(f"完成：成功 {ok}，失败 {failed}。")
