# 错误处理 / 日志 / UX 审计（2026-06-05）

> 状态：**Top 5 已补齐（M4b / 0.4.0）**——service 层结构化异常 + 日志 + 打 body、detail 失败分层、run 退出码、平台早校验、token 过期识别均已上线；并额外做了 traceback 脱敏（不泄漏服务器路径）+ DashScope 重试。本文保留作审计依据。markdown.py 模板注入（autoescape）单列为剩余技术债。

## 一、横向问题（跨模块，按严重度）

1. **service 层零 logging**：`extractor / fetcher / model / storage / markdown` 五个核心模块**完全没有 logger**，只有 `discover.py`、`routes.py` 有。失败时唯一痕迹是 WebUI 路径写的 SQLite `log_excerpt`；**CLI 路径失败不落任何文件**，只在终端打一行就没了，事后无法排查。
2. **异常类型不分层**：只有 `discover.py` 有自定义异常（`RiskControlError` / `CookieError`）。`extractor / fetcher / model` 全是裸 `ValueError` / `RuntimeError` / `HTTPError`，上层**无法区分**"链接不支持 / 网络超时 / API 报错 / 风控 / cookie 失效"，只能统一 `except Exception` 转字符串。
3. **`raise_for_status()` 吞 response body**：`fetcher.py`、`model.py` 的 LLM/VLM/上传调用直接 `raise_for_status()`，**违反 CLAUDE.md「调用失败要打印 response body」**。B站 403/风控、DashScope 报错的细节全丢。仅 `model._submit_transcription_task` 一处做对了。
4. **裸异常糊给终端用户**：CLI 的 `Failed: {error}` 和 WebUI detail 页的 `error_message + log_excerpt`（含完整 traceback）都把 Python 异常原文展示给用户，无"该刷 cookie / 该重试 / 链接不支持"之类可操作建议。
5. **无重试机制**：CLAUDE.md 风险表写"ffmpeg/音频直链过期 3 次失败标 failed"，但代码里**没有任何重试逻辑**，单次失败即挂。

## 二、顺带挖出的真 bug

- **CLI `run` 退出码 bug**（`cli.py` 74-80）：失败时 `return` 而非 `raise typer.Exit(1)`，**退出码是 0**，脚本/CI 无法感知失败（`fetch` 已正确，`run` 漏了）。
- **提交时不校验平台**（`routes.py` `create_job`）：非 B站/小红书链接要等任务异步跑到 `detect_platform` 才报错，用户白等一轮。前端已有 `detectPlatform`，后端没同步早校验。
- **markdown.py 模板注入风险**（`markdown.py` 98）：Jinja2 `autoescape=False`，sanitize 去了特殊符号但**未 escape `{` `}`**，CLAUDE.md 风险表提过的"脏标题炸模板"仍有口子。

## 三、Top 5 最该补（subagent 排序）

1. **service 层网络/API 调用补 response body 日志 + 自定义异常**（`fetcher.py` / `model.py`）——排查 #1 黑洞，且违反项目自己的规范。引入 `NetworkError` / `ApiError` 让上层能分类。**最高价值**。
2. **WebUI detail 页失败展示分层 + 重试按钮**（`detail.html` `renderFailed`）——现在整段 traceback 糊给用户；详情页竟没有重试入口（列表卡片有）。默认一句人话，traceback 折叠，加重试。
3. **CLI `run` 退出码 bug + 错误文案**（`cli.py`）——退出码修对 + 裸异常翻成可操作提示。
4. **提交时做平台校验**（`routes.py` `create_job` + 前端）——立即 toast"不支持的链接"，别白等一轮。
5. **discover 兜底不丢细节**（`discover.py` 585）——撞风控/网络错时 `_ = exc` 把真实异常丢了，只留机器码 reason；把 `str(exc)` 落 logger + 把机器码翻人话。

## 四、做得好的部分（符合红线，无需动）

- WebUI `_run_job` 失败持久化（SQLite error_message + log_excerpt，红线 #6）
- 原子写（markdown / comments，先 .tmp 后替换，红线 #7）
- 文件下载走 `job_id` 防路径穿越（红线 #1）
- `discover.py` 自定义异常 + 账号保护频率日志（`_log_rate`）
- `login` 命令的 UX、`fetch --all` 的逐条进度与半份清单拒绝

## 五、与「博主安全批量」功能的关系

新功能的错误 UX（token 过期/代理不通/风控/半份清单）建立在 service 层之上。**横向问题 1-3（service 零日志、异常不分层、吞 body）若不先补，新功能的错误提醒也只能拿到裸异常字符串**，做不出"可操作建议"。建议：博主批量功能动工前，至少先补 Top 5 的 #1（service 异常分层 + body 日志），其余可并行或排期。
