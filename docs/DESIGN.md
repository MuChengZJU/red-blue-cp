# DESIGN.md · Red Blue CP 设计系统「红蓝品牌」

> 单一真相源。**所有界面（WebUI / Desktop / 将来 Mobile）共用这套系统**——保持一眼认得出是同一个产品。
> 现实现：WebUI 在 `app/web/templates/base.html` 的 `:root`（这份 DESIGN.md 由它归纳）；Desktop 在 `desktop/frontend/styles.css`。
> 加新界面 = 复用这些 token，不要另起炉灶（V0.6 Desktop 第一版另搞了一套暗色 generic UI，已纠正）。

## 记忆点（一句话）
**红蓝撞色 · 大圆角 · 活泼友好 · 内容优先。** 红=小红书侧，蓝=B站侧；产品名「红蓝CP」本身就是红→蓝渐变。

## 颜色
| token | 值 | 用途 |
|---|---|---|
| `--rb-red` / `--rb-red-strong` | `#e5484d` / `#cf3a40` | 小红书侧、重点高亮、危险 |
| `--rb-blue` / `--rb-blue-strong` | `#2563eb` / `#1d4ed8` | B站侧、主按钮、链接、时间戳、主强调 |
| `--rb-green` | `#16a34a` | 成功 / done / 校验通过 |
| `--rb-amber` | `#d9821a` | pending / 警示 |
| `--text` `--muted` `--faint` | `#1a1f2e` `#6b7280` `#9aa1ad` | 正文 / 次要 / 极淡 |
| `--line` | `#e8eaf0` | 分隔线、边框 |
| `--bg` `--soft` `--soft-2` | `#ffffff` `#f5f7fb` `#eef1f8` | 底（白）/ 软底 / 更软底 |
| danger | `--danger-bg #fff1f2` `--danger-line #fecdd3` `--danger-text #be123c` | 失败态 |

**亮色主题（`color-scheme: light`，白底）。** 不做暗色（除非将来明确加暗色变体，须同时给 WebUI+Desktop）。

签名背景（body）：白底 + 双 radial glow——左上红 `rgba(229,72,77,.06)`、右上蓝 `rgba(37,99,235,.07)`。
签名标题：`linear-gradient(96deg, var(--rb-red), var(--rb-blue))` + `background-clip:text` 做红→蓝渐变字。

## 字体
- `--font-ui`: `"Plus Jakarta Sans"` + 系统中文回落（PingFang SC / Microsoft YaHei）。拉丁文用 Jakarta，中文回落。
- `--font-mono`: JetBrains Mono / SF Mono 等。
- 引入：`<link href="https://fonts.bunny.net/css?family=plus-jakarta-sans:500,600,700,800">`（非 Google，隐私友好；离线时优雅回落系统字）。
- 字重：正文 500，强调 600-700，标题 800。

## 圆角 / 阴影
- 圆角：`--r-card 18px`（卡片，**大圆角是品牌特征**）/ `--r-input 14px` / `--r-btn 12px` / `--r-sm 10px` / `--r-pill 999px`。
- 阴影（蓝调、克制）：`--shadow-sm 0 1px 2px rgba(20,30,60,.04)` / `--shadow-md 0 6px 22px rgba(20,30,60,.08)` / `--shadow-lift 0 10px 30px rgba(37,99,235,.12)`。

## 组件约定
- **按钮**：主 = `--rb-blue` 实心白字 + `--r-btn` + hover 提亮/微抬；次 = 白底 `--line` 边；ghost = `--soft-2` 底。
- **卡片**：白底 + `--r-card` + `--shadow-sm`，hover 抬升 `--shadow-md`。
- **状态点**：pending amber / running blue / done green / failed red。
- **链接 / 时间戳 / 强调数字**：`--rb-blue`。
- **重点高亮（速览三形态 ①）**：`--rb-red` 半透明底（`rgba(229,72,77,.18)`，"只看高亮"时加深 + 淡化非高亮）。

## 速览三形态（Desktop 专有，仍守上面系统）
同屏三列「① 全文+重点高亮 / ② 卡片金句 / ③ 脉络大纲」，目标"一竖屏读懂"。列头用 ①②③ 序号 + 软底；
红高亮可点跳读、蓝时间戳；卡片大圆角、锚不回原文的卡淡显不可点；大纲蓝色 border-left 树。

## 维护
改 token 先改这里，再同步 `app/web/templates/base.html` 与 `desktop/frontend/styles.css`（两处当前各存一份；将来可抽公共 CSS）。新界面照抄本系统。
