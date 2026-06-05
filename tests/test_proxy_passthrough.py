"""proxy 穿透契约测试（M4a）。

护 IP 的核心：explore 详情 / B站 API（fetcher）走显式 proxies；
DashScope 调用顺带走；CDN 媒体字节（media_proxies）默认不走。
build_proxies 把 proxy URL 归一成 requests proxies dict，socks5/非法拒绝。
"""

from unittest.mock import patch, MagicMock

import pytest

from app.service import fetcher
from app.service.extractor import extract_url
from app.service.model import DashscopeProvider
from app.service.errors import ConfigError
from app.service.pipeline import build_proxies, probe_exit_ip


PROXY = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}


# ── build_proxies ───────────────────────────────────────────────

class TestBuildProxies:

    def test_none_returns_none(self):
        assert build_proxies(None) is None

    def test_empty_returns_none(self):
        assert build_proxies("") is None

    def test_http_builds_both_schemes(self):
        assert build_proxies("http://127.0.0.1:7897") == PROXY

    def test_https_proxy_url_ok(self):
        out = build_proxies("https://127.0.0.1:7897")
        assert out["http"] == "https://127.0.0.1:7897"

    def test_rejects_socks5(self):
        with pytest.raises(ConfigError):
            build_proxies("socks5://127.0.0.1:1080")

    def test_rejects_no_scheme(self):
        with pytest.raises(ConfigError):
            build_proxies("127.0.0.1:7897")


# ── probe_exit_ip ───────────────────────────────────────────────

class TestProbeExitIp:

    @patch("app.service.pipeline.requests.Session")
    def test_returns_ip_text(self, mock_session_cls):
        session = mock_session_cls.return_value.__enter__.return_value
        session.get.return_value = MagicMock(text="203.0.113.5\n")
        assert probe_exit_ip(PROXY) == "203.0.113.5"

    @patch("app.service.pipeline.requests.Session")
    def test_disables_env_on_session_and_proxies_on_get(self, mock_session_cls):
        session = mock_session_cls.return_value.__enter__.return_value
        session.get.return_value = MagicMock(text="1.1.1.1")
        probe_exit_ip(PROXY)
        # trust_env 是 Session 属性，不能当 get 的 kwarg（否则真实 requests 抛 TypeError）
        assert session.trust_env is False
        assert session.get.call_args.kwargs.get("proxies") == PROXY
        assert "trust_env" not in session.get.call_args.kwargs


# ── fetcher 主站请求走 proxies ──────────────────────────────────

class TestFetcherProxies:

    @patch("app.service.fetcher.requests.get")
    def test_fetch_xiaohongshu_threads_proxies(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, text="", url="u")
        with pytest.raises(Exception):  # 空 text → 解析失败，但请求已带 proxies
            fetcher.fetch_xiaohongshu(
                "https://www.xiaohongshu.com/explore/x", proxies=PROXY
            )
        assert mock_get.call_args.kwargs.get("proxies") == PROXY

    @patch("app.service.fetcher.requests.get")
    def test_get_json_threads_proxies(self, mock_get):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"code": 0, "data": {}}
        mock_get.return_value = resp
        fetcher._get_json("https://api.bilibili.com/x", params={}, proxies=PROXY)
        assert mock_get.call_args.kwargs.get("proxies") == PROXY

    @patch("app.service.fetcher.requests.get")
    def test_resolve_bilibili_url_threads_proxies(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, url="https://www.bilibili.com/video/BV1x")
        fetcher._resolve_bilibili_url("https://b23.tv/abc", proxies=PROXY)
        assert mock_get.call_args.kwargs.get("proxies") == PROXY


# ── extract_url 把 proxies 传给 fetcher ─────────────────────────

class TestExtractorProxies:

    @patch("app.service.extractor.fetcher")
    def test_extract_url_threads_proxies_to_fetcher(self, mock_fetcher):
        provider = MagicMock()
        provider.llm_clean.return_value = "cleaned"
        mock_fetcher.fetch_xiaohongshu.return_value = {
            "platform": "xiaohongshu", "content_type": "image_note",
            "title": "t", "image_urls": [], "url": "u",
        }
        extract_url("https://www.xiaohongshu.com/explore/x", provider, proxies=PROXY)
        assert mock_fetcher.fetch_xiaohongshu.call_args.kwargs.get("proxies") == PROXY


# ── DashscopeProvider 走 proxies（媒体默认不走）─────────────────

class TestModelProxies:

    @patch("app.service.model.requests.post")
    def test_llm_clean_threads_proxies(self, mock_post):
        resp = MagicMock()
        resp.json.return_value = {"choices": [{"message": {"content": "x"}}]}
        mock_post.return_value = resp
        DashscopeProvider("k", proxies=PROXY).llm_clean("t")
        assert mock_post.call_args.kwargs.get("proxies") == PROXY

    @patch("app.service.model.requests.post")
    def test_vlm_threads_proxies(self, mock_post):
        resp = MagicMock()
        resp.json.return_value = {"choices": [{"message": {"content": "x"}}]}
        mock_post.return_value = resp
        DashscopeProvider("k", proxies=PROXY).vlm("http://img")
        assert mock_post.call_args.kwargs.get("proxies") == PROXY

    def test_media_proxies_defaults_none(self):
        p = DashscopeProvider("k", proxies=PROXY)
        assert p._media_proxies is None


# ── fetch_single：proxy 字符串 → build_proxies → 往下传（M4c 关键入口）──

class TestFetchSingleProxyWiring:

    @patch("app.service.pipeline.render_and_write")
    @patch("app.service.pipeline.extract_url")
    @patch("app.service.pipeline._provider_from_env")
    def test_proxy_string_becomes_dict_to_extract_and_provider(
        self, mock_provider, mock_extract, mock_render, tmp_path
    ):
        from app.service.pipeline import fetch_single
        mock_extract.return_value = MagicMock(title="t")
        mock_render.return_value = tmp_path / "out.md"
        out = fetch_single("https://www.xiaohongshu.com/explore/x",
                           api_key="k", output_dir=tmp_path, proxy="http://127.0.0.1:7897")
        assert out == {"md_path": str(tmp_path / "out.md"), "title": "t"}
        assert mock_extract.call_args.kwargs["proxies"] == PROXY
        assert mock_provider.call_args.kwargs["proxies"] == PROXY

    @patch("app.service.pipeline.render_and_write")
    @patch("app.service.pipeline.extract_url")
    @patch("app.service.pipeline._provider_from_env")
    def test_no_proxy_passes_none(self, mock_provider, mock_extract, mock_render, tmp_path):
        from app.service.pipeline import fetch_single
        mock_extract.return_value = MagicMock(title="t")
        mock_render.return_value = tmp_path / "out.md"
        fetch_single("https://www.xiaohongshu.com/explore/x",
                     api_key="k", output_dir=tmp_path)
        assert mock_extract.call_args.kwargs["proxies"] is None
