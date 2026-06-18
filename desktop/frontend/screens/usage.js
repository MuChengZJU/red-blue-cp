// 逐篇明细排序态（跨重渲染保持）：cost-desc / cost-asc / time-desc / time-asc
let _billSort = 'cost-desc';

/** @param {HTMLElement} container @param {import('../api.js').api} api */
export async function render(container, api) {
  // Loading state
  container.innerHTML = '<div class="page-head"><h2>账单</h2><span class="sub">加载中…</span></div>';

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  var data;
  var jobs = [];
  try {
    data = await api.getStats();
    try { jobs = await api.getJobs(); } catch (_je) { jobs = []; }
  } catch (_e) {
    container.innerHTML =
      '<div class="page-head"><h2>账单</h2><span class="sub">加载失败</span></div>' +
      '<div class="page-body"><div class="panel"><p style="color:var(--rb-red);font-size:13px;font-weight:600">无法获取费用数据，请检查后端是否运行。</p></div></div>';
    return;
  }

  if (!data || !data.by_stage || Object.keys(data.by_stage).length === 0) {
    container.innerHTML =
      '<div class="page-head"><h2>账单</h2><span class="sub">暂无数据</span></div>' +
      '<div class="page-body"><div class="panel"><p style="color:var(--muted);font-size:13px;font-weight:600">还没有产生任何费用记录。</p></div></div>';
    return;
  }

  var total = Number(data.total_cost_yuan) || 0;
  var stages = data.by_stage;

  // Sync sidebar cumulative cost
  var cumEl = document.getElementById('cum-cost');
  if (cumEl) cumEl.textContent = '\u00a5' + total.toFixed(2);

  // Friendly stage names
  var NAMES = {
    asr: '语音转写',
    vlm: '图文理解',
    llm_clean: '清洗',
    digest: '速览生成',
    download: '下载'
  };

  // Bar colors cycle
  var COLORS = [
    'var(--rb-blue)',
    'var(--rb-red)',
    'var(--rb-green)',
    'var(--rb-amber)'
  ];

  // Find max cost for bar scaling
  var maxCost = 0;
  var stageKeys = Object.keys(stages);
  for (var i = 0; i < stageKeys.length; i++) {
    var c = Number(stages[stageKeys[i]].cost_yuan) || 0;
    if (c > maxCost) maxCost = c;
  }

  // Format elapsed seconds
  function fmtSec(s) {
    if (s == null) return '\u2014';
    var n = Number(s);
    if (isNaN(n)) return '\u2014';
    if (n < 60) return n.toFixed(1) + 's';
    var m = Math.floor(n / 60);
    var r = Math.round(n % 60);
    return m + 'm ' + r + 's';
  }

  // Build stat-row (total)
  var html =
    '<div class="page-head">' +
    '<img class="ph-ic" src="https://api.iconify.design/flat-color-icons/currency-exchange.svg" alt="">' +
    '<h2>\u8d26\u5355</h2>' +
    '<span class="sub">\u6309\u5b9e\u9645\u7528\u91cf\u4f30\u7b97</span>' +
    '</div>' +
    '<div class="page-body">' +
    '<div class="stat-row">' +
    '<div class="stat"><div class="v blue">\u00a5' + total.toFixed(2) + '</div><div class="k">\u7d2f\u8ba1\u8d39\u7528</div></div>' +
    '</div>';

  // Build by-stage bar panel
  html += '<div class="panel"><h3>\u6309\u73af\u8282</h3>';
  for (var j = 0; j < stageKeys.length; j++) {
    var key = stageKeys[j];
    var stg = stages[key];
    var cost = Number(stg.cost_yuan) || 0;
    var pct = maxCost > 0 ? Math.round((cost / maxCost) * 100) : 0;
    var color = COLORS[j % COLORS.length];
    html +=
      '<div class="brk">' +
      '<div class="nm">' + (NAMES[key] || key) + '</div>' +
      '<div class="bar"><i style="width:' + pct + '%;background:' + color + '"></i></div>' +
      '<div class="amt">\u00a5' + cost.toFixed(2) + '</div>' +
      '</div>';
  }
  html += '</div>';

  // Detail panel: each stage with elapsed + count
  html += '<div class="panel"><h3>\u73af\u8282\u8be6\u60c5</h3>';
  for (var k = 0; k < stageKeys.length; k++) {
    var sk = stageKeys[k];
    var sv = stages[sk];
    html +=
      '<div class="cost-row">' +
      '<div class="ct">' + (NAMES[sk] || sk) + '</div>' +
      '<div class="tm">' +
      '<span class="tmchip">\u8017\u65f6 ' + fmtSec(sv.elapsed_seconds) + '</span>' +
      '<span class="tmchip">' + (sv.count || 0) + ' \u6b21</span>' +
      '</div>' +
      '<div class="ca">\u00a5' + (Number(sv.cost_yuan) || 0).toFixed(2) + '</div>' +
      '</div>';
  }
  html += '</div>';

  // 逐篇明细占位：表格 + 可排序（费用 / 时间），渲染后填充。
  html += '<div class="panel" id="bill-detail"></div>';

  html += '</div>'; // page-body

  container.innerHTML = html;

  // ── 逐篇明细：表格 + 表头点击按「费用 / 时间」排序（替代原来的列表 + chip）──
  var PLAT = { bilibili: 'B站', xiaohongshu: '小红书' };
  var billed = (jobs || []).filter(function (j) {
    return j && j.usage && Number(j.usage.total_cost_yuan) > 0;
  });

  function fmtDate(s) {
    if (!s) return '—';
    var d = new Date(s);
    if (isNaN(d.getTime())) return esc(s);
    var p = function (n) { return (n < 10 ? '0' : '') + n; };
    return (d.getMonth() + 1) + '/' + d.getDate() + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function billRowHtml(bj) {
    var bt = esc(bj.title || bj.url || '无标题');
    var plat = PLAT[bj.platform] || esc(bj.platform || '');
    var bcost = Number(bj.usage.total_cost_yuan) || 0;
    // 同环节多次调用聚合成一个 chip（如 6 次图文理解合并）
    var evs = bj.usage.events || [];
    var agg = {}, order = [];
    for (var ei = 0; ei < evs.length; ei++) {
      var ev = evs[ei], st = ev.stage || 'unknown';
      if (!agg[st]) { agg[st] = { cost: 0, n: 0 }; order.push(st); }
      agg[st].cost += Number(ev.cost_yuan) || 0;
      agg[st].n += 1;
    }
    var chips = '';
    for (var oi = 0; oi < order.length; oi++) {
      var st2 = order[oi];
      var times = agg[st2].n > 1 ? ' ×' + agg[st2].n : '';
      chips += '<span class="tmchip">' + (NAMES[st2] || esc(st2)) +
        times + ' ¥' + agg[st2].cost.toFixed(3) + '</span>';
    }
    return '<tr>' +
      '<td class="bill-title" title="' + bt + '"><span class="tmchip">' + plat + '</span> ' + bt + '</td>' +
      '<td class="bill-chips">' + chips + '</td>' +
      '<td class="bill-cost">¥' + bcost.toFixed(3) + '</td>' +
      '<td class="bill-time">' + fmtDate(bj.created_at) + '</td>' +
      '</tr>';
  }

  function renderBillTable() {
    var panel = document.getElementById('bill-detail');
    if (!panel) return;
    if (billed.length === 0) {
      panel.innerHTML = '<h3>逐篇明细</h3><p style="color:var(--muted);font-size:13px;font-weight:600">还没有按篇计费的记录。</p>';
      return;
    }
    var asc = _billSort.indexOf('-asc') !== -1;
    var byTime = _billSort.indexOf('time') === 0;
    var dir = asc ? 1 : -1;
    billed.sort(function (a, b) {
      if (byTime) return dir * String(a.created_at || '').localeCompare(String(b.created_at || ''));
      return dir * (Number(a.usage.total_cost_yuan) - Number(b.usage.total_cost_yuan));
    });
    var arrow = function (col) {
      if (_billSort.indexOf(col) !== 0) return '';
      return asc ? ' ↑' : ' ↓';
    };
    var rows = '';
    for (var bi = 0; bi < billed.length; bi++) rows += billRowHtml(billed[bi]);
    panel.innerHTML =
      '<h3>逐篇明细 · ' + billed.length + ' 篇</h3>' +
      '<table class="bill-table"><thead><tr>' +
      '<th>内容</th><th>环节</th>' +
      '<th class="sortable" data-sort="cost">费用' + arrow('cost') + '</th>' +
      '<th class="sortable" data-sort="time">时间' + arrow('time') + '</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';
    panel.querySelectorAll('th.sortable').forEach(function (th) {
      th.addEventListener('click', function () {
        var col = th.getAttribute('data-sort');
        // 同列再点切升/降；切到另一列默认降序
        _billSort = (_billSort === col + '-desc') ? col + '-asc' : col + '-desc';
        renderBillTable();
      });
    });
  }
  renderBillTable();
}
