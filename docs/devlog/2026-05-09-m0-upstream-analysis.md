---
date: 2026-05-09
type: milestone
priority: high
related: [SPEC.md, PLAN.md]
status: active
---

# M0 研读上游 + 云端模型调研

> 研读上游 social-post-extractor-mcp 代码，调研阿里云/火山云 ASR、VLM、OCR 能力，确认"URL 直传云端模型"的可行性。

## 一、B 站内容获取链路

### 1.1 视频基本信息

```
GET https://api.bilibili.com/x/web-interface/view?bvid=BVxxxxxxx
Headers: User-Agent + Referer: https://www.bilibili.com/video/{bvid}
```

返回标题、作者、时长、封面、分 P 列表。其中 `pages[0].cid` 是后续拉字幕和音频的必要参数。

不需要 cookie，不需要登录。

### 1.2 字幕获取

```
GET https://api.bilibili.com/x/player/v2?bvid=BVxxxxxxx&cid=987654
```

返回 `data.subtitle.subtitles[]`，每条含 `subtitle_url`（JSON 格式字幕文件地址）。

字幕 JSON 结构：
```json
{"body": [{"from": 0.5, "to": 2.3, "content": "大家好"}, ...]}
```

把所有 `content` 按顺序拼成纯文本即可。

**判断有无字幕**：`subtitles` 数组为空 → 无字幕，走 ASR。

### 1.3 音频流获取（无字幕时用）

```
GET https://api.bilibili.com/x/player/playurl?bvid=BVxxxxxxx&cid=987654&qn=16&fnval=16
Headers: User-Agent + Referer
```

- `qn=16` = 最低画质（只要音频，不需要高清视频）
- `fnval=16` = 请求 DASH 格式

返回 DASH 结构，优先取 `dash.audio[0].baseUrl`（音频直链），没有则取 `dash.video[0].baseUrl`，最后兜底 `durl[0].url`。

**音频 URL 形态**：`.m4s` 格式直链（不是 m3u8），URL 内含时效 token，有效期几小时。

**防盗链**：带 `Referer: https://www.bilibili.com/video/xxx` 即可，不需要 cookie。

### 1.4 能否直传 ASR？

**能，通过 OSS 流式中转。** 上游已验证的方案：

1. 拿到 `.m4s` 音频 URL（带 Referer）
2. 用 `stream_remote_media_to_dashscope_oss` 流式中转到 DashScope 临时 OSS（带 Referer 下载，不落本地磁盘，1MB 分块流式 POST）
3. 得到 `oss://` 路径，喂给 ASR 模型

DashScope OSS 接受 .m4s 格式。整个过程不需要 ffmpeg，不需要本地下载。

**兜底**：如果 OSS 中转失败（URL 过期、网络问题），回退到本地 ffmpeg 下载转码。

---

## 二、小红书内容获取链路

### 2.1 笔记页面

```
GET https://www.xiaohongshu.com/explore/{note_id}
Headers: Chrome UA
allow_redirects=True（处理 xhslink.com 短链跳转）
```

不需要签名、不需要加密、不需要 `x-s` / `x-t` 参数。
公开笔记不需要 cookie（但风控严格时可能需要）。

### 2.2 数据解析

从 HTML 中正则提取：

```python
window.__INITIAL_STATE__=(.*?)</script>
```

解析成 JSON（注意 JS 里的 `undefined` 要替换为 `null`），取 `note.noteDetailMap` 得到笔记详情。

### 2.3 图片 URL

从 `note.imageList` 中按优先级取：`urlDefault` → `urlPre` → `url`

URL 形态：`https://sns-img-hw.xhscdn.com/xxx.jpg`

**防盗链**：存在但不是 100% 严格。有时不带 Referer 也能访问，有时会 403。

### 2.4 视频 URL

从 `note.video.media.stream` 中按编码格式取：`h264` → `h265` → `av1`，取第一个候选的 `masterUrl`。

URL 形态：`https://sns-video-hw.xhscdn.com/stream/110/258/{hash}_258.mp4`

**是 MP4 直链，不是 m3u8。** 多方验证：
- 上游代码直接 `requests.get(url, stream=True)` 下载二进制，没有 m3u8 解析
- yt-dlp 的小红书 extractor 直接取 URL，不走 `_extract_m3u8_formats`
- V2EX、Apify 等来源确认 `masterUrl` 返回的 `format` 字段为 `"mp4"`，`size` 为实际文件大小（MB 级）
- 网页播放器用 `blob:` URL 是浏览器 MediaSource API 的实现方式，底层传输的仍是 MP4

### 2.5 能否直传？

- **图片 → VLM**：URL 直传（双轨策略：URL 优先 + tempfile 兜底，下载时加 `Referer: https://www.xiaohongshu.com/`，然后 base64 传入）。
- **视频 → ASR**：**能。** masterUrl 是 MP4 直链，走 OSS 流式中转（带 Referer 下载 → 流式上传 DashScope 临时 OSS → ASR），跟 B 站音频同一条路。

---

## 三、ASR 云端服务对比

### 3.1 阿里云百炼 DashScope

| 模型 | 调用方式 | 输入方式 | 时长限制 | 价格 |
|---|---|---|---|---|
| paraformer-v2 | 异步（提交+轮询） | HTTP URL（公网可达） | 12 小时 | 0.288 元/小时 |
| qwen3-asr-flash | 同步 | URL / Base64 / 本地文件 | 5 分钟 | 0.792 元/小时 |
| qwen3-asr-flash-filetrans | 异步（提交+轮询） | HTTP URL（公网可达） | 12 小时 | 0.792 元/小时 |

**关键**：三个模型都接受 HTTP URL，但 URL 必须公网无鉴权可达。B 站/小红书的 URL 因防盗链不满足此条件。

**qwen3-asr-flash** 是唯一支持 Base64/本地文件输入的模型，不需要上传到 OSS。但限制 5 分钟。

**免费额度**：每月 10 小时（永久刷新）。

### 3.2 火山引擎（豆包语音）

| 产品 | 调用方式 | 输入方式 | 时长限制 | 价格 |
|---|---|---|---|---|
| 豆包录音文件识别 2.0 | 异步（提交+轮询） | URL / TOS | 5 小时 | 0.8 元/小时 |
| 大模型标准版 | 异步 | URL | 5 小时 | 2.3 元/小时 |
| 大模型极速版 | **同步（一次返回）** | URL / Base64 | 2 小时 | 4.5 元/小时 |
| 大模型闲时版 | 异步 | URL | 5 小时 | 1.2 元/小时 |

**优势**：标准版直接支持 MP4 格式（不需要 ffmpeg 抽音频）；极速版不需要轮询。

**劣势**：价格是 DashScope 的 3-15 倍；同样不能接受带防盗链的 URL。

**免费额度**：20 小时（半年有效，不刷新）。

### 3.3 ASR 结论

**P0 用 DashScope，不用火山。** 理由：
- 价格最低（0.288 元/小时 vs 火山 0.8-4.5 元/小时）
- 每月 10 小时免费额度够 P0 开发测试
- 上游已验证的 OSS 流式中转方案完美适配 DashScope

**P0 ASR 方案——OSS 流式中转（参考上游已验证实现）**：

上游代码已经实现了完整的"URL 直传 ASR"链路，核心是 `stream_remote_media_to_dashscope_oss`：

```
音频/视频 URL（带 Referer）→ 流式中转到 DashScope 临时 OSS（不落本地磁盘）→ oss:// 路径喂给 ASR
```

这意味着**不需要本地 ffmpeg，不需要下载到磁盘**。DashScope OSS 能接受 .m4s 等格式。

| 场景 | 方案 |
|---|---|
| B 站有字幕 | 直接用字幕文本，不走 ASR |
| B 站无字幕 | 拿到音频 URL（.m4s 直链）→ OSS 流式中转 → ASR（按时长选短/长模型） |
| 小红书视频 | 拿到视频 URL（.mp4 直链）→ OSS 流式中转 → ASR |
| OSS 中转失败（兜底） | 本地下载 → ffmpeg 抽音频 → Base64 喂 qwen3-asr-flash（≤5分钟） |

三种场景的主路径都不需要 ffmpeg。兜底路径在 OSS 中转失败时才走本地 ffmpeg。

### OSS 流式中转的具体含义

不需要自己购买阿里云 OSS。DashScope 提供了一个临时上传入口：

```
1. GET dashscope.aliyuncs.com/api/v1/uploads?action=getPolicy&model=xxx
   → 返回一次性 OSS 上传凭证（AccessKeyId、Signature、Policy、upload_host）

2. 本机同时做两件事（流式，1MB 分块）：
   - 从源站下载媒体：requests.get(音频/视频URL, stream=True, headers={Referer: ...})
   - 往 DashScope OSS 上传：requests.post(upload_host, multipart 流式)
   数据经过本机内存，不落磁盘。

3. 上传完成，得到 oss://upload_dir/filename 路径

4. 把 oss:// 路径喂给 ASR 模型
```

**带宽开销**：数据过本机两次（下载+上传）。B 站音频 128kbps 约 1MB/分钟，10 分钟视频 ≈ 10MB；小红书短视频一般 2-5MB。5MB/s 的宽带几秒传完，不是瓶颈。

---

## 四、VLM / OCR 云端服务

### 4.1 VLM（图片理解）

| 服务商 | 模型 | 接口 | 支持 URL 直传 | 中文 OCR 能力 |
|---|---|---|---|---|
| 百炼 | qwen3-vl-flash | OpenAI 兼容 | 是（公网 URL） | 强 |
| 百炼 | qwen3-vl-plus | OpenAI 兼容 | 是 | 很强 |
| 火山 | doubao-seed-2-0-lite | OpenAI 兼容 | 是 | 一般 |

所有 VLM 都支持两种图片输入：
1. **URL 方式**：`{"type": "image_url", "image_url": {"url": "https://..."}}`
2. **Base64 方式**：`{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}`

VLM 服务端会自己去拉取 URL 图片，**但不能设置 Referer 等自定义 header**。小红书 CDN 图片可能因防盗链失败。

### 4.2 OCR

| 方案 | 说明 | 适用场景 |
|---|---|---|
| 用 VLM 当 OCR | qwen3-vl-flash + OCR prompt | P0 足够，简单 |
| qwen-vl-ocr 专用模型 | 百炼专用 OCR 模型，DashScope 原生接口 | 复杂排版、表格、公式 |
| 火山传统 OCR | CV 方案，非 VLM | 不推荐，能力弱 |

**P0 不需要独立 OCR 服务**。小红书图文用 qwen3-vl-flash 做图片理解（同时包含 OCR），prompt 要求提取图片中的文字和画面内容即可。

### 4.3 VLM 方案

| 场景 | 方案 |
|---|---|
| 小红书图文 | 所有图片并发调 qwen3-vl-flash（URL 优先 + base64 兜底） |
| VLM prompt | "提取图片中所有可见文字，描述画面内容和信息线索，不编造不润色" |

---

## 五、核心结论

### "URL 直传云端模型"可行性

| 内容类型 | URL 形态 | 能否直传 | 方案 |
|---|---|---|---|
| B 站音频 | `.m4s` 直链 | **能** | 带 Referer → OSS 流式中转 → ASR |
| 小红书视频 | `.mp4` 直链 | **能** | 带 Referer → OSS 流式中转 → ASR |
| 小红书图片 | CDN `.jpg` | **能** | URL 直传 VLM（兜底：下载 + base64） |

**核心发现**：三种内容类型都不需要本地 ffmpeg。上游 social-post-extractor-mcp 已经验证了完整的"媒体 URL → DashScope 临时 OSS 流式中转 → ASR/VLM"链路。

### 供应商选择

不需要可切换供应商。P0 锁定阿里云百炼：
- **ASR**：qwen3-asr-flash（短）+ paraformer-v2（长）
- **VLM**：qwen3-vl-flash（OpenAI 兼容接口）
- **LLM 清洗**：qwen-flash（OpenAI 兼容接口）

三种能力走两种接口：
1. **DashScope SDK**：ASR 短音频（`dashscope.MultiModalConversation.call`）
2. **OpenAI 兼容 HTTP**：VLM + LLM 清洗 + ASR 长音频异步提交

### 对 SPEC 的修正

SPEC 里写的"dashscope SDK 三种形态"需要修正：实际上只有短音频 ASR 用 dashscope SDK，VLM 和 LLM 走的是 OpenAI 兼容 HTTP `/chat/completions`。长音频 ASR 走 REST API 异步任务提交。

### 复杂度评估

| 模块 | CC 辅助预估 | 难点 |
|---|---|---|
| B 站字幕/音频获取 | 0.5 天 | API 简单直接 |
| 小红书页面解析 | 0.5 天 | HTML 解析 + undefined 处理 |
| DashScope ASR 集成 | 0.5-1 天 | OSS 上传流程、短/长音频分支 |
| VLM 图片理解 | 0.5 天 | OpenAI 兼容，双轨策略 |
| LLM 文本清洗 | 0.5 天 | OpenAI 兼容，最简单 |

**总计约 2-3 天（CC 辅助），与 PLAN.md 预估一致。自实现完全可行，不退回 fork。**

---

## 六、上游代码架构总结

### 6.1 核心架构（social_extractor.py，2495 行）

```
SocialExtractorService
├── platform_adapters（平台适配器，负责爬取和解析）
│   ├── XiaoHongShuPlatformAdapter  → 抓 HTML + 解析 __INITIAL_STATE__
│   ├── BilibiliPlatformAdapter     → 调 B 站 API（view/player/playurl）
│   └── DouyinPlatformAdapter       → 抓抖音分享页
├── asr_providers（ASR 供应商，负责语音转文字）
│   ├── DashScopeASRProvider        → OSS 流式中转 + SDK/REST 调用
│   ├── OpenAICompatibleASRProvider → 本地下载 + ffmpeg + 上传式 ASR
│   └── VolcEngineASRProvider       → 火山引擎 WebSocket
├── vision_providers（VLM 供应商，负责图片理解）
│   └── OpenAICompatibleProvider    → /chat/completions + image_url
├── cleanup_providers（LLM 清洗供应商）
│   └── OpenAICompatibleProvider    → /chat/completions + text prompt
└── ocr_provider（OCR 兜底）
    └── OpenAICompatibleProvider    → /chat/completions + OCR prompt
```

### 6.2 数据流

```
URL 输入
  → platform_adapter.fetch_post()  → SocialPost 数据对象
  → 视频？
      是：有字幕？
          是：直接用字幕文本
          否：asr_provider.transcribe(post) → 文本
      否（图文）：vision_provider.read_image_text(image_url) × N张 → 文本列表
  → cleanup_provider.cleanup(文本) → 清洗后文本
  → 写入 script.md + info.json
```

### 6.3 值得复用的设计

1. **OSS 流式中转**（`stream_remote_media_to_dashscope_oss`，第 1876-1934 行）：
   - 向 DashScope 申请一次性上传凭证
   - 从源站流式下载（带 Referer）→ 1MB 分块 → 流式 POST 到 OSS
   - 不落本地磁盘，返回 `oss://` 路径
   - B 站 .m4s 和小红书 .mp4 都走这条路

2. **ASR 短/长自动切换**（第 903-917 行）：
   - ≤300 秒：qwen3-asr-flash 实时 ASR（SDK 同步调用）
   - \>300 秒：qwen3-asr-flash-filetrans 异步转写（REST 提交+轮询）
   - 短模型失败自动 fallback 到长模型

3. **VLM 双轨降级**（第 769-792 行）：
   - URL 直传 VLM → 失败后换 OCR prompt 重试 → 再失败标 partial_success 不中断

4. **LLM 清洗降级**（第 794-809 行）：
   - API 失败 → 回退到基于规则的文本清洗（`rule_based_cleanup`）

5. **字幕 URL 补全**：B 站字幕 URL 可能是 `//` 开头（省略 scheme），需要自动补 `https:`

6. **`undefined` → `null` 替换**（第 200 行）：小红书 HTML 里的 JS 对象含 `undefined`，不是合法 JSON，需要正则替换后再 `json.loads`
