// Red Blue CP 小红书清单抓取（MV3 主世界 content script）。
//
// 机制（spike 已实测：某博主 326/326 带 token，慢滚零验证码）：
//   在页面自己发 fetch/XHR 之前 hook 住，接住博主主页翻页的 user_posted 分页响应，
//   按 note_id 累计去重，滚到底（has_more=false）自动导出 notes.json 信封。
//
// 用法：
//   1. chrome://extensions 开开发者模式 → 加载已解压的扩展程序 → 选 extension/ 目录。
//   2. 打开小红书博主主页（你已登录），手动慢慢滚到底（最安全；触发风控的是滚动轰炸，不是抓取）。
//   3. 滚到底自动导出 xhs-{user_id}-{YYYYMMDD}-{count}notes.json。也可随时在 Console 跑 __rbcpDump()。
//   4. 把 notes.json 交给 `rbcp batch notes.json --proxy ...` 走代理批量下。
//
// 阶段 1 只导出 JSON（无 popup UI）。只抓清单，不下载、不上传。

(function () {
  "use strict";

  const TAG = "[RBCP 清单]";
  const SCHEMA_VERSION = 1; // 必须与 rbcp service/batch.py 的 SUPPORTED_SCHEMA_VERSION 一致
  const HIT = (url) => typeof url === "string" && url.indexOf("user_posted") !== -1;

  const store = new Map(); // note_id -> 贪婪字段
  window.__rbcpNotes = store;
  let completeSeen = false; // 见过 has_more=false 才算完整清单
  let dumped = false;

  function buildUrl(noteId, xsec) {
    const q = xsec
      ? "?xsec_token=" + encodeURIComponent(xsec) + "&xsec_source=pc_user"
      : "";
    return "https://www.xiaohongshu.com/explore/" + noteId + q;
  }

  function pick(n, card, ...keys) {
    for (const obj of [n, card]) {
      if (!obj) continue;
      for (const k of keys) {
        if (obj[k] !== undefined && obj[k] !== null) return obj[k];
      }
    }
    return undefined;
  }

  function detectUserId() {
    const m = location.pathname.match(/\/user\/profile\/([0-9a-zA-Z]+)/);
    return m ? m[1] : "";
  }

  function detectUserName() {
    // 博主主页 DOM 里的昵称；取不到不阻断导出
    const el =
      document.querySelector(".user-name") ||
      document.querySelector('[class*="userName"]') ||
      document.querySelector(".name");
    return (el && el.textContent && el.textContent.trim()) || "";
  }

  function ingest(data, where) {
    let notes = (data && data.data && data.data.notes) || (data && data.notes) || [];
    if (!Array.isArray(notes)) notes = [];
    let added = 0;
    for (const n of notes) {
      const card = n.note_card;
      const id = pick(n, card, "note_id", "id");
      if (!id) continue;
      const xsec = pick(n, card, "xsec_token") || "";
      // title 取不到留空字符串，不用「(无标题)」占位，避免干扰下游
      const title = pick(n, card, "display_title", "title") || "";
      const rawType = pick(n, card, "type") || "normal";
      const type = rawType === "video" ? "video" : "normal";
      const interact = (card && card.interact_info) || n.interact_info || {};
      const cover = pick(card, n, "cover");
      const coverUrl = (cover && (cover.url_default || cover.url)) || undefined;

      if (!store.has(id)) added++;
      const entry = {
        note_id: id,
        title: title,
        type: type,
        xsec_token: xsec,
        url: buildUrl(id, xsec),
      };
      const liked = interact.liked_count;
      if (liked !== undefined && liked !== null) entry.liked_count = liked;
      if (coverUrl) entry.cover = coverUrl;
      const sticky = pick(n, card, "sticky");
      if (sticky !== undefined) entry.sticky = !!sticky;
      store.set(id, entry);
    }
    const hasMore = data && data.data && data.data.has_more;
    console.log(TAG, where, "本页", notes.length, "新增", added, "累计", store.size, "has_more:", hasMore);
    if (hasMore === false) {
      completeSeen = true;
      if (!dumped) {
        dumped = true;
        console.log(TAG, "✅ 全部抓完，共", store.size, "条。自动导出：");
        window.__rbcpDump();
      }
    }
  }

  function buildEnvelope() {
    const notes = Array.from(store.values());
    return {
      schema_version: SCHEMA_VERSION,
      source: "xhs_user_posted",
      user_id: detectUserId(),
      user_name: detectUserName(),
      captured_at: new Date().toISOString(),
      complete: completeSeen,
      count: notes.length,
      notes: notes,
    };
  }

  function exportFileName(envelope) {
    const d = new Date();
    const ymd =
      d.getFullYear().toString() +
      String(d.getMonth() + 1).padStart(2, "0") +
      String(d.getDate()).padStart(2, "0");
    const uid = envelope.user_id || "unknown";
    return "xhs-" + uid + "-" + ymd + "-" + envelope.count + "notes.json";
  }

  window.__rbcpDump = function () {
    const envelope = buildEnvelope();
    const withXsec = envelope.notes.filter((n) => n.xsec_token).length;
    console.log(
      TAG,
      "==== 共 " + envelope.count + " 条 | 带 token " + withXsec + "/" + envelope.count +
      " | complete=" + envelope.complete + " ===="
    );
    if (!envelope.complete) {
      console.warn(TAG, "⚠ 还没滚到底（has_more 未见 false），这是半份清单。rbcp 会拒绝当全量，确要下加 --allow-partial。");
    }
    try {
      const blob = new Blob([JSON.stringify(envelope, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = exportFileName(envelope);
      document.body.appendChild(a);
      a.click();
      a.remove();
      console.log(TAG, "已触发下载", a.download);
    } catch (e) {
      console.log(TAG, "下载失败，可在 Console 复制 window.__rbcpEnvelope()。", String(e));
    }
    return envelope;
  };

  // 暴露一个取信封的函数，导出失败时可手动复制
  window.__rbcpEnvelope = buildEnvelope;

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
    this.__rbcpUrl = url;
    return _open.apply(this, arguments);
  };
  const _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function () {
    if (HIT(this.__rbcpUrl)) {
      this.addEventListener("load", () => {
        try {
          ingest(JSON.parse(this.responseText), "XHR");
        } catch (e) {}
      });
    }
    return _send.apply(this, arguments);
  };

  console.log(TAG, "hook 已安装。在博主主页慢滚到底自动导出，或随时跑 __rbcpDump()。");
})();
