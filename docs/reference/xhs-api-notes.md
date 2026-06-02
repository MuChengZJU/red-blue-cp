# 小红书接口速查（实测笔记）

> 这是一份**事实速查表**：本项目抓小红书博主笔记和评论时，实测摸清的接口结构、
> 字段含义、风控信号、cookie 性质。给开发者、也给"读不懂代码但想让 AI 讲明白"的人当参考。
> 所有结论来自真实抓取（2026-06），不是看文档猜的。

---

## 一句话背景

小红书没有公开 API。网页版前端调的是内部接口（`edith.xiaohongshu.com`），
请求要**动态签名**（签名算法藏在网页 JS 里，约一季度换一次）。本项目不自己实现签名，
而是用 **pydoll 驱动一个真实 Chrome**，让小红书自己的网页去发这些已签名的请求，
我们在浏览器层**拦截这些请求的返回 JSON**。详见下面「怎么抓」。

---

## 三个接口

| 接口 | 路径（关键词） | 干什么 | 翻页 |
|---|---|---|---|
| 博主笔记清单 | `…/api/sns/web/v1/user_posted` | 列某个博主发的所有笔记 | `cursor` + `has_more` |
| 一级评论 | `…/api/sns/web/v2/comment/page` | 一篇笔记的评论（顶层） | `cursor` + `has_more` |
| 楼中楼回复 | `…/api/sns/web/v2/comment/sub/page` | 某条评论下的回复 | `cursor` + `has_more` + URL 带 `root_comment_id` |

**翻页通用模式**：每页返回里有 `cursor`（下一页游标）和 `has_more`（还有没有下一页）。
`has_more=false` 才算拉到底；中途停下（被风控/出错）拿到的是**半份**，不能当全量。

---

## 怎么抓（实现机制）

用 pydoll 的**原生网络捕获**，不是往页面注入 JS：

1. `enable_network_events()` 打开网络事件监听
2. 打开博主主页 / 笔记页，**滚动**触发前端自己翻页（前端会发上面那些已签名的请求）
3. `get_network_logs(filter="user_posted")` 拿到这些请求的记录（含请求 URL 和 requestId）
4. `get_network_response_body(requestId)` 取出每个请求的返回 JSON

**为什么不往页面注入 JS 拦截器**：试过，抓到 0 条。原因是页面的应用脚本早在我们注入之前
就缓存了原始的 `fetch`/`XMLHttpRequest`，我们后注入的覆盖版被绕过。原生网络捕获在浏览器
内核层抓，不受这个影响，且能直接拿到请求 URL（楼中楼归组要用）。
踩坑详情见 [pydoll 原生捕获复盘](../devlog/2026-06-03-pydoll-native-capture-and-login.md)。

**别用滚动 DOM 读节点**：小红书是虚拟滚动（滚下去上面的节点会被回收销毁），
滚太快还触发风控。抓接口 JSON 才是对的，详见
[博主全量·拦截器经验](../devlog/2026-06-02-xhs-blogger-full-fetch-via-interceptor.md)。

---

## 字段速查

### 博主清单（user_posted）

返回顶层：`{success, code, msg, data}`。`data` 里：

```
data.cursor      下一页游标（末页为 ""）
data.has_more    还有下一页吗
data.notes[]     这一页的笔记
```

每条 `note`：

```
note_id          笔记 ID
xsec_token       访问令牌，拼笔记 URL 用；一次性、会过期，拿到尽快用
type             "normal"（图文）或 "video"（视频）
display_title    标题，可能是空字符串 ""
user.nickname    作者昵称（也有个 nick_name，值一样）
user.user_id     作者 ID
interact_info.liked_count   点赞数
cover.…          封面图 URL
```

**重要坑**：

- **清单里没有"发布时间"**。note 只有上面这些字段，没有 published_at。
  想要发布日期得去抓单篇笔记详情。清单的"按发布倒序"是接口用时间序游标 `cursor` 保证的，不是我们排的。
- **计数字段是字符串**：`liked_count` 是 `"128"` 这种字符串，甚至可能是**空字符串 `""`**（没点赞/隐藏），
  解析时要安全转成数字（空串→0），直接 `int("")` 会崩。

### 评论（comment/page）

`data` 里：`cursor` / `has_more` / `comments[]`。每条评论：

```
id               评论 ID
content          正文（可能含 [表情] 标记）
create_time      发布时间，毫秒级时间戳（如 1780408417000）
like_count       点赞数（字符串）
ip_location      IP 属地（如 "北京"，可能为空）
user_info.nickname / user_info.user_id   评论者
sub_comments[]   内联的前几条楼中楼（不是全部）
sub_comment_count        这条评论一共多少楼中楼（字符串）
sub_comment_has_more     还有没抓全的楼中楼吗
sub_comment_cursor       续拉楼中楼的游标
```

### 楼中楼（comment/sub/page）

结构同上，每条子评论多一个 `target_comment`（它回复的是哪条评论/谁）。
**关键**：这个接口的返回里**不带"它属于哪条顶层评论"**，得从**请求的 URL** 里取
`root_comment_id` 参数才能归组。所以抓的时候必须连请求 URL 一起记，不能只记返回体。

**楼中楼怎么拼完整**：一条顶层评论自带前几条 `sub_comments`（内联）；
如果 `sub_comment_has_more=true`，就用 `comment/sub/page` 接着 `sub_comment_cursor` 续拉，
再按 `root_comment_id` 把续拉的合并回对应顶层评论。

---

## 风控信号（被限了怎么看出来）

- **页面标题/正文出现「安全验证」「验证码」「滑动验证」** → 撞验证墙了，这页不是数据页。
  本项目检测到就停手，报 `risk_control`，绝不把半份当全量。
- **接口返回 `code != 0` 或 `success=false`** → 被限流，同样按风控处理。
- **触发原因**：短时间发太多请求、滚动太猛、同一会话开太多次浏览器。
  实测温和频率（清单 ~14、评论 ~4 请求·分钟⁻¹）不会触发；猛抓会。
- **恢复**：停手冷却（几十分钟到几小时），或换新鲜登录会话。行为级的风控光换 cookie 没用。

---

## cookie 性质

- 抓清单和评论**要登录态**（单篇公开笔记的正文转录不用，那个走普通 HTTP）。
- **`web_session` 游客也有**：未登录时小红书也发这个 cookie。所以**不能用"出现 web_session"
  判断登录成功**（本项目的 `rbcp login` 早期犯过这个错，秒关浏览器，详见
  [复盘](../devlog/2026-06-03-pydoll-native-capture-and-login.md)）。判断登录得靠用户确认或看页面登录态。
- **关键 cookie 是 httpOnly**：`web_session` 等在浏览器里设了 httpOnly，
  网页 JS 的 `document.cookie` 读不到。要导出得从浏览器 DevTools 的 Cookies 面板，
  或让工具自己的浏览器持有（本项目 `rbcp login` 就是这么干）。
- **会过期**：cookie 有有效期，过期要重新登录。

---

## 博主清单的隐藏坑

- **博主自己的笔记编号会乱**：标题里写「第N篇」的系列，博主可能跳号（21、30 缺）或重复（97、130 两条）。
  所以**核对"抓全没"要按内容数，不能按标题里的编号数**。
- 不同时间抓同一博主，`xsec_token` 会变（一次性令牌），note_id 不变。

---

## 相关文档

- [pydoll 原生捕获 + 扫码登录复盘](../devlog/2026-06-03-pydoll-native-capture-and-login.md)（实现踩坑）
- [博主全量·拦截器经验](../devlog/2026-06-02-xhs-blogger-full-fetch-via-interceptor.md)（一次性手动抓的经验）
- [博主全量+评论设计](../devlog/2026-06-02-blogger-full-and-comments-design.md)（产品/工程设计）
- `tests/fixtures/xhs/` —— 脱敏的真实接口 JSON 样本（单测用）
