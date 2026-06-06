"""WebUI routes 测试 — 定义 FastAPI 接口契约 + 路径穿越安全。

测试策略：用 FastAPI dependency_overrides 注入 mock Storage 和 mock pipeline，
避免真正跑业务逻辑，专注测路由层。
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.web.routes import app, get_storage, get_pipeline_fn


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def tmp_md_dir(tmp_path):
    """临时目录用于放假的 .md 文件"""
    return tmp_path


@pytest.fixture
def mock_storage(tmp_md_dir):
    """In-memory storage backed by a real SQLite under tmp_path."""
    from app.service.storage import Storage
    return Storage(tmp_md_dir / "test.db")


@pytest.fixture
def mock_pipeline():
    """Pipeline 函数 mock，返回固定 md_path"""
    pipe = MagicMock()
    pipe.return_value = "/fake/path/to/file.md"
    return pipe


@pytest.fixture
def client(mock_storage, mock_pipeline):
    """TestClient with overridden dependencies."""
    app.dependency_overrides[get_storage] = lambda: mock_storage
    app.dependency_overrides[get_pipeline_fn] = lambda: mock_pipeline
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── POST /api/jobs ────────────────────────────────────────────

class TestCreateJob:

    def test_returns_job_id(self, client):
        resp = client.post("/api/jobs", json={"url": "https://www.bilibili.com/video/BV1test"})
        assert resp.status_code in (200, 201, 202)
        data = resp.json()
        assert "job_id" in data
        assert isinstance(data["job_id"], int)

    def test_creates_pending_job_in_storage(self, client, mock_storage):
        resp = client.post("/api/jobs", json={"url": "https://www.bilibili.com/video/BV1test"})
        job_id = resp.json()["job_id"]
        job = mock_storage.get_job(job_id)
        assert job is not None
        assert job["url"] == "https://www.bilibili.com/video/BV1test"

    def test_cleans_share_text_url(self, client, mock_storage):
        """粘贴 B 站分享文案（标题 + 追踪后缀）→ 存的是干净 URL。"""
        raw = "【标题】 https://www.bilibili.com/video/BV1ZZ/?share_source=copy_web&vd_source=abc"
        resp = client.post("/api/jobs", json={"url": raw})
        assert resp.status_code in (200, 201, 202)
        job = mock_storage.get_job(resp.json()["job_id"])
        assert job["url"] == "https://www.bilibili.com/video/BV1ZZ/"

    def test_missing_url_returns_422(self, client):
        resp = client.post("/api/jobs", json={})
        assert resp.status_code == 422

    def test_empty_url_rejected(self, client):
        resp = client.post("/api/jobs", json={"url": ""})
        assert resp.status_code in (400, 422)

    def test_unsupported_platform_rejected_early(self, client, mock_storage):
        """audit #4：非 B站/小红书链接提交时立即 400，别建 job 让用户白等一轮。"""
        resp = client.post("/api/jobs", json={"url": "https://www.youtube.com/watch?v=x"})
        assert resp.status_code == 400
        assert "不支持" in resp.json().get("detail", "")
        # 不该留下任何 job
        assert mock_storage.list_jobs() == []

    def test_supported_platform_still_creates_job(self, client):
        resp = client.post("/api/jobs", json={"url": "https://www.xiaohongshu.com/explore/abc"})
        assert resp.status_code in (200, 201, 202)
        assert "job_id" in resp.json()


# ── POST /api/jobs/{id}/retry ─────────────────────────────────

class TestRetryJob:

    def test_retry_reuses_same_job_not_new(self, client, mock_storage):
        job_id = mock_storage.create_job("https://www.bilibili.com/video/BV1x")
        mock_storage.mark_running(job_id)
        mock_storage.mark_failed(job_id, error_message="boom", log_excerpt="tb")
        resp = client.post(f"/api/jobs/{job_id}/retry")
        assert resp.status_code in (200, 201, 202)
        assert resp.json()["job_id"] == job_id      # 同一条，不新建
        assert len(mock_storage.list_jobs()) == 1    # 没堆出新任务

    def test_retry_404_on_missing(self, client):
        assert client.post("/api/jobs/99999/retry").status_code == 404


class TestResetForRetry:
    """storage.reset_for_retry 重置语义（直测，避开路由后台时序）。"""

    def test_resets_failed_job_in_place(self, mock_storage):
        job_id = mock_storage.create_job("https://x/1")
        mock_storage.mark_running(job_id)
        mock_storage.mark_failed(job_id, error_message="boom", log_excerpt="tb")
        assert mock_storage.reset_for_retry(job_id) is True
        job = mock_storage.get_job(job_id)
        assert job["status"] == "pending"
        assert job["error_message"] is None
        assert job["retry_count"] == 1

    def test_returns_false_on_missing(self, mock_storage):
        assert mock_storage.reset_for_retry(99999) is False


class TestSafeErrorDetail:
    """log_excerpt 脱敏：异常链摘要，绝不泄漏文件路径 / 用户名 / traceback。"""

    def test_no_paths_or_username_leak(self):
        from app.web.routes import _safe_error_detail
        from app.service.errors import NetworkError

        try:
            try:
                raise TimeoutError("read timed out")
            except TimeoutError as e:
                raise NetworkError("DashScope llm_clean 网络重试 3 次仍失败") from e
        except NetworkError as err:
            detail = _safe_error_detail(err)

        assert "NetworkError" in detail and "网络重试 3 次" in detail
        assert "TimeoutError" in detail            # 异常链保留，便于排查
        for leak in ("/home/", ".venv", "site-packages", 'File "', "line "):
            assert leak not in detail, f"泄漏了 {leak!r}"


# ── GET /api/jobs ─────────────────────────────────────────────

class TestListJobs:

    def test_empty_returns_empty_list(self, client):
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.json()
        # 可能返回 list 或 {"jobs": [...]}
        jobs = data if isinstance(data, list) else data.get("jobs", data)
        assert jobs == [] or len(jobs) == 0

    def test_returns_existing_jobs(self, client, mock_storage):
        mock_storage.create_job("https://example.com/1")
        mock_storage.create_job("https://example.com/2")
        resp = client.get("/api/jobs")
        data = resp.json()
        jobs = data if isinstance(data, list) else data.get("jobs", data)
        assert len(jobs) == 2

    def test_supports_limit_param(self, client, mock_storage):
        for i in range(5):
            mock_storage.create_job(f"https://example.com/{i}")
        resp = client.get("/api/jobs?limit=3")
        data = resp.json()
        jobs = data if isinstance(data, list) else data.get("jobs", data)
        assert len(jobs) == 3

    def test_supports_offset_param(self, client, mock_storage):
        for i in range(5):
            mock_storage.create_job(f"https://example.com/{i}")
        resp = client.get("/api/jobs?limit=2&offset=2")
        data = resp.json()
        jobs = data if isinstance(data, list) else data.get("jobs", data)
        assert len(jobs) == 2


# ── GET /api/jobs/{id} ────────────────────────────────────────

class TestGetJob:

    def test_returns_job(self, client, mock_storage):
        job_id = mock_storage.create_job("https://example.com")
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == job_id
        assert data["url"] == "https://example.com"

    def test_404_on_nonexistent(self, client):
        resp = client.get("/api/jobs/99999")
        assert resp.status_code == 404

    def test_includes_status(self, client, mock_storage):
        job_id = mock_storage.create_job("https://example.com")
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.json()["status"] == "pending"


# ── GET /api/jobs/{id}/markdown ───────────────────────────────

class TestGetMarkdown:

    def test_returns_content_when_done(self, client, mock_storage, tmp_md_dir):
        md_file = tmp_md_dir / "test.md"
        md_file.write_text("# Test Markdown\n\n内容", encoding="utf-8")

        job_id = mock_storage.create_job("https://example.com")
        mock_storage.mark_running(job_id)
        mock_storage.mark_done(job_id, md_path=str(md_file), title="Test", author="A")

        resp = client.get(f"/api/jobs/{job_id}/markdown")
        assert resp.status_code == 200
        # 可能返回 plain text 或 JSON
        body = resp.text
        assert "Test Markdown" in body or "内容" in body

    def test_404_when_job_not_found(self, client):
        resp = client.get("/api/jobs/99999/markdown")
        assert resp.status_code == 404

    def test_404_when_not_done(self, client, mock_storage):
        job_id = mock_storage.create_job("https://example.com")
        # 没有 mark_done，所以 md_path 是 None
        resp = client.get(f"/api/jobs/{job_id}/markdown")
        assert resp.status_code == 404

    def test_404_when_md_file_missing(self, client, mock_storage):
        job_id = mock_storage.create_job("https://example.com")
        mock_storage.mark_running(job_id)
        mock_storage.mark_done(job_id, md_path="/nonexistent/file.md", title="X", author="Y")
        resp = client.get(f"/api/jobs/{job_id}/markdown")
        assert resp.status_code == 404


# ── GET /api/jobs/{id}/download ───────────────────────────────

class TestDownload:

    def test_returns_file(self, client, mock_storage, tmp_md_dir):
        md_file = tmp_md_dir / "下载测试.md"
        md_file.write_text("# 下载内容", encoding="utf-8")

        job_id = mock_storage.create_job("https://example.com")
        mock_storage.mark_running(job_id)
        mock_storage.mark_done(job_id, md_path=str(md_file), title="X", author="Y")

        resp = client.get(f"/api/jobs/{job_id}/download")
        assert resp.status_code == 200
        assert "下载内容" in resp.text

    def test_content_disposition_header(self, client, mock_storage, tmp_md_dir):
        md_file = tmp_md_dir / "test.md"
        md_file.write_text("content", encoding="utf-8")

        job_id = mock_storage.create_job("https://example.com")
        mock_storage.mark_running(job_id)
        mock_storage.mark_done(job_id, md_path=str(md_file), title="X", author="Y")

        resp = client.get(f"/api/jobs/{job_id}/download")
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd.lower() or "filename" in cd.lower()

    def test_404_on_nonexistent(self, client):
        resp = client.get("/api/jobs/99999/download")
        assert resp.status_code == 404


# ── 路径穿越安全（不变量 #1） ──────────────────────────────────

class TestPathTraversal:

    def test_dotdot_in_id_returns_4xx(self, client):
        """SPEC §4.1: 文件接口必须通过 job_id（int）反查"""
        resp = client.get("/api/jobs/abc/../../etc/passwd")
        # FastAPI 的 int 类型校验会直接 404 或 422
        assert resp.status_code in (404, 422)

    def test_string_id_rejected(self, client):
        resp = client.get("/api/jobs/abc/markdown")
        assert resp.status_code in (404, 422)

    def test_negative_id(self, client):
        resp = client.get("/api/jobs/-1/markdown")
        assert resp.status_code in (404, 422)

    def test_no_path_query_in_download(self, client):
        """绝不允许通过 query 参数传 path"""
        resp = client.get("/api/jobs/1/download?path=/etc/passwd")
        # 即使有 path 参数也不能用，应该走 job_id 反查
        # 这个测试只确认不会泄漏 /etc/passwd 内容
        if resp.status_code == 200:
            assert "root:" not in resp.text

    def test_no_arbitrary_file_endpoint(self, client):
        """确保没有 GET /api/files/{path} 这种危险接口"""
        resp = client.get("/api/files/../../etc/passwd")
        assert resp.status_code == 404
        resp = client.get("/api/files/etc/passwd")
        assert resp.status_code == 404


# ── 首页和详情页（HTML） ───────────────────────────────────────

class TestHtmlPages:

    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        ct = resp.headers.get("content-type", "")
        assert "html" in ct.lower()

    def test_index_has_input_form(self, client):
        resp = client.get("/")
        # 至少要有 input 或 form 元素
        assert "<input" in resp.text or "<form" in resp.text or "<textarea" in resp.text

    def test_job_detail_page_exists(self, client, mock_storage):
        job_id = mock_storage.create_job("https://example.com")
        resp = client.get(f"/jobs/{job_id}")
        assert resp.status_code == 200
        ct = resp.headers.get("content-type", "")
        assert "html" in ct.lower()

    def test_job_detail_page_includes_job_id(self, client, mock_storage):
        """模板必须把 job_id 注入 JS / fetch URL，否则前端拉不到具体任务"""
        # 用一个 url 里不包含 id 数字的 job，避免误判
        job_id = mock_storage.create_job("https://www.bilibili.com/video/abcdef")
        # 创建几个干扰 job 让 id 不是 1
        for _ in range(7):
            mock_storage.create_job("https://example.com/x")
        target = mock_storage.create_job("https://www.bilibili.com/video/target")

        resp = client.get(f"/jobs/{target}")
        # 期望 HTML 里出现 /api/jobs/{target} 或者 "{target}" 这种 jobId 字面量
        assert f'/api/jobs/{target}' in resp.text or f'"{target}"' in resp.text

    def test_job_detail_404_on_missing(self, client):
        resp = client.get("/jobs/99999")
        assert resp.status_code == 404


# ── 异步任务触发 ──────────────────────────────────────────────

class TestAsyncJobExecution:

    def test_job_runs_in_background(self, client, mock_storage, mock_pipeline, tmp_md_dir):
        """提交任务后，pipeline 应被异步调用（最终状态变为 done）"""
        # pipeline 返回 dict（包含 md_path + 业务元数据）
        md_file = tmp_md_dir / "result.md"
        md_file.write_text("done", encoding="utf-8")
        mock_pipeline.return_value = {
            "md_path": str(md_file),
            "title": "测试视频标题",
            "author": "测试UP主",
            "platform": "bilibili",
            "content_type": "video",
        }

        resp = client.post("/api/jobs", json={"url": "https://www.bilibili.com/video/BV1test"})
        job_id = resp.json()["job_id"]

        # TestClient 是同步的，但 create_task 应该已经被调度
        # 等一小段时间让后台任务运行
        import time
        for _ in range(20):
            job = mock_storage.get_job(job_id)
            if job["status"] in ("done", "failed"):
                break
            time.sleep(0.05)

        job = mock_storage.get_job(job_id)
        assert job["status"] == "done", f"Expected done, got {job['status']}: {job.get('error_message')}"
        assert mock_pipeline.called

    def test_done_job_persists_metadata(self, client, mock_storage, mock_pipeline, tmp_md_dir):
        """成功的任务必须把 title/author/platform/content_type 写入 storage（修 UI '未知作者' bug）"""
        md_file = tmp_md_dir / "result.md"
        md_file.write_text("hello", encoding="utf-8")
        mock_pipeline.return_value = {
            "md_path": str(md_file),
            "title": "我的视频标题",
            "author": "张三UP",
            "platform": "bilibili",
            "content_type": "video",
        }

        resp = client.post("/api/jobs", json={"url": "https://www.bilibili.com/video/BV1test"})
        job_id = resp.json()["job_id"]

        import time
        for _ in range(20):
            job = mock_storage.get_job(job_id)
            if job["status"] in ("done", "failed"):
                break
            time.sleep(0.05)

        job = mock_storage.get_job(job_id)
        assert job["status"] == "done"
        assert job["title"] == "我的视频标题"
        assert job["author"] == "张三UP"
        assert job["platform"] == "bilibili"
        assert job["content_type"] == "video"

    def test_failed_job_persists_error(self, client, mock_storage, mock_pipeline):
        """pipeline 抛错时，job 应该被 mark_failed 并存 error_message"""
        mock_pipeline.side_effect = RuntimeError("API 403 风控")

        resp = client.post("/api/jobs", json={"url": "https://www.xiaohongshu.com/explore/abc"})
        job_id = resp.json()["job_id"]

        import time
        for _ in range(20):
            job = mock_storage.get_job(job_id)
            if job["status"] in ("done", "failed"):
                break
            time.sleep(0.05)

        job = mock_storage.get_job(job_id)
        assert job["status"] == "failed"
        assert "403" in (job.get("error_message") or "")
