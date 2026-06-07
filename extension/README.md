# Red Blue CP — 小红书清单导出（浏览器插件）

把你**正在浏览**的小红书博主主页的笔记清单，整理导出为 `notes.json`，再交给 Red Blue CP 命令行工具（`rbcp batch`）沉淀为本地 Markdown 知识库。

**职责切分**：插件只在你浏览器的真实登录态里**整理清单**；下载正文/转录交给 `rbcp`（走代理护 IP）。插件**不下载正文、不上传任何数据、不联网到本地服务**——只读页面自己已经加载的数据，整理后让你导出。一切落在你自己的会话与 IP。

两个等价实现，挑一个装：

| 装法 | 适合 | 自动更新 |
|---|---|---|
| **油猴脚本**（推荐） | 普通用户，省事 | ✅ 自动 |
| MV3 扩展（加载已解压） | 开发/调试，或不想装油猴 | ❌ 手动重载 |

两者共用同一核心逻辑、同一版本号；更新记录见 [CHANGELOG.md](CHANGELOG.md)。

---

## 装法 A：油猴脚本（推荐）

1. 浏览器装 [Tampermonkey](https://www.tampermonkey.net/)（Chrome/Edge/Firefox 应用商店搜「Tampermonkey」，它本身可信、已上架）。
2. 点这个链接安装脚本，Tampermonkey 会弹安装确认：
   **https://raw.githubusercontent.com/MuChengZJU/red-blue-cp/main/extension/rbcp-xhs.user.js**
3. 装完即用。以后我们推修复，Tampermonkey 会**自动拉新版**（脚本头写了 `@updateURL`），你不用管。

## 装法 B：MV3 扩展（加载已解压）

1. Chrome/Edge 打开 `chrome://extensions`，右上角开「开发者模式」。
2. 点「加载已解压的扩展程序」，选本仓库的 `extension/` 目录。
3. 装一次就持久存在（浏览器重启也在）。代码更新后需回到这页点「刷新」。

---

## 用（两种装法都一样）

1. 打开任意小红书**博主主页**（你已登录的状态）。
2. 右下角出现「Red Blue CP 清单」悬浮面板（油猴版）/ 点浏览器工具栏的插件图标（扩展版）。
3. **笔记多的博主**：手动慢慢往下滑到底。慢滚是纪律——触发风控的是滚动渲染轰炸，不是整理本身。面板显示「✓ 已到底」即抓全。
4. **笔记少的博主**：第一屏就是全部，不用滚，面板直接显示条数（会标「部分」，因为没有翻页信号无法自动确认是否到底，但数量是对的）。
5. 点「导出 notes.json」下载，或「复制 JSON」到剪贴板。
6. 交给 rbcp：

   ```bash
   rbcp batch xhs-xxx-notes.json --proxy http://127.0.0.1:7897
   ```

   或在 WebUI 的「批量」标签上传/粘贴。若面板显示「部分」，导入时勾「允许半份清单」（或 CLI 加 `--allow-partial`）。

> Console 兜底：按 F12，跑 `__rbcpDump()` 手动导出、`__rbcpEnvelope()` 取完整对象。

---

## 导出格式（与 rbcp `service/batch.py` 的契约）

```json
{
  "schema_version": 1,
  "source": "xhs_user_posted",
  "user_id": "...", "user_name": "...",
  "captured_at": "ISO8601",
  "complete": true,
  "count": 326,
  "notes": [
    { "note_id": "...", "title": "...", "type": "normal|video",
      "xsec_token": "...", "url": "https://www.xiaohongshu.com/explore/{id}?xsec_token=...",
      "liked_count": 158, "cover": "...", "sticky": false }
  ]
}
```

`schema_version` 必须与 rbcp 端 `SUPPORTED_SCHEMA_VERSION` 一致（当前 `1`）。**这是插件与主程序之间唯一需要同步的东西**——版本号各走各的，格式版本变了才一起 bump。

---

## 常见问题

**Q：控制台一堆红色 Error，是插件坏了吗？**
不是。那些是小红书自己页面（`apm` / `Hydration` / `vendor-*`）、你装的其他插件（如 Chat-Memo）、以及小红书反爬探测（`chrome-extension://invalid/`）的输出。属于我们的只有 `[RBCP 清单]` 开头的行。

**Q：面板显示「部分」，是没抓全吗？**
两种情况都显示「部分」：① 笔记多、你还没滚到底（确实是部分，继续滚）；② 笔记少、首屏即全部（数量是对的，只是没有翻页信号，插件无法自动确认到底）。笔记少时「部分」可忽略。

**Q：会被风控吗？**
整理清单这步几乎零风险——主数据来自页面已加载的内存数据，读它**不发任何网络请求**。真正有风控风险的是 ① 滚动太快（慢滚即可）② 下载阶段（交给 `rbcp` 走代理 + 限流）。

**Q：为什么不上架商店？**
抓取类扩展在公开商店有被审核拒/事后下架的风险。油猴脚本经 `@updateURL` 自动更新，已能解决「每次手动加载」的麻烦，且零商店风险。

## 残余风险（诚实记录）

换详情**不带 cookie** 但带 `xsec_token`，token 是整理清单时由你的登录态生成的。理论上平台**可能**关联「这批 token 由哪个账号生成」，且「国内住宅生成 + 海外代理使用」的环境差异本身是可疑信号。实测未显现（海外 IP、无 cookie、慢速全过），但风险在此明示。`xsec_token` 一次性、会过期，导出后尽快交给 rbcp，别隔几天。
