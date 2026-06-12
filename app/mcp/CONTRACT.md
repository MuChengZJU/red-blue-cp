# Agent 动词契约 · MCP Demo（实验性）

> **状态：实验 demo（`exp/agent-interface-demo` 分支），未立项。** 拍板转正前不改 PRD/PLAN/SPEC/README/LOG。
> 设计依据：[深度诊断报告](../../docs/devlog/2026-06-10-deep-diagnosis-report.md) §五 + 方向讨论（"可读化层 / Agent 是第一读者"）。
> 协议事实源：[MCP 协议笔记](../../docs/devlog/2026-06-12-mcp-protocol-spec-notes.md)（已对官方规范核实）。

## 定位（一句话）

把 rbcp 的 service 层以 **4 个 Agent 动词** 暴露成本地 stdio MCP server，证明两件事：
① Agent（Claude Code / Claude Desktop）可以直接"读"B站/小红书内容和已攒下的本地语料库；
② 这只是 `service/` 之上的第四层薄壳——**零修改任何现有文件、零新增依赖（纯标准库）**。

## 硬约束（违反即 demo 失败）

1. **零修改现有文件**：只新增 `app/mcp/`、`tests/test_mcp_demo.py`、`scripts/mcp_demo_smoke.py`、`docs/devlog/2026-06-12-*.md`。不碰 `service/`、`web/`、`cli.py`、`pyproject.toml`、任何文档主干。
2. **零新增依赖**：只用标准库（`json/sys/threading/dataclasses/pathlib/logging/re/os`）+ 仓库已有模块。**禁止 `pip install mcp`**（依赖红线）。
3. **stdout 纪律**：stdout 只输出换行分隔的 JSON-RPC 消息；所有日志走 stderr（`logging.basicConfig(stream=sys.stderr)`）。
4. **复用不重写**：业务全部走现有 service 接口（见下"依赖事实"）；唯二允许的小型复制是 `_run_job` / `_safe_error_detail`（约 40 行，源头在 `app/web/routes.py`，壳层之间不互相 import；转正时应把它们上提进 `service/`，在 docstring 里注明）。

## 模块切分（4 个文件，各 < 300 行）

```
app/mcp/
├── __init__.py     # 仅 docstring：定位 + 实验声明
├── protocol.py     # JSON-RPC 2.0 stdio 循环 + 分发（不含业务）
├── tools.py        # 4 个动词的实现（不含协议）
└── __main__.py     # python -m app.mcp 入口：load_dotenv + 接线 + serve
```

## protocol.py ↔ tools.py 接口（锁死，三方共同依赖）

```python
# tools.py 导出 ──────────────────────────────────────────────
@dataclass(frozen=True)
class ToolResult:
    blocks: list[str]          # 依次作为 content 里的多个 text block 输出
    is_error: bool = False

@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict                      # JSON Schema（协议层序列化为 inputSchema）
    handler: Callable[[dict], ToolResult]   # 入参 = tools/call 的 arguments dict

@dataclass
class ToolContext:
    output_dir: Path                            # 知识库目录（RBCP_OUTPUT_DIR，默认 ~/transcript）
    storage_factory: Callable[[], "Storage"]    # 每次调用新建 Storage（仿 web 层 get_storage）
    pipeline_fn: Callable[[str], dict]          # url -> fetch_single 结果 dict（仿 get_pipeline_fn，吃 RBCP_PROXY）
    job_runner: Callable[[Callable[[], None]], None]
    # 默认实现：threading.Thread(target=fn, daemon=True).start()
    # 测试注入：lambda fn: fn()（同步内联，确定性）

def create_default_context() -> ToolContext
def build_tools(ctx: ToolContext) -> list[ToolDef]

# protocol.py 导出 ────────────────────────────────────────────
SERVER_INFO = {"name": "rbcp-mcp-demo", "version": "0.1.0"}
SUPPORTED_PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
LATEST_PROTOCOL_VERSION = "2025-11-25"

def handle_message(msg: dict, tools: list[ToolDef]) -> dict | None
    # 纯函数（便于单测）：一条已解析的 JSON-RPC 消息 -> 响应 dict；notification -> None
def serve(tools: list[ToolDef], stdin=None, stdout=None) -> None
    # 默认 sys.stdin / sys.stdout；逐行 read -> handle -> 单行 json.dumps(ensure_ascii=False) + "\n" + flush
```

## 协议行为（protocol.py，依据已核实笔记）

| 入站 | 行为 |
|---|---|
| `initialize` | result = `{protocolVersion, capabilities: {"tools": {}}, serverInfo: SERVER_INFO}`；客户端版本在 SUPPORTED 内→原样回显，否则回 LATEST |
| `notifications/initialized` 及一切 `notifications/*` | 忽略，**不响应**（返回 None） |
| `ping` | result = `{}` |
| `tools/list` | result = `{"tools": [{name, description, inputSchema}]}`（**驼峰 inputSchema**） |
| `tools/call` | params `{name, arguments}` → result = `{"content": [{"type":"text","text": b} for b in blocks], "isError": is_error}` |
| `tools/call` 未知工具名 | JSON-RPC error `-32602` |
| 未知 method（带 id） | JSON-RPC error `-32601` |
| JSON 解析失败 | error `-32700`，id 为 null |
| handler 抛任意异常 | 兜底捕获 → `ToolResult(blocks=[人话错误], is_error=True)`，循环绝不崩 |
| stdin EOF | 干净退出 |

JSON 序列化一律 `json.dumps(obj, ensure_ascii=False)`（**不带 indent**——消息内禁止内嵌换行；block 文本里的换行在 JSON 字符串内被转义，合法）。

## 4 个动词（tools.py）

通用约定：**结构化结果 block = 一段 `json.dumps(..., ensure_ascii=False, indent=2)` 的 JSON 文本**（这是 block 内容，可以多行）；业务失败用 `is_error=True` + 中文人话（`format_error_for_user`），不抛协议错误。

### 1. `read` — 读一篇内容（缓存优先；未命中触发转录）

- description（给 Agent 看）：`"读取一条 B 站/小红书内容的完整转录文本（Markdown）。已转录过的立即返回；未转录的会启动转录（耗时约 1-5 分钟、消耗少量 API 费用），届时请稍后用 get_status 查询、完成后再次调用 read。接受分享文案（自动抽 URL）。"`
- input_schema：`{type: object, properties: {url: {type: string}, force: {type: boolean, default: false}}, required: ["url"]}`
- 流程：
  1. `url = clean_url(raw)`；`detect_platform(url)`，抛 `RbcpError` → is_error 返回人话。
  2. `key = dedup_key(url)`。
  3. **缓存命中**（非 force 且 key 非 None）：扫 `storage.done_jobs_brief()` 找 `dedup_key(job_url) == key` → `get_job` → 读 `md_path` 文件存在 → 返回两个 block：
     - block1（元数据 JSON）：`{"status":"ready","job_id",… ,"title","author","platform","url","md_path"}`
     - block2：Markdown 全文（原样字符串）
     md 文件已被删 → 视为未命中，继续往下。
  4. **进行中去重**：扫 `storage.list_jobs(limit=100)` 找 status ∈ {pending, running} 且 dedup_key 相同 → 单 block：`{"status":"transcribing","job_id",…,"hint":"已有同内容任务在转录，勿重复提交；用 get_status 查询"}`，**不建新任务**。
  5. **冷启动**：`job_id = storage.create_job(url)`；`ctx.job_runner(lambda: _run_job(job_id, url, storage, ctx.pipeline_fn))` → 单 block：`{"status":"started","job_id",…,"hint":"转录已启动（约 1-5 分钟）。先做别的，稍后用 get_status 查询；done 后再调 read 即缓存命中秒回。"}`
- `_run_job`：mark_running → `pipeline_fn(url)` → `mark_done(job_id, md_path=…, title/author/platform/content_type/usage)`；异常 → `mark_failed(error_message=format_error_for_user(e), log_excerpt=_safe_error_detail(e))`（逻辑照抄 `app/web/routes.py:106-135`，含脱敏纪律：log_excerpt 不含 traceback/路径）。

### 2. `search` — 检索本地语料库

- description：`"在本地知识库（已转录的全部内容）里全文检索。多个关键词空格分隔，须全部命中（AND，不分大小写）。返回标题/作者/原链接/文件路径/上下文摘录。"`
- input_schema：`{type: object, properties: {query: {type: string}, limit: {type: integer, default: 8}}, required: ["query"]}`
- 流程：query 按空白切词、lowercase；`output_dir.rglob("*.md")` 逐文件（>5MB 跳过；读失败跳过不中断）；全部词命中才算 match；score = 各词出现次数之和；frontmatter 手工解析（首个 `---`…`---` 块内的 `key: value` 行，无 yaml 依赖，解析失败给空 dict）；snippet = 第一个命中词前后各 60 字符、换行折叠为空格。
- 输出单 block JSON：`{"query", "total_matched", "results": [{"title","author","platform","url","path","snippet","score"}]}`（按 score 降序，截断 limit；title 缺 frontmatter 时退化用文件名 stem）。空 query/纯空白 → is_error。

### 3. `list_recent` — 盘点最近任务

- description：`"列出最近的转录任务（含状态/标题/作者/链接），用于了解库里有什么、转录进展如何。"`
- input_schema：`{type: object, properties: {limit: {type: integer, default: 10}}}`
- `storage.list_jobs(limit=limit)` → 单 block JSON：`{"jobs": [{"job_id","status","title","author","platform","url","created_at"}], "library_total_cost_yuan": storage.total_cost_yuan()}`

### 4. `get_status` — 查任务进度

- description：`"按 job_id 查询转录任务状态。done 后调用 read 取全文（缓存命中，立即返回）。"`
- input_schema：`{type: object, properties: {job_id: {type: integer}}, required: ["job_id"]}`
- `get_job` 为 None → is_error `"任务不存在：job_id=…"`；否则单 block JSON：`{"job_id","status","title","url","error_message","log_excerpt"}`（log_excerpt 本就脱敏，可安全外显），status=done 时附 `"hint": "调用 read(url) 取全文"`。

## 依赖事实（实现方直接照用，已核实）

| 需要 | 来自 | 备注 |
|---|---|---|
| `fetch_single(url, *, api_key, output_dir, …, proxy=None) -> dict` | `app.service.pipeline` | 返回含 md_path/title/author/platform/content_type/usage |
| `Storage(db_path)`；`create_job/mark_running/mark_done/mark_failed/get_job/list_jobs/done_jobs_brief/total_cost_yuan` | `app.service.storage` | `_connect()` 每操作新建连接 → **跨线程安全**，可把同一 Storage 实例递给后台线程 |
| `clean_url / dedup_key` | `app.service.urls` | dedup_key 解析不出返回 None（短链不猜） |
| `detect_platform` | `app.service.extractor` | 非两平台抛 RbcpError |
| `RbcpError / format_error_for_user` | `app.service.errors` | 人话错误 |
| 默认 context 环境变量 | — | `RBCP_OUTPUT_DIR`（默认 `~/transcript`，db = 其下 `_index.sqlite`）、`DASHSCOPE_API_KEY`、`RBCP_PROXY`（仿 `routes.get_pipeline_fn`） |
| frontmatter 形状 | `app/service/templates/note.md.j2` | 简单 `key: value` 行 + `tags: []`，无嵌套（media_paths 列表项以 `  - ` 开头，解析时忽略即可） |

## 测试契约（tests/test_mcp_demo.py）

风格仿 `tests/test_routes.py`：真 Storage 落 `tmp_path` + `MagicMock` pipeline + `job_runner=lambda fn: fn()`（同步）。fixture 的 md 文件**必须长得像真产物**（带完整 frontmatter + CJK 正文 + 「说话人1：」行——合成数据须保留真实特征）。至少覆盖：

- 协议：initialize 回显已支持版本 / 不支持版本回 LATEST；tools/list 含 4 工具且字段为 `inputSchema`；ping；未知 method → -32601；notification → None；坏 JSON 行不崩循环（serve 层喂字符串流验证）；tools/call 未知工具 → -32602。
- read：冷启动建 job 且同步 runner 跑完 → 再次 read 缓存命中返回 markdown block；进行中去重不建新 job（预置 running 任务）；done 但 md 文件被删 → 重新转录；非法 URL → is_error；pipeline 抛异常 → job 落 failed 且 error_message/log_excerpt 非空、log_excerpt 不含路径。
- search：命中（验证 title/url 来自 frontmatter、snippet 含关键词）；多词 AND；不命中 → total_matched=0；空 query → is_error；坏文件（无 frontmatter）不崩。
- list_recent / get_status：happy path + job 不存在。

## 验收（demo 完成的定义）

1. `uv run pytest` 全绿（现有 484 + 新增，零改动现有测试）。
2. `python -m compileall app/` 通过。
3. 真库冒烟：`RBCP_OUTPUT_DIR=~/transcript` 起 server，管道喂 initialize → initialized → tools/list → search → list_recent，全部返回合法响应（**只用只读动词**，不花钱）。
4. `git diff main --stat` 只含新增文件。
5. 用户可按 devlog 里的命令 `claude mcp add rbcp-demo -- uv run python -m app.mcp` 真接 Claude Code 试用。

## 转正清单（拍板后才做，demo 不做）

PRD「第一层·形态」加 MCP 入口；PLAN 立项（M6?）；`rbcp mcp` CLI 子命令；`_run_job`/`_safe_error_detail` 上提 `service/`；research/comments 动词；LOG.md 索引补行；pyproject 打包含 `app/mcp`。
