"""WebUI 模板结构测试 —— 锁定「红蓝品牌」重做后的关键 UI 契约。

与 test_routes.py 互补：那边测 API/路由契约，这边测重做后的模板里
该有的 UI 元素（平台识别、状态筛选、渲染⇄源码切换、防 XSS 清洗、
空状态引导等），防止以后改模板把这些体验悄悄改没。

策略同 test_routes：dependency_overrides 注入临时 Storage，只看 HTML 输出。
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.web.routes import app, get_storage, get_pipeline_fn


@pytest.fixture
def mock_storage(tmp_path):
    from app.extract.storage import Storage
    return Storage(tmp_path / "test.db")


@pytest.fixture
def client(mock_storage):
    pipe = MagicMock()
    pipe.return_value = "/fake/path/file.md"
    app.dependency_overrides[get_storage] = lambda: mock_storage
    app.dependency_overrides[get_pipeline_fn] = lambda: pipe
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── 基础外壳（base.html） ──────────────────────────────────────

class TestBaseShell:

    def test_brand_present(self, client):
        html = client.get("/").text
        assert "Red Blue CP" in html

    def test_loads_web_font(self, client):
        """拉丁文用 Plus Jakarta Sans（Bunny Fonts CDN，隐私友好）"""
        html = client.get("/").text
        assert "fonts.bunny.net" in html
        assert "plus-jakarta-sans" in html

    def test_has_toast_host(self, client):
        """全局 toast 容器 + 辅助函数"""
        html = client.get("/").text
        assert 'id="toast-host"' in html
        assert "rbToast" in html

    def test_no_old_gradient_banner(self, client):
        """旧版顶部红粉蓝渐变 banner（AI 味）应已移除"""
        html = client.get("/").text
        assert "120deg, #e5484d 0%, #d83b6c" not in html


# ── 首页（index.html） ─────────────────────────────────────────

class TestIndexPage:

    def test_has_url_input(self, client):
        html = client.get("/").text
        assert 'id="url-input"' in html
        assert 'type="url"' in html

    def test_has_status_filters(self, client):
        """状态筛选 chip：全部 / 处理中 / 已完成 / 失败"""
        html = client.get("/").text
        for f in ("all", "running", "done", "failed"):
            assert f'data-filter="{f}"' in html

    def test_has_platform_detection(self, client):
        """输入即识别 B站 / 小红书平台"""
        html = client.get("/").text
        assert "detectPlatform" in html
        assert "bilibili" in html
        assert "xiaohongshu" in html

    def test_has_job_list_container(self, client):
        html = client.get("/").text
        assert 'id="job-list"' in html

    def test_has_empty_state_guidance(self, client):
        """空状态要引导，而不是只有「暂无任务」"""
        html = client.get("/").text
        assert "还没有任务" in html

    def test_polls_for_updates(self, client):
        html = client.get("/").text
        assert "setInterval" in html
        assert "/api/jobs" in html

    def test_anti_flicker_signature(self, client):
        """防闪烁：内容未变不重绘（lastSignature 门控）"""
        html = client.get("/").text
        assert "lastSignature" in html


# ── 详情页（detail.html） ──────────────────────────────────────

class TestDetailPage:

    def _job(self, storage):
        return storage.create_job("https://www.bilibili.com/video/BV1detail")

    def test_has_breadcrumb_back(self, client, mock_storage):
        job_id = self._job(mock_storage)
        html = client.get(f"/jobs/{job_id}").text
        assert "← 任务" in html

    def test_has_render_source_toggle(self, client, mock_storage):
        """渲染 ⇄ 源码 分段开关"""
        job_id = self._job(mock_storage)
        html = client.get(f"/jobs/{job_id}").text
        assert 'id="view-rendered"' in html
        assert 'id="view-source"' in html
        assert "渲染" in html and "源码" in html

    def test_loads_markdown_renderer(self, client, mock_storage):
        """marked 负责 Markdown→HTML"""
        job_id = self._job(mock_storage)
        html = client.get(f"/jobs/{job_id}").text
        assert "marked" in html
        assert "marked.parse" in html

    def test_sanitizes_rendered_html(self, client, mock_storage):
        """不变量：爬来的内容渲染前必须 DOMPurify 清洗，防 XSS"""
        job_id = self._job(mock_storage)
        html = client.get(f"/jobs/{job_id}").text
        assert "DOMPurify" in html
        assert "DOMPurify.sanitize" in html

    def test_strips_frontmatter_before_render(self, client, mock_storage):
        """渲染态要去掉 YAML frontmatter，否则被 marked 当成超大标题（真实 md 都有 frontmatter）"""
        job_id = self._job(mock_storage)
        html = client.get(f"/jobs/{job_id}").text
        assert "stripFrontmatter" in html
        # 渲染走 stripFrontmatter，源码态保留原文
        assert "marked.parse(stripFrontmatter(" in html

    def test_download_uses_job_id(self, client, mock_storage):
        """下载走 job_id，不接受任意路径（不变量 #1）"""
        job_id = self._job(mock_storage)
        html = client.get(f"/jobs/{job_id}").text
        assert f"/api/jobs/{job_id}/download" in html

    def test_references_job_id(self, client, mock_storage):
        job_id = self._job(mock_storage)
        html = client.get(f"/jobs/{job_id}").text
        assert f'"{job_id}"' in html

    def test_has_copy_button(self, client, mock_storage):
        job_id = self._job(mock_storage)
        html = client.get(f"/jobs/{job_id}").text
        assert 'id="copy-button"' in html

    def test_failed_view_humanizes_error(self, client, mock_storage):
        """audit #2：失败默认给一句人话（前端 JS 按 error_message 关键词映射）"""
        job_id = self._job(mock_storage)
        html = client.get(f"/jobs/{job_id}").text
        assert "humanizeError" in html

    def test_failed_view_collapses_traceback(self, client, mock_storage):
        """技术细节（error_message + log_excerpt）折叠进原生 <details>，默认不糊给用户"""
        job_id = self._job(mock_storage)
        html = client.get(f"/jobs/{job_id}").text
        assert "<details" in html

    def test_failed_view_has_retry(self, client, mock_storage):
        """详情页失败要能重试：复用列表卡片机制 POST /api/jobs 重提 job.url"""
        job_id = self._job(mock_storage)
        html = client.get(f"/jobs/{job_id}").text
        assert "重试" in html
        assert "/api/jobs" in html
        assert "POST" in html

    def test_missing_job_returns_styled_html_not_json(self, client):
        """坏的 /jobs/{id} 要返回带样式的 404 页，而不是裸 JSON"""
        resp = client.get("/jobs/99999")
        assert resp.status_code == 404
        assert "html" in resp.headers.get("content-type", "").lower()
        assert "任务不存在" in resp.text
        assert not resp.text.strip().startswith("{")


# ── 首页卡片细节 ───────────────────────────────────────────────

class TestCardDetails:

    def test_source_url_shortened(self, client):
        """卡片源链接显示 host+path（去掉超长 query），避免撑满卡片"""
        html = client.get("/").text
        assert "shortUrl" in html
        assert "job-src" in html
