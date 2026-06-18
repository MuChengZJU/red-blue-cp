"""Command-line entry points for Red Blue CP."""

from __future__ import annotations

import asyncio
import json as _json
import os
from pathlib import Path
from typing import Callable

import typer
import uvicorn
from app.config import candidate_config_paths, config_dir, load_config, resolve_output_dir

from app.extract.errors import RbcpError, format_error_for_user
from app.extract.extractor import extract_url
from app.extract.markdown import render_and_write
from app.extract.pipeline import (
    _provider_from_env,
    build_proxies,
    fetch_single as _fetch_single,
)
from app.extract.pricing import summarize_usage
from app.extract.urls import clean_url


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
            # P1h：provider 账本 → 费用汇总（text_only/纯字幕没调模型则为 None）。
            # getattr 宽容：账本是尽力记账，不是 ModelProvider Protocol 的一部分。
            "usage": summarize_usage(getattr(provider, "usage_events", [])),
        }

    return pipeline


def run_pipeline(url: str) -> str:
    """Run the URL-to-Markdown pipeline and return the generated file path."""
    load_config()
    url = clean_url(url)  # 分享文案抽 URL + 去追踪参数（小红书保 token）
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    output_dir = resolve_output_dir()
    pipeline = _create_pipeline_fn(api_key=api_key, output_dir=output_dir)
    return pipeline(url)["md_path"]


@app.command("run")
def run(url: str) -> None:
    try:
        md_path = run_pipeline(url)
    except Exception as error:  # noqa: BLE001
        # audit #3：失败要退出码非 0（脚本/CI 能感知）+ 翻人话，别糊裸异常。
        typer.secho(format_error_for_user(error), fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    typer.echo(f"Done: {md_path}")



def _build_serve_config(
    *,
    desktop: bool = False,
    host: str | None = None,
    port: int | None = None,
) -> uvicorn.Config:
    """Build a ``uvicorn.Config`` for the *serve* command.

    Desktop mode always binds ``127.0.0.1`` on a random port (port 0).
    """
    if desktop:
        return uvicorn.Config("app.web.routes:app", host="127.0.0.1", port=0, workers=1)
    return uvicorn.Config(
        "app.web.routes:app",
        host=host or "127.0.0.1",
        port=port or 8000,
        workers=1,
    )


class _DesktopServer(uvicorn.Server):
    """Print the kernel-assigned port and auth token as JSON to stdout."""

    async def startup(self, sockets=None):  # type: ignore[override]
        await super().startup(sockets)
        if self.servers:
            real_port = self.servers[0].sockets[0].getsockname()[1]
            from app.web import auth

            print(
                _json.dumps({"port": real_port, "token": auth._ACTIVE_TOKEN or ""}),
                flush=True,
            )


@app.command("serve")
def serve(
    port: int = typer.Option(8000, "--port", help="监听端口（多实例用不同端口错开）"),
    host: str | None = typer.Option(None, "--host", help="绑定地址（默认 127.0.0.1）"),
    desktop: bool = typer.Option(
        False, "--desktop", is_flag=True, help="桌面模式：127.0.0.1+随机端口，stdout 回吐 port/token"
    ),
) -> None:
    load_config()
    if desktop:
        from app.web import auth

        os.environ["RBCP_DESKTOP"] = "1"
        auth.new_token()
        cfg = _build_serve_config(desktop=True)
        server = _DesktopServer(cfg)
        asyncio.run(server.serve())
    else:
        cfg = _build_serve_config(host=host, port=port)
        uvicorn.Server(cfg).run()


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
    load_config()
    from app.extract import discover

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
    load_config()
    from app.extract import discover

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
    load_config()
    if not all_:
        url = clean_url(url)  # 单篇：分享文案抽 URL + 去追踪参数（--all 是博主主页 URL，不动）
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    output_dir = resolve_output_dir()
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
            # JSON 给机器：error 留技术原因；message 给人话
            typer.echo(_json.dumps(
                {"ok": False, "error": str(error),
                 "message": format_error_for_user(error)},
                ensure_ascii=False))
        else:
            typer.secho(format_error_for_user(error), fg=typer.colors.RED)
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
    from app.extract import discover

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


@app.command("batch")
def batch(
    notes_json: Path,
    proxy: str = typer.Option(None, "--proxy", help="走代理护 IP（http://host:port）；默认读 RBCP_PROXY"),
    comments: bool = typer.Option(False, "--comments", help="附带抓评论"),
    no_sub: bool = typer.Option(False, "--no-sub", help="评论只要一级，不要楼中楼"),
    save_media: bool = typer.Option(False, "--save-media", help="额外存原始媒体到独立目录"),
    text_only: bool = typer.Option(False, "--text-only", help="跳过 VLM/ASR，只取现成正文"),
    allow_partial: bool = typer.Option(False, "--allow-partial", help="允许在半份清单上下载"),
    json_out: bool = typer.Option(False, "--json", help="输出机器可读 JSON"),
) -> None:
    """批量下载插件导出的 notes.json：走代理、断点续传、token 过期跳过、汇总成败。"""
    load_config()
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    output_dir = resolve_output_dir()
    proxy = proxy or os.getenv("RBCP_PROXY") or None

    if proxy and comments:
        # batch 标榜安全代理路径，但评论走 pydoll/Chrome，proxy 进不去 → 真实 IP（Codex P1）
        typer.secho(
            "⚠ --proxy 只覆盖正文下载；--comments 抓评论走浏览器（pydoll）真实 IP，不走代理。",
            fg=typer.colors.YELLOW,
        )

    from app.extract.batch import run_batch

    try:
        summary = run_batch(
            notes_json,
            api_key=api_key,
            output_dir=output_dir,
            proxy=proxy,
            comments=comments,
            sub=not no_sub,
            save_media=save_media,
            text_only=text_only,
            allow_partial=allow_partial,
        )
    except RbcpError as error:
        if json_out:
            typer.echo(_json.dumps(
                {"ok": False, "error": format_error_for_user(error)}, ensure_ascii=False))
        else:
            typer.secho(f"批量失败：{format_error_for_user(error)}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    if json_out:
        typer.echo(_json.dumps(summary, ensure_ascii=False))
        return

    if summary.get("proxy_warning"):
        typer.secho(f"⚠ {summary['proxy_warning']}", fg=typer.colors.YELLOW)
    typer.echo(
        f"完成：成功 {summary['ok']}，失败 {summary['failed']}，跳过 {summary['skipped']}。"
    )
    if summary["token_expired"]:
        typer.secho(
            f"⚠ 这些清单已过期，需重新抓清单：{', '.join(summary['token_expired'])}",
            fg=typer.colors.YELLOW,
        )


@app.command("digest")
def digest(
    url: str,
    json_out: bool = typer.Option(False, "--json", help="按 0.6 契约输出 extract+digest JSON"),
    text_only: bool = typer.Option(False, "--text-only", help="跳过 VLM/ASR，只取现成正文"),
    proxy: str = typer.Option(None, "--proxy", help="走代理护 IP（http://host:port）；默认读 RBCP_PROXY"),
) -> None:
    """抓 URL → 速览：高亮 / 卡片金句 / 脉络三形态。

    --json 出机器可读的 {"extract": {...}, "digest": {...}}（0.6 digest-json 契约，Desktop 消费）；
    不加 --json 给人看精简渲染（高亮句 + 金句 + 脉络标题）。
    """
    import dataclasses

    from app.digest.contracts import digest as run_digest
    from app.extract.pipeline import _provider_from_env, build_proxies

    load_config()
    url = clean_url(url)
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    proxy = proxy or os.getenv("RBCP_PROXY") or None

    try:
        proxies = build_proxies(proxy)
        provider = _provider_from_env(api_key, proxies=proxies)
        result = extract_url(url, provider, text_only=text_only, proxies=proxies)
        digest_result = run_digest(
            result.text,
            provider=provider,
            text_sha256=result.text_sha256,
            segments=result.segments,
        )
    except Exception as error:  # noqa: BLE001
        if json_out:
            typer.echo(_json.dumps(
                {"ok": False, "error": str(error),
                 "message": format_error_for_user(error)}, ensure_ascii=False))
        else:
            typer.secho(format_error_for_user(error), fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    if json_out:
        # 0.6 digest-json 契约：extract 子集 + digest 全量（dataclasses.asdict 递归）。
        envelope = {
            "extract": {
                "canonical_text": result.text,
                "text_sha256": result.text_sha256,
                "segments": (
                    [dataclasses.asdict(s) for s in result.segments]
                    if result.segments is not None else None
                ),
                "readable_text": result.readable_text,
            },
            "digest": dataclasses.asdict(digest_result),
        }
        typer.echo(_json.dumps(envelope, ensure_ascii=False))
        return

    # 人话精简渲染
    text = result.text
    typer.secho(f"《{result.title or url}》", fg=typer.colors.CYAN, bold=True)
    if digest_result.highlights:
        typer.secho("\n高亮：", fg=typer.colors.GREEN)
        for h in digest_result.highlights:
            typer.echo(f"  · {text[h.span_start:h.span_end]}")
    if digest_result.cards:
        typer.secho("\n金句：", fg=typer.colors.GREEN)
        for c in digest_result.cards:
            typer.echo(f"  「{c.quote}」")
    if digest_result.outline:
        typer.secho("\n脉络：", fg=typer.colors.GREEN)

        def _print_outline(nodes, depth: int = 0) -> None:
            for node in nodes:
                typer.echo(f"  {'  ' * depth}- {node.title}")
                _print_outline(node.children, depth + 1)

        _print_outline(digest_result.outline)


@app.command("ls")
def ls(
    limit: int = typer.Option(20, "--limit", help="最多列多少条"),
    json_out: bool = typer.Option(False, "--json", help="输出机器可读 JSON"),
) -> None:
    """列最近的任务（从知识库 _index.sqlite 读）+ 累计估算费用。"""
    from app.extract.facade import Jobs

    load_config()
    output_dir = resolve_output_dir()
    jobs = Jobs(output_dir=output_dir)
    rows = jobs.list(limit=limit)
    cost = jobs.total_cost_yuan()

    if json_out:
        typer.echo(_json.dumps({"jobs": rows, "total_cost_yuan": cost}, ensure_ascii=False))
        return

    if not rows:
        typer.echo("还没有任务记录。")
    else:
        for row in rows:
            status = row.get("status", "?")
            title = row.get("title") or row.get("url") or "?"
            typer.echo(f"  [{row.get('id')}] {status:8} {title}")
    typer.echo(f"累计估算费用：￥{cost:.4f}")


@app.command("config")
def config() -> None:
    """查看当前生效的配置来源（修了「~/.config/rbcp/.env 从未被读」的硬伤），并引导写入。"""
    primary = load_config()
    cfg_dir = config_dir()
    typer.echo(f"用户配置目录：{cfg_dir}")
    typer.echo("配置发现顺序（高→低，已存在的环境变量永不被覆盖）：")
    typer.echo("  1. 进程环境变量")
    for i, path in enumerate(candidate_config_paths(), start=2):
        mark = "✓" if path.is_file() else "·"
        tag = "  ← 当前生效" if primary is not None and path == primary else ""
        typer.echo(f"  {i}. [{mark}] {path}{tag}")

    key = os.getenv("DASHSCOPE_API_KEY", "")
    if key:
        masked = f"{key[:4]}…{key[-2:]}" if len(key) > 6 else "已设置"
        typer.echo(f"DASHSCOPE_API_KEY：{masked}")
    else:
        typer.secho("DASHSCOPE_API_KEY：未设置（必填）", fg=typer.colors.YELLOW)
        typer.echo(f"  写入示例：echo 'DASHSCOPE_API_KEY=sk-...' >> {cfg_dir / '.env'}")
