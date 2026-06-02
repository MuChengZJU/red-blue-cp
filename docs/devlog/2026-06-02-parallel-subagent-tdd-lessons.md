---
date: 2026-06-02
type: experience
priority: high
related: [SPEC.md, PLAN.md]
status: active
---

# 并行 SubAgent TDD 开发：收获与教训

> 把博主全量+评论的 P1 实现拆成 3 个 Claude SubAgent 并行 TDD（worktree 隔离），一次跑下来全量 221 测试通过。最大的钱不花在"写"，花在"合"——接口分叉如期发生，靠提前定死的可执行契约才收住。

## 背景

P1 三块新代码（解析层、评论格式化、extractor 双开关）彼此关注点独立，适合并行。决定试一次"多 agent 并行 TDD"，既为提速，也为练 agent 协作的手感。

执行结构定为三阶段：
- **Phase 0（串行，主控做）**：抓真实接口 JSON → 脱敏 fixture；定 `Note`/`Comment` dataclass + parse 函数签名，写进 SPEC §4.4，并落一个**可执行骨架** `discover.py`（dataclass 写实，parse 函数留 `NotImplementedError` 桩）。
- **Phase 1（3 个 SubAgent 并行，worktree 隔离，各自 TDD）**：A=解析纯函数 / B=评论格式化 / C=extractor 双开关。三者改不同文件，设计上合并零冲突。
- **Phase 2（串行，主控收尾）**：pydoll 浏览器壳 + CLI/路由接线 + 端到端实测。

## 经验

### 收获

1. **关注点隔离 + 可执行契约 = 真能并行。** 三个 agent 各自 TDD，A 的解析器和 B 的格式化器**从未互相见过**，最后通过共同的 `Comment` 契约端到端串起来：内联 1 条 + 续拉 2 条楼中楼正确嵌套渲染。这说明只要接口边界定死，独立产出能拼合。
2. **fixture 先行让"测"有据。** 解析层是纯函数，喂真实脱敏 JSON 就能 TDD，完全不碰浏览器。把"碰浏览器的壳"和"纯解析"切开，是这块能并行、能测的前提。
3. **三个 agent 总耗时 ~6 分钟**（并发），各自 36/23/17 测试绿。

### 教训（更值钱）

1. **worktree 隔离可能从旧基线切，agent 手里没有你刚提交的契约文件。**
   实测：三个 worktree 的父提交不是主控刚提交的契约基线，而是更早的提交。结果三个 agent **都没读到** SPEC §4.4 / fixtures / `discover.py` 骨架，全凭 prompt 里的文字描述各自重建。
   - 后果：B 自造了一个**字段不同**的 `Comment`（少 4 个字段、函数名也不同），它自己在返回里都提示"可能要和并行 agent 对齐"。
   - **应对**：派 agent 前确认 worktree 从含契约的基线切；或干脆把契约**完整写进每个 agent 的 prompt**（这次正因为 prompt 里嵌了完整 dataclass，A 才能逐字重建出和契约一致的 `discover.py`）。

2. **并行的真实成本在"合"，不在"写"。**
   不能盲目 merge 三个分支——A、B 都改了 `discover.py`，盲目 merge 直接冲突。正确做法是在**权威基线**上**只挑各 worktree 的实现文件**，丢弃 B 自造的 `discover.py`，把 B 的格式化器统一到 A 实现的契约 `Comment`。合并代价（勘察分叉 + 收敛 + 跑通）大约吃掉并行省下时间的一半。

3. **契约越"可执行"，收敛越省事。**
   这次 B 的 `Comment` 恰好是 A 的 `Comment` 的**子集**（B 只用到公共字段），所以 B 的 `comments.py` 直接能跑在 A 的 `Comment` 上，只有测试工厂构造对象时缺 `note_id`（A 必填），补一行就全绿。如果两边字段集**交叉而非包含**，收敛会痛得多。dataclass 桩（可执行）比纯文档契约强很多。

4. **fixture 也会被重建，要认准权威份。**
   A 凭 prompt 描述把 fixtures 也重建了一份。收敛时坚持用主控那份**从真实接口脱敏**的 fixture（更贴真实 schema），用 A 的实现去跑，36 测试照样全绿——侧面验证 A 重建的结构和真实一致。

## 影响

| 文件/模块 | 影响 |
|---|---|
| 代码 | `app/service/discover.py`（解析层）/ `comments.py`（新）/ `extractor.py`+`fetcher.py`（双开关）落地，全量 221 passed |
| SPEC.md | §4.4 数据模型契约成为并行开发的"可执行接口"，价值被验证 |
| 方法论 | 形成"Phase 0 定可执行契约 → Phase 1 并行隔离 TDD → Phase 2 串行收敛"的可复用模式 |

## 后续 / 复盘

- **下次改进**：派 agent 前显式校验 worktree 基线 = 当前契约提交；prompt 里始终内嵌完整契约（不依赖 agent 去读文件）。
- **何时值得并行**：关注点能切干净、契约能定死、改的文件不相交时才划算；否则合并成本会盖过并行收益。单文件小改、强耦合的活，老老实实串行。
- 浏览器壳（Phase 2）本就不可 TDD、且会改 `discover.py` 同一文件，正确地留在串行阶段，没有强行并行。
