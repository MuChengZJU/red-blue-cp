# docs/research · 调研 memo

针对开发中遇到的**开放问题**做的循证调研（带引用、分清证据与推断、列局限）。区别于 `devlog/`（叙事性踩坑/决策记录）——这里是「向外查、要结论」的研究产出。

产出方式：[Deep Research V8](https://github.com/KKKKhazix/khazix-skills) 方法论 + Claude Code Dynamic Workflow 并行 agent 取证 → 综合 → 对抗性质检门核验引用。非人工逐字撰写，引用以正文链接为准。

| memo | 问题 | 置信度 | 质检 |
|---|---|---|---|
| [Q1 · DW vs 多 Codex 并行](2026-06-19-q1-orchestration-dw-vs-codex.md) | Claude Code Dynamic Workflow 与多 Codex（本地模型）并行写代码，区别与选型 | high | pass |
| [Q2 · Tauri 桌面端 UI 精致度](2026-06-19-q2-tauri-ui-polish.md) | 同套设计系统为何桌面端不如网页端，怎么破 | medium | pass |
| [Q3 · Rust+Tauri 开发成本](2026-06-19-q3-rust-tauri-dev-cost.md) | 开发反馈环是否显著更慢，怎么压缩 | medium | pass |

三个问题也开了讨论征集：[issue #55](https://github.com/MuChengZJU/red-blue-cp/issues/55)。
