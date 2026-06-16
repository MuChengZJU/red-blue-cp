let _timer = null;
var _batchExpanded = {};

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
    actions = '<button class="mini red" data-retry="' + esc(job.id) + '">\u21bb \u91cd\u8bd5</button>';
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
  var done = batch.done_count != null ? batch.done_count : 0;
  var total = batch.total_count != null ? batch.total_count : 0;
  var running = batch.running_count != null ? batch.running_count : 0;
  var pending = batch.pending_count != null ? batch.pending_count : 0;
  var failed = batch.failed_count != null ? batch.failed_count : 0;
  var pct = total > 0 ? Math.round((done / total) * 100) : 0;

  var counts = '\u5b8c\u6210 ' + done +
    (running ? ' \u00b7 \u4e0b\u8f7d\u4e2d ' + running : '') +
    (pending ? ' \u00b7 \u6392\u961f ' + pending : '') +
    (failed ? ' \u00b7 \u5931\u8d25 ' + failed : '');

  return (
    '<div class="batch" data-batch-id="' + esc(batch.id) + '">' +
    '<div class="bt" data-batch-toggle="' + esc(batch.id) + '" style="cursor:pointer">\ud83d\udce6 ' + title + '</div>' +
    '<div class="counts">' + counts + '</div>' +
    '<div class="progress" style="width:100%;margin-top:10px"><i style="width:' + pct + '%"></i></div>' +
    '<div class="batch-items" data-batch-items="' + esc(batch.id) + '"></div>' +
    '</div>'
  );
}

function expandBatch(api, batchId, root) {
  if (_batchExpanded[batchId]) {
    _batchExpanded[batchId] = false;
    var el = root.querySelector('[data-batch-items="' + batchId + '"]');
    if (el) el.innerHTML = '';
    return;
  }
  _batchExpanded[batchId] = true;
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
  root.querySelectorAll('[data-batch-toggle]').forEach(function (el) {
    el.addEventListener('click', function () {
      var bid = el.getAttribute('data-batch-toggle');
      if (bid) expandBatch(api, bid, root);
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
    var html = '';

    if (Array.isArray(batches) && batches.length) {
      html += batches.map(renderBatch).join('');
    }

    if (jobs && jobs._error) {
      var msg = (jobs._error && jobs._error.detail) || (jobs._error && jobs._error.message) || '\u52a0\u8f7d\u5931\u8d25';
      html +=
        '<div class="job"><div class="st fail"><span class="dot fail"></span>\u9519\u8bef</div>' +
        '<div class="info"><div class="jt" style="color:var(--rb-red)">\u65e0\u6cd5\u52a0\u8f7d\u4efb\u52a1\u5217\u8868</div>' +
        '<div class="ju"><span class="fail-note">' + esc(msg) + '</span></div></div>' +
        '<div class="act"><button class="mini" onclick="location.reload()">\u5237\u65b0</button></div></div>';
    } else if (Array.isArray(jobs) && jobs.length) {
      html += jobs.map(renderJob).join('');
    } else {
      html += '<div style="padding:40px 0;text-align:center;color:var(--muted);font-weight:600;font-size:13px">\u6682\u65e0\u4efb\u52a1</div>';
    }

    container.innerHTML = html;
    bindEvents(container, api);
  });
}

export function render(container, api) {
  if (_timer) { clearInterval(_timer); _timer = null; }
  load(container, api);
  _timer = setInterval(function () { load(container, api); }, 2000);
}
