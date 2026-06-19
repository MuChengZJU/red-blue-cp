"""Tests for serve desktop-mode configuration (Task 1.1)."""

from __future__ import annotations


def test_serve_builds_loopback_config():
    """Desktop mode must bind 127.0.0.1 on a random port (port 0)."""
    from app.cli import _build_serve_config

    cfg = _build_serve_config(desktop=True)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 0  # port 0 = kernel picks a free port


def test_serve_default_host_is_loopback():
    """Non-desktop mode also defaults to loopback, not 0.0.0.0."""
    from app.cli import _build_serve_config

    cfg = _build_serve_config(desktop=False)
    assert cfg.host == "127.0.0.1"


def test_serve_custom_host_and_port():
    """Explicit host/port override defaults."""
    from app.cli import _build_serve_config

    cfg = _build_serve_config(host="192.168.1.10", port=9090)
    assert cfg.host == "192.168.1.10"
    assert cfg.port == 9090


def test_serve_desktop_ignores_custom_host_port():
    """Desktop mode forces loopback+0 regardless of host/port args."""
    from app.cli import _build_serve_config

    cfg = _build_serve_config(desktop=True, host="0.0.0.0", port=8080)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 0
