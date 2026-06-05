"""CLI 测试 — 验证命令行入口能正确解析参数和调用业务逻辑。"""

from unittest.mock import patch, MagicMock
from typer.testing import CliRunner

import pytest
from app.cli import app


runner = CliRunner()


class TestRunCommand:

    @patch("app.cli.run_pipeline")
    def test_accepts_bilibili_url(self, mock_run):
        mock_run.return_value = "/home/user/transcript/bili/test.md"
        result = runner.invoke(app, ["run", "https://www.bilibili.com/video/BV1test"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    @patch("app.cli.run_pipeline")
    def test_outputs_done_path(self, mock_run):
        mock_run.return_value = "/home/user/transcript/bili/test.md"
        result = runner.invoke(app, ["run", "https://www.bilibili.com/video/BV1test"])
        assert "Done" in result.stdout or "transcript" in result.stdout

    @patch("app.cli.run_pipeline")
    def test_outputs_failed_on_error(self, mock_run):
        mock_run.side_effect = RuntimeError("连接超时")
        result = runner.invoke(app, ["run", "https://www.bilibili.com/video/BV1test"])
        assert "Failed" in result.stdout or "连接超时" in result.stdout

    def test_run_requires_url(self):
        result = runner.invoke(app, ["run"])
        assert result.exit_code != 0

    @patch("app.cli.run_pipeline")
    def test_run_failure_exits_nonzero(self, mock_run):
        """audit #3：run 失败必须退出码非 0，否则脚本/CI 感知不到失败。"""
        mock_run.side_effect = RuntimeError("连接超时")
        result = runner.invoke(app, ["run", "https://www.bilibili.com/video/BV1test"])
        assert result.exit_code == 1

    @patch("app.cli.run_pipeline")
    def test_run_failure_shows_human_message(self, mock_run):
        """裸异常翻人话：不支持的链接给可操作提示，不糊 Python traceback。"""
        from app.service.errors import UnsupportedUrlError
        mock_run.side_effect = UnsupportedUrlError("douyin", operation="detect_platform")
        result = runner.invoke(app, ["run", "https://www.douyin.com/video/1"])
        assert result.exit_code == 1
        assert "不支持" in result.stdout


class TestServeCommand:

    @patch("app.cli.uvicorn")
    def test_serve_starts_uvicorn(self, mock_uvicorn):
        result = runner.invoke(app, ["serve"])
        mock_uvicorn.run.assert_called_once()

    @patch("app.cli.uvicorn")
    def test_serve_binds_0000(self, mock_uvicorn):
        runner.invoke(app, ["serve"])
        call_kwargs = mock_uvicorn.run.call_args[1]
        assert call_kwargs.get("host") == "0.0.0.0"

    @patch("app.cli.uvicorn")
    def test_serve_no_workers_flag(self, mock_uvicorn):
        runner.invoke(app, ["serve"])
        call_kwargs = mock_uvicorn.run.call_args[1]
        assert call_kwargs.get("workers", 1) == 1
