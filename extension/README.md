# 小红书清单抓取插件（Red Blue CP）

在你**登录态**的小红书博主主页，随滚动接住 `user_posted` 分页，攒出整个博主的清单，导出 `notes.json` 交给 `rbcp batch` 走代理批量下载。

**职责切分**：插件只在浏览器真实环境里**抓清单**（有风控的部分最安全）；下载+转录交给 `rbcp`（走代理护 IP）。插件**不下载、不上传、不联网到本地服务**——只读页面已发出的接口响应，风险落你自己的会话与 IP。

## 装

1. Chrome/Edge 打开 `chrome://extensions`，右上角开「开发者模式」。
2. 「加载已解压的扩展程序」，选这个 `extension/` 目录。

## 用

1. 打开任意小红书**博主主页**（你已登录的状态）。
2. **手动慢慢滚到底**。慢滚是纪律——触发风控的是滚动渲染轰炸，不是抓取本身。别用已被风控盯上的号。
3. 滚到底（接口 `has_more=false`）会**自动导出** `xhs-{user_id}-{YYYYMMDD}-{count}notes.json`。
   - 也可随时按 F12 在 Console 跑 `__rbcpDump()` 手动导出。
   - 没滚到底就导出 = 半份清单（`complete:false`），`rbcp batch` 会拒绝当全量，确要下加 `--allow-partial`。
4. 把导出的 `notes.json` 交给 rbcp：

   ```bash
   rbcp batch xhs-xxx-notes.json --proxy http://127.0.0.1:7897
   ```

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

`schema_version` 必须与 rbcp 端 `SUPPORTED_SCHEMA_VERSION` 一致（当前 `1`）。

## 残余风险（诚实记录）

换详情**不带 cookie**但带 `xsec_token`，token 是抓列表时带登录态生成的。理论上平台**可能**关联「这批 token 由哪个账号生成」，且「国内住宅生成 + 海外代理使用」的环境差异本身是可疑信号。实测未显现（海外 IP、无 cookie、慢速全过），但风险在此明示。`xsec_token` 一次性、会过期，抓完尽快交给 rbcp，别隔几天。

## 阶段

阶段 1（当前）：只导出 JSON，无 popup UI。
阶段 2：popup 面板（已抓 N 条/导出/一键发送/自动滚开关）、一键转发本地 `rbcp serve`、温和自动滚。
