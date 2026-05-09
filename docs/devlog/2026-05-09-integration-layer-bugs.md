---
date: 2026-05-09
type: experience
priority: high
related: [CLAUDE.md, PLAN.md]
status: active
---

# P0 真实 bug 全在"接线层"——多轮文档审阅 + 全单测全过都抓不到

> 4 轮文档审阅（CEO / Eng R1 / Eng R2 / Codex）+ 137 单测全过，commit 后用真实链接一跑还是踩 5 个 bug。原因不是审阅不够细，是审阅和单测的盲区刚好重叠在"组装接缝"上。

## 触发

M1a + M1b 完成后用 `/qa` 跑用户提的 3 条真实 URL，连续踩坑：

1. WebUI 模式 401（serve 命令绕过了 .env 加载）
2. 详情页彻底废（job_id 没传给模板）
3. 列表"未知作者"（pipeline 返回值丢业务字段）
4. ASR 60s 不够 timeout
5. ASR 400 InvalidParameter（字段名抄上游错的：`file_url` 应为 `file_urls`）

每个修复都很小（1-10 行），但累积起来 P0 完成度从"测试全过 = 完工"幻觉，跌到"真实跑通 = 还差几小时"现实。

## 根因分类

### 根因 A：审阅都是"出现代码前"的设计审阅

CEO / Eng R1 / Eng R2 / Codex 全部在 PRD/PLAN/SPEC 文档阶段，能抓出"P0 范围""配置发现顺序""SDK 该不该用"这种**架构选择**问题。

但这次踩的所有 bug 都是：
- API 字段名错 → 必须真打 API 才能发现
- 入口忘了调初始化 → 必须真启动进程才能发现
- 模板变量没传 → 必须真渲染 HTML 才能发现
- 函数返回值丢字段 → 必须真存进 DB 才能发现

**结论：架构审阅检不出实现层错误。** 我做了 4 轮架构审阅但端到端跑了 0 次，结构性失衡。

### 根因 B：单测覆盖了"我设计的那一面"，覆盖不了"组装接缝"

| Bug | 为什么单测抓不到 |
|---|---|
| ASR `file_urls` | model.py 测试 mock 了 `requests.post`，从来没真打过 DashScope |
| serve 漏 load_dotenv | test_cli mock 了 uvicorn，没人验证"启动后 routes 能拿到 .env 值" |
| job_detail 漏 job_id | 测试只验证 `200 OK`，没验证模板渲染出的 HTML 里 jobId 真的是 5 |
| _run_job 漏 metadata | 测试只验证 `status=done`，没验证 `job["title"]` 不是 None |

**测试都是我自己写的——我心里"完整"的概念太弱。** 每个测试精准验证"我设计的那一面"，没人验证"组装起来用户看到的样子"。

### 根因 C：smoke test 用了不会跑到深处的 URL

M1b commit 前我用 `https://www.youtube.com/x` 做 smoke test。这个 URL 在 `detect_platform` 第一步就 ValueError，根本走不到 model.py。

smoke test "通过"了，等于零。

### 根因 D：相信引用代码

ASR 字段名 `file_url`/`language` 是从 `_reference/social-post-extractor-mcp` 抄的，那边也是错的。可能上游也没真跑通这条路径，或者 DashScope 改过 schema。

**外部 API 必须查官方文档，不能信引用代码。**

## 修法（防下次）

### 1. P0 完成定义里加"端到端真实数据跑通"

不是 smoke test 通过，是真链接 → 真 API → 真 .md。这条不过不算 done。

### 2. smoke test 必须跑到外部 API 那一步

哪怕用一个会 404 的真实 BV 号，也能暴露"401 因为 serve 没 load_dotenv"。比"完美 smoke 假 URL"强一百倍。

### 3. 测试要验证用户视角的输出，不只是函数返回值

```
✗ assert response.status_code == 200
✓ assert "jobId = \"5\"" in response.text  # 验证模板真渲染出值

✗ assert job["status"] == "done"
✓ assert job["title"] == "测试视频"  # 验证业务字段真写入了
```

### 4. brief Codex 时强调"配置/初始化是入口职责"

`load_dotenv()` 这种横切关注点放在业务函数体内就是埋雷。下次 brief 要明确："配置加载放进程入口（CLI 命令开头 / 模块加载时），别埋进业务函数。"

### 5. 不要相信引用代码的外部 API 调用

读官方文档为准。引用代码可以参考流程，但字段名必须查官方源头。

### 6. /qa 应该提前到每个里程碑收尾必跑

`/qa` 配合浏览器自动化跑一轮也就 5-10 分钟。这次 QA 一次性抓了 5 个真实 bug，性价比远高于第 5 轮文档审阅。

应该在 P0 完成定义里加："里程碑 commit 前必须跑一次 /qa（或等价的端到端实测）"。

## 复盘

QA 用 `/qa` 配合 browse 自动化，调试反馈周期短到几乎不痛。所以这事不算严重——只要工具链支持快速端到端测试，"接线 bug 在 QA 阶段才发现"是健康的，不需要也不可能在文档审阅阶段抓出来。

真正要修的是**心智模型**：不要把"测试全过 + 审阅通过"当成"完工"，那只是"组件就绪"。完工 = 用户视角真链路跑得通。
