## 审查报告：feat/0.6-extract-digest-render → main

变更概览：137 个文件改动，+16803 / -3954 行。已跑 `./.venv/bin/pytest -q tests`，结果 594 passed。

### 🔴 P1 — 桌面批次页和后端批量接口契约不一致
- **文件**: `app/web/routes.py:415-426`, `desktop/frontend/screens/jobs.js:102-146`
- **问题**: 后端 `/api/batches` 返回的是 `{"batches": [...]}`，`/api/batches/{id}/items` 返回的是 `{"items": [...]}`；但桌面端直接把响应当数组用，还按 `done_count/total_count` 这种扁平字段渲染。结果是批次卡片不会渲染，展开明细也拿不到数据。
- **建议**: 桌面端先解包 `batches` / `items`，并按后端的 `counts` 结构做一次 normalize；或者统一后端返回桌面端需要的扁平形状，但不要两边各说各话。
- **代码**:
  ```diff
  - return {"batches": storage.list_batches(limit=50)}
  + if (Array.isArray(batches) && batches.length) {
  ```

### 🔴 P1 — 设置页把空 `output_dir` 写成了当前目录
- **文件**: `desktop/frontend/screens/settings.js:84-111`, `app/web/config_api.py:55-73`, `app/web/routes.py:95-97`
- **问题**: 前端保存时无条件提交 `output_dir`；后端也接受空字符串并写入 `RBCP_OUTPUT_DIR=`。后续所有 `Path(os.getenv("RBCP_OUTPUT_DIR", "~/transcript")).expanduser()` 会把空值解析成 `.`，也就是当前工作目录。用户只要在设置页直接点一次保存，就可能把输出目录切到仓库/启动目录。
- **建议**: `output_dir` 为空时不要写入环境变量，或在后端强制回退到默认目录/直接拒绝保存；代理可以空，输出目录不该空。
- **代码**:
  ```diff
  - payload[f.key] = el.value.trim();
  + if (ui == "dashscope_key" && val == "") continue
  + os.environ[env] = val
  ```

### 🔴 P1 — 同一 job_id 复跑后，digest 缓存会返回旧内容
- **文件**: `app/web/routes.py:234-249, 429-456`, `app/extract/batch.py:152-170`
- **问题**: `retry_job` 和批量重跑都会复用同一个 `job_id`，但 `get_digest()` 只要命中 `digest_cache` 就直接返回，不会校验新 artifact，也没有在成功重跑时清掉旧 cache。这样用户重试同一任务后，阅读器可能继续展示上一次的 digest。
- **建议**: 在 job 重新产出成功时同步失效 digest cache，或者在读取 cache 前比对 `text_sha256` / `source_text_sha256`，不一致就重算。
- **代码**:
  ```diff
  - if cached is not None:
  -     return cached
  + # 这里没有任何基于 text_sha256 的失效判断
  ```

### 🟡 P2 — 删除 job 没有清理 batch_item 引用，批次会留下悬挂链接
- **文件**: `app/extract/storage.py:407-423`, `app/extract/batch.py:152-170`
- **问题**: `delete_job()` 只删 `jobs` 表和 markdown 文件，不会同步清掉 `batch_item.job_id`。批次卡片继续指向已经删除的 job；更糟的是，批量重跑时 `existing_jobs` 仍会捞到这个失效 job_id，后续 `reset_for_retry/mark_done` 会落空或留下脏状态。
- **建议**: 删除 job 时一并清理关联的 `batch_item.job_id`，或者在批量重跑前校验 job 是否还存在，失效就重新建 job。
- **代码**:
  ```diff
  - conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
  + existing_jobs = {
  +     item["note_id"]: item["job_id"]
  +     for item in storage.list_batch_items(batch_id)
  ```

### 其他观察
- 工作区里还有未跟踪的 `_index.sqlite` 和两个 `rbcp-serve-*.spec` 文件，看起来像运行/打包产物；如果不是刻意保留，建议别进提交。
