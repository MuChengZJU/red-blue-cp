/* settings screen —— 接后端配置（写 os.environ + 配置 .env，转录真正用得上） */

function esc(s) {
  if (s == null) return '';
  var d = document.createElement('div');
  d.appendChild(document.createTextNode(String(s)));
  return d.innerHTML;
}

// UI 字段 → 后端 config 字段名
var TEXT_FIELDS = [
  { id: 's-output', key: 'output_dir', label: '知识库输出目录',
    desc: 'Markdown 存放处（只放 .md + 索引，不混媒体）。', ph: '~/transcript', dir: true },
  { id: 's-proxy', key: 'proxy', label: '代理（可选）',
    desc: 'RBCP_PROXY，批量下载护 IP 用。', ph: 'http://127.0.0.1:7897' }
];

var MODEL_FIELDS = [
  { id: 's-asr', key: 'asr_model', label: 'ASR 模型', ph: 'paraformer-v2' },
  { id: 's-vlm', key: 'vlm_model', label: 'VLM 模型', ph: 'qwen3-vl-flash' },
  { id: 's-llm', key: 'llm_model', label: 'LLM 模型', ph: 'qwen-plus' }
];

function buildForm(cfg) {
  var keySet = cfg && cfg.dashscope_key_set;
  var html = '';
  html += '<div class="page-head">'
    + '<img class="ph-ic" src="https://api.iconify.design/flat-color-icons/settings.svg" alt="">'
    + '<h2>设置</h2>'
    + '<span class="sub">存在本机 · 不上传</span>'
    + '</div>';
  html += '<div class="page-body"><div class="form">';

  // 百炼 API Key（password）。已配置则留空+占位提示（留空=不改）
  html += '<div class="field">'
    + '<label>百炼 API Key</label>'
    + '<div class="desc">DashScope key，用于 ASR / VLM / 速览 LLM。只存本机，不上传。</div>'
    + '<input id="s-key" type="password" value="" placeholder="'
    + (keySet ? '已配置 ' + esc(cfg.dashscope_key_masked) + '（留空不改）' : 'sk-xxxxxx')
    + '">'
    + '</div>';

  // 文本字段（输出目录带"选择…"原生选择框）
  for (var i = 0; i < TEXT_FIELDS.length; i++) {
    var f = TEXT_FIELDS[i];
    var val = esc((cfg && cfg[f.key]) || '');
    var pick = f.dir
      ? '<button class="btn-soft" id="' + f.id + '-pick" type="button" style="margin-top:6px">选择文件夹…</button>'
      : '';
    html += '<div class="field">'
      + '<label>' + esc(f.label) + '</label>'
      + '<div class="desc">' + esc(f.desc) + '</div>'
      + '<input id="' + f.id + '" type="text" value="' + val + '" placeholder="' + esc(f.ph) + '">'
      + pick
      + '</div>';
  }

  // 模型字段
  html += '<div class="row2">';
  for (var j = 0; j < 2; j++) {
    var m = MODEL_FIELDS[j];
    html += '<div class="field"><label>' + esc(m.label) + '</label>'
      + '<input id="' + m.id + '" value="' + esc((cfg && cfg[m.key]) || '') + '" placeholder="' + m.ph + '"></div>';
  }
  html += '</div>';
  var m3 = MODEL_FIELDS[2];
  html += '<div class="field"><label>' + esc(m3.label) + '</label>'
    + '<input id="' + m3.id + '" value="' + esc((cfg && cfg[m3.key]) || '') + '" placeholder="' + m3.ph + '"></div>';

  html += '<button class="btn-primary" id="s-save"><i data-lucide="check"></i>保存设置</button>';
  html += '<span id="s-fb" style="margin-left:12px;font-size:13px;display:none"></span>';
  html += '</div></div>';
  return html;
}

function feedback(msg, ok) {
  var fb = document.getElementById('s-fb');
  if (!fb) return;
  fb.textContent = msg;
  fb.style.color = ok ? 'var(--rb-green)' : 'var(--rb-red)';
  fb.style.display = 'inline';
  clearTimeout(fb._t);
  fb._t = setTimeout(function () { fb.style.display = 'none'; }, 2600);
}

function bind(api) {
  // 原生文件夹选择（Tauri dialog；浏览器 dev 无则提示手动输入）
  var pick = document.getElementById('s-output-pick');
  if (pick) {
    pick.addEventListener('click', function () {
      var dlg = window.__TAURI__ && window.__TAURI__.dialog;
      if (!dlg || !dlg.open) {
        feedback('浏览器环境无系统选择框，请手动输入路径', false);
        return;
      }
      dlg.open({ directory: true, multiple: false }).then(function (sel) {
        if (sel) document.getElementById('s-output').value = sel;
      });
    });
  }

  var btn = document.getElementById('s-save');
  if (!btn) return;
  btn.addEventListener('click', function () {
    var payload = {};
    var key = document.getElementById('s-key');
    if (key && key.value.trim()) payload.dashscope_key = key.value.trim();  // 留空=不改
    for (var i = 0; i < TEXT_FIELDS.length; i++) {
      var f = TEXT_FIELDS[i];
      var el = document.getElementById(f.id);
      if (el) payload[f.key] = el.value.trim();
    }
    for (var j = 0; j < MODEL_FIELDS.length; j++) {
      var m = MODEL_FIELDS[j];
      var mel = document.getElementById(m.id);
      if (mel) payload[m.key] = mel.value.trim();
    }
    btn.disabled = true;
    api.setConfig(payload).then(function () {
      feedback('已保存（立即生效）', true);
      if (key) key.value = '';  // 清空 key 输入，避免明文停留
    }).catch(function (e) {
      feedback('保存失败：' + ((e && e.detail) || '后端未响应'), false);
    }).then(function () { btn.disabled = false; });
  });
}

export function render(container, api) {
  container.innerHTML = '<div class="placeholder">加载设置…</div>';
  api.getConfig().then(function (cfg) {
    container.innerHTML = buildForm(cfg);
    bind(api);
    if (window.lucide) window.lucide.createIcons();
  }).catch(function () {
    // 后端拿不到也给空表单（至少能填）
    container.innerHTML = buildForm(null);
    bind(api);
    if (window.lucide) window.lucide.createIcons();
  });
}
