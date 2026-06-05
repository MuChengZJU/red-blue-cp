"""extractor.py 结构化异常 + save_media 下载异常分层（M4b audit #1/#5）。"""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.service.extractor import detect_platform, _download_file
from app.service.errors import UnsupportedUrlError, NetworkError


class TestDetectPlatformError:

    def test_unsupported_url_raises_unsupported_url_error(self):
        with pytest.raises(UnsupportedUrlError):
            detect_platform("https://www.youtube.com/watch?v=x")

    def test_unsupported_carries_operation(self):
        try:
            detect_platform("https://www.douyin.com/video/1")
        except UnsupportedUrlError as exc:
            assert exc.operation == "detect_platform"
        else:
            pytest.fail("did not raise")


class TestSaveMediaDownloadError:

    @patch("app.service.extractor.requests.get")
    def test_download_http_error_raises_network_error(self, mock_get, tmp_path):
        import requests
        resp = MagicMock(status_code=403, text="防盗链")
        resp.raise_for_status.side_effect = requests.HTTPError("403")
        mock_get.return_value = resp
        with pytest.raises(NetworkError):
            _download_file(
                "https://img.xhs.com/x.jpg",
                tmp_path / "x.jpg",
                {"Referer": "https://www.xiaohongshu.com/"},
            )
