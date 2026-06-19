"""URL 清理 / 分享文案提取测试。"""

from app.extract.urls import clean_url


class TestExtractFromShareText:
    def test_bilibili_share_text(self):
        raw = "【50分钟！具身智能…】 https://www.bilibili.com/video/BV1ZNVy69EtT/?share_source=copy_web&vd_source=8bd8185749ffccadae2a691212d378d8"
        assert clean_url(raw) == "https://www.bilibili.com/video/BV1ZNVy69EtT/"

    def test_xhs_share_text_keeps_token(self):
        raw = "【标题】 😆 i1Dhyj35sQTA0Pv 😆 https://www.xiaohongshu.com/discovery/item/6a16?xsec_token=ABv5-aSbw=&xsec_source=pc_share&xhsshare=CopyLink&appuid=123"
        out = clean_url(raw)
        assert out == "https://www.xiaohongshu.com/discovery/item/6a16?xsec_token=ABv5-aSbw=&xsec_source=pc_share"
        assert "xsec_token=ABv5-aSbw=" in out  # base64 尾部的 = 不被破坏
        assert "xhsshare" not in out and "appuid" not in out

    def test_no_url_returns_stripped(self):
        assert clean_url("  随便一段文字没有链接  ") == "随便一段文字没有链接"


class TestBilibili:
    def test_strips_tracking_keeps_p_and_t(self):
        raw = "https://www.bilibili.com/video/BV1xx/?p=2&t=10&spm_id_from=333.999&vd_source=abc&unique_k=zzz"
        out = clean_url(raw)
        assert "p=2" in out and "t=10" in out
        assert "spm_id_from" not in out and "vd_source" not in out and "unique_k" not in out

    def test_clean_url_unchanged(self):
        url = "https://www.bilibili.com/video/BV1GJ411x7h7"
        assert clean_url(url) == url

    def test_b23_short_link_kept(self):
        assert clean_url("https://b23.tv/abc123") == "https://b23.tv/abc123"


class TestXiaohongshu:
    def test_keeps_only_xsec(self):
        raw = "https://www.xiaohongshu.com/explore/64a?xsec_token=TOK&xsec_source=pc_user&source=web&share_id=99"
        out = clean_url(raw)
        assert "xsec_token=TOK" in out and "xsec_source=pc_user" in out
        assert "share_id" not in out and "source=web" not in out

    def test_xhslink_short_kept(self):
        assert clean_url("http://xhslink.com/o/6F9Yaskyf7w") == "http://xhslink.com/o/6F9Yaskyf7w"


class TestEdge:
    def test_empty(self):
        assert clean_url("") == ""

    def test_trailing_bracket_stripped(self):
        raw = "https://www.bilibili.com/video/BV1xx/】"
        assert clean_url(raw) == "https://www.bilibili.com/video/BV1xx/"


class TestCJKTrailing:
    """URL 后紧跟中文/全角标点没空格时，不能把中文尾巴吞进 URL。"""

    def test_xhs_app_share_no_chinese_tail(self):
        raw = (
            "XX发布了一篇小红书笔记，快来看吧！ 😆 hQ3abc 😆 "
            "http://xhslink.com/a/abc123，复制本条信息，打开【小红书】App查看精彩内容！"
        )
        assert clean_url(raw) == "http://xhslink.com/a/abc123"

    def test_xhslink_m_short_link_kept(self):
        assert clean_url("http://xhslink.com/m/1gJ5tOG6M1b") == "http://xhslink.com/m/1gJ5tOG6M1b"

    def test_bili_app_share_chinese_tail(self):
        raw = "【标题】 https://www.bilibili.com/video/BV1xx/?share_source=copy_web，复制打开"
        assert clean_url(raw) == "https://www.bilibili.com/video/BV1xx/"

    def test_emoji_glued_to_url(self):
        raw = "😆http://xhslink.com/a/abc123😆复制本条信息"
        assert clean_url(raw) == "http://xhslink.com/a/abc123"
