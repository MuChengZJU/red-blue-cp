---
date: 2026-06-03
type: decision
priority: high
related: [PRD.md, PLAN.md, LOG.md]
status: active
---

# 产品形态定案（PLAN Q1）与 V3 范围

> 形态不收敛到单一入口：现在做"自部署 WebUI 手机可达 + 上 PyPI"，GUI 桌面客户端门控待触发，靠"service 核心保持前端无关"给它留门。

## 背景

PLAN 开放问题 Q1 一直挂着没拍：产品形态在"自部署服务端 / 打包客户端(Tauri) / 纯 CLI / Python 包"之间没定。
现状是 WebUI + CLI 双入口、README 按"人 / 开发者 / Agent"三受众分区——看着整齐，实则是还没取舍。

触发讨论的真实处境（office-hours 诊断逼出来的）：

- **零真实用户**：刚开源，除作者外没人装过跑过。
- **作者本人也不常用**：因为现状 WebUI 是 localhost 自部署，手机够不着，而高频场景恰恰是手机刷到内容顺手存。

## 决策

**形态不收敛到单一入口，而是明确"投入哪条、明确不做哪条"：**

### 现在做（服务真实存在的用户：作者 + 技术早期采用者 + Agent，成本极低）

1. **自部署 WebUI 做成手机可远程访问**。远程访问首选 **Tailscale 等私有网**（零公网暴露、不需先做鉴权）；FRP 公网域名等加了鉴权再上。
2. **正式发 PyPI**。发布用 `uv build` + `uv publish`；用户端 `pipx install red-blue-cp` 或 `uv tool install red-blue-cp` 随意（同一个 PyPI 包，两种装法都行）。

### 门控待触发（不是否决，是有明确扳机的待办）

3. **Tauri/Electron 桌面 GUI 客户端**，放 P2。触发条件**两条缺一不做**：
   - (a) 有真实非技术倾向用户开口要；
   - (b) API Key 上手路径想清楚。
   GUI 框架选型（Tauri vs 其他）+ WebUI/GUI 视觉设计，一并放到这个阶段再细想。

### 架构纪律（现在就要守，给 GUI 留门）

4. `service/` 核心**保持前端无关**：不 import fastapi/typer，不放"模块加载即执行"的副作用，保持是任何前端都能调的纯函数/类。
   现状 `app/service/`(核心) + `app/web/`(Server 前端) + `app/cli.py`(CLI 前端) 已经是"核心 + 多薄壳"的正确分层，CLI 和 Server 已分开。GUI 以后就是第三层薄壳。

## 理由

- **核心判断**：CLI / WebUI / Python 包三者成本低且已基本建好；真正贵的只有 Tauri 这条——打包 + Mac 公证（99 美元/年开发者号）+ Windows 签名 + ffmpeg 原生依赖跨平台打包 + 自动更新 + 两套 CI。零需求阶段不为想象中的用户提前烧这个季度。
- **GUI 不是"加个启动 flag"**：CLI 和 Server 是同一个 PyPI 包的两个入口（`rbcp serve` / `rbcp run`），用户已能自选；但 Tauri 桌面 app **不能 pipx 装**，是独立的构建/签名/分发管线，属于**第二条分发线**。所以"用户自己选 server/cli/gui"里，前两者是一个包的事，gui 是另一码事。
- **受众再定位（修正早期判断）**：早期担心"非技术用户卡在配 API Key"会让 GUI 白做。但本工具是**知识调研工具**，真有"把 B站/小红书 转知识库"需求的人偏知识工作者，百炼开放已久、多半已有 key；没 key 的人本就不是目标用户。所以 GUI 的受众是"有 key、只是不想折腾命令行/网络部署的人"——这是真实群体，GUI 对他们有价值。结论不变（现在不做），但理由从"墙太高"修正为"时机未到 + 零需求"。
- **不做"模式调度层"**：别为"将来三模式"现在抽一个 launcher，违反 CLAUDE.md 反过度抽象红线，也没必要。

## 绕不开的安全前提

WebUI 现状 `serve` 绑 `0.0.0.0:8000` 且**全程无鉴权**（`app/web/routes.py` 所有路由裸奔，`Depends` 只用于注入 storage/pipeline，非鉴权）。
- 私有网（Tailscale）自用：安全。
- **任何公网暴露（FRP/域名）前必须先加一层最简鉴权**（token / Basic Auth），否则等于把百炼 API Key 钱包和整个知识库挂公网，任何人扫到 URL 就能烧你的钱、读你的库、用你的小红书 cookie。

## 部署拓扑（作者自用，先跑通再写进使用文档）

```
Windows 主机（装 Tailscale）
   └─ WSL2（networkingMode=mirrored，已开）
        └─ rbcp serve  (0.0.0.0:8000)
手机 / Mac（装 Tailscale）── 经 tailnet IP:8000 ── 访问 WebUI（看/复制文本）
```

- **WSL2 mirrored networking**（Win11 22H2+，`.wslconfig` 里 `networkingMode=mirrored`）：WSL 服务直接出现在 Windows 各网络接口（含 Tailscale IP），不用 `netsh portproxy`。作者已开。
- **Mac 要"直接操作 md 文件夹"**（非 WebUI，是文件系统级，给 Obsidian 类工具用）：
  - 复用作者已有的**群晖 NAS + Synology Drive**。
  - 坑：Win11 读 WSL 目录走 `\\wsl.localhost\` 网络 UNC 路径，同步客户端对 UNC 实时监控不稳。
  - 解法：把 `RBCP_OUTPUT_DIR` 指到 **Windows 本地盘**（如 `/mnt/c/Users/.../transcript`），Synology Drive 盯本地真目录同步到 NAS，Mac 端 Synology Drive 拉下来。代价：WSL 写 `/mnt/c` 略慢，但 md 小文本可忽略。

## 影响

| 文件/模块 | 影响 |
|---|---|
| PRD.md | 第一层·形态：补形态收敛与分发定位、GUI 门控 P2、service 核心前端无关纪律 |
| PLAN.md | Q1 标"已定"并写入决策；新增 Q2「知识库文件浏览与管理」开放问题 |
| 代码 | 守 `service/` 前端无关；V3 加 PyPI 发布配置；WebUI 远程可达；无 P0/P1 功能回退 |

## V3 范围（本次确认）

1. 上架 PyPI（`uv build`/`uv publish`；用户 `pipx`/`uv tool` 装）
2. 打通 WSL 自部署（mirrored 已开 + Tailscale 手机/Mac 访问 + 输出目录走 `/mnt/c` 给群晖同步到 Mac）
3. GUI / 知识库浏览页 = 后期，开发时守住 `service/` 干净即可

## 后续 / 复盘（可选）

- WebUI 优化由并行 Claude Code session 在独立分支推进（碰 `app/web/`），与本条形态/部署流（碰 docs + `pyproject.toml`）文件不重叠，唯一交叠是 LOG.md 索引行。
- Q2（Mac/手机方便浏览管理知识库 md）待 Q1 自部署跑起来后再定具体形态（WebUI 知识库页 vs 现成 Markdown 浏览器）。
