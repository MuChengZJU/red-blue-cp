---
date: 2026-06-03
type: experience
priority: high
related: [docs/devlog/2026-06-02-parallel-subagent-tdd-lessons.md, docs/devlog/2026-06-03-pydoll-native-capture-and-login.md, CLAUDE.md]
status: active
---

# 复盘：用 Claude Code 做完 P1（v0.2.0）的经验与教训

> 一次会话里从「文档定稿」做到「v0.2.0 上线」（22 个提交、3 个 PR）。按业界对 agent 编码复盘的共识方法——**`调研→规划→执行→评审→交付` 五段，每段问三件事**——逐段拆。结论先行：**最大的杠杆是"提前把契约定成可执行的"；最大的两个坑是"并行 agent 写同一文件冲突"和"漏提交的修复只活在工作区"。**

## 方法说明（为什么这么复盘）

业界对 AI agent 编码的复盘有几条收敛共识（见文末来源）：

1. 成熟工作流都收敛到 **`Research → Plan → Execute → Review → Ship`** 五段；复盘也按这五段问"哪步结构给够了/没给够"。
2. 主线不是"AI 行不行"，而是**"我给的结构够不够"**——"结构给得越多，产出越好；领域专长才是瓶颈"。
3. **TDD 是最强模式**，红绿循环是关键证据。
4. **Document & Clear**——别让一段长会话成为你唯一的记录；频繁提交、把进展落盘。
5. **Subagent 并行写同一文件会冲突**（业界明确警告）。

本篇即按"**五段 × 三问**（哪里对了 / 哪里晚了 / 下次改法）"展开，锚定真实提交。

---

## 一、调研（Research）

**做对了**：动手前真投网调研了博主全量抓取方案（对比 MediaCrawler / nodriver / playwright / xhshow），定了 pydoll；并把一次性手动抓取的经验先沉成 devlog。领域知识（小红书三接口、签名、风控）是后面一切的地基——印证"领域专长是瓶颈"。

**晚了/错了**：对 **pydoll 的真实行为**调研不够，只查了"它能连 Chrome"，没验证"execute_script 注入的 fetch 覆盖能不能钩到页面请求"。结果执行期才发现 JS 拦截器抓 0（`f7e58e7`），返工改原生网络捕获。

**下次改法**：调研要落到**"我将要依赖的那个具体 API 调用"**层面，而不是停在"这个库能干这件事"。关键外部行为，调研阶段就写个 10 行 spike 验一下。

## 二、规划（Plan）

**做对了**：**Phase 0 先把契约定成可执行的**——`dataclass` 桩 + fixture + SPEC §4.4（`f1837cb` `81fb716`），再派并行 agent。这是整段最大的杠杆：正因为 `Note`/`Comment` 字段定死，三个独立 agent 的产出才拼得回来。也印证"结构给够，产出才好"。

**晚了/错了**：规划"并行三件套"时，没把"**它们改的文件必须真不相交**"和"**worktree 必须从含契约的基线切**"当成硬前提写进派活说明。

**下次改法**：派并行 agent 前，显式列"每个 agent 只许碰哪些文件"，并校验**worktree 基线 = 当前契约提交**。

## 三、执行（Execute）

**做对了**：TDD 落地解析层/评论/extractor（`80de9e1`），真实脱敏 fixture 当输入；用 sonnet 跑 3 个并行 subagent、opus 当编排（业界推荐的配比）。

**晚了/错了（两个核心坑）**：

1. **并行 agent 写同一文件冲突**——A、B 都重建了 `discover.py`、B 还自造了不一样的 `Comment`。这正是业界明确警告"多 agent 并行写同一文件会冲突"的那条。所幸契约提前定死，收敛只补一行 `note_id`（但那行又埋了第二个坑）。
2. **真链路实测抓出 fixture 漏的边界**——真实 `liked_count` 可能是空串，`int("")` 崩（`e7fe660`）。脱敏 fixture 仿真度再高也漏。

**下次改法**：并行只切**真正不相交**的新文件；共享类型放公共模块、别让两个 agent 各建。里程碑必跑真链路（这条项目里早有，继续守）。

## 四、评审（Review）

**做对了**：Codex review 跑出 4 个真问题（批量 JSON 缺失、cookie 误分类、评论计数漏楼中楼、媒体孤儿），全修 + 加回归（`f802097`）。独立第二意见确实抓到了自审漏的。

**晚了/错了**：评审盯的是"diff 对不对"，**没盯"提交的版本 == 我测的版本"**。漏提交的 `note_id` 修复只活在工作区，pytest 永远跑工作区，于是"243 passed"是假绿，坏测试合进了 main（`bd18978` 事后热修）。

**下次改法**：合并前在**干净 checkout / `git status` 必须空**的前提下验一次；"测试全过"≠"提交版全过"。（已记进 memory）

## 五、交付（Ship）

**做对了**：版本号 0.1.0→0.2.0、tag + GitHub release、分支清理一条龙。发现 main 被搞红后**没有绕过保护直接推**，老老实实走 hotfix PR（`#2`）。

**晚了/错了**：**分支保护是出事后才补的**。一开始 main 没保护，PR #1 合并时本地步骤中断、还差点被允许直接 push 热修。

**下次改法**：开源项目**开仓即设分支保护**（禁直接推 / 必须 PR），别等出事补课。

---

## 写进规矩的三条（已落地）

1. **派并行 agent 前**：声明每个 agent 的文件边界 + 校验 worktree 基线 = 当前契约提交；共享类型先在公共模块定稿。
2. **提交后必查 `git status` 干净**；合并前在干净状态验"提交版"真绿（pytest 跑工作区，假绿会骗人）。
3. **开源仓库开仓即设分支保护**。

> 第 2 条已存 memory（[[verify-commit-matches-worktree]]）。第 1、3 条建议补进 CLAUDE.md 的「工程纪律」。

## 一句话总结

这次 Claude Code 把"五段"走全了，**赢在规划阶段把契约定成可执行的**，**输在执行/评审阶段对"并行隔离"和"提交=所测"两个前提没设硬门**。教训都不是"AI 不行"，而是**"我哪步结构给晚了"**——和业界共识完全对上。

---

## 来源（方法论参考）

- [10 Lessons for Agentic Coding — dbreunig](https://www.dbreunig.com/2026/05/04/10-lessons-for-agentic-coding.html)
- [Best practices for Claude Code — 官方文档](https://code.claude.com/docs/en/best-practices)
- [Effective context engineering for AI agents — Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Claude Code Best Practices: Planning, Context Transfer, TDD — DataCamp](https://www.datacamp.com/tutorial/claude-code-best-practices)
