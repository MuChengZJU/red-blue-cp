---
description: 调用 rbcp CLI 做 B 站/小红书内容转录和调研
allowed-tools: Bash
---

## rbcp 是什么

Red Blue CP（红蓝CP）CLI，把 B 站和小红书的视频/图文内容转成本地 Markdown 知识库。
安装方式：`pip install red-blue-cp`（PyPI）或源码 `uv run rbcp`。

用途：当你需要把某个 B 站视频或小红书笔记的内容变成可检索的文本时，用这个工具。

## 前置条件

- `DASHSCOPE_API_KEY` 必须在环境变量或 `.env` 中配置（百炼 API Key，ASR/VLM/LLM 都靠它）
- 小红书博主全量 / 评论功能需要先 `rbcp login` 扫码登录（存 cookie 到本地）
- B 站公开视频不需要额外认证

## 命令速查

### `rbcp run <url>`

单篇转录，同步阻塞，输出 Markdown 文件路径。最简用法。

```bash
rbcp run "https://www.bilibili.com/video/BV1xxxxx"
rbcp run "https://www.xiaohongshu.com/explore/xxxxx"
```

输出：`Done: ~/transcript/bili/2026-06-03-作者名-标题-BVxxx.md`

### `rbcp list <博主主页URL> [--json]`

列出博主全部笔记清单（不下载内容）。目前仅支持小红书博主。

```bash
rbcp list "https://www.xiaohongshu.com/user/profile/xxxxxx" --json
```

**`--json` 输出结构：**

```jsonc
{
  "user_id": "...",
  "complete": true,           // true=拉全了；false=中途被风控/出错，是半份
  "incomplete_reason": null,  // complete=false 时：risk_control | cookie_expired | network
  "captured": 65,             // 实际抓到的笔记数
  "estimated_total": null,    // 多数情况未知
  "estimate": {
    "image_notes": 40,
    "video_notes": 25,
    "vlm_calls": 40,
    "asr_minutes": 120
  },
  "notes": [
    {
      "note_id": "...",
      "title": "...",
      "type": "image | video",
      "liked_count": 128,
      "xsec_token": "..."     // 拼单篇 URL 用的一次性令牌
    }
  ]
}
```

**关键：`complete` 字段是硬契约。** 看到 `complete: false` 必须停下告知用户，不得当全量继续处理。半份清单的退出码非 0。

### `rbcp fetch <url> [选项]`

抓取单篇笔记或整个博主的全部笔记。

| 选项 | 作用 |
|---|---|
| `--all` | 整博主全量下载（先列清单再逐条抓） |
| `--comments` | 附带抓评论（默认含楼中楼） |
| `--no-sub` | 评论只要一级，不要楼中楼 |
| `--save-media` | 额外保存原始视频/图片到独立目录 |
| `--text-only` | 跳过 VLM/ASR，只取网页正文 |
| `--json` | 输出机器可读 JSON |
| `--yes` | `--all` 时跳过确认（`--json` 模式下必须加） |

**单篇 `--json` 输出：**

```jsonc
// 成功
{"ok": true, "md_path": "~/transcript/xhs/...", "title": "..."}
// 带评论时多出
{"ok": true, "md_path": "...", "title": "...", "comments_path": "...", "comment_count": 42}
// 失败
{"ok": false, "error": "错误描述"}
```

**博主全量 `--all --json --yes` 输出：**

```jsonc
{
  "ok": true,
  "captured": 65,       // 清单总数
  "downloaded": 63,     // 成功数
  "failed": 2,          // 失败数
  "results": [
    {"note_id": "...", "ok": true, "md_path": "...", "title": "..."},
    {"note_id": "...", "ok": false, "error": "..."}
  ]
}
```

### `rbcp login`

弹出浏览器，扫码登录小红书，把 cookie 存到本地。交互式操作，需要人工扫码。

### `rbcp serve`

启动 WebUI（FastAPI + HTMX），默认监听 `0.0.0.0:8000`。

## 典型工作流

### 1. 单篇转录

```bash
rbcp run "https://www.bilibili.com/video/BV1xxxxx"
# 或用 fetch（功能相同，fetch 支持更多选项）
rbcp fetch "https://www.xiaohongshu.com/explore/xxxxx" --json
```

### 2. 博主调研（列清单 → 筛选 → 逐条下载）

Agent 编排博主内容调研的标准流程：

```bash
# 第 1 步：列出博主全部笔记
rbcp list "https://www.xiaohongshu.com/user/profile/xxxxxx" --json > /tmp/notes.json

# 第 2 步：检查 complete 字段
# 如果 complete=false，停下告知用户

# 第 3 步：用 jq 筛选（按点赞/类型/关键词等）
cat /tmp/notes.json | jq '[.notes[] | select(.liked_count > 100)]'

# 第 4 步：逐条 fetch（拼 URL 时用 note_id + xsec_token）
rbcp fetch "https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source=pc_user" --json
```

### 3. 带评论的单篇下载

```bash
rbcp fetch "https://www.xiaohongshu.com/explore/xxxxx" --comments --json
```

### 4. 博主全量下载（不筛选）

```bash
rbcp fetch "https://www.xiaohongshu.com/user/profile/xxxxxx" --all --json --yes
# 带评论
rbcp fetch "https://www.xiaohongshu.com/user/profile/xxxxxx" --all --comments --json --yes
```

## 注意事项

1. **`xsec_token` 一次性、会过期。** `list` 拿到清单后尽快逐条 `fetch`，不要存着过几天再用。
2. **博主全量和评论需要登录态。** 没登录或 cookie 过期会导致 `complete: false`。提示用户跑 `rbcp login`。
3. **不需要手动限频。** rbcp 内部已做温和节奏控制，不要在命令之间加 `sleep`。
4. **半份清单不要当全量用。** `complete: false` 时只拿到了一部分笔记，必须告知用户而非继续处理。
5. **`--json` 模式下 `--all` 必须加 `--yes`。** 否则会返回 `confirmation_required` 错误。
6. **Markdown 输出目录默认 `~/transcript/`。** 按平台分子目录：`bili/` 和 `xhs/`。
7. **失败不会中断批量。** `--all` 模式下单篇失败会跳过继续，最终汇总成功/失败数。
