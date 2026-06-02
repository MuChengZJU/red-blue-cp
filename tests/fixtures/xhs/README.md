# 小红书接口 fixture（脱敏）

这些 JSON 是 `parse_user_posted` / `parse_comments` 单测的输入。

## 来源与脱敏

结构（字段名、嵌套层级、类型）来自真实接口的实测捕获（2026-06-02，pydoll/XHR 拦截器），
**所有值都已脱敏**：note_id / user_id / xsec_token / 昵称 / 头像 / 封面 URL / 正文全部替换为假数据。
不含任何真实用户数据，可安全提交到开源仓库。

捕获方法见 [docs/devlog/2026-06-02-xhs-blogger-full-fetch-via-interceptor.md]。

## 文件清单

| 文件 | 模拟接口 | 测什么 |
|---|---|---|
| `user_posted_page1.json` | `GET /api/sns/web/v1/user_posted` | 中间页：`has_more=true` + `cursor` 非空；3 条 note（2 图文 + 1 视频；第 3 条 `display_title` 为空，测"标题空→用 note_id 当文件名"） |
| `user_posted_last.json` | 同上 | 末页：`has_more=false` + `cursor=""`（测翻页终止） |
| `comment_page.json` | `GET /api/sns/web/v2/comment/page` | 一级评论：2 条。c1 无楼中楼；c2 `sub_comment_count=3`、内联 `sub_comments` 1 条、`sub_comment_has_more=true`（测"需续拉"判定） |
| `comment_sub_page.json` | `GET /api/sns/web/v2/comment/sub/page` | c2 的剩余 2 条楼中楼，`has_more=false`（测合并：内联 1 + 续拉 2 = 声明的 3） |

## Schema 关键事实（实测，非文档推断）

- **`user_posted` 的 note 没有发布时间字段**。note 只有 `note_id / xsec_token / type / display_title / user / interact_info / cover`。
  清单接口拿不到 `published_at`，只能靠 `cursor`（时间序游标）保证"按发布倒序"。SPEC §4.3 的 note 不再声明 `published_at`。
- `type` 取值：`normal`（图文）/ `video`（视频）。
- 计数字段是**字符串**：`liked_count` / `like_count` / `sub_comment_count` 都是 `"128"` 这种字符串，解析时要转 int。
- `create_time` 是**毫秒级 epoch 整数**（如 `1780408417000`）。
- 一级评论自带内联 `sub_comments[]`（前几条），配 `sub_comment_count` / `sub_comment_has_more` / `sub_comment_cursor`；
  楼中楼超出内联部分用 `comment/sub/page` 接 `sub_comment_cursor` 续拉。
- 子评论（含内联的）都带 `target_comment`，指向它回复的那条（父评论 or 另一条子评论）。
- `user` 同时有 `nick_name` 和 `nickname` 两个键（值相同）；评论里的用户对象用 `user_info`，键是 `nickname`。
