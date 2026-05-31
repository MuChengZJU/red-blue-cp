"""Command-line entry points for Red Blue CP."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import typer
import uvicorn
from dotenv import load_dotenv

from app.service.extractor import extract_url
from app.service.markdown import render_and_write
from app.service.model import DashscopeProvider


app = typer.Typer()


def _create_pipeline_fn(api_key: str, output_dir: Path) -> Callable[[str], dict]:
    """Create a URL-to-Markdown pipeline bound to runtime configuration.

    Returns a dict with md_path + 业务元数据，供 storage.mark_done 持久化。
    """

    asr_model = os.getenv("RBCP_ASR_MODEL", "paraformer-v2")
    diarization_enabled = os.getenv("RBCP_ASR_DIARIZATION", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    speaker_count_raw = os.getenv("RBCP_ASR_SPEAKER_COUNT", "").strip()
    speaker_count = int(speaker_count_raw) if speaker_count_raw.isdigit() else None

    def pipeline(url: str) -> dict:
        provider = DashscopeProvider(
            api_key=api_key,
            asr_model=asr_model,
            diarization_enabled=diarization_enabled,
            speaker_count=speaker_count,
        )
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
