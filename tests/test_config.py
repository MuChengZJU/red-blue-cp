"""M6a §A · 配置发现测试。守住 SPEC.md:53 的发现顺序（之前代码从不读用户配置目录）。"""

import os
from pathlib import Path

import pytest

import app.config as cfg


@pytest.fixture(autouse=True)
def _isolate_env():
    # load_dotenv 会直接写 os.environ；测试后恢复，防泄漏污染别的测试。
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def fake_userdir(tmp_path, monkeypatch):
    """把 platformdirs 用户配置目录指到 tmp（不预先创建，交给 config_dir 建）。"""
    d = tmp_path / "userconfig"
    monkeypatch.setattr(cfg.platformdirs, "user_config_dir", lambda name: str(d))
    return d


def test_config_dir_created(fake_userdir):
    result = cfg.config_dir()
    assert result == fake_userdir
    assert result.is_dir()  # 保证存在


def test_returns_none_when_no_file(fake_userdir, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RBCP_CONFIG_FILE", raising=False)
    assert cfg.load_config() is None


def test_env_var_never_overridden(fake_userdir, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("RBCP_T=fromfile\n")
    monkeypatch.setenv("RBCP_T", "fromenv")
    cfg.load_config()
    assert os.environ["RBCP_T"] == "fromenv"  # 进程环境变量最高，文件不覆盖


def test_userdir_beats_cwd(fake_userdir, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RBCP_T", raising=False)
    fake_userdir.mkdir(parents=True, exist_ok=True)
    (fake_userdir / ".env").write_text("RBCP_T=fromuser\n")
    (tmp_path / ".env").write_text("RBCP_T=fromcwd\n")
    primary = cfg.load_config()
    assert primary == fake_userdir / ".env"      # 命中最高优先级
    assert os.environ["RBCP_T"] == "fromuser"    # 高优先级文件 key 胜出


def test_explicit_path_wins(fake_userdir, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RBCP_T", raising=False)
    explicit = tmp_path / "custom.env"
    explicit.write_text("RBCP_T=fromexplicit\n")
    fake_userdir.mkdir(parents=True, exist_ok=True)
    (fake_userdir / ".env").write_text("RBCP_T=fromuser\n")
    primary = cfg.load_config(str(explicit))
    assert primary == explicit
    assert os.environ["RBCP_T"] == "fromexplicit"


def test_explicit_via_env_var(fake_userdir, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RBCP_T", raising=False)
    explicit = tmp_path / "via_env.env"
    explicit.write_text("RBCP_T=fromenvfile\n")
    monkeypatch.setenv("RBCP_CONFIG_FILE", str(explicit))
    primary = cfg.load_config()
    assert primary == explicit
    assert os.environ["RBCP_T"] == "fromenvfile"


def test_candidate_order(fake_userdir, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RBCP_CONFIG_FILE", raising=False)
    assert cfg.candidate_config_paths() == [fake_userdir / ".env", Path.cwd() / ".env"]
    # 带 explicit 时它排最前
    paths = cfg.candidate_config_paths("/x/y.env")
    assert paths[0] == Path("/x/y.env")
