// 一次性 spike。验证目标只有一个：
//   MV3 的 world:"MAIN" + run_at:"document_start" 脚本，
//   能否赶在小红书页面自己的 JS 之前，包住 fetch / XMLHttpRequest，
//   抓到博主主页翻页时发出的 user_posted 响应。
//
// 装载后：打开任意博主主页，手动向下滚动几屏，看 DevTools Console。
//   - 出现 [SPIKE] ... 命中 ... 笔记数: N  → 锁住，插件路线可行，可 fan out。
//   - 滚动有新内容加载但 Console 没有任何 [SPIKE] 命中行 → hook 没拦到，
//     说明小红书改了传输方式或防了 monkey-patch → 退回 pydoll。
//
// 这段代码不进 app/，验证完整个 _sandbox/xhs-capture-spike/ 可删。

(function () {
  const TAG = "[SPIKE user_posted]";
  const HIT = (url) => typeof url === "string" && url.indexOf("user_posted") !== -1;

  // 不假设 JSON 结构：先尝试常见路径，找不到就把顶层 key 打出来，
  // 方便顺手把"返回里笔记列表到底在哪个字段"这个契约也锁了。
  function summarize(data) {
    try {
      const notes =
        (data && data.data && data.data.notes) ||
        (data && data.notes) ||
        null;
      if (Array.isArray(notes)) {
        const sample = notes.slice(0, 2).map((n) => ({
          note_id: n.note_id || n.id,
          title: n.display_title || n.title,
          has_xsec: !!(n.xsec_token || (n.note_card && n.note_card.xsec_token)),
        }));
        return { 笔记数: notes.length, has_more: data && data.data && data.data.has_more, 样本: sample };
      }
      return { 笔记字段未命中: true, 顶层key: Object.keys(data || {}), data层key: Object.keys((data && data.data) || {}) };
    } catch (e) {
      return { 解析异常: String(e) };
    }
  }

  // --- hook fetch ---
  const _fetch = window.fetch;
  if (typeof _fetch === "function") {
    window.fetch = function (input, init) {
      const url = typeof input === "string" ? input : (input && input.url) || "";
      const promise = _fetch.apply(this, arguments);
      if (HIT(url)) {
        promise
          .then((resp) => resp.clone().json())
          .then((data) => console.log(TAG, "fetch 命中", url, summarize(data)))
          .catch(() => console.log(TAG, "fetch 命中但读取失败", url));
      }
      return promise;
    };
  }

  // --- hook XHR ---
  const _open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__spikeUrl = url;
    return _open.apply(this, arguments);
  };
  const _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function () {
    if (HIT(this.__spikeUrl)) {
      this.addEventListener("load", () => {
        try {
          console.log(TAG, "XHR 命中", this.__spikeUrl, summarize(JSON.parse(this.responseText)));
        } catch (e) {
          console.log(TAG, "XHR 命中但 JSON 解析失败", this.__spikeUrl);
        }
      });
    }
    return _send.apply(this, arguments);
  };

  console.log(TAG, "hook 已安装 @document_start（fetch + XHR）。打开博主主页并向下滚动。");
})();
