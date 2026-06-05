"""fetcher.py 结构化异常 + 日志 + response body + token 过期检测（M4b）。

audit #1：裸 raise_for_status / ValueError / RuntimeError → errors 类，替换前打 body。
token 过期：fetch_xiaohongshu 请求后查 final_url 含 /404 或 error_code=300031（spike 信号）。
"""

from unittest.mock import patch, MagicMock

import pytest

from app.service import fetcher
from app.service.errors import (
    UnsupportedUrlError,
    ApiError,
    AuthError,
    ParseError,
)


def _resp(*, status_code=200, text="", url="", json_data=None):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.url = url
    if json_data is not None:
        r.json.return_value = json_data
    return r


# ── 小红书页面抓取 ───────────────────────────────────────────────

class TestFetchXiaohongshuErrors:

    @patch("app.service.fetcher.requests.get")
    def test_token_expired_redirect_to_404(self, mock_get):
        mock_get.return_value = _resp(
            status_code=200, text="<html></html>",
            url="https://www.xiaohongshu.com/404",
        )
        with pytest.raises(AuthError) as ei:
            fetcher.fetch_xiaohongshu("https://www.xiaohongshu.com/explore/x")
        assert ei.value.reason == "token_expired"
        assert ei.value.platform == "xiaohongshu"
        assert ei.value.operation == "fetch_detail"

    @patch("app.service.fetcher.requests.get")
    def test_token_expired_error_code_300031(self, mock_get):
        mock_get.return_value = _resp(
            status_code=200, text="<html></html>",
            url="https://www.xiaohongshu.com/explore/x?error_code=300031",
        )
        with pytest.raises(AuthError) as ei:
            fetcher.fetch_xiaohongshu("https://www.xiaohongshu.com/explore/x")
        assert ei.value.reason == "token_expired"

    @patch("app.service.fetcher.requests.get")
    def test_http_error_raises_api_error_and_logs_body(self, mock_get, caplog):
        # 服务器响应了非 2xx（reach 到站点）→ ApiError 而非 NetworkError，
        # 否则 format_error_for_user 会把它说成"代理未生效"，误导用户（Codex P2）。
        mock_get.return_value = _resp(
            status_code=503, text="风控页面 body 内容",
            url="https://www.xiaohongshu.com/explore/x",
        )
        with caplog.at_level("ERROR"):
            with pytest.raises(ApiError) as ei:
                fetcher.fetch_xiaohongshu("https://www.xiaohongshu.com/explore/x")
        assert ei.value.platform == "xiaohongshu"
        assert ei.value.api_code == 503
        assert "风控页面 body 内容" in caplog.text

    @patch("app.service.fetcher.requests.get")
    def test_missing_initial_state_raises_parse_error(self, mock_get):
        mock_get.return_value = _resp(
            status_code=200, text="<html>no state here</html>",
            url="https://www.xiaohongshu.com/explore/x",
        )
        with pytest.raises(ParseError):
            fetcher.fetch_xiaohongshu("https://www.xiaohongshu.com/explore/x")

    @patch("app.service.fetcher.requests.get")
    def test_valid_token_not_misjudged(self, mock_get):
        # 真实有效但解析不到 note → ParseError，绝不能误判成 AuthError
        mock_get.return_value = _resp(
            status_code=200,
            text="<script>window.__INITIAL_STATE__={\"note\":{}}</script>",
            url="https://www.xiaohongshu.com/explore/realid",
        )
        with pytest.raises(ParseError):
            fetcher.fetch_xiaohongshu("https://www.xiaohongshu.com/explore/realid")


# ── B 站 ─────────────────────────────────────────────────────────

class TestFetchBilibiliErrors:

    @patch("app.service.fetcher.requests.get")
    def test_no_bvid_raises_unsupported_url(self, mock_get):
        with pytest.raises(UnsupportedUrlError):
            fetcher.fetch_bilibili("https://www.bilibili.com/video/notabv")

    @patch("app.service.fetcher.requests.get")
    def test_get_json_http_error_raises_api_error_with_body(self, mock_get, caplog):
        mock_get.return_value = _resp(status_code=412, text='{"code":-412,"message":"risk"}')
        with caplog.at_level("ERROR"):
            with pytest.raises(ApiError) as ei:
                fetcher._get_json("https://api.bilibili.com/x", params={})
        assert ei.value.api_code == 412
        assert ei.value.provider == "bilibili"
        assert ei.value.payload_excerpt and "risk" in ei.value.payload_excerpt
        assert "risk" in caplog.text

    def test_api_data_error_code_raises_api_error(self):
        payload = {"code": -404, "message": "啥都没有", "data": None}
        with pytest.raises(ApiError) as ei:
            fetcher._api_data(payload, "Bilibili video info")
        assert ei.value.api_code == -404

    def test_api_data_missing_data_raises_parse_error(self):
        payload = {"code": 0, "data": "not a dict"}
        with pytest.raises(ParseError):
            fetcher._api_data(payload, "Bilibili video info")

    @patch("app.service.fetcher.requests.get")
    def test_get_json_non_dict_raises_parse_error(self, mock_get):
        mock_get.return_value = _resp(status_code=200, json_data=[1, 2, 3])
        with pytest.raises(ParseError):
            fetcher._get_json("https://api.bilibili.com/x", params={})

    @patch("app.service.fetcher.requests.get")
    def test_resolve_bilibili_url_http_error_raises_api(self, mock_get):
        mock_get.return_value = _resp(status_code=500, text="boom", url="https://b23.tv/x")
        with pytest.raises(ApiError):
            fetcher._resolve_bilibili_url("https://b23.tv/x")
