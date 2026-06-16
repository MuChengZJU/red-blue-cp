// 三形态渲染核心（M6d）。纯函数 + DOM，无框架。
// 契约见 docs/contracts/0.6-digest-json-contract.md。
//
// ⚠️ 坐标系：span_start/span_end/char_* 都是 Python codepoint 下标，不是 JS UTF-16。
// 高亮切片必须按 codepoint（Array.from + slice），否则 emoji/罕用字会错位。

// ---- codepoint 工具 ----

/** 按 codepoint 切片 [start, end)（左闭右开）。绝不要用 string.slice。 */
export function cpSlice(text, start, end) {
  const cps = Array.from(text); // 按 codepoint 拆（emoji 算 1 个）
  return cps.slice(start, end).join("");
}

/** canonical text 的 codepoint 总数。 */
export function cpLength(text) {
  return Array.from(text).length;
}

function fmtTime(seconds) {
  if (seconds == null) return "";
  const s = Math.floor(seconds % 60);
  const m = Math.floor(seconds / 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

// ---- ① 全文 + 重点高亮（可"只看高亮"） ----

/**
 * 把 canonical text 渲染成一串 <span>，重点区间包成可点击高亮。
 * 按 codepoint 走，区间外是普通文本，区间内带 .hl（weight → 透明度档）。
 * @returns {HTMLElement}
 */
export function renderFullText(canonicalText, highlights) {
  const cps = Array.from(canonicalText);
  const total = cps.length;

  // 收集区间，按 span_start 排序；裁剪越界（防脏数据）。
  const spans = highlights
    .map((h) => ({
      start: Math.max(0, Math.min(h.span_start, total)),
      end: Math.max(0, Math.min(h.span_end, total)),
      weight: h.weight,
      seconds: h.source ? h.source.seconds : null,
    }))
    .filter((s) => s.end > s.start)
    .sort((a, b) => a.start - b.start);

  const container = document.createElement("div");
  container.className = "fulltext";

  let cursor = 0;
  let hlIndex = 0;
  for (const sp of spans) {
    if (sp.start < cursor) continue; // 跳过重叠（简单策略：先到先得）
    if (sp.start > cursor) {
      container.appendChild(plainPiece(cps.slice(cursor, sp.start).join("")));
    }
    const mark = document.createElement("span");
    mark.className = "hl";
    mark.dataset.charStart = String(sp.start);
    mark.dataset.weight = String(sp.weight);
    mark.id = `hl-anchor-${hlIndex++}`;
    // weight → 高亮强度（0-1 映射到背景 alpha）
    mark.style.setProperty("--hl-alpha", String(0.25 + 0.55 * (sp.weight ?? 0.5)));
    mark.textContent = cps.slice(sp.start, sp.end).join("");
    if (sp.seconds != null) {
      const t = document.createElement("sup");
      t.className = "ts";
      t.textContent = ` ${fmtTime(sp.seconds)}`;
      mark.appendChild(t);
    }
    container.appendChild(mark);
    cursor = sp.end;
  }
  if (cursor < total) {
    container.appendChild(plainPiece(cps.slice(cursor).join("")));
  }
  return container;
}

function plainPiece(text) {
  const span = document.createElement("span");
  span.className = "plain";
  span.textContent = text;
  return span;
}

// ---- ② 卡片 / 金句 ----

export function renderCards(cards) {
  const wrap = document.createElement("div");
  wrap.className = "cards";
  for (const c of cards) {
    const card = document.createElement("blockquote");
    card.className = "card";
    if (c.source == null) card.classList.add("free"); // 锚不回原文
    const q = document.createElement("p");
    q.className = "quote";
    q.textContent = c.quote;
    card.appendChild(q);
    const meta = document.createElement("div");
    meta.className = "meta";
    if (c.source == null) {
      meta.textContent = "（自由生成，不可跳转）";
    } else {
      meta.textContent = c.source.seconds != null ? `⏱ ${fmtTime(c.source.seconds)} · 点击跳到原文` : "点击跳到原文";
      card.classList.add("clickable");
      card.dataset.charStart = String(c.source.char_start);
    }
    card.appendChild(meta);
    wrap.appendChild(card);
  }
  return wrap;
}

// ---- ③ 脉络大纲（递归） ----

export function renderOutline(outline) {
  const root = document.createElement("ul");
  root.className = "outline";
  for (const node of outline) root.appendChild(outlineNode(node));
  return root;
}

function outlineNode(node) {
  const li = document.createElement("li");
  const head = document.createElement("div");
  head.className = "ol-title";
  head.textContent = node.title;
  if (node.source != null) {
    head.classList.add("clickable");
    head.dataset.charStart = String(node.source.char_start);
    if (node.source.seconds != null) {
      const t = document.createElement("span");
      t.className = "ts";
      t.textContent = ` ${fmtTime(node.source.seconds)}`;
      head.appendChild(t);
    }
  } else {
    head.classList.add("free");
  }
  li.appendChild(head);
  if (node.children && node.children.length) {
    const ul = document.createElement("ul");
    for (const c of node.children) ul.appendChild(outlineNode(c));
    li.appendChild(ul);
  }
  return li;
}

// ---- 跳读：点卡片/大纲 → 滚到全文对应高亮 ----

/** 在全文容器里找 char_start 最接近的高亮锚点，滚过去并闪一下。 */
export function jumpToChar(fullTextEl, charStart) {
  const marks = Array.from(fullTextEl.querySelectorAll(".hl"));
  if (!marks.length) return;
  let best = marks[0];
  let bestDiff = Infinity;
  for (const m of marks) {
    const diff = Math.abs(Number(m.dataset.charStart) - charStart);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = m;
    }
  }
  best.scrollIntoView({ behavior: "smooth", block: "center" });
  best.classList.remove("flash");
  void best.offsetWidth; // 重启动画
  best.classList.add("flash");
}

// ---- 顶层装配 ----

export function renderAll(rootEl, payload) {
  const canonical = payload.extract.canonical_text;
  const digest = payload.digest;

  const fullCol = rootEl.querySelector("#col-fulltext .col-body");
  const cardsCol = rootEl.querySelector("#col-cards .col-body");
  const outlineCol = rootEl.querySelector("#col-outline .col-body");

  fullCol.innerHTML = "";
  cardsCol.innerHTML = "";
  outlineCol.innerHTML = "";

  const fullEl = renderFullText(canonical, digest.highlights);
  fullCol.appendChild(fullEl);
  cardsCol.appendChild(renderCards(digest.cards));
  outlineCol.appendChild(renderOutline(digest.outline));

  // 跳读接线
  rootEl.addEventListener("click", (e) => {
    const t = e.target.closest(".clickable");
    if (!t || !t.dataset.charStart) return;
    jumpToChar(fullEl, Number(t.dataset.charStart));
  });

  // "只看高亮"开关（在顶栏，rootEl 外）
  const toggle = document.querySelector("#only-highlights");
  if (toggle) {
    toggle.addEventListener("change", () => {
      fullEl.classList.toggle("only-hl", toggle.checked);
    });
  }

  // 坐标系自检：sha 不一致就报警（坐标已漂，整份作废）。
  // banner 在顶栏（rootEl 外），用 document 查。
  const banner = document.querySelector("#sha-banner");
  if (banner) {
    const ok = payload.extract.text_sha256 === digest.source_text_sha256;
    banner.textContent = ok
      ? `坐标系一致 ✓ (${digest.coordinate_space})`
      : "⚠ sha 不一致：坐标已漂，高亮可能错位";
    banner.className = ok ? "sha-ok" : "sha-bad";
  }
}
