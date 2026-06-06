# 产品功能文档：博主安全批量下载

> 状态：**阶段 1 已交付（M4 / 0.4.0）**。插件抓清单 + `rbcp batch` 走代理 + 错误地基已上线。本文是设计依据，阶段 2（收信箱 / 一键转发 / Clash 轮替 / WebUI 批量进度）仍为待办。
> 本文覆盖：① 产品现状（已有功能）② 安全批量下载的完整设计。

---

## 一、产品现状（已有功能）

rbcp 目标：URL → 纯文本 Markdown 知识库。PRD 五层能力**已全部实现**（v0.1 / v0.3）：

| 层 | 能力 | 入口 |
|---|---|---|
| ① 视频转录 | B 站视频、小红书视频 → 字幕优先/ASR | `rbcp run` / WebUI |
| ② 图文识别 | 小红书图文 → VLM 识别 | 同上 |
| ③ 说话人分离 | 多人对谈标「说话人 N」 | 自动 |
| ④ 博主全量 | `fetch --all`：pydoll 抓清单 + 串行下 | CLI |
| ⑤ 评论 | `fetch --comments`，含楼中楼 | CLI / WebUI |

双入口（CLI + WebUI 红蓝品牌、手机可达）、扫码登录、PyPI 发布 + CI/CD 均已具备。

## 二、问题：现有「博主全量」是残次品

第 ④ 层 `fetch --all` happy path 能跑，但**用不安全的方式**，真放手用会出问题：

1. **抓清单用 pydoll**：CDP 驱动 Chrome 带 `webdriver` 自动化痕迹，易被识别；不可分发给普通用户（要宿主装 Chrome + CDP）。
2. **下载用串行裸 IP**：量一大就标记该 IP。**固定共享出口 IP（多人共用一个公网出口）尤其危险**——被标记会影响整个出口、且 IP 固定洗不掉。

> 结论：**「安全地批量下载」本就是管道该有的完整能力，不是产品层附加。** 本功能 = 把博主全量从残次品补成真能用。

## 三、新方案：插件抓清单 + rbcp 代理批量下载

数据流（两条路径共用一份契约）：

```
手动导出:  [插件] 抓→去重→导出 notes.json ──手动──> [rbcp batch] 或 [WebUI 导入清单] 走代理逐条下 → Markdown
一键转发:  [插件] 抓→去重 ──POST──> [rbcp serve /api/import-list] 建任务→后台代理下→WebUI 看进度
```

**职责切分**：插件只在用户登录态里**抓清单**（有风控的部分，浏览器真实环境最安全）；rbcp 只**下载+转录**（算力部分，走代理护 IP）。

### 浏览器插件（新，MV3）
- 机制：博主主页 `world:MAIN` + `document_start` hook 接 `user_posted`，累计去重（已验证：某博主 326/326 带 token，慢滚零验证码）。
- 范围：**先只小红书博主主页**（搜索页/收藏夹待定）。
- **UI**：一个 popup 面板——显示「已抓 N 条 / 完整或截断」状态、导出按钮、一键发送按钮、设置（代理握手、自动滚开关）。不是纯后台脚本，要有可见的操作界面。
- 交互：**默认手动滚（最安全）**，可选温和自动滚（带节流，守「慢滚」纪律）。
- 出口：导出 `notes.json` / 一键发本地 rbcp。
- 优于 pydoll：无自动化痕迹、可分发、风险落用户自己会话+IP。

### rbcp 本体（改 `app/`）
- 新命令 `rbcp batch <notes.json>`：读清单 → 逐条 `_fetch_single` → 出 Markdown。走代理、可控速/并发、断点续传。
- WebUI 加「导入清单」入口（上传/粘贴 notes.json，批量下）。
- serve 加 `POST /api/import-list`（一键转发，阶段 2）。

## 四、数据契约 `notes.json`（插件 ↔ rbcp 的接缝）✅ 已定稿

**贪婪存全**：`user_posted` 返回的有用字段都留，方便后续筛选/归档。字段已足够贪婪，定稿如下：

```json
{
  "schema_version": 1,
  "source": "xhs_user_posted",
  "user_id": "<博主id>",
  "user_name": "<博主名>",
  "captured_at": "2026-06-05T12:00:00+08:00",
  "complete": true,
  "count": 326,
  "notes": [
    {
      "note_id": "...",
      "title": "...",
      "type": "normal | video",
      "xsec_token": "...",
      "url": "https://www.xiaohongshu.com/explore/{id}?xsec_token=..&xsec_source=pc_user",
      "liked_count": 158,
      "cover": "<封面直链，可选>",
      "sticky": false
    }
  ]
}
```

- `schema_version`：契约版本（当前 `1`）。rbcp `batch` 读入先校验，不匹配则拒绝（不猜测、不降级）。插件写、batch 校验，两端用同一常量。
- 导出文件名：`xhs-{user_id}-{YYYYMMDD}-{count}notes.json`。
- `complete=false`（被风控截断半份）→ rbcp 必须**警告**，不当全量处理。

## 五、代理（两种模式）

下载走代理是「安全」的核心。支持两种：

1. **固定单 URL**：`.env` 配 `RBCP_PROXY=http://127.0.0.1:7897`（或 CLI `--proxy` 覆盖）。最简单，适合自用单节点。
2. **Clash 轮替**：CLI 调本地 mihomo 控制端口（`external-controller`）的 API，每下 N 条换一个节点，把请求摊到多节点降低单 IP 频率。适合上量/无人值守。**这种复杂的命令行编排不做专门 UI，交给 AI Agent（rbcp skill）来调用**——配置项（控制端口、密钥、selector 组名、轮换步长）由 Agent 按需编排。

> CDN 媒体字节（图片/视频）：**默认不走代理**（CDN 宽松、不做 IP 风控，省代理流量），可配置为走代理。只有抓 explore 详情（主站）默认走代理护 IP。

## 六、错误处理 UX（横切，全功能适用）

**所有可能出错的点都要：① 落日志 ② 提醒用户**，不许默默失败/默默存假数据。

> ⚠️ 范围说明：错误处理是**整个项目各处**的横切关注点，不止本功能。全项目错误日志/UX 审计已完成，见 **[docs/error-handling-audit.md](error-handling-audit.md)**（5 条横向问题 + 3 个真 bug + Top 5 补齐项）。关键：service 层零 logging、异常不分层、`raise_for_status` 吞 body——**这三条不先补，本功能的错误提醒也只能拿到裸异常**。下表先列本功能相关的：

| 出错点 | 检测 | 日志 | 用户提醒 |
|---|---|---|---|
| token 过期（返空壳，title 空）| 判 title 空/无 note | 记 note_id + 时间 | 「第 N 条清单已过期，已跳过」|
| 代理不通 / 出口异常 | 连接失败 / 出口 IP 非预期 | 记错误 | 「代理未生效，当前出口=X，请检查 Clash」|
| 单条下载失败 | 异常捕获 | 记 note_id + 原因 | 批量汇总「成功 X / 失败 Y」，失败列表可见 |
| 清单半份（complete=false）| 读契约字段 | 记 captured/reason | 「清单未拉全（风控），不在半份上做全量」|
| 风控触发（验证码/薯队长）| 响应特征 | 记 | 「触发风控，建议慢速/换节点/稍后重试」|

> token 过期处理策略：**跳过该条继续**（不整批停），最后在汇总里列出所有跳过的过期条目，提示用户「这些需重新抓清单」。

## 七、一键转发 + 导入收信箱（阶段 2，方案已定）

插件抓完一键 POST 给 `rbcp serve`。WebUI 设一个**「导入收信箱」**收这些请求（用户可能点多次，避免一堆任务无序堆叠）：

- 每条导入请求显示：博主名、条数、抓取时间、来源。
- **整体操作**：全部开始 / 全部忽略（拒绝本次）。
- **单条操作**：先检查确认再开始（展开看清单内容再下）。
- 每个导入批次 = 一个**独立的批量任务**，有自己的进度/成败管理，互不干扰。
- **防滥用**：靠"用户在收信箱里点开始/确认"——任意网页就算 POST 了，没点也不会下。**零配置、不用 token。**

跨域：插件 manifest 配 `host_permissions: http://localhost:*`，serve 开 CORS 仅允许扩展来源。

> 配对 token 方案弃用——收信箱的人工确认已足够防滥用，且更简单。

## 八、残余风险：xsec_token 与用户的关联（诚实记录）

换详情**不带 cookie**，但带 xsec_token。token 是你抓列表时**带登录态生成**的，所以：
- 理论上小红书后台**可能**把「这批 token 由哪个账号生成」关联起来。
- 更微妙：token 在「国内住宅 + 登录态」生成，却在「海外代理 + 无 cookie」使用，这种**生成环境 ≠ 使用环境**本身是可疑信号。
- **但实测未显现**：海外 IP、无 cookie、30 条 8 并发全过，说明小红书目前没拿 token 反查账号封号、也没严格查环境一致性。
- 风险排序：**IP 层（已用代理解决）> token 关联（理论存在、实测未现）**。
- 彻底消除需「抓列表与下载同环境」，但那放弃代理护 IP，是另一种取舍。当前分离架构实测安全，残余风险在此明示。

## 九、分阶段

- **阶段 1（最小可行，先做）**：插件抓清单 + 导出 JSON + popup UI；`rbcp batch` 走代理（单 URL）+ 断点续传 + 错误 UX；WebUI 导入清单。能 dogfood。
- **阶段 2（好用目标态）**：Clash 轮替代理（Agent 编排）；一键转发；WebUI 进度。

## 十、与红线 #9 的关系

红线 #9 锁定 P1 博主全量用 pydoll。本方案把「抓清单」从 pydoll 换插件——是**经讨论的范围调整**（理由：pydoll 不安全/不可分发）。
**把红线 #9 改为：插件为主，pydoll 降级为一个「不稳定、不保证维护」的可选项**，留给需要无浏览器/脚本化的场景或开源社区自行维护，不再作为主路径。正式做之前更新 PRD/SPEC/PLAN。

## 十一、拍板记录（用户已定）

| 点 | 决定 |
|---|---|
| 数据契约字段 | ✅ 够贪婪，定稿 |
| 插件范围 | ✅ 先只博主页 |
| 自动滚 | ✅ 加上，但默认/建议手动滚 |
| token 过期 | ✅ 跳过该条继续 |
| CDN 下字节走代理 | ✅ 可选，默认不走 |
| 插件 UI | ✅ 要 popup UI |
| Clash 轮替的复杂配置 | ✅ 交给 Agent 调用，不做专门 UI |
| 一键转发方案 | ✅ 导入收信箱（人工确认，零配置，可全部开始/逐个确认/全部忽略，每批独立任务）|
| 全项目错误 UX 缺口 | ✅ 审计完成，见 docs/error-handling-audit.md |
| 断点续传粒度 | ✅ B：SQLite 批次表（batch/batch_item），storage 纳入串行地基先锁 |

## 十二、阶段 1 实施计划（plan-eng-review 锁定 2026-06-05）

### 执行结构：先串行地基 → 再并行两流

```
M4a 地基（一个人，串行，锁公共接缝）
  a1  service/errors.py：异常最小集 + 结构化字段 + format_error_for_user()
  a2  抽 _fetch_single → service/pipeline.py（cli / batch 共用）
  a3  修代理覆盖：model.py trust_env，让媒体/ASR 下载也能走代理
  a4  storage 扩展：batch / batch_item 表 + 迁移（锁定 schema）
        ↓ M4a 合并后
M4b ‖ M4c 并行
  M4b 错误流：各 service 填 errors 异常 + logging + body；detail.html 分层+重试；cli.py run 退出码
  M4c 批量流：service/batch.py + cli batch 命令 + 插件(抓清单导出 JSON) + schema 校验 + 断点(查 batch_item)
```

### 异常契约（Codex 最小集）
`RbcpError`(基类，带 `kind/platform/operation/retryable/user_message/debug_context`) → `UnsupportedUrlError / ConfigError / NetworkError / ApiError(provider/api_code/payload_excerpt) / RiskControlError / AuthError(合 Cookie+Token) / ParseError`；`format_error_for_user(exc)` 出人话（CLI/Web 共用）。

### _fetch_single 接口（G2）
`service/pipeline.py: fetch_single(url, *, api_key, output_dir, comments, sub, save_media, text_only, proxy=None) -> dict`。cli / batch 都调它，cli 只做参数解析+输出。

### storage 模型（G4，锁定）
- `batch(id, source, user_id, count, complete, status, created_at)`
- `batch_item(batch_id, note_id, url, status, md_path, error_message, finished_at)`
- 沿用现有 `_init_schema` IF NOT EXISTS 模式建表。阶段 1 **不建 inbox 表**（收信箱阶段 2）。

### 文件边界（防相交）
- **M4a（串行独占）**：`errors.py`(新)、`pipeline.py`(新)、`model.py`、`storage.py`。
- **M4b 碰**：`service/*.py`(在 M4a 锁定接口上填异常)、`detail.html`、`cli.py` 的 `run`。
- **M4c 碰**：`service/batch.py`(新)、`cli.py` 的 `batch`(新函数)、插件(新 JS)、web 导入入口。
- `cli.py` 相交：M4b 改 `run/fetch`，M4c 加 `batch`(新函数) → 不同函数，git 自动合并。
- `storage.py`：M4a 锁定 schema 后，M4b 用 `retry_count`(已有)、M4c 用 `batch` 表 → 不再改结构。

### 阶段 1 验收
- `rbcp batch notes.json`：读 → schema 校验(`schema_version`) → 走单 URL 代理(**开跑前出口探测确认生效**) → 逐条下 → 断点跳已下 → 汇总 ok/failed/skipped。
- 真链路：拿插件导出的真实 `notes.json` 跑 ≥5 条出 Markdown（**含 1 条视频，验证 trust_env 修复后音频走代理**）。
- 错误：token 过期跳过继续 + 汇总列出；代理不通报错；各 service 抛结构化异常 + body 日志。
- 测试：errors 映射单测；batch 断点/跳过/失败汇总单测；`pipeline.fetch_single` 单测；trust_env 代理生效测。

### 边缘情况
schema_version 不匹配→拒绝；complete=false→警告不当全量；空 notes→友好提示；token 过期→跳过+记 batch_item(reason=token_expired)；代理未生效(出口=本机)→开跑前报错。

### NOT in scope（阶段 1）
插件 popup UI（阶段 1 插件只导出 JSON）/ 收信箱 / 一键转发 / Clash 轮替 / WebUI 批量进度 / inbox 表 → 全部阶段 2。
