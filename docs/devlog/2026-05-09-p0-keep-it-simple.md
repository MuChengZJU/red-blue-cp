---
date: 2026-05-09
type: decision
priority: high
related: [SPEC.md, PLAN.md, CLAUDE.md]
status: active
---

# P0 砍到极简，不引入抽象层

> P0 阶段不抽 Pipeline / Adapter / Provider 等接口，三种内容类型用 if/elif 直接分发；
> 所有抽象延后到 P1 真正需要时再做。

## 背景

技术架构 v1（5 月 9 日上午产出）一次性铺开了完整的工程分层：

```
入口层 → 编排层 → 流水线层 → 适配层 → 存储层
```

P0 阶段就要实现：
- `PlatformAdapter` / `BiliAdapter` / `XhsAdapter` 类
- `Pipeline` 接口 + `BiliVideoPipeline` / `XhsVideoPipeline` / `XhsImagePipeline` 实现
- `IModelProvider` 接口 + `DashscopeProvider` 实现
- `asyncio.Queue` + N worker 任务队列
- SSE 实时进度
- FTS5 全文检索

外部审阅指出："P0 写重了，把工程优雅凑进了 P0 验证可行性"。

## 决策

P0 阶段**只用三个文件夹**：

```
app/
  service/
    extractor.py    # 包装上游 extract 函数，内部 if/elif 分发三种内容类型
    markdown.py     # frontmatter + 模板 + sanitize + 原子写入
    storage.py     # SQLite jobs CRUD
  web/
    routes.py       # 输入页 + 任务列表 + 详情 + 下载
  cli.py            # rbcp run <url>
```

**P0 不引入**：
- `PlatformAdapter` / `Pipeline` / `IModelProvider` 等接口
- `asyncio.Queue` + worker 池（用 `asyncio.create_task` 替代）
- SSE（用 2s 轮询替代）
- FTS5（P2）

具体见 SPEC.md §1-2 和 CLAUDE.md "P0 阶段反过度抽象"红线。

## 理由

### 为什么 P0 不抽象

1. **P0 的目标是"产物正确"，不是"架构优雅"**
   验证从 URL 到 Markdown 这条路能不能稳定走通，才是 P0 的核心。架构是否优雅是 P1 之后才需要操心的问题。

2. **上游 social-post-extractor-mcp 已经处理了大部分脏活**
   ASR 调度、视觉模型调用、ffmpeg 流式抽音频、jinja2 模板这些都已经实现。再套一层抽象只是增加 bug 面，没有解决任何实际问题。

3. **抽象的代价是双向的**
   - "现在花时间写"：P0 拖长 1-2 天
   - "未来如果需求变了改起来更难"：抽象一旦成型很难推翻
   不抽象的代价只有"P1 阶段重构一次"——这是可控成本。

4. **DreameClaw 范式：先跑通再分层**
   验证流水线能稳定出产物之后，自然会暴露真正需要的抽象点。提前抽象往往抽错地方。

### 为什么这个错误会出现

最初设计时把"完整工程架构"当成"最终目标"画出来，然后倒推 P0 应该做哪些。结果就是 P0 承担了太多"为以后做准备"的工作。

正确的方向是：**P0 是 MVP，P1 才需要为以后做准备**。

## 影响

| 文件/模块 | 影响 |
|---|---|
| SPEC.md §1-2 | 重写"模块分层"和"P0 代码组织" |
| SPEC.md §10 | 加 "P0 不做抽象 / Pipeline / Provider / FTS5 / SSE" 决策记录 |
| PLAN.md M1 | 拆成 M1a (CLI 极简闭环) + M1b (WebUI 最小页) |
| PLAN.md M2e | 模型抽象单独排足 1.5 天，与 M2a-d 串行不并行 |
| CLAUDE.md | 新增"P0 阶段反过度抽象"红线和"工程纪律" |
| 时间盘 | P0 从原计划 ~5 天压缩到 4 天 |

## 节省下来的时间用于

- API 安全：所有文件接口走 job_id，禁用 path 参数（防路径穿越）
- 部署约束：单进程 uvicorn，禁 --workers
- 失败持久化：error_message + log_excerpt 进 SQLite
- 文件名 sanitize：emoji / 特殊字符 / 超长 / 空标题等边界
- 原子写入：写 .tmp + os.replace

这些工程纪律比 P0 阶段的抽象更重要。

## 后续 / 复盘

待 P1 启动时回顾：
- 哪些抽象在 P1 真的需要（验证决策）
- 哪些 P0 时"以为以后会用"的抽象其实没用（验证克制是对的）
- 重构成本是否可控（验证"P1 阶段重构一次"的代价确实可接受）

如果 P1 阶段发现某个抽象其实 P0 就该做，在本 logs 文件追加"复盘"章节，并新增一条决策记录。

## 相关

- 上游审阅意见：来自 2026-05-09 的需求收敛讨论（私有对话，未公开）
- 配套约束：参见 CLAUDE.md "不变量" 和 "工程纪律" 章节
- 后续抽象引入计划：PLAN.md M2 子任务序列
