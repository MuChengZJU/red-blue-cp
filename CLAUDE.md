# CLAUDE.md · Red Blue CP

> 本仓库的规则书是 **[AGENTS.md](./AGENTS.md)**（跨工具通用标准，单一真相源——Codex / Cursor / Copilot / Gemini 等都读它）。
> Claude Code 通过下面的 `@import` 读取它；本文件只追加 Claude Code 专属内容（Skill routing）。
> 改规则去 AGENTS.md 改，别在这里改。

@AGENTS.md

## Skill routing（Claude Code 专属，其它 agent 忽略）

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
