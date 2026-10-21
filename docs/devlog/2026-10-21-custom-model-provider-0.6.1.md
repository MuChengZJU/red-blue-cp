---
date: 2026-10-21
type: decision
priority: high
related: [PLAN.md, SPEC.md, PRD.md, CHANGELOG.md]
status: active
---

# 0.6.1 · 自定义模型服务商 + 迁移千问AI平台

> 一次「不改 Pipeline、只换模型接入层」的小版本：把写死的 DashScope 端点拆成 ASR / VLM / LLM 三套可配端点，默认迁到千问AI平台，并把性价比选型与思考模式开关固化成默认值。

## 背景

项目搁置一段时间后，阿里侧入口已从「百炼 DashScope」迁到「千问AI平台」（`platform.qianwenai.com`）。两件事迫使我们动模型层：

1. 旧的默认 VLM `qwen3-vl-flash` 不在新平台模型列表里；继续用旧默认会直接 404。
2. 新平台同时提供 OpenAI 兼容与 DashScope 原生协议，理论上可以接任意兼容服务商；但代码里 chat/ASR 端点全是硬编码常量，用户无法换模型/换服务商。

用户的需求很明确：**支持自定义模型服务商和模型，先把服务器做好，再看桌面端**。

## 调研结论（2026-10-21 官方文档 + 真机实测）

### 端点

- 新模型（`qwen3.7-flash` / `qwen3.8-flash`）只在 **`cn-beijing.maas.qianwenaiapi.com`** 区域端点可用。
- 全局 `maas.qianwenaiapi.com` 对 `qwen3.8-flash` 返回 `Model not exist`；ASR/老模型在全局端点可用，但统一到 cn-beijing 更省心。
- ASR 仍兼容 DashScope 原生异步协议：`/api/v1/uploads` → `/api/v1/services/audio/asr/transcription` → `/api/v1/tasks/{id}`。
- VLM/LLM 走 OpenAI 兼容 `/compatible-mode/v1/chat/completions`。

### 性价比选型

| 能力 | 默认 | 单价 | 理由 |
|---|---|---|---|
| ASR | `paraformer-v2` | 0.00008 元/秒 = 0.288 元/小时 | 新平台仍支持，且**支持说话人分离**；`qwen3-asr-flash-filetrans` / `fun-asr` 都是 0.792 元/小时 |
| VLM | `qwen3.7-flash` | 0.2 / 0.8 元每百万 token（≤32K） | 比 `qwen3.8-flash`（0.8 / 2.7）便宜约 4 倍；支持图片/视频、1M 上下文、结构化输出；实测中文 OCR 准确 |
| LLM | `qwen3.7-flash` | 同上 | 1M 上下文 + 结构化输出；实测速览 JSON 可锚定 |

ASR 选型有个反直觉点：`qwen3-asr-flash-filetrans` 虽然贵，但**不支持说话人分离**；`paraformer-v2` 反而同时满足「最便宜 + 说话人分离」。长音频（>2h）开说话人分离可能超时，此时才考虑 `fun-asr` 或关分离。

### 思考模式是隐藏成本

`qwen3.7-flash` / `qwen3.8-flash` 默认开启思考模式。实测一句短文本清洗：

- 不关：`output_tokens=1371`，耗时 ~18s
- 关掉（`enable_thinking: false`）：`output_tokens=9~15`，耗时 <1s

也就是说，不显式关闭的话，「更便宜的模型」会因为思考 token 反而更贵、更慢。因此本版把 `RBCP_LLM_THINKING` / `RBCP_VLM_THINKING` 默认设为 `false`，只对千问/百炼端点注入 `enable_thinking`，第三方 OpenAI 兼容服务不会收到不认识的扩展字段。

## 决策

1. **保持单 Provider、参数化端点**，不引入 `OpenAICompatProvider` / 多 Provider 类层级。
   - `app/model_endpoints.py` 解析 ASR/VLM/LLM 三套 `base_url + api_key + model`。
   - `DashscopeProvider`（历史类名保留）改成可接收分能力端点；ASR 走原生协议，VLM/LLM 走 OpenAI 兼容。
2. **默认全部走千问AI平台 cn-beijing**，移除旧「百炼 DashScope」预设，只保留「千问AI平台」+「自定义 OpenAI 兼容」。旧端点仍可手填，只是不再作为一键预设。
3. **VLM 图片双轨**：`auto` 下千问直传 URL；第三方服务商先下载转 base64（带 referer）；服务端取图失败（400/403/404/422）回退一次。这补上了 SPEC 里一直写着、代码却没实现的「URL 优先 + 失败回退」。
4. **配置 API 扩展**：`GET/POST /api/config` 支持分能力字段与 key 打码；新增 `POST /api/config/test`，ASR 只取上传凭证（不计费），VLM/LLM 发 8 token 短请求。
5. **Desktop 设置页重做**：服务商预设、ASR/VLM/LLM 分区、模型候选、图片传法、思考开关、逐项「测试连接（先保存）」。
6. **定价表按阶梯计价**：`qwen3.7/3.5/3.6-flash` 单次请求输入落在哪档、该请求所有 token 都按那档结算；未知模型仍展示用量但不瞎编费用。

## 理由 / 备选

- **为什么不做多 Provider 类层级**：AGENTS 明确反对过度抽象；ASR 与 chat 的差异已经在方法内部按端点分派解决，新增类只会增加注入和测试成本。
- **为什么默认 LLM 也选 `qwen3.7-flash` 而不是 `qwen-plus`**：前者 1M 上下文 + 结构化输出，价格约为后者的 1/4~1/2.5；实测速览 4 highlights / 3 cards / 4 outline、0 diagnostics，质量可接受。质量不够时设置页一键换 `qwen-plus` / `qwen3.8-flash`。
- **为什么保留 `DASHSCOPE_API_KEY`**：新平台官方示例仍用它作环境变量；保持兼容，避免老用户迁移时多一步。
- **为什么 ASR 不接 OpenAI Whisper**：本项目依赖句级时间戳 + 说话人分离 + 长音频异步任务，Whisper 的 OpenAI 兼容接口不满足；留作后续独立课题。

## 影响

| 文件/模块 | 影响 |
|---|---|
| `app/model_endpoints.py` | 新增：端点解析、预设、思考开关、图片传法 |
| `app/extract/model.py` | `DashscopeProvider` 参数化；`enable_thinking` 注入；VLM base64 回退；`probe()` |
| `app/extract/pipeline.py` | `_provider_from_env` 改为按端点构造 |
| `app/web/config_api.py` / `routes.py` | 分能力配置、key 打码、`/api/config/test` |
| `desktop/frontend/screens/settings.js` | 设置页重做 |
| `app/extract/pricing.py` | 新模型 + 阶梯计价 |
| SPEC / PRD / PLAN / README / .env.example / CHANGELOG | 默认配置、模型表、发布信息同步 |

## 验证

- 653 测试全绿；`compileall` / `check-leaks.sh` 通过。
- 真链路：
  - ASR：公开英文音频真实转写成功（`paraformer-v2`，3s，segments=1）。
  - LLM：`qwen3.7-flash` 真实清洗 + `complete_json` 速览 JSON。
  - VLM：中文截图 OCR，`qwen3.7-flash` 与 `qwen3.8-flash` 结果一致；URL 与 base64 两种传法均通过。
  - 冻结 sidecar：起服务 → `/api/config` 返回默认三模型 → ASR/LLM/VLM 三项 `/api/config/test` 全绿。
- 桌面端：`.app` 重打；DMG 在本机沙箱里被 `bundle_dmg.sh` 拦住，改由 GitHub Actions 在 tag 上构建。

## 后续

- 本机旧的 `RBCP_VLM_MODEL=Qwen-flash` 需要删掉，否则会覆盖新默认。
- 第三方服务商的 `response_format=json_object` 兼容性未逐家实测；报错体明确提到 `response_format` 时会去掉重试一次。
- Windows 桌面产物由 CI 构建，但引擎尚未在 Windows 实机跑真链路。
- `app/service/` 弃用 shim 仍按原计划在 0.7 删除，本版不扩大范围。
