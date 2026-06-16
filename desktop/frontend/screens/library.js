/* state */
var _jobs = [];
var _search = '';
var _sort = 'time-desc';
var _platform = 'all';
var _view = 'card';

/* helpers */
function esc(s) {
  if (s == null) return '';
  var d = document.createElement('div');
  d.appendChild(document.createTextNode(String(s)));
  return d.innerHTML;
}

function platformKey(p) {
  var s = (p || '').toLowerCase();
  if (s.indexOf('bilibili') !== -1 || s.indexOf('b\u7ad9') !== -1 || s === 'bili') return 'bilibili';
  if (s.indexOf('xiaohongshu') !== -1 || s.indexOf('\u5c0f\u7ea2\u4e66') !== -1 || s === 'xhs') return 'xiaohongshu';
  return s || '';
}

function platformBadge(platform) {
  var k = platformKey(platform);
  if (k === 'bilibili') return '<span class="plat b">B\u7ad9</span>';
  if (k === 'xiaohongshu') return '<span class="plat x">\u5c0f\u7ea2\u4e66</span>';
  if (platform) return '<span class="plat">' + esc(platform) + '</span>';
  return '';
}

/* filter + sort */
function applyFilters() {
  var list = _jobs.slice();
  if (_platform !== 'all') {
    list = list.filter(function (j) { return platformKey(j.platform) === _platform; });
  }
  if (_search) {
    var q = _search.toLowerCase();
    list = list.filter(function (j) {
      return ((j.title || '') + ' ' + (j.author || '')).toLowerCase().indexOf(q) !== -1;
    });
  }
  list.sort(function (a, b) {
    var ta = new Date(a.created_at || 0).getTime() || 0;
    var tb = new Date(b.created_at || 0).getTime() || 0;
    if (_sort === 'time-desc') return tb - ta;
    if (_sort === 'time-asc') return ta - tb;
    if (_sort === 'title-asc') return (a.title || '').localeCompare(b.title || '');
    if (_sort === 'title-desc') return (b.title || '').localeCompare(a.title || '');
    return 0;
  });
  return list;
}

/* render pieces */
function renderCard(job) {
  var id = esc(job.id);
  var t = esc(job.title || '\u65e0\u6807\u9898');
  var a = esc(job.author || '');
  var ch = t.charAt(0) || '?';
  return (
    '<div class="lib-card" data-open="' + id + '">' +
    '<div class="lib-cover">' + ch + '</div>' +
    '<div class="lib-meta">' +
    platformBadge(job.platform) +
    '<div class="lib-title">' + t + '</div>' +
    '<div class="lib-sub"><span>' + a + '</span></div>' +
    '<div class="lib-acts">' +
    '<button class="mini" data-copy="' + id + '">\u590d\u5236</button>' +
    '<button class="mini red" data-del="' + id + '">\u5220\u9664</button>' +
    '</div></div></div>'
  );
}

function renderToolbar() {
  var sorts = [
    ['time-desc', '\u6700\u65b0\u4f18\u5148'],
    ['time-asc', '\u6700\u65e9\u4f18\u5148'],
    ['title-asc', '\u540d\u79f0 A\u2192Z'],
    ['title-desc', '\u540d\u79f0 Z\u2192A']
  ];
  var so = '<select class="sort" data-sort>' +
    sorts.map(function (s) {
      return '<option value="' + s[0] + '"' + (_sort === s[0] ? ' selected' : '') + '>' + s[1] + '</option>';
    }).join('') + '</select>';

  var chips = [
    ['all', '\u5168\u90e8', ''],
    ['bilibili', 'B\u7ad9', ' blue'],
    ['xiaohongshu', '\u5c0f\u7ea2\u4e66', ' red']
  ];
  var ch = '<div class="chips">' +
    chips.map(function (c) {
      return '<span class="chip' + c[2] + (_platform === c[0] ? ' on' : '') + '" data-chip="' + c[0] + '">' + c[1] + '</span>';
    }).join('') + '</div>';

  var vt = '<div class="vt">' +
    '<button' + (_view === 'card' ? ' class="on"' : '') + ' data-view="card">\u25a6</button>' +
    '<button' + (_view === 'list' ? ' class="on"' : '') + ' data-view="list">\u2630</button>' +
    '</div>';

  return (
    '<div class="lib-tools">' +
    '<div class="search"><input placeholder="\u641c\u7d22\u6807\u9898 / \u4f5c\u8005\u2026" data-search value="' + esc(_search) + '"></div>' +
    ch +
    '<div class="right">' + so + vt + '</div></div>'
  );
}

/* full re-render */
function renderAll(container, api) {
  var list = applyFilters();
  var html =
    '<div class="page-head"><h2>\u6587\u4ef6\u5e93</h2>' +
    '<span class="sub">\u672c\u5730\u77e5\u8bc6\u5e93 \u00b7 ' + _jobs.length + ' \u7bc7</span></div>';
  html += renderToolbar();
  html += '<div class="page-body">';
  if (list.length) {
    var cls = 'lib-grid' + (_view === 'list' ? ' list' : '');
    html += '<div class="' + cls + '">' + list.map(renderCard).join('') + '</div>';
  } else if (_jobs.length === 0) {
    html += '<div style="padding:60px 0;text-align:center;color:var(--muted);font-weight:600;font-size:14px">' +
      '\u8fd8\u6ca1\u6709\u5df2\u5b8c\u6210\u7684\u5185\u5bb9<br>' +
      '<span style="font-size:12px;font-weight:400;margin-top:8px;display:inline-block">' +
      '\u53bb\u4efb\u52a1\u5217\u8868\u770b\u770b\u5427</span></div>';
  } else {
    html += '<div style="padding:60px 0;text-align:center;color:var(--muted);font-weight:600;font-size:14px">' +
      '\u6ca1\u6709\u5339\u914d\u7684\u5185\u5bb9</div>';
  }
  html += '</div>';
  container.innerHTML = html;
  bindEvents(container, api);
}

/* events */
function bindEvents(root, api) {
  /* search */
  var si = root.querySelector('[data-search]');
  if (si) {
    si.addEventListener('input', function () {
      _search = si.value;
      renderAll(root, api);
      var n = root.querySelector('[data-search]');
      if (n) { n.focus(); n.selectionStart = n.selectionEnd = n.value.length; }
    });
  }

  /* sort */
  var so = root.querySelector('[data-sort]');
  if (so) {
    so.addEventListener('change', function () { _sort = so.value; renderAll(root, api); });
  }

  /* platform chips */
  root.querySelectorAll('[data-chip]').forEach(function (el) {
    el.addEventListener('click', function () {
      _platform = el.getAttribute('data-chip');
      renderAll(root, api);
    });
  });

  /* view toggle */
  root.querySelectorAll('[data-view]').forEach(function (el) {
    el.addEventListener('click', function () {
      _view = el.getAttribute('data-view');
      renderAll(root, api);
    });
  });

  /* card click -> reader */
  root.querySelectorAll('[data-open]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      if (e.target.closest('button')) return;
      var id = el.getAttribute('data-open');
      if (id && window.rbcpOpenReader) window.rbcpOpenReader(id);
    });
  });

  /* copy */
  root.querySelectorAll('[data-copy]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      e.stopPropagation();
      var id = el.getAttribute('data-copy');
      var url = '';
      try { url = api.downloadUrl(id); } catch (_e) { /* ok */ }
      var job = _jobs.find(function (j) { return String(j.id) === String(id); });
      var text = url || (job && job.title) || '';
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          el.textContent = '\u5df2\u590d\u5236';
          setTimeout(function () { el.textContent = '\u590d\u5236'; }, 1500);
        }).catch(function () {
          el.textContent = '\u5931\u8d25';
          setTimeout(function () { el.textContent = '\u590d\u5236'; }, 1500);
        });
      }
    });
  });

  /* delete */
  root.querySelectorAll('[data-del]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      e.stopPropagation();
      var id = el.getAttribute('data-del');
      if (!confirm('\u786e\u5b9a\u5220\u9664\uff1f')) return;
      el.disabled = true;
      el.textContent = '\u5220\u9664\u4e2d\u2026';
      api.deleteJob(id).then(function () {
        _jobs = _jobs.filter(function (j) { return String(j.id) !== String(id); });
        renderAll(root, api);
      }).catch(function () {
        el.disabled = false;
        el.textContent = '\u5220\u9664';
      });
    });
  });
}

/* load */
function load(container, api) {
  return api.getJobs().then(function (jobs) {
    _jobs = Array.isArray(jobs)
      ? jobs.filter(function (j) { return j && j.status === 'done'; })
      : [];
    renderAll(container, api);
  }).catch(function (e) {
    container.innerHTML =
      '<div class="page-head"><h2>\u6587\u4ef6\u5e93</h2></div>' +
      '<div style="padding:40px;text-align:center;color:var(--rb-red);font-weight:600">' +
      '\u52a0\u8f7d\u5931\u8d25\uff1a' + esc((e && e.message) || '\u672a\u77e5\u9519\u8bef') + '</div>';
  });
}

export function render(container, api) {
  container.innerHTML = '';
  load(container, api);
}
