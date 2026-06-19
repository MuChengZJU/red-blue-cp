import { segmentByHighlights } from '../lib/highlight.js';

/* -- helpers ----------------------------------------------------------- */

function esc(s) {
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function fmtTime(sec) {
  if (sec == null) return '--:--';
  var m = Math.floor(sec / 60);
  var s = Math.floor(sec % 60);
  return m + ':' + (s < 10 ? '0' : '') + s;
}

function buildOutline(nodes, jumpFn) {
  var ul = document.createElement('ul');
  ul.className = 'outline';
  for (var i = 0; i < nodes.length; i++) {
    var node = nodes[i];
    var li = document.createElement('li');
    var title = document.createElement('div');
    var hasSrc = node.source && node.source.seconds != null;
    title.className = 'ol-title' + (hasSrc ? '' : ' free');
    title.textContent = node.title;
    if (hasSrc) {
      var ts = document.createElement('span');
      ts.className = 'ts';
      ts.textContent = fmtTime(node.source.seconds);
      title.appendChild(ts);
    }
    if (node.source && node.source.char_start != null && jumpFn) {
      title.addEventListener('click', (function(cs) {
        return function() { jumpFn(cs); };
      })(node.source.char_start));
    }
    li.appendChild(title);
    if (node.children && node.children.length > 0) {
      li.appendChild(buildOutline(node.children, jumpFn));
    }
    ul.appendChild(li);
  }
  return ul;
}

/* -- main render ------------------------------------------------------- */

export function render(container, api, jobId) {
  container.innerHTML = '';

  if (!jobId) {
    container.innerHTML = '<div class="placeholder">\u4ece\u6587\u4ef6\u5e93\u6216\u4efb\u52a1\u5217\u8868\u9009\u4e00\u7bc7</div>';
    return;
  }

  container.innerHTML = '<div class="placeholder">\u52a0\u8f7d\u4e2d\u2026</div>';

  // \u6e10\u8fdb\u52a0\u8f7d\uff1a\u901f\u89c8\uff08digest\uff09\u8981\u73b0\u7b97 LLM\u3001\u6162\uff1b\u5148\u7528\u5df2\u8f6c\u597d\u7684 .md \u5168\u6587\u9876\u4e0a\uff0c\u8ba9\u7528\u6237\u7acb\u523b\u80fd\u8bfb\uff0c
  // \u901f\u89c8\u751f\u6210\u5b8c\u518d\u6574\u4f53\u66ff\u6362\u6210\u7cbe\u534e/\u5361\u7247/\u8109\u7edc\u3002digest \u5148\u56de\u6765\u5c31\u522b\u8ba9 .md \u8986\u76d6\u3002
  // 350ms \u5185 digest \u5c31\u56de\u6765\uff08\u547d\u4e2d\u7f13\u5b58\uff09\u5219\u4e0d\u95ea\u8fd9\u5c42\u4e2d\u95f4\u6001\u3002
  var digestSettled = false;
  var mdPending = api.getMarkdown(jobId).catch(function () { return null; });
  setTimeout(function () {
    if (digestSettled) return;
    mdPending.then(function (md) {
      if (digestSettled || md == null) return;
      _renderMdDoc(container, md, '\u901f\u89c8\u751f\u6210\u4e2d\uff0c\u5148\u770b\u5168\u6587\u2026\uff08\u9ad8\u4eae / \u5361\u7247 / \u8109\u7edc\u9a6c\u4e0a\u5c31\u597d\uff09');
    });
  }, 350);

  api.getDigest(jobId).then(function(data) {
    digestSettled = true;
    container.innerHTML = '';

    var extract = data.extract || {};
    var digest  = data.digest  || {};
    var canonicalText = extract.canonical_text || '';
    var readableText  = extract.readable_text  || '';
    var segments   = extract.segments   || null;
    var highlights = digest.highlights  || [];
    var cards      = digest.cards       || [];
    var outline    = digest.outline     || [];

    var view   = 'digest';
    var hlOnly = false;
    var markdownCached = null;   // 整篇 markdown 懒加载缓存（成功才赋值，失败置 null 允许重试）
    var markdownLoading = false;

    /* -- reader-head --------------------------------------------------- */
    var head = document.createElement('div');
    head.className = 'reader-head';

    var back = document.createElement('button');
    back.className = 'back';
    back.innerHTML = '<i data-lucide="chevron-left"></i>';
    back.addEventListener('click', function() {
      var nav = document.querySelector('.nav-item[data-s="library"]');
      if (nav) nav.click();
    });
    head.appendChild(back);

    var titleWrap = document.createElement('div');
    var rt = document.createElement('div');
    rt.className = 'rt';
    rt.textContent = digest.model ? '\u901f\u89c8\u9605\u8bfb' : '\u9605\u8bfb';
    var rm = document.createElement('div');
    rm.className = 'rm';
    rm.textContent = digest.model || '';
    titleWrap.appendChild(rt);
    titleWrap.appendChild(rm);
    head.appendChild(titleWrap);

    var tools = document.createElement('div');
    tools.className = 'tools';

    /* -- seg control --------------------------------------------------- */
    var seg = document.createElement('div');
    seg.className = 'seg';

    var segBtns = {};
    var views   = {};
    var segDefs = [
      ['digest',   '\u7cbe\u534e\u901f\u89c8', '\u2460'],
      ['clean',    '\u6e05\u6d17\u5168\u6587', '\u2461'],
      ['markdown', '\u6574\u7bc7\u9605\u8bfb', '\u2462'],
      ['raw',      '\u539f\u59cb\u9010\u5b57', '\u2463']
    ];
    for (var si = 0; si < segDefs.length; si++) {
      (function(def) {
        var key = def[0], label = def[1], lvl = def[2];
        var btn = document.createElement('button');
        if (key === view) btn.className = 'on';
        var lvlSpan = document.createElement('span');
        lvlSpan.className = 'lvl';
        lvlSpan.textContent = lvl;
        btn.appendChild(lvlSpan);
        btn.appendChild(document.createTextNode(label));
        btn.addEventListener('click', function() { switchView(key); });
        seg.appendChild(btn);
        segBtns[key] = btn;
      })(segDefs[si]);
    }
    tools.appendChild(seg);

    /* -- hl toggle (event bound after ftEl exists) --------------------- */
    var hlBtn = document.createElement('button');
    hlBtn.className = 'toggle';
    hlBtn.innerHTML = '<i data-lucide="highlighter"></i>\u53ea\u770b\u9ad8\u4eae';
    tools.appendChild(hlBtn);

    /* -- copy ---------------------------------------------------------- */
    var copyBtn = document.createElement('button');
    copyBtn.className = 'toggle';
    copyBtn.innerHTML = '<i data-lucide="copy"></i>\u590d\u5236';
    copyBtn.addEventListener('click', function() {
      var text = '';
      if (view === 'digest') text = canonicalText;
      else if (view === 'clean') text = readableText;
      else if (view === 'markdown' && markdownCached !== null) text = _stripFrontmatter(markdownCached);
      else if (view === 'raw' && segments) {
        text = segments.map(function(s) {
          return '[' + fmtTime(s.start_sec) + '] ' + s.text;
        }).join('\n');
      }
      if (!text) return;  // 整篇还在加载 / 无内容 → 不复制空串、不显示假「已复制」
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function() {
          copyBtn.innerHTML = '<i data-lucide="check"></i>\u5df2\u590d\u5236';
          setTimeout(function() {
            copyBtn.innerHTML = '<i data-lucide="copy"></i>\u590d\u5236';
            if (window.lucide) lucide.createIcons();
          }, 1500);
        });
      }
    });
    tools.appendChild(copyBtn);

    /* -- export .md ---------------------------------------------------- */
    // \u7528 button + \u5e26\u9274\u6743\u7684 fetch\u2192blob\u2192\u4fdd\u5b58\uff0c\u4e0d\u7528 <a href> \u8df3\u8f6c\uff08\u8df3\u8f6c\u4e0d\u5e26 token \u2192
    // 401\u300cNot authenticated\u300d\u4e14\u628a webview \u5bfc\u822a\u5230 401 \u9875\u3001\u65e0\u9000\u8def\uff0c\u5c31\u662f\u7528\u6237\u53cd\u9988\u7684\u90a3\u4e2a bug\uff09\u3002
    var exportBtn = document.createElement('button');
    exportBtn.className = 'toggle';
    exportBtn.style.textDecoration = 'none';
    exportBtn.innerHTML = '<i data-lucide="download"></i>\u5bfc\u51fa';
    var exportLabel = function (txt) {
      exportBtn.innerHTML = '<i data-lucide="download"></i>' + txt;
      if (window.lucide) lucide.createIcons();
    };
    exportBtn.addEventListener('click', function () {
      exportBtn.disabled = true;
      api.downloadMarkdown(jobId).then(function (blob) {
        var fname = ((digest && digest.title) || ('rbcp-note-' + jobId))
          .replace(/[\\/:*?"<>|]/g, '_') + '.md';
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = fname;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        exportLabel('\u5df2\u5bfc\u51fa');
        setTimeout(function () { exportLabel('\u5bfc\u51fa'); }, 1500);
      }).catch(function () {
        exportLabel('\u5bfc\u51fa\u5931\u8d25');
        setTimeout(function () { exportLabel('\u5bfc\u51fa'); }, 1800);
      }).then(function () { exportBtn.disabled = false; });
    });
    tools.appendChild(exportBtn);

    head.appendChild(tools);
    container.appendChild(head);

    /* === (1) highlight digest view ===================================== */
    var rvDigest = document.createElement('div');
    rvDigest.className = 'rview on';
    rvDigest.id = 'rv-digest';
    views.digest = rvDigest;

    /* col-1: canonical fulltext + highlights */
    var col1 = document.createElement('div');
    col1.className = 'col';
    var col1H = document.createElement('div');
    col1H.className = 'col-head';
    col1H.innerHTML = '<span class="n">\u2460</span>\u5168\u6587 + \u91cd\u70b9\u9ad8\u4eae';
    col1.appendChild(col1H);
    var col1B = document.createElement('div');
    col1B.className = 'col-body';

    var ftEl = document.createElement('div');
    ftEl.className = 'fulltext';
    ftEl.id = 'ft';

    var hlSpans = highlights.map(function(h) { return { s: h.span_start, e: h.span_end }; });
    var segs = segmentByHighlights(canonicalText, hlSpans);

    var hlMap = {};
    for (var hi = 0; hi < highlights.length; hi++) {
      hlMap[highlights[hi].span_start] = highlights[hi];
    }

    var hlElements = [];
    var cPos = 0;
    for (var gi = 0; gi < segs.length; gi++) {
      var segItem = segs[gi];
      if (segItem.highlighted) {
        var sp = document.createElement('span');
        sp.className = 'hl';
        sp.setAttribute('data-cs', cPos);
        sp.setAttribute('data-ce', cPos + segItem.text.length);
        sp.appendChild(document.createTextNode(segItem.text));
        var matched = hlMap[cPos];
        if (matched && matched.source && matched.source.seconds != null) {
          var tsSp = document.createElement('span');
          tsSp.className = 'ts';
          tsSp.textContent = fmtTime(matched.source.seconds);
          sp.appendChild(tsSp);
        }
        ftEl.appendChild(sp);
        hlElements.push(sp);
      } else {
        var pl = document.createElement('span');
        pl.className = 'plain';
        pl.textContent = segItem.text;
        ftEl.appendChild(pl);
      }
      cPos += segItem.text.length;
    }

    col1B.appendChild(ftEl);
    col1.appendChild(col1B);
    rvDigest.appendChild(col1);

    /* col-2: cards */
    var col2 = document.createElement('div');
    col2.className = 'col';
    var col2H = document.createElement('div');
    col2H.className = 'col-head';
    col2H.innerHTML = '<span class="n">\u2461</span>\u5361\u7247 / \u91d1\u53e5';
    col2.appendChild(col2H);
    var col2B = document.createElement('div');
    col2B.className = 'col-body';

    var cardsDiv = document.createElement('div');
    cardsDiv.className = 'cards';
    for (var ci = 0; ci < cards.length; ci++) {
      (function(card) {
        var cardEl = document.createElement('div');
        cardEl.className = 'card' + (card.source ? '' : ' free');
        var quote = document.createElement('p');
        quote.className = 'quote';
        quote.textContent = card.quote;
        cardEl.appendChild(quote);
        var meta = document.createElement('div');
        meta.className = 'meta';
        if (card.source && card.source.seconds != null) {
          meta.textContent = '\u8df3\u5230 ' + fmtTime(card.source.seconds) + ' \u25B8';
          cardEl.addEventListener('click', function() { jumpTo(card.source.char_start); });
        } else {
          meta.textContent = '\u91d1\u53e5\uff08\u65e0\u951a\u70b9\uff09';
        }
        cardEl.appendChild(meta);
        cardsDiv.appendChild(cardEl);
      })(cards[ci]);
    }
    col2B.appendChild(cardsDiv);
    col2.appendChild(col2B);
    rvDigest.appendChild(col2);

    /* col-3: outline */
    var col3 = document.createElement('div');
    col3.className = 'col';
    var col3H = document.createElement('div');
    col3H.className = 'col-head';
    col3H.innerHTML = '<span class="n">\u2462</span>\u8109\u7edc\u5927\u7eb2';
    col3.appendChild(col3H);
    var col3B = document.createElement('div');
    col3B.className = 'col-body';
    if (outline.length > 0) {
      col3B.appendChild(buildOutline(outline, jumpTo));
    }
    col3.appendChild(col3B);
    rvDigest.appendChild(col3);

    container.appendChild(rvDigest);

    /* === (2) clean fulltext view ======================================= */
    var rvClean = document.createElement('div');
    rvClean.className = 'rview';
    rvClean.id = 'rv-clean';
    views.clean = rvClean;

    var cleanInner = document.createElement('div');
    cleanInner.className = 'inner';
    var ft2 = document.createElement('div');
    ft2.className = 'fulltext';
    ft2.id = 'ft2';

    var paras = readableText.split('\n');
    for (var pi = 0; pi < paras.length; pi++) {
      if (paras[pi].trim()) {
        var pDiv = document.createElement('div');
        pDiv.textContent = paras[pi];
        ft2.appendChild(pDiv);
      }
    }
    cleanInner.appendChild(ft2);
    rvClean.appendChild(cleanInner);
    container.appendChild(rvClean);

    /* === (3) raw segments view ========================================= */
    var rvRaw = document.createElement('div');
    rvRaw.className = 'rview';
    rvRaw.id = 'rv-raw';
    views.raw = rvRaw;

    var rawNote = document.createElement('div');
    rawNote.className = 'raw-note';
    rawNote.innerHTML = '<i data-lucide="info"></i>\u539f\u59cb\u65f6\u95f4\u5bf9\u9f50\u6587\u672c\uff08ASR \u9010\u5b57\u7a3f\uff0c\u672a\u7ea0\u9519\uff09\u3002\u4e3b\u8981\u4f9b AI \u5904\u7406 / \u6838\u5bf9\uff0c\u65e5\u5e38\u9605\u8bfb\u7528\u300c\u7cbe\u534e\u300d\u300c\u6e05\u6d17\u300d\u4e24\u5c42\u5373\u53ef\u3002';
    rvRaw.appendChild(rawNote);

    var rawList = document.createElement('div');
    rawList.className = 'raw-list';
    rawList.id = 'rawlist';

    if (segments && segments.length > 0) {
      for (var ri = 0; ri < segments.length; ri++) {
        var line = document.createElement('div');
        line.className = 'raw-line';
        var rawTs = document.createElement('div');
        rawTs.className = 'raw-ts';
        rawTs.textContent = fmtTime(segments[ri].start_sec);
        var rawTx = document.createElement('div');
        rawTx.className = 'raw-tx';
        rawTx.textContent = segments[ri].text;
        line.appendChild(rawTs);
        line.appendChild(rawTx);
        rawList.appendChild(line);
      }
    } else {
      var emptyMsg = document.createElement('div');
      emptyMsg.className = 'placeholder';
      emptyMsg.textContent = '\u56fe\u6587\u65e0\u9010\u5b57';
      rawList.appendChild(emptyMsg);
    }
    rvRaw.appendChild(rawList);
    container.appendChild(rvRaw);

    /* === (4) 整篇连贯阅读：markdown 渲染（懒加载 .md）================== */
    var rvMarkdown = document.createElement('div');
    rvMarkdown.className = 'rview';
    rvMarkdown.id = 'rv-markdown';
    views.markdown = rvMarkdown;
    var mdInner = document.createElement('div');
    mdInner.className = 'inner';
    var mdBody = document.createElement('article');
    mdBody.className = 'markdown-body';
    mdBody.innerHTML = '<div class="placeholder">加载全文…</div>';
    mdInner.appendChild(mdBody);
    rvMarkdown.appendChild(mdInner);
    container.appendChild(rvMarkdown);

    function loadMarkdownView() {
      if (markdownCached !== null || markdownLoading) return;
      markdownLoading = true;
      api.getMarkdown(jobId).then(function (md) {
        markdownCached = typeof md === 'string' ? md : String(md == null ? '' : md);
        mdBody.innerHTML = _renderMarkdownHtml(markdownCached);
      }).catch(function () {
        mdBody.innerHTML = '<div class="placeholder">无法加载全文</div>';
      }).finally(function () { markdownLoading = false; });  // 无论成败都复位，允许重试
    }

    /* -- bind hl toggle now that ftEl exists ---------------------------- */
    hlBtn.addEventListener('click', function() {
      hlOnly = !hlOnly;
      hlBtn.classList.toggle('on', hlOnly);
      ftEl.classList.toggle('only-hl', hlOnly);
    });

    /* -- view switch --------------------------------------------------- */
    function switchView(v) {
      view = v;
      var keys = ['digest', 'clean', 'markdown', 'raw'];
      for (var k = 0; k < keys.length; k++) {
        if (views[keys[k]])    views[keys[k]].classList.toggle('on',    keys[k] === v);
        if (segBtns[keys[k]])  segBtns[keys[k]].classList.toggle('on',  keys[k] === v);
      }
      if (v === 'markdown') loadMarkdownView();
    }

    /* -- jumpTo (card / outline -> highlight scroll) ------------------- */
    function jumpTo(charStart) {
      if (charStart == null) return;
      switchView('digest');
      for (var j = 0; j < hlElements.length; j++) {
        var el = hlElements[j];
        var cs = parseInt(el.getAttribute('data-cs'), 10);
        var ce = parseInt(el.getAttribute('data-ce'), 10);
        if (charStart >= cs && charStart < ce) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.style.transition = 'background 0.3s';
          el.style.background = 'rgba(229,72,77,0.4)';
          setTimeout(function() { el.style.background = ''; }, 1200);
          return;
        }
      }
    }

    /* -- lucide -------------------------------------------------------- */
    if (window.lucide) lucide.createIcons();

  }).catch(function(err) {
    digestSettled = true;
    container.innerHTML = '';
    // 409 = \u65e9\u671f\u8f6c\u5f55\u65e0 canonical/segments\uff08Task 1.0 \u524d\uff09\uff0c\u901f\u89c8\u6ca1\u6570\u636e\u6e90\u3002
    // \u4e0d\u62a5\u9519\uff0c\u56de\u9000\u663e\u793a\u5df2\u6709\u7684 .md \u53ef\u8bfb\u5168\u6587\uff08\u5b8c\u6574\u901f\u89c8\u9700\u91cd\u65b0\u8f6c\u5f55\uff09\u3002
    if (err && err.status === 409) {
      renderMarkdownFallback(container, api, jobId);
      return;
    }
    var msg = '\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5';
    if (err && err.detail) {
      msg = esc(String(err.detail));
    }
    var div = document.createElement('div');
    div.className = 'placeholder';
    div.textContent = msg;
    container.appendChild(div);
  });
}

/** \u6e32\u67d3\u6574\u7bc7 .md \u6587\u6863\uff08\u590d\u5236\u5168\u6587 + \u63d0\u793a\u6761 + markdown \u6e32\u67d3\uff09\u3002\u65e9\u671f\u8f6c\u5f55\u56de\u9000 & \u901f\u89c8\u751f\u6210\u4e2d\u90fd\u7528\u5b83\u3002 */
function _renderMdDoc(container, md, bannerText) {
  container.innerHTML = '';
  // \u4e00\u952e\u590d\u5236\u5168\u6587
  var bar = document.createElement('div');
  bar.className = 'md-fallback-bar';
  var copyBtn = document.createElement('button');
  copyBtn.className = 'toggle';
  copyBtn.innerHTML = '<i data-lucide="copy"></i>\u590d\u5236\u5168\u6587';
  copyBtn.addEventListener('click', function () {
    var text = _stripFrontmatter(md);
    if (!text || !navigator.clipboard || !navigator.clipboard.writeText) return;
    navigator.clipboard.writeText(text).then(function () {
      copyBtn.innerHTML = '<i data-lucide="check"></i>\u5df2\u590d\u5236';
      if (window.lucide) lucide.createIcons();
      setTimeout(function () {
        copyBtn.innerHTML = '<i data-lucide="copy"></i>\u590d\u5236\u5168\u6587';
        if (window.lucide) lucide.createIcons();
      }, 1500);
    });
  });
  bar.appendChild(copyBtn);
  container.appendChild(bar);

  if (bannerText) {
    var banner = document.createElement('div');
    banner.className = 'md-fallback-banner';
    banner.textContent = bannerText;
    container.appendChild(banner);
  }
  // \u548c\u300c\u6574\u7bc7\u9605\u8bfb\u300d\u89c6\u56fe\u540c\u4e00\u5957 markdown \u6e32\u67d3\uff0c\u522b\u518d\u628a .md \u6e90\u7801\u5f53\u7eaf\u6587\u672c\u7cca\u4e0a\u53bb
  var body = document.createElement('article');
  body.className = 'markdown-body';
  body.innerHTML = _renderMarkdownHtml(md);
  container.appendChild(body);
  if (window.lucide) lucide.createIcons();
}

/** \u65e9\u671f\u8f6c\u5f55\uff08\u65e0 artifacts\uff09\u56de\u9000\uff1a\u663e\u793a\u5df2\u6709 .md \u53ef\u8bfb\u5168\u6587 + \u91cd\u8f6c\u63d0\u793a\u3002 */
function renderMarkdownFallback(container, api, jobId) {
  container.innerHTML = '<div class="placeholder">\u52a0\u8f7d\u53ef\u8bfb\u5168\u6587\u2026</div>';
  api.getMarkdown(jobId).then(function(md) {
    _renderMdDoc(container, md, '\u65e9\u671f\u8f6c\u5f55\uff1a\u4ec5\u53ef\u8bfb\u5168\u6587\u3002\u751f\u6210\u5b8c\u6574\u901f\u89c8\uff08\u9ad8\u4eae / \u5361\u7247 / \u8109\u7edc\uff09\u9700\u91cd\u65b0\u8f6c\u5f55\u3002');
  }).catch(function() {
    var div = document.createElement('div');
    div.className = 'placeholder';
    div.textContent = '\u9700\u91cd\u65b0\u8f6c\u5f55\uff08\u65e0\u53ef\u8bfb\u5185\u5bb9\uff09';
    container.innerHTML = '';
    container.appendChild(div);
  });
}

function _stripFrontmatter(md) {
  if (typeof md !== 'string') return md == null ? '' : String(md);
  var m = md.match(/^---\n[\s\S]*?\n---\n?/);
  return (m ? md.slice(m[0].length) : md).trim();
}

// .md → 连贯 HTML（marked + DOMPurify 防 XSS，去 frontmatter，复用 WebUI detail 管线）。
// CDN 没加载到则降级为安全纯文本。供「整篇阅读」视图和早期转录回退共用。
function _renderMarkdownHtml(md) {
  var src = _stripFrontmatter(md);
  if (window.marked && window.DOMPurify) {
    var rawHtml = window.marked.parse(src, { gfm: true, breaks: true });
    return window.DOMPurify.sanitize(rawHtml, { ADD_ATTR: ['target', 'rel'] });
  }
  var safe = document.createElement('div');
  safe.style.cssText = 'white-space:pre-wrap;line-height:1.9';
  safe.textContent = src;
  return safe.outerHTML;
}
