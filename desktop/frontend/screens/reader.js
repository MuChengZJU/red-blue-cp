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

  api.getDigest(jobId).then(function(data) {
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
      ['digest', '\u7cbe\u534e\u901f\u89c8', '\u2460'],
      ['clean',  '\u6e05\u6d17\u5168\u6587', '\u2461'],
      ['raw',    '\u539f\u59cb\u9010\u5b57', '\u2462']
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
      else if (view === 'raw' && segments) {
        text = segments.map(function(s) {
          return '[' + fmtTime(s.start_sec) + '] ' + s.text;
        }).join('\n');
      }
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
    var exportBtn = document.createElement('a');
    exportBtn.className = 'toggle';
    exportBtn.href = api.downloadUrl(jobId);
    exportBtn.download = '';
    exportBtn.style.textDecoration = 'none';
    exportBtn.innerHTML = '<i data-lucide="download"></i>\u5bfc\u51fa';
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

    /* -- bind hl toggle now that ftEl exists ---------------------------- */
    hlBtn.addEventListener('click', function() {
      hlOnly = !hlOnly;
      hlBtn.classList.toggle('on', hlOnly);
      ftEl.classList.toggle('only-hl', hlOnly);
    });

    /* -- view switch --------------------------------------------------- */
    function switchView(v) {
      view = v;
      var keys = ['digest', 'clean', 'raw'];
      for (var k = 0; k < keys.length; k++) {
        if (views[keys[k]])    views[keys[k]].classList.toggle('on',    keys[k] === v);
        if (segBtns[keys[k]])  segBtns[keys[k]].classList.toggle('on',  keys[k] === v);
      }
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

/** \u65e9\u671f\u8f6c\u5f55\uff08\u65e0 artifacts\uff09\u56de\u9000\uff1a\u663e\u793a\u5df2\u6709 .md \u53ef\u8bfb\u5168\u6587 + \u91cd\u8f6c\u63d0\u793a\u3002 */
function renderMarkdownFallback(container, api, jobId) {
  container.innerHTML = '<div class="placeholder">\u52a0\u8f7d\u53ef\u8bfb\u5168\u6587\u2026</div>';
  api.getMarkdown(jobId).then(function(md) {
    container.innerHTML = '';
    var banner = document.createElement('div');
    banner.style.cssText = 'padding:10px 14px;margin-bottom:14px;border-radius:8px;'
      + 'background:rgba(217,130,26,.12);color:#9a5a00;font-size:13px;line-height:1.6;';
    banner.textContent = '\u65e9\u671f\u8f6c\u5f55\uff1a\u4ec5\u53ef\u8bfb\u5168\u6587\u3002'
      + '\u751f\u6210\u5b8c\u6574\u901f\u89c8\uff08\u9ad8\u4eae / \u5361\u7247 / \u8109\u7edc\uff09\u9700\u91cd\u65b0\u8f6c\u5f55\u3002';
    container.appendChild(banner);
    var body = document.createElement('div');
    body.style.cssText = 'white-space:pre-wrap;line-height:1.9;font-size:15px;max-width:760px;';
    body.textContent = _stripFrontmatter(md);
    container.appendChild(body);
  }).catch(function() {
    var div = document.createElement('div');
    div.className = 'placeholder';
    div.textContent = '\u9700\u91cd\u65b0\u8f6c\u5f55\uff08\u65e0\u53ef\u8bfb\u5185\u5bb9\uff09';
    container.appendChild(div);
  });
}

function _stripFrontmatter(md) {
  if (typeof md !== 'string') return md == null ? '' : String(md);
  var m = md.match(/^---\n[\s\S]*?\n---\n?/);
  return (m ? md.slice(m[0].length) : md).trim();
}
