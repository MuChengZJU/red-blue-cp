---
date: 2026-06-06
type: experience
priority: high
related: [PLAN.md, docs/devlog/2026-06-05-m4-wave1-contracts-and-token-spike.md]
status: active
---

# 挂机一夜自主完成 M4 —— 多 agent 编排 + Codex 门 + 真链路的复盘

> 用户挂机睡觉，要求"自主完成 M4 全过程"。一次连续约 1h12m 的无人值守开发：波2 并行 TDD → 各过 Codex review → 按序合并 → 真链路验收 → 收尾。复盘什么编排住了、什么差点翻车、可复用的判断。

## 背景

M4（博主安全批量 + 错误地基）波1 已完成（三流并行写计划 + token 过期 spike 锁信号，见 [波1契约+spike](2026-06-05-m4-wave1-contracts-and-token-spike.md)）。本次是波2 实现到收尾，全程无人值守，明确授权 push + 合并到 main。产出：4 个 PR 合并、367 测试全绿、真链路验过。

## 编排结构（成功的部分）

**串行锁契约 → 并行填充** 的波次法在多 agent 下成立：

1. **M4a 先串行**（组织者本会话亲自 TDD）：errors / pipeline.fetch_single / proxy 穿透 / storage batch 表四个契约定死、合并进 main（PR #16）。**先合再开下游**是关键——M4b/M4c 从含 M4a 的 main 切，接口不漂移。
2. **M4b ‖ M4c 并行**：两个后台 worktree agent（`isolation: worktree`）各跑一条流的 TDD。**契约嵌进 agent prompt**（精确签名 + 文件边界 + token 信号），这是波1 教训"可执行契约 + 把契约嵌进 prompt 才收得住"的落地。
3. **Codex review 门**：每条流合并前过一遍 `codex review --base main`，真 bug TDD 修、pydoll 死路径问题按警告/文档处理。
4. **按序合并**：M4b 先合 → M4c `git rebase origin/main` 解 `cli.py`（不同函数 + import 行）冲突再合。波1 预判的"cli.py/routes.py 相交"如期发生，rebase 一处冲突即解。

## 差点翻车 + 怎么处理

1. **后台 agent 网络中断半途死**（最该记的）：M4c agent 跑 ~12 分钟、14 个 tool use 后撞 `ECONNRESET`，**只留下一个写好的 RED 测试**（无 commit、无 batch.py）。处置：**没重派**（怕又断），salvage 它的测试、主会话在 worktree 里接手把 batch.py / cli / 插件做完。教训：**长跑后台 agent 脆，网络一断就是半成品**；关键产物应让 agent 边做边 commit，或不确定时主会话接管比重派稳。M4b agent 则正常完成（7 commit）。

2. **mock 掩盖真 bug**（Codex 的真实价值）：`probe_exit_ip` 写成 `requests.get(url, trust_env=False)`——`trust_env` 是 `Session` 的属性、**不是 `requests.get` 的参数**，真跑必 `TypeError`。但单测 mock 了 `requests.get`，mock 笑纳了非法 kwarg，**单测全绿**。Codex 独立 review 静态读出 + 真链路执行复现才抓到。强化已有记忆"合成/mock 数据要像真的"：**对外部调用别只信 mock，留一处真链路；mock 不校验 kwarg 合法性**。

3. **Codex 九处发现全处理**：M4a 1×P3（上面的真 bug）+ M4b 3×P2（错误分类误导：服务器 403 被说成"代理未生效"、无 BV 路由糊成通用提示、token 文案对单篇说"清单"）+ M4c 1×P1+1×P2（batch `--proxy --comments` 不警告评论腿走真实 IP；resume 只跳 done 导致重跑重试死 token）。真 bug/真误导 TDD 修，pydoll 死路径按"加诚实警告"处理（不给将死的子系统投资）。

4. **遇"没法验证"的 scope 主动停**：WebUI 导入清单入口 §九 列在阶段1 但最低优先，其有用形态（进度页/收信箱）是阶段2，且半成品 web UI 无法自主浏览器 QA（违反"里程碑收尾必须真链路实测"）。**明确推迟 + 写清楚**，没硬塞把 main 带歪。

## 真链路验收（不止过 mock）

- **`rbcp batch` 端到端**：真实小红书 URL → 真抓 → 出 Markdown（标题/作者/发布日期全对）→ batch_item 写 done → **断点续传 live 验证**（第二次跑 ok=0 跳过已下、不再烧 API）。输出重定向 `/tmp` 不污染知识库。
- **插件↔batch 跨语言契约**：node 加载真实插件代码灌模拟 `user_posted` → 导出信封 → Python `batch._load_and_validate` 接受。无需浏览器就验通接缝。

## 度量

| 项 | 值 |
|---|---|
| 无人值守时长 | ~1h12m |
| 合并 PR | 4（#16 M4a / #17 M4b / #18 M4c / #19 文档） |
| 测试 | 367 全绿（波2 新增 ~50） |
| Codex 发现并修 | 9（1 真 bug + 8 UX/安全/正确性） |
| 翻车 | 1（M4c agent ECONNRESET，已接手） |

## 可复用的判断

1. **波次法（串行锁契约→并行填充）在多 agent 下成立**：先合地基再开下游，接口不漂移、合并冲突可控。
2. **Codex review 当合并门有真实价值**：对单测的 mock 盲区（非法 kwarg、误导文案）是独立一双眼。每条流过一遍值。
3. **后台长跑 agent 不可靠**：网络断 = 半成品。要么让它边做边 commit，要么关键流主会话自己跑（工具调用级重试更抗断）。
4. **自主跑遇"不可验证的 scope" 要停**：写清楚留给人，别为"做完"硬塞没 QA 的东西。
5. **工具缺口已识别**：gstack `/browse`（headless CDP，表单/上传/断言）能自动化 WebUI QA——这消掉了"推迟 WebUI 入口"的理由，下次建它可连着自动 QA。插件真抓不适合自动化（安全靠人慢滚）。
