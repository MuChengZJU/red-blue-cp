# RBCP Desktop GUI 设计 · 0.6（功能 / UI-UX / 前端美术）

> 状态：**草案 v2，待审**（已过一轮 5 视角 AI 审：工程/产品/设计UX/安全红线 + Codex；本版把发现都收进来了）。审定后据此写实现计划（writing-plans）并更新 PLAN / DESIGN.md / digest 契约。
> 视觉 token 见 [DESIGN.md](../DESIGN.md)，采集模型见 [SPEC.md](../SPEC.md)，复用的后端端点见 `app/web/routes.py`，digest 形状见 `docs/contracts/0.6-digest-json-contract.md`。
> 交互参照物：`_sandbox/0.6-planning/{desktop-gui-mockup,desktop-layout-variants,icon-compare}.html`。

---

## 0. 背景与定位

0.6 引擎（Extract+Digest）+ CLI 已扎实，但桌面端此前只是「速览查看器」spike，缺 V0.5 WebUI 的全部交互能力（复盘见 [devlog 2026-06-16](devlog/2026-06-16-0.6-m6-build-and-desktop-gap.md)）。这份文档把**全功能桌面端**的设计固化。

**定位**：RBCP Desktop = 给人的「速览阅读 + 转录管理」桌面端。核心价值 = **免装 Python、双击即用、原生窗口 + 键盘流**，把已开源的引擎包成普通人能用的 App。它不是「浏览器开 localhost 加个壳」。

---

## 0.5 一页读懂（不用懂技术也能审）

用大白话把「要做什么、AI 审发现了什么、定了哪些事」讲一遍。你审的就是这些判断对不对，下面 §1 起是给工程实现看的详细版，不用逐字啃。

**要做的东西**：一个双击就能用的桌面 App（不用装 Python）。左边一列菜单（文件库 / 任务列表 / 账单 / 设置），右边是内容。核心是「速览阅读器」——一篇转录好的内容，同屏给你三样：① 全文带重点高亮、② 金句卡片、③ 脉络大纲。

**AI 审帮我们发现的 3 件大事**（这是这次改文档的主因）：
1. **比原想的要多做点**。我原来写「后端不用改、直接复用现成的」——不准确。现在桌面端那个小程序是「喂一段文字、吐一份速览」的简化 demo，要换成「常驻的本地小服务」。里面的业务逻辑能复用，但外壳和连接方式要重做。不是推翻，是把工作量说明白，别再像上次低估。
2. **速览的数据还没通**。「三形态速览」要的数据，现成接口里没有，得新开一个接口把它送出来，否则点开详情页是空的。
3. **本地小服务要上锁**。这个服务现在「谁都能连」（同一个 wifi 下别的电脑、你浏览器里随便一个网页，都能偷偷调用它、花你的 API 钱、读你的知识库）。必须改成「只许本机 + 要钥匙(token)才放行」。这是安全红线，原来漏了。

**定了的判断（你重点审这几条）**：
- 账单只显示**各个 AI 环节的耗时 + 花了多少钱**，不要「首字延迟」那种没数据的指标。（按你说的）
- 桌面端**彻底不碰 pydoll**（连真浏览器的爬虫）。文档里提它，只是为了说「把会用到它的两个旧接口关掉」。
- 转录完**顺手把速览也算好存起来**，点开秒显示。
- **单篇删除这版就做**（基本操作）；批量整理后面再说。
- 字体那条先当**提案**放着，等定了再正式改设计规范（DESIGN.md）。

---

## 1. 功能设计（Feature Spec）

### 1.1 架构 / 接缝 ⚠️ 这是一次架构替换，不是「零重写」

**现状（被替换的）**：当前 `desktop/` 是 Tauri command `run_digest` **spawn 一次性 sidecar**（`rbcp_sidecar.py` 读 stdin 纯文本、`FakeProvider` 桩造 extract、打印 digest JSON 即退出），无 URL 抓取、无任务队列、无常驻 server。

**目标架构**：
- **前端** = App 自带原生红蓝界面（HTML/CSS/JS 无框架，打包进 `.app`、离线即开）。
- **后端** = 把 `rbcp serve`（FastAPI）作为**常驻本地 sidecar**拉起：绑 `127.0.0.1` + **随机端口**、随 App 起停。前端经握手拿到端口后 `fetch` 它的 JSON 接口。
- **复用的是业务逻辑**（`Storage` / asyncio 任务队列 / `batch` / `pipeline` / `routes.py` 现成端点），**不是**现有 desktop 接缝——壳、sidecar 入口、serve 加固、digest 端点都是新增工作。

**因此「后端零改」是错的。** 下面这些「接缝」（= 前后端怎么连、怎么打包的关键衔接点）必须在写实现计划前先做小实验验证、再锁。🔴 = 卡死级、必须先验真；🟠 = 要做但风险小：

1. 🔴 **本地服务怎么绑** — 现在 serve 写死「绑所有网卡 `0.0.0.0`、固定端口 8000」。要改成「只绑本机 `127.0.0.1` + 随机端口」（更安全，见 §1.7）。
2. 🔴 **端口怎么告诉界面** — 端口随机了，得有个办法把实际端口号传给前端界面（经 Tauri / 临时文件）。现在没有这套握手。
3. 🔴 **跨源拦截（CORS）** — Tauri 界面去连本地服务，浏览器会当成「跨网站请求」直接拦掉。要么给服务加「允许名单」，要么让 Tauri 的 Rust 层代为转发。先写 10 行小实验确认界面的真实「身份(origin)」再定。
4. 🔴 **加钥匙（token）才放行** — 见 §1.7，本地服务必须「要钥匙」才响应。
5. 🔴 **速览数据接口** — 现成接口不吐「速览三形态」的数据，要新开一个接口 `GET /api/jobs/{id}/digest`，否则点开详情页是空的。
6. 🟠 **关掉 pydoll 旧接口** — 复用的 serve 里有两个旧接口（列博主清单 / 抓评论）会用到 pydoll（连真浏览器的爬虫）。桌面模式**把这俩接口关掉** → 桌面端彻底不碰 pydoll。
7. 🟠 **进程别变僵尸** — 常驻服务在 App 退出/崩溃时要确保被杀掉，否则占着端口。
8. 🟠 **只许开一个** — 同时开两个 App 会有两个服务写同一个数据库（违反「单进程」红线#3）→ 加「单实例锁」。
9. 🟠 **打包要带全** — 把 serve（含网页模板）打进离线包，比只打速览引擎复杂；先做个打包小实验，量大小、理清模板路径。

**打包闭包**：全仓 `app/` 确不用 ffmpeg（`ffmpeg-python` 仅 `pyproject.toml` 声明、零 import）→ 打包前删该依赖 + README 同步，或 `--exclude-module ffmpeg`。pydoll 确为 lazy import（`discover.py` 顶层不 import）→ 可排除，但需打包策略验证「`routes`→`discover` 这条能力面不被拖进二进制」。

### 1.2 能力清单（进 / 不进）

**进 App**：
- 提交单条 URL → 转录（复用 `POST /api/jobs`）。**分平台**：B站普通视频链接直接可用；**小红书单篇需带 `xsec_token` 的分享链接/文案**（`xsec_token` 是小红书专有，不是通用前提）。
- 任务列表 + 2s 轮询（`GET /api/jobs`）；去重 409；失败重试（`/api/jobs/{id}/retry`）。
- 任务详情 = **速览阅读器**（§1.3）。
- **导出 / 复制**：复制正文到剪切板（快捷）+ 单篇导出 `.md`（复用 `GET /api/jobs/{id}/download`）+ 在访达中显示。批量导出后做。
- **单篇删除**（基本卫生，进 v1）；批量整理后做。
- 账单（§1.5）；**速览三形态**（核心，§1.3，需新增 digest 端点）。
- **博主批量**：插件抓清单 → 导出 `notes.json`（文件/剪切板）→ App「导入」（`POST /api/import-list`）→ 走代理下载 → **批次进度**（轮询 `/api/batches` + `/api/batches/{id}/items`，逐条 `job_id` 失败复用 `/retry`）。
- 设置（§1.6）。

**不进这版**：博主清单 App 内 pydoll 抓取（走插件）；评论抓取（搁置）；整个 pydoll / 系统 Chrome 依赖（且 desktop serve 模式禁掉相关端点，见 §1.1）。

**采集模型（见 SPEC）**：内容正文靠带 `xsec_token` 的链接（requests，单篇不碰浏览器）；单篇链接靠**分享**；多篇靠**浏览器插件**导出 `notes.json`。

### 1.3 倒三角内容模型（三层）+ 坐标系

| 层 | 内容 | 文本坐标系 | 主要用途 | 来源 |
|---|---|---|---|---|
| ① **精华** | 高亮 / 卡片 / 脉络 + **带高亮的全文** | **canonical（原始）** | 给人读，默认 | `digest()` + 服务端锚定 |
| ② **清洗全文** | LLM 纠错后的可读版（**无高亮、纯阅读**） | readable（独立坐标系） | 舒适阅读；喂 AI | `ExtractResult.readable` |
| ③ **原始·时间对齐** | ASR 逐字 + 时间戳（未纠错） | canonical + segments | 存档；供 AI / 核对 | `canonical` + `segments` |

> ⚠️ **坐标系铁律**（AI 审抓出的硬伤）：highlight 的 `span_start/end` 锚在 **canonical** 上；`readable` 与 char 区间**无 offset 对齐**（见 `contracts.py`）。所以 **①「带高亮的全文」列必须渲染 canonical 文本**（与高亮同坐标系），**不能**用清洗版②，否则高亮必错位。清洗版只用于②那个无高亮、无跳读的纯阅读层。

- 阅读器默认 = ①精华速览；段控可切 ②清洗全文 / ③原始逐字。段控 label 带副标传达差异：「清洗全文 · 已纠错」/「原始逐字 · 未纠错·带时间戳」。
- **digest 数据怎么到前端 / 落哪**（默认决策，可改）：转录成功后**顺带跑 `digest()`**，把 digest JSON（highlights/cards/outline + canonical + segments）落到 **App 缓存目录**（platformdirs cache / sqlite 旁表，**不进 `~/transcript` 知识库**，守红线#5），详情页 `GET /api/jobs/{id}/digest` 直接读缓存 → 秒开。备选：按需触发 + 缓存（省 LLM 钱，首开等待）。

### 1.4 文件库

- 搜索（标题/作者/正文）、排序（时间 / 名称）、平台筛选（全部 / B站 / 小红书）、**卡片 + 列表**双模式。
- **封面缩略图**：⚠️ 这是**新增采集能力**，不是复用——现 pipeline 不抓封面（媒体只在 tempfile 临时存用完即删，红线#5），`notes.json` 未必带封面 URL。需新增「抓封面→超压缩→存 **App 缓存目录**（不进 `~/transcript`）」管线；工作量大可降级**后做**，先用平台色块 / 首字占位。
- 「文件库管理」（批量删/移/整理）→ 后做。

### 1.5 账单

- 数字卡：累计 / 本月 / 平均每篇。
- **按环节**：ASR / VLM / LLM 各金额 + 占比条（数据来自 `pricing.summarize_usage` 的 per-stage `cost_yuan`/`elapsed_seconds`，**有支撑**）。
- **按任务**：每条预计计费 + 各环节**耗时**（`elapsed_seconds`）。
- **首字延迟（TTFT）**：⚠️ 现有 usage schema **没有**这个字段（只有总 `elapsed_seconds`）→ **这版不做**，列入 §6 待决（需 `model.py` 流式解析时加 `first_token_at` 埋点）。
- 诊断信息：各环节耗时 / 用量（数据小、不压缩）落 **App 缓存**（非知识库）。注意与 digest 自身 diagnostics 分清。

### 1.6 设置

- 百炼 API Key（只存本机不上传）、知识库输出目录、代理（`RBCP_PROXY`）、速览模型(LLM) / 图文模型(VLM)。
- **数据与清理（规划中）**：本地诊断数据 + 封面缓存的审计与安全清理。占位，后做。
- 路径展示一律用 `~/` 缩写（不显绝对家目录，脱敏，对齐 CLAUDE.md）。

### 1.7 红线对齐（必须遵守，见 CLAUDE.md）

下载走 `job_id` 不传 path；密钥不进 git；**单进程 uvicorn（→ 桌面端单实例锁保证一台机一个 serve）**；知识库只 `.md`+`_index.sqlite`（封面/digest/诊断走 App 缓存，不混入 `~/transcript`）；失败留痕（任务行显 `error_message` 人话，`log_excerpt` 技术详情折叠、脱敏不露路径/用户名）；Markdown 原子写；不做抖音/飞书；桌面端不沾 pydoll（且禁掉 serve 的 pydoll 端点）。
**新增红线**：**本地 serve 必须绑 `127.0.0.1`（绝不 `0.0.0.0`）+ 随机端口 + 启动 token 鉴权**（防本机其它进程/网页越权花额度、读知识库）。审定后同步进 CLAUDE.md 不变量。

---

## 2. UI/UX 设计

### 2.1 信息架构 / 导航（经典左侧栏）

```
左侧栏（固定）              主区（随导航切换）
├ 品牌 红蓝CP               ├ 文件库   （搜索/排序/筛选/卡片·列表/缩略图）
├ 新建区                    ├ 任务列表 （批次卡 + 任务行 + 轮询）
│  ├ 粘链[转录]  ← 主操作   ├ 速览阅读器（= 详情页，三层）
│  └ 批量导入    ← 次级     ├ 账单
├ 导航 文件库/任务/账单/设置 └ 设置
└ 底部 累计费用 · API 状态
```

- **新建区主次分明**：单条转录是高频主路径常驻；批量导入降为次级（小字/折叠 + 一句「需配合浏览器插件导出 notes.json」引导；浮层空态给「如何拿到 notes.json」一步引导）。
- **统一**：点文件库卡片 / 任务列表里一条 done → 主区进入**速览阅读器**。

### 2.2 各屏布局 + 状态

**文件库**：工具条（搜索 + 平台 chips + 排序 + 卡片/列表）+ 网格/列表。空库（暖文案 + 「粘贴第一条链接」）、搜索无结果、加载态都要做。

**任务列表**：批次卡片（进度 + 计数）+ 任务行（状态点+文字 / 进度 / 操作）。状态点 pending 琥珀 / running 蓝 / done 绿 / failed 红。失败行：只显 `error_message` 人话（如「图片防盗链 403 · 已兜底重试 3 次」），技术详情收「详情/复制错误」折叠。去重 409 弹「已下过《标题》，重下 / 打开已有」。

**速览阅读器**（核心）：
- 头：返回 / 标题+作者·平台·时长 / **三档段控**（精华速览 · 清洗全文·已纠错 · 原始逐字·未纠错）/ 只看高亮 / **复制** / 导出 / 在访达中显示。
- ① 精华速览：三列（全文+高亮[canonical] / 卡片金句 / 脉络大纲）。交互：
  - 正向：点红高亮/卡片/大纲 → 滚到全文对应处闪烁；蓝时间戳；无锚点金句灰显不可点。
  - **反向（AI 审补）**：全文滚动时大纲/卡片 **scrollspy** 高亮当前节点；「只看高亮」可一键退回全文上下文；定义三列联动滚动规则（点任一列定位，其余列是否跟随）。
- ② 清洗全文：单栏舒适阅读（measure 45–75 字），无高亮。
- ③ 原始逐字：顶部黄条「未纠错·主要供 AI/核对」+ 逐行（时间戳 + 文本）。

**账单 / 设置**：见 §1.5 / §1.6。

### 2.3 关键交互流程

1. **单条**：粘链（B站普通链 / 小红书分享链）→ 转录 → 轮询 → 完成进库 + 顺带出 digest → 点开速览。
2. **批量**：插件导出 `notes.json` → 导入浮层（拖入/粘贴）→ 早校验 schema → 代理后台下载 → 批次进度（轮询 batches+items，单条失败复用 `/retry`）。
3. **复制 / 导出**：复制正文到剪切板（快捷）；单篇导出 `.md`（复用 `/download`）；在访达中显示。导出不被「复制」取代。

### 2.4 键盘流（AI 审补，原生 App 的兑现点）

- 全局 **Cmd+V** 粘贴即新建转录；**Cmd+F** 聚焦搜索；**Esc** 返回；段控 **1/2/3** 切三层；**Cmd+C** 复制正文。
- 列表方向键 ↑↓ + Enter 打开；阅读器三列/三档段控用 roving tabindex + `aria-current`。

### 2.5 状态 / 无障碍（实现必须做）

空状态 / 加载·骨架 / 失败分层；`focus-visible` 焦点环 + **视图切换的焦点转移与返回恢复**（点卡片进阅读器焦点移到主标题，返回恢复到原卡片）；`prefers-reduced-motion`；真实封面缩略图（mockup 现为占位）。

---

## 3. 前端美术设计

### 3.1 设计系统

套用 [DESIGN.md](../DESIGN.md) 红蓝品牌系统（token 不重复）：红蓝撞色 · 大圆角 · 活泼友好 · 内容优先；亮色白底双 glow；品牌字红→蓝渐变。新界面复用 token，不另起炉灶。

### 3.2 字体（**提案，DESIGN.md 暂为准**）

- 诉求：macOS = 系统 **SF Pro**（`-apple-system`，无版权、最原生）+ 苹方回落；Windows = **打包一款可嵌入再分发的字体**（不用微软原生，渲染差）+ 中文回落。
- ⚠️ DESIGN.md 现锁 Plus Jakarta Sans 优先；本节是**对 DESIGN.md 的修订提案**。按 CLAUDE.md「改规范先改文档」，**审定时先改 DESIGN.md**（并定 WebUI 是否跟随），再落桌面实践。在此之前 DESIGN.md 为准，避免两份真相源并存。
- 字重：正文 500 / 强调 600–700 / 标题 800。

### 3.3 图标（全部打进离线包，不依赖 CDN）

- 导航 / 版块 / 物体类 = **Flat Color Icons**（Icons8，彩色）；UI 微动作 = **Lucide**（单色线性）；平台 logo = **Simple Icons**（B站/小红书）。
- mockup 阶段走 CDN（Iconify/unpkg/simpleicons）预览；正式版全部下载打进离线包，**保留各图标集 LICENSE/署名**（核实 Flat Color Icons 仓库实际许可与署名要求）。

### 3.4 风格基调

苹果「优雅」规范，但**不是液态玻璃（Liquid Glass）**，是之前那套（Big Sur→Sonoma 清爽材质）：克制 vibrancy（轻 blur，非厚玻璃）、hairline 分隔线、软阴影、选中项淡蓝底、圆角 14px、舒适留白。

### 3.5 组件视觉规格

沿用 DESIGN.md 组件约定。本版新增：三档段控（软底 + 选中白底浮起）；账单（数字卡 / 按环节占比条 ASR蓝·VLM红·LLM绿 / 按任务行 + 耗时 chip / 诊断条）；彩色 Flat Color 导航图标（早期「彩色圆角块」版已弃）。

### 3.6 AI-slop 自审（已过，保留项说明）

经 /design-review 校准：无紫渐变 / 无三栏图标功能格 / 无全居中 / 无装饰 blob / 无 emoji / 无套话。**刻意保留**（非 slop）：SF 系统字（原生 app 正确做法）、大圆角（品牌）、卡片红左边框（品牌 + 功能区分）、彩色 FC 图标（用户选定）。

---

## 4. 完成定义（DoD）

- **写 writing-plans 前必须补的 spike**：① webview 实际 origin + CORS 方案；② serve 绑 127.0.0.1 + 随机端口 + token 握手；③ PyInstaller 打 serve 的闭包/模板路径。
- **后端新增**（非零重写）：desktop serve 模式（host/port/token/CORS、禁 pydoll 端点）；`GET /api/jobs/{id}/digest`；转录后顺带 digest 落缓存。
- **真链路实测**（里程碑收尾必须）：双击 App → 粘真链 → 转录 → 速览三层（高亮对齐 canonical）→ 进库 → 导出/复制；批量导入真 `notes.json` → 代理下载 → 单条重试。
- 空/失败/加载/键盘流/焦点管理都在；a11y（对比过 AA、focus-visible）；图标字体离线可用；serve 绑 loopback+token、单实例。

## 5. 参考

mockup：`_sandbox/0.6-planning/{desktop-gui-mockup,desktop-layout-variants,icon-compare}.html`
契约/系统：[DESIGN.md](../DESIGN.md)、[SPEC.md](../SPEC.md)、`app/web/routes.py`、`app/cli.py`、`docs/contracts/0.6-digest-json-contract.md`、`app/extract/contracts.py`
复盘：[devlog 2026-06-16](devlog/2026-06-16-0.6-m6-build-and-desktop-gap.md)

## 6. 待决 / 风险

- **digest 落库方式**：转录顺带跑（默认，秒开）vs 按需触发+缓存（省 LLM 钱）。
- **CORS vs Tauri 转发**：前端直 fetch 127.0.0.1（需 CORS + 宽 CSP）vs Rust http plugin 转发（前端不直连，CSP 可严）——连接方式定了一并定 **CSP**（`tauri.conf.json` 现 `csp=null`）。
- **首字延迟 TTFT**：要不要做（需 model.py 加埋点）。
- **Windows 字体选型**：须 SIL OFL（可嵌入+再分发），中英文都好看（候选思源黑体 / HarmonyOS Sans / Inter+思源）。
- 封面缩略图缓存目录命名 + 清理策略；诊断数据 schema；「数据与清理」接口（后做）；批量导出 / 分享（后做）。
- **审定后需更新**：CLAUDE.md（本地 serve 绑定+token 红线、单实例）、PLAN.md（桌面全功能里程碑 + 上面的 spike/新增端点）、DESIGN.md（字体平台化）、`0.6-digest-json-contract.md`（Desktop 接缝从 digest-sidecar 改为 serve + `/api/jobs/{id}/digest`）。
