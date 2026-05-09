---
date: 2026-05-09
type: decision
priority: high
related: [README.md, PRD.md, SPEC.md, PLAN.md, CLAUDE.md, REFERENCES.md]
status: active
---

# 项目命名为 Red Blue CP（红蓝CP）

> 自古红蓝出 CP —— B 站小红书 Content Pipeline。
> CLI 命令 `rbcp`，仓库 / PyPI 包名 `red-blue-cp`，内部代号 `rbcp`。

## 背景

工程文档冻结 v3.1 时项目还叫"Social Post Extractor"，是工程描述性命名，没有产品调性。

候选名字头脑风暴时考虑过：
- **Mark Media Down**：双关 Markdown，但跟 Microsoft 25k⭐ 的 MarkItDown 拼写发音过近，搜索引擎污染严重
- **PostMark**：被 PostMark.com（邮件 SaaS）占用
- **拓本 / Tuoben**：中文古典意象贴合，但英文用户读不出
- **Distill / Steno / Imprint / Pluck**：英文短词，但跟项目"中文互联网平台专用"定位不够紧密

最终定为 **Red Blue CP**，tagline："**自古红蓝出 CP —— B 站小红书 Content Pipeline**"。

## 决策

### 命名方案

| 用途 | 名字 |
|---|---|
| 中文展示 | **红蓝CP** |
| 英文展示 | **Red Blue CP** |
| 仓库 / PyPI 包名 | `red-blue-cp` |
| 内部代号 / CLI 命令 | `rbcp` |

### Tagline

> **自古红蓝出 CP —— B 站小红书 Content Pipeline**

## 理由

### "Red Blue CP" 的语义密度

四层双关精准对应项目要素：

| 层 | 解读 | 命中点 |
|---|---|---|
| 1 | **Red** = 小红书 / **Blue** = B 站 | 平台定位一眼明 |
| 2 | **CP = couple** = 中文互联网"嗑 CP"梗 | 把红蓝两站"嗑成一对"，原生中文互联网梗 |
| 3 | **CP = Content Pipeline** | 工程语义 / 技术主解释 |
| 4 | **CP = caption** | 字幕功能（视频转文本） |

### Tagline 的妙处

- "**自古红蓝出 CP**" —— 中文互联网亚文化既成事实（动漫游戏圈红蓝角色配对几乎天然 CP，鸣佐、艾萨等大量先例）
- "**B 站小红书 Content Pipeline**" —— 技术语义钉死，避免被误解为情感配对工具
- 前半玩梗后半正经，破折号节奏好

### 为什么不用 "copy" 解释 CP

最初讨论时 CP 解释含 "copy" 一层，被否决。理由：
- "copy" 在中文互联网有"复制粘贴"、"抄袭"、"搬运"的负面联想
- 跟内容创作者的关系上，"copy down" 听起来像在盗版
- "Content Pipeline" 显得专业、中性、技术化
- "Pipeline" 强调"处理流程"而非"占有"

### 为什么不用 "Mark Media Down"

虽然双关好（Mark + Media + Down 解构 Markdown），但：
- Microsoft MarkItDown（25k⭐，2024 年发布）已占据"X 转 Markdown"的认知位
- 名字拼写发音过近，搜索引擎层面会被压制
- 永远活在 Microsoft 项目阴影下

### 为什么不用"拓本"

中文古典意象贴合度极高（"拓"本身就是"提取保留便携"），但：
- 英文用户读不出 Tuoben
- 古典调性可能跟 B 站小红书的青年用户气质不完全匹配
- "Red Blue CP" 在亲和力和传播力上更胜

## 风险与应对

### 风险：未来扩平台后名字不准

如果未来加抖音、知乎，"red blue" 字面意义就不准了。

**应对**：现在接受这个名字承诺"只做 B 站和小红书"。这跟 PRD 里"抖音划掉、瞄准 B 站和小红书"的定位完全自洽，是差异化优势不是劣势。MarkItDown 那种通用工具的反面。

如果真要扩平台，CP 的 Content Pipeline 解读保留即可，"红蓝"是历史命名遗产，可以接受。

### 风险：CLI 命令 rbcp 跟 Unix `cp` 视觉接近

肌肉记忆敲 `rbcp` 时容易打成 `cp`。

**应对**：可接受，命令长 4 字符也不算长。用户可以自己设 alias 简化。Unix `cp` 是基础命令不能动，`rbcp` 也不会跟系统命令真冲突。

## 影响

| 文件/模块 | 影响 |
|---|---|
| README.md | 标题改 / 加 tagline / 状态行加包名 / 启动命令 spx → rbcp / 项目结构注释 |
| PRD.md | 标题改 / 加 tagline |
| SPEC.md | 标题改 / 加 tagline / CLI 命令段 spx → rbcp / 修订记录加 v3.2 |
| PLAN.md | 标题改 / 加 tagline / 所有 `spx ...` → `rbcp ...` |
| CLAUDE.md | 标题改 / 项目目标加 tagline |
| REFERENCES.md | 标题改 / 加 tagline |
| LOG.md | 标题改 / 加 tagline / 决策纲要表加本条 / 开发纲要表加 v3.2 条目 |
| 仓库 / PyPI 包名 | M0 fork 时建仓直接用 `red-blue-cp` |
| 文档版本 | v3.1 → v3.2 |

## 后续 / 复盘

待 P0 完成或开源时回顾：
- 实际使用中"嗑 CP"梗的接受度
- 国际用户对 "Red Blue" 的理解
- 是否有人把 CP 误读为"Couple Photos"（跟图文笔记功能混淆）
- 平台扩展时命名遗产的成本

## 相关

- 配套 tagline：`自古红蓝出 CP —— B 站小红书 Content Pipeline`
- 替代命名候选记录：详见原对话（2026-05-09 Claude.ai）的"项目命名头脑风暴"环节
