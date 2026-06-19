---
type: 经验 / 复盘
priority: 🔴 高
related:
  - 2026-06-17-0.6-desktop-built-and-running.md
  - 2026-06-18-0.6-retro-short.md
  - 2026-06-03-retro-p1-claude-code.md
status: active
---

# V0.6 复盘：Codex(MIMO) 并行 vs DynamicWorkflow(Opus) 并行 —— 运行时/提示词结构与稳定调用

> 复盘对象：V0.6（Extract→Digest→Render + Desktop）开发的四个会话（2026-06-13~18）。
> 核心问题：同一个项目里，桌面端用「Codex CLI + 本地 mimo 模型」并行写，引擎/收尾用「DynamicWorkflow(Opus 子 agent)」并行写，**为什么后者顺、前者反复返工**？到底差在哪？怎么优化？

---

## 0. 一句话结论

**不是「mimo 代码能力差」，主因是「运行时/工具带不匹配」+ 一个真实的计划级契约缺陷。** 凡是「独立、纯新建文件、无特殊字符、不碰复杂既有文件」的任务，mimo 写的代码质量过关（前端 lib 一次过 15/15、auth.py、5/6 屏）。失败集中在工具层：**Codex 的 `apply_patch` 按"模型 slug 查内置目录"决定实现方式，mimo 不在目录里 → 根本没被注入 apply_patch 工具和 V4A diff 指令**，于是要么散文回答啥都不改、要么产出语法错的 patch、再叠加 CJK 字符 panic 与中途预算耗尽静默停。

**DynamicWorkflow 顺，是因为它的子 agent 和主会话同一个运行时**：同一个 `Edit` 工具（精确字符串替换、unicode 安全、原子写）、同一本规则书（CLAUDE.md 在场）、同一个模型家族（Opus）、结果回流到同一棵树立即验证。**差距在「同物种同工具带」vs「异物种自带一套会卡壳的工具」，不在「上下文多少」。**

---

## 1. 开发分工（证据：commit timeline + transcript）

| 模块 | 谁写的 | 结果 |
|---|---|---|
| digest 锚定引擎、CLI、desktop spike | **DynamicWorkflow(Opus 子 agent)** + 主 Opus | 顺，零返工 |
| 桌面端 6 屏前端 + 一批 web 端点(auth/artifacts/digest/batch/delete) | **Codex + mimo-v2.5-pro 并行** | 6 屏高光；结构性任务反复翻车 |
| Tauri/Rust 壳、所有 commit、codex 失手处「最后一公里」 | 主 Opus | — |
| 收尾修 bug + 四项 WebUI 对齐 + 缩略图 | **DynamicWorkflow(Opus)** | 当场抓 16 问题，零新债 |

→ 两种方式**都在真写代码**，是干净的「控制变量」对照：计划严谨度大致不变，换执行者，质量翻转。

---

## 2. 计划问题 vs 执行问题（逐个失败归因，重证据）

任务包写得**非常细**（契约锁好、字段名/类型/文件边界/验收命令、甚至要求 grep 核实、镜像 WebUI 取数）。"光是计划不够细"基本被证伪。

| 失败 | 性质 | 根因 |
|---|---|---|
| task 1.0（sed 改坏 pipeline.py，烧 587k token 没 commit） | **计划 bug + 执行放大** | 任务包两条约束自相矛盾（文件白名单 vs "不许新增失败测试"，在 `test_proxy_passthrough` 上互斥），作者没预见 → mimo 用 sed 硬解改坏文件 |
| task 1.2（最难的 APIRouter 重构没做，停在"Step 3"） | **执行/运行时** | 一个包塞「建 auth + 写测试 + 大重构」，做完前两步 token 预算到了就停、没 commit。拆小后即过 |
| settings.js（报 completed 实为 4 行 stub） | **执行/运行时** | apply_patch 对 stub 里全角中文持续匹配失败，卡死后放弃。包里加一句"整文件覆盖别 patch"一次过 |
| reader.js（写入 `\uXXXX` 字面量，至今仓库 15 处） | **执行/运行时** | apply_patch 把 unicode 转义当字面字符串写入（能跑但源码脏） |

**纯模型能力锅几乎没有。** 主因是执行/运行时层，加一个真实计划缺陷。

**受控对比**：同样详细的任务包下——
- ✅ 成功轴：独立、纯新建文件、无特殊字符、不碰复杂既有文件（前端 lib、各屏）。
- ❌ 失败轴：结构性重构 / 改复杂既有文件（1.0/1.2）；**特殊字符（全角中文）是独立的失败轴**（settings.js 是简单新建文件也照样崩 apply_patch）。

---

## 3. 根因（联网调研 + 本机源码实证）

**`apply_patch` 工具的实现按 `ModelInfo.apply_patch_tool_type` 决定，按 model slug 在 Codex 内置 catalog 里查，用户 config 改不了**（codex issue #14046）。用一个不在 catalog 的 slug（mimo 必然不在）：
- 不注入 V4A diff 格式的 system 指令；
- tool list 里默认没有 apply_patch 工具；
- freeform apply_patch 还依赖模型支持 Responses API 的 custom tool + grammar 约束——没调教过的模型即使给了也不会按 V4A 正确产出。

**典型掉链子**（issue #14046 / #8161）：拿不到工具 → 散文回答啥都不改；或产出语法错 patch；多文件 refactor 质量塌方。
**CJK panic**：apply_patch 碰中文按 byte 边界处理出错 panic（issue #9580，OPEN，不分平台）——对中文知识库项目致命。
**Codex 自设 token 预算**：达内部预算会标 `budget_limited` 自己停、只总结部分进度（issue #24629），且会口头说 committed 实则没提交（#18018）。

→ 这些都是**运行时/工具协议层**的问题，**在提示词层面看不见**，再细的任务包也兜不住。

---

## 4. 代码层 + 提示词层：四种"并行/外包"机制到底差在哪

| | 提示词层（上下文怎么组织） | 代码/特性层（控制流 & 工具 & 上下文管理） |
|---|---|---|
| **① CC 主会话(Opus)** | CC 系统提示 + 全局/项目 CLAUDE.md + 按需 Skill + **全量累积的会话历史** | 单一上下文窗口，长了自动压缩；工具 Read/Edit/Grep/Bash；记忆文件 |
| **② CC Sub Agent(Agent 工具)** | **自己的**子 agent 系统提示(精简) + 你给的单条任务 prompt + 项目 CLAUDE.md 在场；**不继承会话历史**；agentType 决定系统提示 + 工具白名单(如 Explore 只读) | **控制流由主模型即兴决定**(要不要派、派几个)；**只把最终消息回传给父**(中间步骤不进父窗口=上下文防火墙)；每个 agent 全新窗口；可 background / worktree 隔离 |
| **③ DynamicWorkflow** | 每个 `agent()` = 一个子 agent，prompt **写在脚本里**；可带 JSON Schema → 强制 StructuredOutput 工具、校验失败自动重试；默认继承会话模型(Opus) | **控制流是确定性 JS 脚本**(parallel/pipeline/循环/判断)，不是模型即兴；脚本只持有结构化返回(小)，不持有子 agent 的 transcript → 所以能 scale；内建对抗验证/judge 模式；budget 按 token 缩放；可 resume |
| **④ CC → Codex(`codex exec`)** | Codex **自己的** base 指令(非 CC 的) + **AGENTS.md**(codex 惯例，**不读 CLAUDE.md**) + 你管道喂的任务包；推荐 XML 块结构(`<task>`/`<completeness_contract>`/`<verification_loop>`/`<completion_protocol>`)，"像指挥操作员不是协作者" | **另一个进程**：自己的 agent loop、自己的工具(apply_patch/shell，**按 slug-catalog 选**)、自己的 sandbox、自己的预算自管理；CC 只看到 JSONL 事件流 / .output 文件；--json / --sandbox / --add-dir / --model / worktree / --resume-last |

**关键洞察**：
- **①②③ 是同一个运行时**(CC)：同模型家族、同工具(Read/Edit)、同规则书(CLAUDE.md)。它们只差**控制流**(一个窗口 / 主模型派子 agent / 代码编排子 agent)和**上下文范围**(累积 / 每 agent 全新)。
- **④ 是不同运行时**：不同模型(mimo)、不同工具(apply_patch 按 slug 接线、会静默断)、不同规则书(AGENTS.md)，只靠「一段文本任务包 + 一条事件流」连接。**提示词层交接有损，代码层工具接线还可能静默坏**——这正是上一轮没讲清、却是症结的那一层。
- 纠正一个直觉：**不是「DW 上下文更多所以更好」。** 子 agent 和 Codex 都是精简上下文起步、都不继承会话历史。真正的差距是「同物种 + 能自己回仓库 grep 补齐缺失上下文(强模型 + 同工具)」vs「异物种 + 补齐能力弱 + 工具会卡」。

---

## 5. 速度：端到端是「任务类型依赖」的

mimo ~1000 TPS，单位 token 速度吊打 Opus、反馈循环快。但端到端 = 生成 + 返工轮次 + 编排器修复/验证：
- **甜区任务**（独立/新建/无特殊字符）：codex+mimo 端到端更快（6 屏一波拿下）。
- **结构性/复杂既有文件/特殊字符**：codex+mimo 端到端更慢——快速生成被返工轮次吃光（1.0 烧 587k + 手修、1.2 烧 232k 重发、settings 重发 + 一整个收尾会话）。
- **DW-Opus**：单位 token 慢但首轮成功率高、返工少，硬活上端到端能打平甚至更快，且收 codex 烂摊子很顺。

→ **mimo 的快只有在「甜区任务 + 严格验证」下才兑现成端到端的快。**

---

## 6. 下一步：精简成几条可跑的实验（不堆建议）

> 教训：上一轮一堆未经测试的建议会翻车（没复查就误判"mimo 弱"）。落实前先用最小实验逼近。三条，按依赖顺序：

### 实验 A（前置闸门，~10 行 spike）：mimo×codex 工具协议现实检查
单跑一次 `codex exec`（mimo）做一个**必须改含中文的文件并 commit** 的小任务，观察：
1. mimo 到底有没有拿到 apply_patch 工具？还是散文回答啥都不改？
2. 碰中文是否 panic（#9580）？
3. 先 `curl` mimo 的 `/v1/responses` 看 Responses API 通不通（很多本地栈只暴露 chat/completions）。

**这一条决定整个方向**：若工具协议不通 → 直接把 codex 切「禁 apply_patch、强制 shell 整文件写(`cat > file`)」模式（#8161），同时规避 CJK panic。

### 实验 B（用户要的正面对照）：同任务 DW-Opus vs Codex-mimo 端到端
选一个**有代表性、自包含**的真实任务（如"加一个新桌面屏 + 端点 + 测试"），跑两次：
- 路 1：DW 一个 Opus 子 agent；
- 路 2：`codex exec` + mimo。

量**端到端墙钟**（含返工到「测试绿 + 已 commit」）+ **质量**（首轮过没过、事后有没有 bug）。用数据替代猜测。

### 实验 C（核心欠债：自建稳定调用封装）：先做"验证 wrapper"而非全套 skill
官方 `codex-rescue` skill 是「单次转发器」，**不是为并行开发设计的**（用户实测不好用是对的）。自己写一个薄封装，最高杠杆的是「**不信 exit 0，解析事件流**」，硬性检查点（调研已验证的）：
1. 流必须以 `turn.completed` 结尾才算成功（见 `turn.failed`/`error` 即失败留痕）；
2. 测试命令：找 `item.completed` 且 `type=="command_execution"`，校验 `exit_code==0`；
3. 文件改动：收集 `type=="file_change"` 且 `status=="completed"` 的路径，确认目标文件在列、无残留 in_progress；
4. **commit 校验**：worktree 里 `git rev-parse HEAD` 确认真有新 commit（别信模型口头）；
5. 预算检测：累加 `turn.completed.usage`，超阈值或「turn 完成但 commit 校验没过」= 未完成上报；
6. CJK 守卫：扫 stderr 有无 `not a char boundary` panic，命中降级 shell 整写重试；
7. 并发限 3–5（本地模型 RAM/吞吐）；prompt 里塞 `<completion_protocol>` 约定 done/committed/reason 的 JSON 终态。

> 已部分就位：main 上 `AGENTS.md 设为规则书蓝本 + CLAUDE.md @import` 这个提交，已经把规则书喂给 Codex 的一半做了。

---

## 附录:多 Agent 编排方法论速查(跨项目,RBCP 无关)

> 这段是从本次复盘延伸出的**通用方法论**,不限 RBCP。规则一旦经实验验证,应提炼进 AGENTS.md 或独立 skill;此处先存档。

### A. DynamicWorkflow 内部机制(为什么 JS 能控制并行)
- 脚本是「指挥家」,自己不干活;真正并行的是它派出的 subagent(各自独立执行循环)。
- `agent()` 是 **async,返回 Promise 立刻不阻塞**(本质是等一个在别处跑的 subagent 的 I/O)。
- JS 事件循环单线程,但能同时挂一大堆 pending Promise → **只要不 `await` 就接着发,多个 agent 同时在飞**。
- harness 有 worker 池限流(约 `min(16, 核数-2)`),多出来排队。重活在 subagent 进程,不在 JS 线程。
- `parallel()` = `Promise.all`(出错变 null)+ 屏障;`pipeline()` = 每个 item 各走 `s1.then(s2)` 链、所有链同时跑、阶段间无屏障(墙钟=最慢单链)。
- `schema` 强制 subagent 结构化返回 + 校验重试 → 返回是**可被代码 `.filter`/去重/喂下一阶段的对象**。
- 「确定性代码控制」:控制流是 `for`/`if`/`Promise.all`,跑一万次一样;区别于主 Agent **agentic 即兴**调 Task N 次(不确定、易过度 spawn)。

### B. 子 agent 上下文模型(官方文档证实)
- **加载**全局 `~/.claude/CLAUDE.md` + 项目 `./CLAUDE.md`(`@AGENTS.md` import 照样展开)+ git 快照 + 预加载 skill。
- **不继承**主会话对话历史(`fork` 例外:继承全部;`Explore`/`Plan` 例外:跳过 CLAUDE.md 求快)。
- 只回传 summary,verbose 留在子 agent 上下文 → **官方设计目的就是并行跑大量互不相交任务**。
- 与 Codex 的关键差:子 agent 自动继承 CLAUDE.md;Codex 靠 AGENTS.md(已链接,这层拉平)。

### C. CC 编排多 Codex 并行(现成可抄,不要从零造)
- `am-will/swarms`:**依赖 DAG + 波次执行**(Wave1 验证过才启 Wave2),planner/executor 分离,Claude+Codex 都支持。**最贴合"锁接缝再 fan out"**。
- `kingbootoshi/codex-orchestrator`(315★,CC 插件):Claude 拆任务、每任务一 tmux session、job 元数据落盘。
- `kky42/codex-as-mcp`(166★):`spawn_agents_parallel`,最干净的"一次起多个 codex"。
- 官方 `codex-rescue` 是**单次转发器,源码硬性禁并行**;但底层 `codex-companion.mjs` 支持并发后台 job + jobId 轮询(策略禁了不是没能力)。

### D. 验证铁律(所有可信来源一致)
- **绝不信 agent 自述,对照磁盘验证四件套**:`git diff vs base SHA` → build → **test(核心防谎报门)** → 期望产物存在。
- 完成门机械化:`PostToolUse`/`Stop` hook 跑测试,**不过不许标 done**。
- 并发上限 **3–5**(瓶颈是人 review,不是 token);**预执行硬 kill**(token 上限 + 卡 3 次自动 kill;有人没设上限烧了 $47K)。
- 现有 CLAUDE.md 纪律已覆盖踩坑前三(worktree 隔离/不重叠文件/真链路实测/锁契约再 fan out);**增量只两条:机械化完成门 + 预执行硬 kill**。

### E. 根因再确认(本次复盘的最硬结论)
- Codex+mimo 出问题**不是 mimo 代码弱**,是两层:① **mimo↔codex 工具协议**(apply_patch 按 model-slug 查 catalog 决定是否注入,mimo 不在 catalog→工具没给;CJK panic;自设预算静默停)——这层靠 **config + 钉版本 + 前置 spike**,不是写指导;② **CC↔codex 编排/验证**——这层才是写 skill 能解决的。
- ⚠️ 一个 skill 修不了的硬风险:本地模型最弱处恰是编排最吃的(多轮工具调用+指令遵守)。**必须先 spike 验证 mimo 有没有天花板,再决定写不写 skill。**

## 7. 关键来源
- 本地源码：`~/.claude/plugins/.../codex/1.0.1/scripts/lib/codex.mjs`（`buildResultStatus`/`looksLikeVerificationCommand`）、`gpt-5-4-prompting/SKILL.md`（XML 块提示词规范）。
- Codex issues：#14046（apply_patch 按 slug 选实现）、#8161（禁 apply_patch 走 shell）、#9580（CJK panic）、#15003（大 patch）、#24629（自设预算静默停）、#18018（谎报 committed）、#15451（--output-schema 带工具时静默坏）、Discussion #7782（wire_api 仅 responses）。
- 社区并行编排：firecrawl / particula(oh-my-codex) / danielvaughan（worktree-per-task + 后台 codex exec + 资源约束）。
