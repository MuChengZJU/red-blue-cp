# 产品功能文档：博主安全批量下载（提案 / 草案）

> 状态：**提案，待 review**。涉及与红线 #9（P1 用 pydoll）的取舍，敲定后才并进 PRD/SPEC/PLAN、才动 `app/`。
> 本文覆盖：① 产品现状（已有功能）② 新增功能（安全批量下载）的完整设计。

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

第 ④ 层 `fetch --all` happy path 能跑，但**用不安全的方式**，真放心用会出事：

1. **抓清单用 pydoll**：CDP 驱动 Chrome 带 `webdriver` 自动化痕迹，易被识别；不可分发给普通用户（要宿主装 Chrome + CDP）。
2. **下载用串行裸 IP**：量一大就标记你的 IP。**固定共享出口 IP（校园网/公司网）尤其危险**——被标记会连累整个出口、且 IP 固定洗不掉。

> 结论：**「安全地批量下载」本就是管道该有的完整能力，不是产品层附加。** 本功能 = 把博主全量从残次品补成真能用。

## 三、新方案：插件抓清单 + rbcp 代理批量下载

数据流（两条路径共用一份契约）：

```
手动导出:  [插件] 抓→去重→导出 notes.json ──手动──> [rbcp batch] 走代理逐条下 → Markdown
一键转发:  [插件] 抓→去重 ──POST──> [rbcp serve /api/import-list] 建任务→后台代理下→WebUI 看进度
```

**职责切分**：插件只在用户登录态里**抓清单**（有风控的部分，浏览器真实环境最安全）；rbcp 只**下载+转录**（算力部分，走代理护 IP）。

### 浏览器插件（新，MV3）
- 机制：博主主页 `world:MAIN` + `document_start` hook 接 `user_posted`，累计去重（已验证：某博主 326/326 带 token，慢滚零验证码）。
- 范围：先只小红书博主主页（搜索页/收藏夹待定）。
- 交互：默认手动滚（最安全），可选温和自动滚（带节流）；显示「已抓 N 条」+ 完整/截断提示。
- 出口：导出 `notes.json` / 一键发本地 rbcp。
- 优于 pydoll：无自动化痕迹、可分发、风险落用户自己会话+IP。

### rbcp 本体（改 `app/`）
- 新命令 `rbcp batch <notes.json>`：读清单 → 逐条 `_fetch_single` → 出 Markdown。走代理、可控速/并发、断点续传。
- WebUI 加「导入清单」入口。
- serve 加 `POST /api/import-list`（一键转发，阶段 2）。

## 四、数据契约 `notes.json`（插件 ↔ rbcp 的接缝）

**贪婪存全**：`user_posted` 返回的有用字段都留，方便后续筛选/归档。

```json
{
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

- 导出文件名：`xhs-{user_id}-{YYYYMMDD}-{count}notes.json`。
- `complete=false`（被风控截断半份）→ rbcp 必须**警告**，不当全量处理。

## 五、代理（两种模式）

下载走代理是「安全」的核心。支持两种：

1. **固定单 URL**：`.env` 配 `RBCP_PROXY=http://127.0.0.1:7897`（或 CLI `--proxy` 覆盖）。最简单，适合自用单节点。
2. **Clash 轮替**：CLI 调本地 mihomo 控制端口（`external-controller`）的 API，每下 N 条换一个节点，把请求摊到多节点降低单 IP 频率。适合上量/无人值守。配置项：控制端口、密钥、selector 组名、轮换步长。

> 注：抓 explore 详情（主站）走代理护 IP；下媒体字节走 CDN，CDN 宽松、可不走代理省流量（待定为可配）。

## 六、错误处理 UX（横切，全功能适用）

**所有可能出错的点都要：① 落日志 ② 提醒用户**，不许默默失败/默默存假数据。

| 出错点 | 检测 | 日志 | 用户提醒 |
|---|---|---|---|
| token 过期（返空壳，title 空）| 判 title 空/无 note | 记 note_id + 时间 | 「清单已过期，请用插件重新抓取」|
| 代理不通 / 出口异常 | 连接失败 / 出口 IP 非预期 | 记错误 | 「代理未生效，当前出口=X，请检查 Clash」|
| 单条下载失败 | 异常捕获 | 记 note_id + 原因 | 批量汇总「成功 X / 失败 Y」，失败列表可见 |
| 清单半份（complete=false）| 读契约字段 | 记 captured/reason | 「清单未拉全（风控），不在半份上做全量」|
| 风控触发（验证码/薯队长）| 响应特征 | 记 | 「触发风控，建议慢速/换节点/稍后重试」|

> token 过期的处理策略（待 review）：**整批停 + 报错** 还是 **跳过该条继续**？建议默认整批停（过期通常是全批 token 一起失效）。

## 七、一键转发方案（阶段 2，待 review）

目标：插件抓完一键发本地 rbcp，免手动导出/命令行。防「任意网页偷偷 POST 乱下」：

1. 插件探测本地 `rbcp serve`（健康检查 `GET /api/health`），在跑才显示「一键发送」。
2. **配对 token**：首次 `rbcp serve` 生成一个一次性 token 显示给用户，用户填进插件设置；之后插件 POST 带此 token，serve 校验。
3. 跨域：插件 manifest 配 `host_permissions: http://localhost:*`，serve 开 CORS 仅允许扩展来源。
4. serve 收到 → 建批量任务 → 后台走代理下 → WebUI 看进度。

## 八、分阶段

- **阶段 1（最小可行，先做）**：插件抓清单 + 导出 JSON；`rbcp batch` 走代理（单 URL）+ 断点续传 + 错误 UX。能 dogfood。
- **阶段 2（好用目标态）**：Clash 轮替代理；一键转发；WebUI 进度。

## 九、与红线 #9 的关系

红线 #9 锁定 P1 博主全量用 pydoll。本方案把「抓清单」从 pydoll 换插件——是**经讨论的范围调整**（理由：pydoll 不安全/不可分发）。pydoll 可作为「无浏览器/脚本化」场景保留，与插件并存。**正式做之前更新 PRD/SPEC/PLAN，并把红线 #9 改为「插件优先，pydoll 备选」。**

## 十、待 review 的拍板点

1. 数据契约字段够不够（还要存什么）。
2. 插件范围：先只博主页？
3. 自动滚要不要。
4. token 过期：整批停 vs 跳过继续。
5. CDN 下字节走不走代理。
6. 一键转发的配对 token 方案是否可接受。
