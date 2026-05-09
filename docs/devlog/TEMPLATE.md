---
date: YYYY-MM-DD
type: decision | milestone | issue | experience
priority: high | medium | low
related: [PRD.md, SPEC.md, PLAN.md, CLAUDE.md, REFERENCES.md]
status: active | superseded | deprecated
---

# {标题}

> 一句话摘要，方便扫读时定位。

## 背景

简述当时的处境 / 触发因素 / 上下文。
对外审阅 / 实测发现 / 业务变化等。

## 决策 / 现象 / 经验

写清楚：
- 如果是 decision：做了什么决策
- 如果是 milestone：完成了什么里程碑
- 如果是 issue：遇到了什么问题，如何复现
- 如果是 experience：学到了什么可复用的经验

## 理由

为什么这么做 / 为什么会发生。
列出考虑过的备选方案及不选的原因。

## 影响

| 文件/模块 | 影响 |
|---|---|
| PRD.md | 改了哪一节 |
| SPEC.md | 改了哪一节 |
| PLAN.md | 改了哪个里程碑 |
| 代码 | 影响哪个目录 |

## 后续 / 复盘（可选）

- 事后回顾这个决策是否正确
- 暴露的新问题
- 是否需要补充新决策

---

## 模板使用提示

写完一个新 docs/devlog/ 详情文档后：
1. 文件名用 `YYYY-MM-DD-{slug}.md`，slug 用小写连字符，如 `p0-keep-it-simple`
2. 在 LOG.md 对应的纲要表格里新增一行索引
3. 如果这个决策让其他文档过时，在那些文档里加注释指向本文件
4. status 字段在决策被推翻时改为 `superseded`，并加链接指向新决策

删除本"模板使用提示"和模板分隔线以下的部分。
