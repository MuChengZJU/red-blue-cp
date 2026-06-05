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

from app.service.extractor import extract_url
from app.service.markdown import render_and_write
from app.service.pipeline import (
    _provider_from_env,
    build_proxies,
    fetch_single as _fetch_single,
)


app = typer.Typer()


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


def _build_note_url(note_id: str, xsec_token: str) -> str:
    return (
        f"https://www.xiaohongshu.com/explore/{note_id}"
        f"?xsec_token={xsec_token}&xsec_source=pc_user"
    )


@app.command("login")
def login() -> None:
    """弹出浏览器，扫码登录小红书，把 cookie 存到本地（博主全量/评论要用）。

    会等你扫完码、回到终端按回车再保存——不会自动关。
    """
    load_dotenv()
    from app.service import discover

    typer.echo("即将弹出浏览器并打开小红书。")
    typer.echo("→ 用手机扫码登录，看到自己头像/进入首页后，回这里按【回车】。")
    count, path = asyncio.run(discover.login_and_save_cookies())
    if count > 0:
        typer.secho(f"✓ 已保存 {count} 条 cookie 到 {path}", fg=typer.colors.GREEN)
        typer.echo("现在可以用 rbcp list / fetch --comments / fetch --all 了。")
        typer.echo("（若接着 list 仍抓到 0 条，多半是没真登录上，重跑 rbcp login。）")
    else:
        typer.secho("✗ 没拿到 cookie。重跑 rbcp login 再试。", fg=typer.colors.RED)
        raise typer.Exit(code=1)


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
    proxy: str = typer.Option(None, "--proxy", help="走代理护 IP（http://host:port）；默认读 RBCP_PROXY"),
) -> None:
    """抓单篇笔记，或用 --all 抓整个博主。"""
    load_dotenv()
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    output_dir = Path(os.getenv("RBCP_OUTPUT_DIR", "~/transcript")).expanduser()
    proxy = proxy or os.getenv("RBCP_PROXY") or None

    if proxy and (all_ or comments):
        # --proxy 只穿透下载层（requests）。抓清单/评论走 pydoll/Chrome，proxy 进不去 → 真实 IP。
        typer.secho(
            "⚠ --proxy 只覆盖下载；--all 抓清单 / --comments 抓评论走浏览器（pydoll）真实 IP，"
            "不走代理。安全批量请用插件导出清单 + rbcp batch。",
            fg=typer.colors.YELLOW,
        )

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
            json_out=json_out,
            proxy=proxy,
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
            proxy=proxy,
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
    json_out: bool = False,
    proxy: str | None = None,
) -> None:
    """博主全量：列清单 → 预览 → 确认 → 逐条下载。半份清单默认拒绝继续。"""
    from app.service import discover

    listing = asyncio.run(discover.discover_user_posts(url))
    est = listing["estimate"]

    if not listing["complete"]:
        if json_out:
            typer.echo(_json.dumps(
                {"ok": False, "error": "incomplete_list",
                 "incomplete_reason": listing["incomplete_reason"],
                 "captured": listing["captured"]}, ensure_ascii=False))
        else:
            typer.secho(
                f"⚠ 清单未拉全（{listing['incomplete_reason']}）。不在半份清单上做全量下载。"
                "请稍后重试或刷新 cookie。",
                fg=typer.colors.RED,
            )
        raise typer.Exit(code=1)

    if not listing["notes"]:
        if json_out:
            typer.echo(_json.dumps({"ok": True, "captured": 0, "downloaded": 0,
                                    "failed": 0, "results": []}, ensure_ascii=False))
        else:
            typer.echo("这个博主没有可下载的笔记。")
        return

    if not yes:
        # JSON/非交互模式不弹确认；要批量下载必须显式 --yes
        if json_out:
            typer.echo(_json.dumps(
                {"ok": False, "error": "confirmation_required",
                 "hint": "--all 在 --json 模式下需加 --yes", "captured": listing["captured"]},
                ensure_ascii=False))
            raise typer.Exit(code=1)
        typer.echo(
            f"博主 {listing['user_id']}：共 {listing['captured']} 篇"
            f"（图文 {est['image_notes']} / 视频 {est['video_notes']}）"
        )
        if not typer.confirm(f"确认下载这 {listing['captured']} 篇？"):
            typer.echo("已取消。")
            raise typer.Exit(code=0)
    elif not json_out:
        typer.echo(
            f"博主 {listing['user_id']}：共 {listing['captured']} 篇"
            f"（图文 {est['image_notes']} / 视频 {est['video_notes']}）"
        )

    ok, failed = 0, 0
    results: list[dict] = []
    for note in listing["notes"]:
        note_url = _build_note_url(note["note_id"], note["xsec_token"])
        try:
            out = _fetch_single(
                note_url,
                api_key=api_key,
                output_dir=output_dir,
                comments=comments,
                sub=sub,
                save_media=save_media,
                text_only=text_only,
                proxy=proxy,
            )
            ok += 1
            results.append({"note_id": note["note_id"], "ok": True, **out})
            if not json_out:
                typer.echo(f"  [{ok + failed}/{listing['captured']}] ✓ {note['title'][:30]}")
        except Exception as error:  # noqa: BLE001 - 单篇失败不中断整批
            failed += 1
            results.append({"note_id": note["note_id"], "ok": False, "error": str(error)})
            if not json_out:
                typer.secho(
                    f"  [{ok + failed}/{listing['captured']}] ✗ {note['note_id']}: {error}",
                    fg=typer.colors.YELLOW,
                )

    if json_out:
        typer.echo(_json.dumps(
            {"ok": True, "captured": listing["captured"], "downloaded": ok,
             "failed": failed, "results": results}, ensure_ascii=False))
    else:
        typer.echo(f"完成：成功 {ok}，失败 {failed}。")
