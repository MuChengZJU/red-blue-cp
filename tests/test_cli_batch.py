"""cli `batch` 命令测试（M4c）。run_batch 全 mock，只测命令的参数解析 + 输出 + 退出码。"""

from __future__ import annotations

from typer.testing import CliRunner

import app.cli as cli
from app.service.errors import ConfigError

runner = CliRunner()


def _summary(**over):
    base = {"ok": 2, "failed": 1, "skipped": 1, "token_expired": ["nX"],
            "results": [], "batch_id": 7}
    base.update(over)
    return base


def test_batch_outputs_human_summary(monkeypatch, tmp_path):
    captured = {}

    def fake_run(path, **kw):
        captured["path"] = path
        captured["kw"] = kw
        return _summary()

    monkeypatch.setattr("app.service.batch.run_batch", fake_run)
    notes = tmp_path / "n.json"
    notes.write_text("{}")
    result = runner.invoke(cli.app, ["batch", str(notes)])
    assert result.exit_code == 0
    assert "成功 2" in result.stdout
    assert "失败 1" in result.stdout
    assert "跳过 1" in result.stdout
    assert "nX" in result.stdout  # 过期条目提示重抓


def test_batch_proxy_from_flag(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(
        "app.service.batch.run_batch",
        lambda path, **kw: captured.update(kw) or _summary(),
    )
    notes = tmp_path / "n.json"
    notes.write_text("{}")
    runner.invoke(cli.app, ["batch", str(notes), "--proxy", "http://127.0.0.1:7897",
                            "--allow-partial", "--no-sub"])
    assert captured["proxy"] == "http://127.0.0.1:7897"
    assert captured["allow_partial"] is True
    assert captured["sub"] is False


def test_batch_config_error_exits_1(monkeypatch, tmp_path):
    def boom(path, **kw):
        raise ConfigError("清单 schema_version=2，本版只认 1")

    monkeypatch.setattr("app.service.batch.run_batch", boom)
    notes = tmp_path / "n.json"
    notes.write_text("{}")
    result = runner.invoke(cli.app, ["batch", str(notes)])
    assert result.exit_code == 1
    assert "schema_version" in result.stdout or "清单" in result.stdout


def test_batch_json_output(monkeypatch, tmp_path):
    monkeypatch.setattr("app.service.batch.run_batch", lambda path, **kw: _summary())
    notes = tmp_path / "n.json"
    notes.write_text("{}")
    result = runner.invoke(cli.app, ["batch", str(notes), "--json"])
    assert result.exit_code == 0
    assert '"ok": 2' in result.stdout or '"ok":2' in result.stdout
