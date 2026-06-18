let _timer = null;
var _batchExpanded = {};
var _lastSig = null;
var _filter = 'all';  // 任务状态筛选：all / running / done / failed（对齐 WebUI）

// 筛选用计数：running 桶含 pending（排队也算"处理中"），与 WebUI updateCounts 一致
function bucketCounts(jobs) {
  var c = { all: 0, running: 0, done: 0, failed: 0 };
  for (var i = 0; i < jobs.length; i++) {
    c.all++;
    var s = jobs[i].status;
    if (s === 'running' || s === 'pending') c.running++;
    else if (s === 'done') c.done++;
    else if (s === 'failed') c.failed++;
  }
  return c;
}

function applyFilter(jobs) {
  if (_filter === 'all') return jobs;
  return jobs.filter(function (j) {
    if (_filter === 'running') return j.status === 'running' || j.status === 'pending';
    return j.status === _filter;
  });
}

function renderFilterBar(jobs) {
  var c = bucketCounts(jobs);
  var defs = [
    ['all', '全部', ''],
    ['running', '处理中', 'run'],
    ['done', '完成', 'done'],
    ['failed', '失败', 'fail'],
  ];
  var chips = defs.map(function (d) {
    var key = d[0], label = d[1], dotCls = d[2];
    var on = _filter === key ? ' on' : '';
    var dot = dotCls ? '<span class="dot ' + dotCls + '"></span>' : '';
    return '<button class="filter-chip' + on + '" data-filter="' + key + '"'
      + ' aria-pressed="' + (_filter === key ? 'true' : 'false') + '">'
      + dot + label + ' <span class="cnt">' + c[key] + '</span></button>';
  }).join('');
  return '<div class="filters">' + chips + '</div>';
}

var STATUS_LABEL = {
  pending: '\u6392\u961f',
  running: '\u5904\u7406\u4e2d',
  done: '\u5b8c\u6210',
  failed: '\u5931\u8d25',
};

var STATUS_CLASS = {
  pending: 'pend',
  running: 'run',
  done: 'done',
  failed: 'fail',
};

function esc(s) {
  if (s == null) return '';
  var d = document.createElement('div');
  d.appendChild(document.createTextNode(String(s)));
  return d.innerHTML;
}

function platformLabel(platform) {
  var p = (platform || '').toLowerCase();
  if (p.indexOf('bilibili') !== -1 || p.indexOf('b\u7ad9') !== -1 || p === 'bili') {
    return '<span class="plat b">B\u7ad9</span>';
  }
  if (p.indexOf('xiaohongshu') !== -1 || p.indexOf('\u5c0f\u7ea2\u4e66') !== -1 || p === 'xhs') {
    return '<span class="plat x">\u5c0f\u7ea2\u4e66</span>';
  }
  if (p) return '<span class="plat">' + esc(platform) + '</span>';
  return '';
}

function shortUrl(url) {
  if (!url) return '';
  try {
    var u = new URL(url);
    var path = u.pathname;
    if (path.length > 20) path = path.slice(0, 18) + '...';
    return u.hostname.replace('www.', '') + path;
  } catch (_e) {
    return url.length > 40 ? url.slice(0, 38) + '...' : url;
  }
}

function renderJob(job) {
  var st = STATUS_CLASS[job.status] || 'pend';
  var label = STATUS_LABEL[job.status] || job.status || '\u672a\u77e5';
  var title = esc(job.title || job.url || ('\u4efb\u52a1 #' + job.id));
  var subtitle = '';
  var actions = '';
  var rowAttr = '';

  if (job.status === 'done') {
    rowAttr = ' data-open-row="' + esc(job.id) + '" style="cursor:pointer"';
    subtitle = platformLabel(job.platform);
    var extra = '';
    if (job.duration) extra = ' \u00b7 ' + esc(job.duration);
    if (job.cost != null) extra += ' \u00b7 \u00a5' + Number(job.cost).toFixed(2);
    if (extra) subtitle += '<span>' + extra + '</span>';
    actions = '<button class="mini" data-open="' + esc(job.id) + '">\ud83d\udcd6 \u901f\u89c8</button>';
  } else if (job.status === 'running') {
    subtitle = platformLabel(job.platform);
    var pct = job.progress != null ? job.progress : null;
    if (pct != null) {
      var pctInt = Math.round(pct * 100);
      actions =
        '<span style="font-size:12px;color:var(--muted);font-weight:700">' + pctInt + '%</span>' +
        '<div class="progress"><i style="width:' + pctInt + '%"></i></div>';
    }
  } else if (job.status === 'failed') {
    var errMsg = job.error_message || '\u672a\u77e5\u9519\u8bef';
    subtitle = '<span class="fail-note">' + esc(errMsg) + '</span>';
    var logx = job.log_excerpt && String(job.log_excerpt).trim();
    if (logx) {
      subtitle += '<div class="fail-detail" id="faildet-' + esc(job.id) + '"'
        + ' style="display:none;margin-top:6px;font-size:12px;color:var(--muted);'
        + 'white-space:pre-wrap;font-family:ui-monospace,monospace;'
        + 'background:var(--soft-2);border-radius:6px;padding:8px;max-height:160px;overflow:auto">'
        + esc(job.log_excerpt) + '</div>';
    }
    actions = (logx ? '<button class="mini" data-detail="' + esc(job.id) + '">\u8be6\u60c5</button>' : '')
      + '<button class="mini red" data-retry="' + esc(job.id) + '">\u21bb \u91cd\u8bd5</button>'
      + '<button class="mini red" data-del="' + esc(job.id) + '">\u5220\u9664</button>';
  } else {
    subtitle = platformLabel(job.platform) +
      '<span>' + esc(shortUrl(job.url)) + '</span>';
  }

  return (
    '<div class="job"' + rowAttr + '>' +
    '<div class="st ' + st + '"><span class="dot ' + st + '"></span>' + esc(label) + '</div>' +
    '<div class="info"><div class="jt">' + title + '</div><div class="ju">' + subtitle + '</div></div>' +
    '<div class="act">' + actions + '</div>' +
    '</div>'
  );
}

function renderBatch(batch) {
  var title = esc(batch.title || batch.name || ('\u6279\u6b21 #' + batch.id));
  // \u540e\u7aef list_batches \u7ed9\u7684\u662f counts={status: \u6570\u91cf} \u5b57\u5178\uff08done/failed/skipped/pending\uff09\uff0c
  // \u6ca1\u6709\u6241\u5e73\u7684 *_count \u5b57\u6bb5\uff0c\u4e5f\u4e0d\u5355\u5217 running\u2014\u2014\u4e0e WebUI batchCardHtml \u5bf9\u9f50\u3002
  var c = batch.counts || {};
  var done = c.done || 0;
  var failed = c.failed || 0;
  var skipped = c.skipped || 0;
  var pending = c.pending || 0;
  var total = done + failed + skipped + pending;
  var finished = done + failed + skipped;
  var pct = total > 0 ? Math.round((finished / total) * 100) : 0;

  // \u8fdb\u5ea6\u6587\u6848\uff1a\u5b8c\u6210/\u603b\u6570 \u00b7 \u4f30\u7b97\u8d39\u7528\uff08\u5bf9\u9f50 WebUI batch-progress-text\uff09
  var cost = Number(batch.cost_yuan || 0);
  var costText = cost > 0 ? ' \u00b7 \u4f30\u7b97 \u00a5' + (cost >= 0.01 ? cost.toFixed(2) : cost.toFixed(4)) : '';
  var counts =
    '<span>\u2713 ' + done + '</span>' +
    (failed ? '<span class="sep">\u00b7</span><span>\u2717 ' + failed + '</span>' : '') +
    (skipped ? '<span class="sep">\u00b7</span><span>\u293c ' + skipped + '</span>' : '') +
    (pending ? '<span class="sep">\u00b7</span><span>\u5f85 ' + pending + '</span>' : '');

  return (
    '<div class="batch" data-batch-id="' + esc(batch.id) + '">' +
    '<div class="batch-head" data-batch-toggle="' + esc(batch.id) + '" style="cursor:pointer">' +
    '<div class="bt">\ud83d\udce6 ' + title + '</div>' +
    '<div class="batch-prog-text">' + finished + '/' + total + esc(costText) + '</div>' +
    '</div>' +
    '<div class="counts">' + counts + '</div>' +
    '<div class="progress" style="width:100%;margin-top:10px"><i style="width:' + pct + '%"></i></div>' +
    '<div class="batch-items" data-batch-items="' + esc(batch.id) + '"></div>' +
    '</div>'
  );
}

function fillBatchItems(api, batchId, root) {
  api.getBatchItems(batchId).then(function (items) {
    var el = root.querySelector('[data-batch-items="' + batchId + '"]');
    if (!el) return;
    if (!Array.isArray(items) || !items.length) { el.innerHTML = ''; return; }
    el.innerHTML = items.map(function (item) {
      var s = STATUS_CLASS[item.status] || 'pend';
      return '<div class="job" style="margin-bottom:4px">' +
        '<div class="st ' + s + '"><span class="dot ' + s + '"></span>' +
        esc(STATUS_LABEL[item.status] || item.status) + '</div>' +
        '<div class="info"><div class="jt" style="font-size:12.5px">' +
        esc(item.title || item.url || '#' + item.id) + '</div></div></div>';
    }).join('');
  }).catch(function () {});
}

function expandBatch(api, batchId, root) {
  if (_batchExpanded[batchId]) {
    _batchExpanded[batchId] = false;
    var el = root.querySelector('[data-batch-items="' + batchId + '"]');
    if (el) el.innerHTML = '';
    return;
  }
  _batchExpanded[batchId] = true;
  fillBatchItems(api, batchId, root);
}

function bindEvents(root, api) {
  root.querySelectorAll('[data-open-row]').forEach(function (el) {
    el.addEventListener('click', function () {
      var id = el.getAttribute('data-open-row');
      if (id && window.rbcpOpenReader) window.rbcpOpenReader(id);
    });
  });
  root.querySelectorAll('[data-open]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      e.stopPropagation();
      var id = el.getAttribute('data-open');
      if (id && window.rbcpOpenReader) window.rbcpOpenReader(id);
    });
  });
  root.querySelectorAll('[data-retry]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      e.stopPropagation();
      var id = el.getAttribute('data-retry');
      if (!id) return;
      el.disabled = true;
      el.textContent = '\u91cd\u8bd5\u4e2d...';
      api.retryJob(id).then(function () {
        return load(root, api);
      }).catch(function () {
        el.disabled = false;
        el.textContent = '\u21bb \u91cd\u8bd5';
      });
    });
  });
  root.querySelectorAll('[data-del]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      e.stopPropagation();
      var id = el.getAttribute('data-del');
      if (!id) return;
      el.disabled = true;
      el.textContent = '删除中...';
      api.deleteJob(id).then(function () {
        return load(root, api);
      }).catch(function () {
        el.disabled = false;
        el.textContent = '删除';
      });
    });
  });
  root.querySelectorAll('[data-detail]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      e.stopPropagation();
      var id = el.getAttribute('data-detail');
      var det = document.getElementById('faildet-' + id);
      if (det) det.style.display = det.style.display === 'none' ? 'block' : 'none';
    });
  });
  root.querySelectorAll('[data-batch-toggle]').forEach(function (el) {
    el.addEventListener('click', function () {
      var bid = el.getAttribute('data-batch-toggle');
      if (bid) expandBatch(api, bid, root);
    });
  });
  root.querySelectorAll('[data-filter]').forEach(function (el) {
    el.addEventListener('click', function () {
      var f = el.getAttribute('data-filter');
      if (!f || f === _filter) return;
      _filter = f;
      _lastSig = null;   // 强制重渲染（数据没变但筛选变了）
      load(root, api);
    });
  });
  root.querySelectorAll('[data-reload]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      e.stopPropagation();
      location.reload();
    });
  });
}

function load(container, api) {
  var batchP = Promise.resolve(null);
  var jobsP = api.getJobs().catch(function (e) { return { _error: e }; });

  try {
    batchP = api.getBatches().catch(function () { return null; });
  } catch (_e) { /* ok */ }

  return Promise.all([batchP, jobsP]).then(function (results) {
    var batches = results[0];
    var jobs = results[1];

    // 数据没变就不重渲染——否则 2 秒一次的轮询会把用户手动展开的失败「详情」
    // 和批次明细冲掉（与 WebUI refreshBatches 的 signature 同思路）。
    var sig = _filter + '|' + JSON.stringify(batches) + '|' + JSON.stringify(jobs)
      + '|' + Object.keys(_batchExpanded).filter(function (k) { return _batchExpanded[k]; }).join(',');
    if (sig === _lastSig) return;
    _lastSig = sig;

    var html = '';

    // 批次卡片是聚合视图——只在「全部」筛选下显示；选了具体状态时只看任务行，
    // 否则会出现「批次显示全量计数、任务行却被筛掉」的两层可见性不一致。
    if (_filter === 'all' && Array.isArray(batches) && batches.length) {
      html += batches.map(renderBatch).join('');
    }

    if (jobs && jobs._error) {
      var msg = (jobs._error && jobs._error.detail) || (jobs._error && jobs._error.message) || '\u52a0\u8f7d\u5931\u8d25';
      html +=
        '<div class="job"><div class="st fail"><span class="dot fail"></span>\u9519\u8bef</div>' +
        '<div class="info"><div class="jt" style="color:var(--rb-red)">\u65e0\u6cd5\u52a0\u8f7d\u4efb\u52a1\u5217\u8868</div>' +
        '<div class="ju"><span class="fail-note">' + esc(msg) + '</span></div></div>' +
        '<div class="act"><button class="mini" data-reload="1">\u5237\u65b0</button></div></div>';
    } else if (Array.isArray(jobs) && jobs.length) {
      // \u72b6\u6001\u7b5b\u9009 chip\uff08\u8ba1\u6570\u7528\u5168\u91cf jobs\uff09+ \u8fc7\u6ee4\u540e\u7684\u5217\u8868
      html += renderFilterBar(jobs);
      var view = applyFilter(jobs);
      if (view.length) {
        html += view.map(renderJob).join('');
      } else {
        html += '<div class="empty">\u6ca1\u6709\u300c' + esc(STATUS_LABEL[_filter] || _filter) + '\u300d\u7684\u4efb\u52a1</div>';
      }
    } else if (!(Array.isArray(batches) && batches.length)) {
      html += '<div class="empty">\u6682\u65e0\u4efb\u52a1 \u00b7 \u5728\u5de6\u4e0a\u89d2\u7c98\u8d34\u94fe\u63a5\u5f00\u59cb\u8f6c\u5f55</div>';
    }

    container.innerHTML = html;
    bindEvents(container, api);
    // 重渲染会清空批次明细 DOM——把仍处于展开态的批次重新填回，否则用户得再点一次。
    Object.keys(_batchExpanded).forEach(function (bid) {
      if (_batchExpanded[bid]) fillBatchItems(api, bid, container);
    });
  });
}

export function render(container, api) {
  if (_timer) { clearInterval(_timer); _timer = null; }
  _lastSig = null;  // 容器是新空的，强制首帧渲染（否则沿用旧 signature 会留白）
  container.innerHTML = '<div class="loading"><span class="spinner"></span>加载中…</div>';
  load(container, api);
  _timer = setInterval(function () { load(container, api); }, 2000);
}
