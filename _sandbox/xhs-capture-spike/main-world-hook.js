// 端到端 spike（累计模式）。验证目标：
//   插件能否在用户登录态里，随滚动接住所有 user_posted 分页，
//   攒出"整个博主的 标题 + 单篇链接 全表"，并确认每条带 xsec_token。
//
// 用法：
//   1. chrome://extensions 重新加载本扩展（改了代码要点「刷新」）。
//   2. 打开博主主页，慢慢滚到底（看到 ✅ 全部抓完 即停）。
//   3. 滚到底会自动打印全表 + 下载 xhs-notes-<N>.json。
//      也可随时手动在 Console 跑 __rbcpDump()。
//
// 不进 app/，验证完整个 _sandbox/xhs-capture-spike/ 可删。

(function () {
  const TAG = "[SPIKE user_posted]";
  const HIT = (url) => typeof url === "string" && url.indexOf("user_posted") !== -1;

  const store = new Map(); // note_id -> {note_id, title, type, xsec_token, url}
  window.__rbcpNotes = store;
  let dumped = false;

  function buildUrl(noteId, xsec) {
    const q = xsec
      ? "?xsec_token=" + encodeURIComponent(xsec) + "&xsec_source=pc_user"
      : "";
    return "https://www.xiaohongshu.com/explore/" + noteId + q;
  }

  function ingest(data, where) {
    let notes = (data && data.data && data.data.notes) || (data && data.notes) || [];
    if (!Array.isArray(notes)) notes = [];
    let added = 0;
    for (const n of notes) {
      const id = n.note_id || n.id || (n.note_card && n.note_card.note_id);
      if (!id) continue;
      const xsec = n.xsec_token || (n.note_card && n.note_card.xsec_token) || "";
      const title =
        n.display_title || n.title || (n.note_card && n.note_card.display_title) || "(无标题)";
      const type = n.type || (n.note_card && n.note_card.type) || "";
      if (!store.has(id)) added++;
      store.set(id, { note_id: id, title, type, xsec_token: xsec, url: buildUrl(id, xsec) });
    }
    const hasMore = data && data.data && data.data.has_more;
    console.log(TAG, where, "本页", notes.length, "新增", added, "累计", store.size, "has_more:", hasMore);
    if (hasMore === false && !dumped) {
      dumped = true;
      console.log(TAG, "✅ 全部抓完，共", store.size, "条。自动导出：");
      window.__rbcpDump();
    }
  }

  window.__rbcpDump = function () {
    const arr = Array.from(store.values());
    console.log(TAG, "==== 全表 共 " + arr.length + " 条（标题 + 链接）====");
    arr.forEach((n, i) => console.log((i + 1) + ". " + n.title + "  →  " + n.url));
    const withXsec = arr.filter((n) => n.xsec_token).length;
    console.log(TAG, "带 xsec_token 的:", withXsec, "/", arr.length, "| 类型分布:", arr.reduce((m, n) => ((m[n.type || "?"] = (m[n.type || "?"] || 0) + 1), m), {}));
    try {
      const blob = new Blob([JSON.stringify(arr, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "xhs-notes-" + arr.length + ".json";
      document.body.appendChild(a);
      a.click();
      a.remove();
      console.log(TAG, "已触发下载 xhs-notes-" + arr.length + ".json");
    } catch (e) {
      console.log(TAG, "下载失败，可手动复制上面的 JSON。", String(e));
    }
    return arr;
  };

  // --- hook fetch ---
  const _fetch = window.fetch;
  if (typeof _fetch === "function") {
    window.fetch = function (input) {
      const url = typeof input === "string" ? input : (input && input.url) || "";
      const p = _fetch.apply(this, arguments);
      if (HIT(url)) {
        p.then((r) => r.clone().json())
          .then((d) => ingest(d, "fetch"))
          .catch(() => {});
      }
      return p;
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
          ingest(JSON.parse(this.responseText), "XHR");
        } catch (e) {}
      });
    }
    return _send.apply(this, arguments);
  };

  console.log(TAG, "hook 已安装（累计模式）。滚到底自动导出，或随时跑 __rbcpDump()。");
})();
