// ==UserScript==
// @name         Red Blue CP — 小红书清单导出
// @namespace    https://github.com/MuChengZJU/red-blue-cp
// @version      0.3.1
// @description  在你正在浏览的小红书博主主页，把笔记清单整理导出为 notes.json，配合 Red Blue CP 命令行工具沉淀为本地 Markdown 知识库。只在本地整理与导出，不下载正文、不上传任何数据。
// @author       Red Blue CP
// @match        https://www.xiaohongshu.com/*
// @run-at       document-start
// @grant        none
// @homepageURL  https://github.com/MuChengZJU/red-blue-cp
// @supportURL   https://github.com/MuChengZJU/red-blue-cp/issues
// @updateURL    https://raw.githubusercontent.com/MuChengZJU/red-blue-cp/main/extension/rbcp-xhs.user.js
// @downloadURL  https://raw.githubusercontent.com/MuChengZJU/red-blue-cp/main/extension/rbcp-xhs.user.js
// ==/UserScript==
//
// 与 MV3 扩展（extension/）共用同一套核心逻辑。@grant none 让脚本跑在页面主世界，
// document-start 抢在页面脚本前 hook 网络。主数据源是页面初始状态（零网络最稳），
// 网络 hook 只补翻页。只抓清单，不下载正文、不上传，风险落你自己的会话与 IP。

(function () {
  "use strict";

  const TAG = "[RBCP 清单]";
  const SCHEMA_VERSION = 1; // 必须与 rbcp service/batch.py 的 SUPPORTED_SCHEMA_VERSION 一致
  const HIT = (url) => typeof url === "string" && url.indexOf("user_posted") !== -1;

  const store = new Map(); // note_id -> 贪婪字段
  let completeSeen = false; // 见过 has_more=false 才算完整清单

  function buildUrl(noteId, xsec) {
    const q = xsec
      ? "?xsec_token=" + encodeURIComponent(xsec) + "&xsec_source=pc_user"
      : "";
    return "https://www.xiaohongshu.com/explore/" + noteId + q;
  }

  function pick(n, card) {
    const keys = Array.prototype.slice.call(arguments, 2);
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
    const el =
      document.querySelector(".user-name") ||
      document.querySelector('[class*="userName"]') ||
      document.querySelector(".name");
    return (el && el.textContent && el.textContent.trim()) || "";
  }

  // 字段两种命名都认：网络请求是下划线（note_card/xsec_token），
  // 页面初始状态 __INITIAL_STATE__ 是驼峰（noteCard/xsecToken）。
  function ingest(data, where) {
    let notes = (data && data.data && data.data.notes) || (data && data.notes) || [];
    if (!Array.isArray(notes)) notes = [];
    let added = 0;
    for (const n of notes) {
      const card = n.note_card || n.noteCard;
      const id = pick(n, card, "note_id", "noteId", "id");
      if (!id) continue;
      const xsec = pick(n, card, "xsec_token", "xsecToken") || "";
      const title = pick(card, n, "display_title", "displayTitle", "title") || "";
      const rawType = pick(n, card, "type") || "normal";
      const type = rawType === "video" ? "video" : "normal";
      const interact =
        (card && (card.interact_info || card.interactInfo)) ||
        n.interact_info || n.interactInfo || {};
      const cover = pick(card, n, "cover");
      const coverUrl =
        (cover && (cover.url_default || cover.urlDefault || cover.url)) || undefined;

      if (!store.has(id)) added++;
      const entry = {
        note_id: id,
        title: title,
        type: type,
        xsec_token: xsec,
        url: buildUrl(id, xsec),
      };
      const liked = interact.liked_count !== undefined ? interact.liked_count : interact.likedCount;
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
      console.log(TAG, "✅ 全部抓完，共", store.size, "条。点右下角面板导出。");
      renderPanel();
    } else if (added > 0) {
      renderPanel();
    }
  }

  // 从页面初始状态补抓：小红书把已加载笔记堆在 window.__INITIAL_STATE__.user.notes
  // （Vue ref，真数组在 .value）。这是 app 自己的笔记仓库，不管首屏直出/翻页/换接口都在这里。
  // 笔记少的博主一屏到底不触发翻页请求，只能靠这条路。
  function seedFromInitialState() {
    try {
      const st = window.__INITIAL_STATE__;
      const user = st && st.user;
      if (!user) return 0;
      let n = user.notes;
      if (n && typeof n === "object" && "value" in n) n = n.value;
      if (!Array.isArray(n)) return 0;
      const flat = typeof n.flat === "function" ? n.flat() : n;
      const before = store.size;
      ingest({ notes: flat }, "页面状态");
      return store.size - before;
    } catch (e) {
      return 0;
    }
  }

  function buildEnvelope() {
    seedFromInitialState();
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

  function doDownload() {
    const envelope = buildEnvelope();
    try {
      const blob = new Blob([JSON.stringify(envelope, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = exportFileName(envelope);
      document.body.appendChild(a);
      a.click();
      a.remove();
      toast("已导出 " + envelope.count + " 条" + (envelope.complete ? "" : "（部分）"));
    } catch (e) {
      toast("导出失败：" + String(e));
    }
    return envelope;
  }

  async function doCopy() {
    const envelope = buildEnvelope();
    try {
      await navigator.clipboard.writeText(JSON.stringify(envelope, null, 2));
      toast("已复制 " + envelope.count + " 条到剪贴板" + (envelope.complete ? "" : "（部分）"));
    } catch (e) {
      toast("复制失败，改用导出按钮。" + String(e));
    }
  }

  // 兼容：扩展版的钩子函数名也暴露出来，Console 里仍可手动调
  window.__rbcpDump = doDownload;
  window.__rbcpEnvelope = buildEnvelope;
  window.__rbcpSeed = seedFromInitialState;

  // ── hook fetch（@grant none 跑在主世界，可改页面 window.fetch）──
  const _fetch = window.fetch;
  if (typeof _fetch === "function") {
    window.fetch = function (input) {
      const url = typeof input === "string" ? input : (input && input.url) || "";
      const p = _fetch.apply(this, arguments);
      if (HIT(url)) {
        p.then((r) => r.clone().json()).then((d) => ingest(d, "fetch")).catch(() => {});
      }
      return p;
    };
  }

  // ── hook XHR（改原型，最稳——大博主翻页走这条）──
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

  // ── 页内悬浮面板（替代扩展的 popup）──────────────────────────
  let panelEl = null;
  let toastTimer = null;

  function onUserProfile() {
    return /\/user\/profile\//.test(location.pathname);
  }

  function toast(msg) {
    renderPanel();
    const t = panelEl && panelEl.querySelector(".rbcp-toast");
    if (!t) return;
    t.textContent = msg;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.textContent = ""; }, 4000);
  }

  function renderPanel() {
    if (!onUserProfile()) {
      if (panelEl) { panelEl.remove(); panelEl = null; }
      return;
    }
    if (!panelEl) {
      panelEl = document.createElement("div");
      panelEl.id = "rbcp-panel";
      panelEl.innerHTML =
        '<style>' +
        '#rbcp-panel{position:fixed;right:18px;bottom:18px;z-index:2147483647;' +
        'width:248px;background:#fff;border:1px solid #e5e7eb;border-radius:14px;' +
        'box-shadow:0 8px 28px rgba(0,0,0,.16);font:13px/1.5 -apple-system,system-ui,sans-serif;' +
        'color:#1f2330;overflow:hidden}' +
        '#rbcp-panel .rbcp-hd{display:flex;align-items:center;gap:7px;padding:11px 13px;' +
        'background:linear-gradient(90deg,#e23744,#2f6fed);color:#fff;font-weight:700}' +
        '#rbcp-panel .rbcp-dot{width:9px;height:9px;border-radius:50%;background:#fff;opacity:.9}' +
        '#rbcp-panel .rbcp-bd{padding:12px 13px}' +
        '#rbcp-panel .rbcp-cnt{font-size:22px;font-weight:800}' +
        '#rbcp-panel .rbcp-st{font-size:12px;color:#6b7280;margin:2px 0 10px}' +
        '#rbcp-panel button{width:100%;margin:5px 0 0;padding:8px;border:0;border-radius:9px;' +
        'cursor:pointer;font-weight:600;font-size:13px}' +
        '#rbcp-panel .rbcp-exp{background:#2f6fed;color:#fff}' +
        '#rbcp-panel .rbcp-cp{background:#eef2fb;color:#2f6fed}' +
        '#rbcp-panel .rbcp-toast{font-size:12px;color:#16a34a;margin-top:8px;min-height:16px;overflow-wrap:anywhere}' +
        '#rbcp-panel .rbcp-min{margin-left:auto;cursor:pointer;opacity:.85;font-weight:400}' +
        // 折叠态：整个面板缩成一个小方块（只剩渐变方块 + 圆点），点一下展开
        '#rbcp-panel.rbcp-folded{width:40px;height:40px;border-radius:12px}' +
        '#rbcp-panel.rbcp-folded .rbcp-bd{display:none}' +
        '#rbcp-panel.rbcp-folded .rbcp-hd{width:40px;height:40px;padding:0;' +
        'justify-content:center;cursor:pointer;border-radius:12px}' +
        '#rbcp-panel.rbcp-folded .rbcp-title,#rbcp-panel.rbcp-folded .rbcp-min{display:none}' +
        '#rbcp-panel.rbcp-folded .rbcp-dot{width:12px;height:12px}' +
        '</style>' +
        '<div class="rbcp-hd"><span class="rbcp-dot"></span>' +
        '<span class="rbcp-title">Red Blue CP 清单</span>' +
        '<span class="rbcp-min" title="折叠">—</span></div>' +
        '<div class="rbcp-bd">' +
        '<div class="rbcp-cnt">0</div><div class="rbcp-st"></div>' +
        '<button class="rbcp-exp">导出 notes.json</button>' +
        '<button class="rbcp-cp">复制 JSON</button>' +
        '<div class="rbcp-toast"></div></div>';
      document.body.appendChild(panelEl);
      panelEl.querySelector(".rbcp-exp").addEventListener("click", doDownload);
      panelEl.querySelector(".rbcp-cp").addEventListener("click", doCopy);
      panelEl.querySelector(".rbcp-min").addEventListener("click", (e) => {
        e.stopPropagation();
        panelEl.classList.add("rbcp-folded");
      });
      // 折叠态下点小方块（表头）展开
      panelEl.querySelector(".rbcp-hd").addEventListener("click", () => {
        if (panelEl.classList.contains("rbcp-folded")) panelEl.classList.remove("rbcp-folded");
      });
    }
    const count = store.size;
    panelEl.querySelector(".rbcp-cnt").textContent = count;
    const st = panelEl.querySelector(".rbcp-st");
    const exp = panelEl.querySelector(".rbcp-exp");
    if (count === 0) {
      st.textContent = "向下滑动开始抓取";
      exp.textContent = "导出 notes.json";
    } else if (completeSeen) {
      st.innerHTML = '<span style="color:#16a34a">✓ 已到底</span>';
      exp.textContent = "导出 notes.json";
    } else {
      st.textContent = "笔记多请滑到底；少的可能已是全部（无翻页信号无法确认）";
      exp.textContent = "导出部分";
    }
  }

  // body 可能 document-start 时还没有，等就绪再挂面板
  function whenBody(fn) {
    if (document.body) return fn();
    new MutationObserver((_, obs) => {
      if (document.body) { obs.disconnect(); fn(); }
    }).observe(document.documentElement, { childList: true });
  }

  console.log(TAG, "用户脚本已就绪（油猴版）。打开博主主页右下角出现面板；滚到底更全。");

  // hydration 后补抓一次 + 挂面板
  setTimeout(function () {
    whenBody(function () {
      const got = seedFromInitialState();
      if (got > 0) console.log(TAG, "从页面状态补抓", got, "条，累计", store.size, "条。");
      renderPanel();
    });
  }, 2000);

  // 小红书是单页应用，切博主页时面板跟着出现/消失
  let lastPath = location.pathname;
  setInterval(function () {
    if (location.pathname !== lastPath) {
      lastPath = location.pathname;
      setTimeout(renderPanel, 800);
    }
  }, 1000);
})();
