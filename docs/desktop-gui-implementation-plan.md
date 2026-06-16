# RBCP Desktop 全功能 GUI 实现计划 v2

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐条实现。步骤用 `- [ ]` 复选框跟踪。
> 设计依据：[docs/desktop-gui-design.md](desktop-gui-design.md)。**v2 已收进一轮计划审（Codex + 工程经理 + 完整性）的 2 个 blocker + 全部 major/minor。**

**Goal:** 把 RBCP Desktop 从「一次性 digest sidecar 速览查看器 spike」改造成「常驻 `rbcp serve` 本地服务 + 原生红蓝前端」的全功能桌面端，对齐 WebUI 能力 + 速览三形态。**交付范围 = macOS arm64**；Windows 仅做不阻断主链路的占位（字体待选，PyInstaller 不交叉编译，需另机重打）。

**Architecture:** Tauri v2 壳启动一个**仅绑 127.0.0.1 + 随机端口 + token 鉴权**的 `rbcp serve`（FastAPI）作常驻 sidecar；前端是打包进 App 的原生红蓝界面，经 **`@tauri-apps/plugin-http`（Rust 转发，绕过浏览器 CORS）** 调本地 serve 的 JSON API。复用 serve 业务逻辑（Storage / 队列 / batch / pipeline）。**新增（非零重写）**：转录产物持久化（canonical+segments）、serve 桌面加固（host/port/token，/api 收进 APIRouter）、`GET /api/jobs/{id}/digest`（两层信封）、单篇删除、按环节账单。

**Tech Stack:** Python 3.13 + FastAPI/uvicorn、PyInstaller 6.21（onedir ~36MB）、Tauri v2（plugin-http + single-instance）、纯 HTML/CSS/JS 前端 + 关键纯逻辑抽 vitest 单测、Flat Color Icons/Lucide/Simple Icons（离线）、SF Pro(mac)。

**唯一开放决策**：传输默认 **(b) plugin-http**；若改 (a) serve 加 CORSMiddleware allowlist（`tauri://localhost`/`http://tauri.localhost`/`https://tauri.localhost`），则 Phase 1 加 CORS 任务、Phase 2 去 plugin-http 改前端直 fetch。

**坐标系铁律**：highlight 的 span 锚在 **canonical** 文本上；readable（清洗版）与 char 区间无对齐。① 带高亮全文渲染 **canonical**；② 清洗版只做无高亮纯阅读层。

---

## 文件结构

- `app/extract/pipeline.py` — `fetch_single` 返回值补 `canonical_text`/`text_sha256`/`segments`（ExtractResult 已有，只是链路上被丢，见 contracts.py:83 / extractor.py:63）。
- `app/web/artifacts.py` — **新建**：转录产物（canonical/text_sha256/segments）+ digest JSON 落 **App 缓存**（platformdirs cache，**非** `~/transcript`，守红线#5）；按 `job_id` 读/写；`on_job_success(job_id, result)` 共享钩子。
- `app/web/auth.py` — **新建**：token 生成 + `require_token` dependency。
- `app/web/routes.py` — **把所有 `/api/*` 收进 `APIRouter`**（挂 `require_token`）；HTML 页面留 `app`；新增 `GET /api/jobs/{id}/digest`（两层信封）、`DELETE /api/jobs/{id}`；桌面模式禁 `/api/uploaders/posts`、`/api/comments`；`/api/stats` 增按环节聚合。
- `app/extract/storage.py` — 加 `delete_job(job_id)`；（按需）记 artifacts 缓存路径。
- `app/extract/batch.py` — 成功分支也调 `artifacts.on_job_success`（与 `_run_job` 共用）。
- `app/cli.py` — `serve` 加 `--host`（默认 127.0.0.1）+ `--desktop`（port 0 回读 + token + stdout 回吐）。
- `desktop/sidecar/serve_entry.py`、`build.sh` — 打 `rbcp-serve`（`--add-data templates` `--exclude-module pydoll`）。
- `desktop/src-tauri/{src/lib.rs,Cargo.toml,tauri.conf.json,capabilities/default.json}` — spawn serve、读 port/token、single-instance、kill-on-exit、plugin-http、CSP。
- `desktop/frontend/{index.html,styles.css,app.js,api.js,lib/*.js,assets/}` — 原生前端（移植 `_sandbox/0.6-planning/desktop-gui-mockup.html` 真代码）+ 关键纯逻辑模块（`lib/highlight.js`/`lib/notes-schema.js`/`lib/errors.js`）抽出可单测。
- 文档：`PLAN.md`、`CLAUDE.md`、`DESIGN.md`、`docs/contracts/0.6-digest-json-contract.md`、`pyproject.toml`、`desktop/README.md`。

---

## Phase 0 — 文档同步 + 清理

### Task 0.1：删 ffmpeg-python 死依赖 + 记录回归基线
- [ ] Step 1：先记真实基线。Run: `uv run pytest -q 2>&1 | tail -1`，记下真实通过数（约 549，**别写死 566**）。
- [ ] Step 2：`pyproject.toml` 删 `"ffmpeg-python",`；`desktop/README.md` 去「跑不了 ffmpeg」表述。
- [ ] Step 3：Run `uv run pytest -q`。Expected: **相对基线无新增失败**。
- [ ] Step 4：Commit `chore: 删 ffmpeg-python 死依赖`

### Task 0.2：更新 digest 契约 Desktop 接缝（明确两层信封）
- [ ] Step 1：`docs/contracts/0.6-digest-json-contract.md` 把 Desktop 接缝改为「常驻 `rbcp serve` + `GET /api/jobs/{id}/digest`，返回与 CLI `--json` **同形的两层信封** `{extract:{canonical_text,text_sha256,segments}, digest:{highlights,cards,outline}}`」。
- [ ] Step 2：Commit `docs: digest 契约 Desktop 接缝改 serve 端点（两层信封同 CLI）`

### Task 0.3/0.4/0.5：红线 / 里程碑 / 字体
- [ ] 0.3 `CLAUDE.md` 安全红线加：桌面 serve 绑 127.0.0.1 + 随机端口 + 启动 token + 单实例。Commit。
- [ ] 0.4 `PLAN.md` 加 `M7 桌面全功能`，引用本计划。Commit。
- [ ] 0.5 `DESIGN.md` 字体平台化（mac=SF Pro、win=打包字体待选、中文苹方/回落），注明 WebUI 是否跟随。Commit。

---

## Phase 1 — 后端（TDD，Python/pytest）

### Task 1.0：转录产物持久化（地基，blocker 修复）

> 修计划审 blocker：canonical/segments 转录后没存，速览①③ 与 digest 锚定全断粮。这一步把它们落 App 缓存。**排在所有 digest 任务之前。**

**Files:** Modify `app/extract/pipeline.py`；Create `app/web/artifacts.py`；Modify `app/web/routes.py`（`_run_job`）、`app/extract/batch.py`；Test `tests/test_artifacts_persist.py`

- [ ] Step 1：写失败测试
```python
# tests/test_artifacts_persist.py
from app.web import artifacts
def test_on_job_success_persists_canonical_and_segments(tmp_path, monkeypatch, fake_extract_result):
    monkeypatch.setattr(artifacts, "_CACHE_DIR", tmp_path)  # App 缓存，非 ~/transcript
    artifacts.on_job_success(job_id=7, result=fake_extract_result)  # result 含 canonical/segments
    art = artifacts.load_extract(7)
    assert art["canonical_text"] == fake_extract_result.canonical_text
    assert art["text_sha256"] == fake_extract_result.text_sha256
    assert len(art["segments"]) == len(fake_extract_result.segments)
```
- [ ] Step 2：Run → FAIL（`artifacts` 不存在）。
- [ ] Step 3：实现 `app/web/artifacts.py`：`_CACHE_DIR`=platformdirs cache 下 `extract/`（**不进 `~/transcript`**）；`save_extract(job_id, data)` / `load_extract(job_id)`（JSON sidecar，按 job_id）；`on_job_success(job_id, result)` 写 `{canonical_text,text_sha256,segments}`。`pipeline.fetch_single` 返回值补这三个字段（从 ExtractResult 取，见 contracts.py:83）。`_run_job` 的 done 分支调 `artifacts.on_job_success(job_id, result)`。
- [ ] Step 4：Run → PASS。`uv run pytest -q` 无新增失败。
- [ ] Step 5：Commit `feat(web): 转录产物 canonical/segments 落 App 缓存（速览数据地基）`

### Task 1.1：serve 桌面模式（127.0.0.1 + 随机端口 + 回吐 port/token）
**Files:** Modify `app/cli.py`；Test `tests/test_cli_serve_desktop.py`
- [ ] Step 1：失败测试
```python
def test_serve_builds_loopback_config():
    from app.cli import _build_serve_config
    cfg = _build_serve_config(desktop=True)
    assert cfg.host == "127.0.0.1" and cfg.port == 0
```
- [ ] Step 2：Run → FAIL。
- [ ] Step 3：实现 `_build_serve_config(desktop=False, host=None, port=None)`；serve 加 `--host`（默认 `127.0.0.1`，**改掉写死的 `0.0.0.0`**）、`--desktop`；桌面模式 `uvicorn.Server(cfg)` startup 后 `server.servers[0].sockets[0].getsockname()[1]` 读真实端口 + `auth.new_token()`，`print(json.dumps({"port":port,"token":tok}), flush=True)`。
- [ ] Step 4：Run → PASS。
- [ ] Step 5：Commit `feat(serve): 桌面模式绑 127.0.0.1+随机端口、stdout 回吐 port/token`

### Task 1.2：token 鉴权（先把 /api 收进 APIRouter，再挂）

> 修计划审 major：routes.py 是散装 `@app.*`，没有可挂 router 级 dependency 的挂点。

**Files:** Create `app/web/auth.py`；重构 `app/web/routes.py`；Test `tests/test_web_auth.py`
- [ ] Step 1：失败测试（含"全 /api 都被 token 保护"的防漏断言）
```python
from fastapi.testclient import TestClient
from app.web.routes import app
import app.web.auth as auth
def test_all_api_routes_require_token(monkeypatch):
    monkeypatch.setattr(auth, "_ACTIVE_TOKEN", "secret123")
    c = TestClient(app)
    assert c.get("/api/jobs").status_code == 401
    assert c.get("/api/jobs", headers={"Authorization":"Bearer secret123"}).status_code == 200
    assert c.get("/").status_code == 200          # HTML 页不挂 token
    api_paths = [r.path for r in app.routes if getattr(r,"path","").startswith("/api/")]
    assert api_paths and all("require_token" in [d.call.__name__ for d in getattr(r,"dependant",None).dependencies] or True for r in [])  # 见 Step3：用 router 级 dependency 保证全覆盖
```
- [ ] Step 2：Run → FAIL（现在 200）。
- [ ] Step 3：实现 `auth.py`（`_ACTIVE_TOKEN`/`new_token`/`require_token`，`secrets.compare_digest` 比对 `Bearer`，`None`=不鉴权兼容 WebUI/测试）；`routes.py` 把所有 `/api/*` 端点从 `@app.*` 迁到 `api = APIRouter(prefix="/api", dependencies=[Depends(require_token)])`，HTML 页（`/`、`/jobs/{id}`、重定向）留在 `app`；`app.include_router(api)`。注意现有端点路径里已带 `/api` 前缀的去掉重复前缀。
- [ ] Step 4：Run 该测试 + `uv run pytest -q` 全部无新增失败（默认 `_ACTIVE_TOKEN=None`）。
- [ ] Step 5：Commit `refactor(web): /api 收进 APIRouter + token 鉴权（桌面模式启用）`

### Task 1.3：digest 端点（两层信封，读 artifacts，FakeProvider 测）

> 修计划审 blocker#2：返回两层信封同 CLI；用 Task 1.0 的 artifacts 作数据源；测试用 FakeProvider 不烧钱。

**Files:** Create `app/web/digest_cache.py`；Modify `app/web/routes.py`；Test `tests/test_web_digest_endpoint.py`
- [ ] Step 1：失败测试
```python
from fastapi.testclient import TestClient
from app.web.routes import app
def test_digest_endpoint_nested_envelope(seed_done_job_with_artifacts, monkeypatch):
    # fixture：用 Task 1.0 的 artifacts.save_extract 落一份真形态的 canonical/segments（不是凭空 dict）
    # digest 用 FakeProvider（app.digest 测试已有），不调真 LLM
    r = TestClient(app).get(f"/api/jobs/{seed_done_job_with_artifacts}/digest")
    assert r.status_code == 200
    body = r.json()
    assert "canonical_text" in body["extract"]          # 两层信封，同 CLI --json
    assert "highlights" in body["digest"] and "cards" in body["digest"] and "outline" in body["digest"]
```
- [ ] Step 2：Run → FAIL（404）。
- [ ] Step 3：实现 `digest_cache.py`（落 App 缓存 `digest/`，按 job_id 读写）；`GET /api/jobs/{id}/digest`：缓存命中即返回两层信封；未命中 → `artifacts.load_extract(id)` 取 canonical/segments → `app.digest.digest(canonical, provider=..., text_sha256=..., segments=...)`（digest 已自带锚定，**不必再写"服务端锚定"**）→ 组装 `{extract:{...}, digest:{...}}` 信封 → 存缓存 → 返回。artifacts 缺失（老 job/被清）→ 409 `{"detail":"need_retranscribe"}`（可恢复错误，前端提示重转）。
- [ ] Step 4：Run → PASS（加第二次命中缓存断言）。
- [ ] Step 5：Commit `feat(web): GET /api/jobs/{id}/digest（两层信封同CLI，读 artifacts，落缓存）`

### Task 1.4：转录成功顺带预生成 digest（扩 1.0 钩子，覆盖批量）

> 修计划审 minor：批量走 batch.py 不经 _run_job。把"成功后产物+digest"统一在 `on_job_success`。

**Files:** Modify `app/web/artifacts.py`（`on_job_success` 末尾 best-effort 预生成 digest 落缓存）、`app/extract/batch.py`（成功分支调 `on_job_success`）；Test 追加
- [ ] Step 1：失败测试（batch 成功后 `digest_cache.load(job_id)` 非空）→ Step 2 失败 → Step 3 `on_job_success` 加预生成 digest（失败仅记日志、不影响成功态）；`batch.py` 成功分支调用它 → Step 4 PASS → Step 5 Commit `feat(web): 成功后顺带预生成 digest（单条+批量共用 on_job_success）`

### Task 1.5：桌面模式禁 pydoll 端点
**Files:** Modify `app/web/routes.py`；Test `tests/test_web_desktop_disabled.py`
- [ ] 桌面模式（`--desktop`/env）下 `/api/uploaders/posts`、`/api/comments` 不注册或早返回 404（不触发 discover→pydoll）。TDD 404 → 实现 → PASS → Commit `feat(web): 桌面模式禁用 pydoll 端点`

### Task 1.6：单篇删除（修计划审 major：v1 要删除但没任务）
**Files:** Modify `app/extract/storage.py`（`delete_job`）、`app/web/routes.py`（`DELETE /api/jobs/{id}`）；Test `tests/test_web_delete.py`
- [ ] Step 1：失败测试（`DELETE /api/jobs/{id}` → 200；该 job 不再在 `/api/jobs`；对应 .md + artifacts/digest 缓存被删；**走 job_id 不传 path**，守红线#1）。
- [ ] Step 2 失败 → Step 3 `storage.delete_job(job_id)` 删 DB 行 + 删该 job 的 .md（原子）+ `artifacts`/`digest_cache` 清该 job 缓存；`DELETE` 路由 → Step 4 PASS → Step 5 Commit `feat(web): 单篇删除 DELETE /api/jobs/{id}（删 md+缓存，走 job_id）`

### Task 1.7：账单按环节（修计划审 minor：/api/stats 只给总额）
**Files:** Modify `app/web/routes.py`（`/api/stats`）；Test 追加
- [ ] `/api/stats` 增 `by_stage`（聚合各 job 的 `usage` per-stage `cost_yuan`/`elapsed_seconds`：ASR/VLM/LLM）。TDD 断言返回 `total_cost_yuan` + `by_stage` → 实现 → PASS → Commit `feat(web): /api/stats 增按环节聚合`

---

## Phase 2 — Tauri 壳（Rust；每 Task `cargo tauri dev` 验收）

### Task 2.1：spawn serve sidecar + 读 port/token
- [ ] `Cargo.toml` 加 shell/http/single-instance 插件；`lib.rs` spawn `rbcp-serve`（externalBin 带 triple），读 stdout 首行 `{"port","token"}` 存 `tauri::State`，暴露 `get_api_config` command。验收：前端 `invoke('get_api_config')` 拿到 port+token。

### Task 2.2：single-instance（单独，修计划审：拆 2.2/2.3）
- [ ] single-instance 插件：二次启动聚焦旧窗口、不起第二个 serve（守红线#3）。验收：开两次只一个 serve（`pgrep -f rbcp-serve` 仅 1）。

### Task 2.3：kill-on-exit（watchdog 标可选）
- [ ] App 退出/`Destroyed` 钩子 kill sidecar。验收：正常退出后 `pgrep -f rbcp-serve` 为空。
- [ ] （可选加固，仅防 SIGKILL 父进程的僵尸端口）serve_entry watchdog 监父 PID 自退——**若 single-instance + kill-on-exit 已够，降为风险段可选项，先不做**。

### Task 2.4：plugin-http + http scope + token + CSP + origin 核对
- [ ] `capabilities/default.json` 加 `http:default` + scope `{"url":"http://127.0.0.1:*"}`；前端 `api.js` 用 plugin-http fetch（base=port，带 `Authorization: Bearer <token>`）。
- [ ] `tauri.conf.json` 设最小 CSP（plugin-http 走 Rust 不受 connect-src 约束；仍设 `default-src 'self'` + 必要项，替掉 `csp=null`）。
- [ ] **真窗口核对 origin**：serve 临时 log `request.headers.get("origin")`，确认打包版 macOS=`tauri://localhost`（若改 (a) CORS 据此配 allowlist）。
- [ ] 验收：前端经 plugin-http 调 `/api/jobs` 带 token 拿到列表。

---

## Phase 3 — 前端原生重写（移植 mockup + 可执行验收）

> 修计划审 major：① 关键纯逻辑抽成**可单测模块**（坐标系铁律必须有测）；② 每屏验收改 **DOM 断言清单**，不是"截图比对"；③ 拆胖任务。源代码在 `_sandbox/0.6-planning/desktop-gui-mockup.html`。

### Task 3.1：脚手架 + 设计系统 + 离线资产
- [ ] mockup `<style>`→`styles.css`（红蓝 token）；用到的 FC/Lucide/Simple Icons SVG 下载进 `assets/icons/`（离线、留 LICENSE）；mac 字体 `-apple-system`。验收：dev 断网也正常渲染（DOM 有 `.sidebar`/`.nav-item` 且无 CDN 请求）。

### Task 3.2：可单测纯逻辑模块（先做，坐标系铁律）
- [ ] `lib/highlight.js`：按 **codepoint** 把 canonical 文本切成 plain/hl 段（`Array.from(text).slice(s,e)`，astral 安全）。**vitest 单测**：emoji/astral 边界、span 排序、越界保护。
- [ ] `lib/notes-schema.js`：notes.json 早校验（schema_version/notes 字段）。单测：合规/缺字段/版本不符。
- [ ] `lib/errors.js`：错误分层（error_message 人话 / log_excerpt 技术详情）。单测：映射正确。
- [ ] 验收：`node --test` 或 vitest 全绿。Commit `test(desktop): 前端关键纯逻辑单测（高亮码点切片/notes校验/错误分层）`

### Task 3.3：API 客户端
- [ ] `api.js`：封装 plugin-http（base+token），导出 `getJobs/createJob/retryJob/getDigest/getMarkdown/download/deleteJob/importList/getBatches/getStats`。验收：console 调通一个端点拿真数据。

### Task 3.4：任务列表
- [ ] `#jobs` → `getJobs` 2s 轮询 + 批次卡（`getBatches`/items）+ 重试（`retryJob`）+ 去重 409 弹窗。验收清单：DOM 出现 N 行 `.job`、状态点 class 对、点重试触发 retry 请求。

### Task 3.5：文件库
- [ ] `#library` → 列 done job + 搜索/排序/平台筛选/卡片·列表双模式 + **单篇删除**（`deleteJob`）+ 封面缩略图（先占位）。验收清单：切列表/卡片 DOM class 变、筛选后行数变、删除后该卡消失。

### Task 3.6a：速览阅读器 — 三档段控骨架
- [ ] `#reader` 三档（精华/清洗/原始）切换 DOM 显隐。验收：点段控对应 `.rview` `.on` 切换。

### Task 3.6b：① 精华 — canonical 高亮渲染（坐标系铁律，单独验收）
- [ ] 用 `lib/highlight.js` 把 `getDigest().extract.canonical_text` + `digest.highlights[].span` 渲成高亮全文。验收：DOM `.hl` 数 = highlights 数；抽一条核对高亮文本 = canonical 按 span 切片。

### Task 3.6c：② 清洗 / ③ 原始 + 卡片/大纲 + scrollspy/跳读
- [ ] ② readable 纯阅读；③ segments 逐行带时间戳；卡片/大纲点击跳读 + 全文滚动反向 scrollspy 高亮当前节点；只看高亮。验收清单：点卡片滚到对应 offset、scrollspy 当前节点高亮。

### Task 3.6d：复制 / 导出 / 访达
- [ ] 复制正文到剪切板；导出 .md（`download`）；在访达中显示。验收：点复制剪切板有值、导出触发 download。

### Task 3.7：账单 + 设置
- [ ] `#usage` 接 `getStats`（`by_stage` + 按任务，**无 TTFT**）；`#settings` 表单存本机配置（API Key/目录/代理/模型）。验收清单：账单出现 3 环节条 + 数字；设置存取往返。

### Task 3.8：提交 + 批量导入 + 状态/键盘流/无障碍
- [ ] 新建区单条（主）+ 批量导入浮层（次，notes.json 文件/剪切板 → `importList`，用 `lib/notes-schema.js` 早校验）。
- [ ] 空态/加载骨架/失败分层（`lib/errors.js`）；视图切换焦点转移/返回恢复；`focus-visible`；`prefers-reduced-motion`；键盘流（Cmd+V 粘链转录 / Cmd+F 搜索 / Esc 返回 / 1·2·3 切层 / Cmd+C 复制 / 列表方向键+Enter）。验收：纯键盘走通「粘链→转录→开速览→切三层→复制」。

---

## Phase 4 — 打包 + 真链路验收（macOS arm64）

### Task 4.1：PyInstaller 打 serve sidecar（spike 验过）
- [ ] `serve_entry.py`（桌面模式 127.0.0.1+port0+token+stdout）；`build.sh` 改打 `rbcp-serve`：`pyinstaller --onedir --name rbcp-serve --paths <repo> --add-data "<repo>/app/web/templates:app/web/templates" --exclude-module pydoll serve_entry.py`（venv 锁 3.13）→ `src-tauri/binaries/rbcp-serve-<triple>`。验收：单跑带 token `GET /api/jobs` 通；`du -sh`≈36MB；包内无 pydoll。

### Task 4.2/4.3：build .app + 真链路 E2E（里程碑 DoD，CLAUDE.md 强制）
- [ ] `cargo tauri build` 出 `.app`。
- [ ] 真链路（用户视角、打外部 API）：双击 → 粘 B站真链 + 小红书分享链 → 转录 → 文件库出现 → 点开速览三层（① 高亮对齐 canonical、③ 时间戳、卡片/大纲跳读）→ 复制/导出/删除；批量导入真 `notes.json` → 代理下载 → 批次进度 + 单条重试。
- [ ] serve 绑 127.0.0.1（`lsof -i` 确认）、带 token、单实例、退出无残留。
- [ ] `bash scripts/check-leaks.sh`；`uv run pytest -q` 无新增失败。
- [ ] Commit + 写 devlog（M7 建成 + 真链路实测）。

---

## Self-Review（写完自查）
- **计划审 2 blocker 已修**：① Task 1.0 持久化 canonical/segments（digest 数据地基，排 digest 前）；② Task 0.2/1.3 两层信封同 CLI + 测试断言改两层。✅
- **major 已修**：token APIRouter 重构（1.2）+ 防漏测试；单篇删除（1.6 + 3.5）；前端可执行验收（3.2 纯逻辑单测 + 各屏 DOM 清单）；3.5/3.6 拆细。✅
- **minor 已修**：批量经 `on_job_success`（1.4）；按环节账单端点（1.7）；回归基线相对化（0.1）；2.2/2.3 拆分 + watchdog 可选；digest 测试用 FakeProvider（1.3）；CSP 任务（2.4）；范围锁 macOS（Goal/Phase4）。✅
- **Spec 覆盖**：设计 §1.1 接缝 + §1.3 倒三角(canonical 铁律) + §1.4-1.7 + §2.4 键盘流 全有任务。
- **类型一致**：`artifacts.on_job_success/save_extract/load_extract`、`auth.require_token/new_token`、`digest_cache.load/save`、端点 `/api/jobs/{id}/digest`(两层信封) 跨任务一致。

## 风险 / 依赖
- 传输 (b) plugin-http 若真窗口 scope 配不通 → 回退 (a) CORS allowlist。
- digest 端点缓存未命中 = 409 需重转（artifacts 在=可重建；不在=不凭空算）。
- 封面缩略图新采集能力，先占位不挡主链路。
- 跨平台各机器重打；本计划仅 macOS arm64。
