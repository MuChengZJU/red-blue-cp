/** @param {HTMLElement} container @param {import('../api.js').api} api */
export async function render(container, api) {
  // Loading state
  container.innerHTML = '<div class="page-head"><h2>账单</h2><span class="sub">加载中…</span></div>';

  var data;
  try {
    data = await api.getStats();
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

  html += '</div>'; // page-body

  container.innerHTML = html;
}
