/* settings screen - local-only config UI */

var STORAGE_PREFIX = 'rbcp.';

var FIELD_MAP = [
  { id: 's-apiKey',        key: 'apiKey',        type: 'password', label: '\u767e\u7ec4 API Key',
    desc: 'DashScope key\uff0c\u7528\u4e8e ASR / VLM / \u901f\u89c8 LLM\u3002\u53ea\u5b58\u672c\u673a\uff0c\u4e0d\u4e0a\u4f20\u3002',
    placeholder: 'sk-xxxxxx' },
  { id: 's-transcriptDir', key: 'transcriptDir',  type: 'text',     label: '\u77e5\u8bc6\u5e93\u8f93\u51fa\u76ee\u5f55',
    desc: 'Markdown \u5b58\u653e\u5904\uff08\u53ea\u653e .md + \u7d22\u5f15\uff0c\u4e0d\u6df7\u5a92\u4f53\uff09\u3002',
    placeholder: '~/transcript' },
  { id: 's-proxy',         key: 'proxy',          type: 'text',     label: '\u4ee3\u7406\uff08\u53ef\u9009\uff09',
    desc: 'RBCP_PROXY\uff0c\u6279\u91cf\u4e0b\u8f7d\u62a4 IP \u7528\u3002',
    placeholder: 'http://127.0.0.1:7897' }
];

var MODEL_FIELDS = [
  { id: 's-asrModel', key: 'asrModel', label: 'ASR \u6a21\u578b', ph: 'paraformer-v2' },
  { id: 's-vlmModel', key: 'vlmModel', label: 'VLM \u6a21\u578b', ph: 'qwen3-vl-flash' },
  { id: 's-llmModel', key: 'llmModel', label: 'LLM \u6a21\u578b', ph: 'qwen-plus' }
];

function esc(s) {
  if (s == null) return '';
  var d = document.createElement('div');
  d.appendChild(document.createTextNode(String(s)));
  return d.innerHTML;
}

function readStore(key) {
  try { return localStorage.getItem(STORAGE_PREFIX + key) || ''; } catch (_) { return ''; }
}

function writeStore(key, val) {
  try { localStorage.setItem(STORAGE_PREFIX + key, val); } catch (_) { /* noop */ }
}

/* build form HTML */
function buildForm() {
  var html = '';
  html += '<div class="page-head">'
    + '<img class="ph-ic" src="https://api.iconify.design/flat-color-icons/settings.svg" alt="">'
    + '<h2>\u8bbe\u7f6e</h2>'
    + '<span class="sub">\u5b58\u5728\u672c\u673a \u00b7 \u4e0d\u4e0a\u4f20</span>'
    + '</div>';
  html += '<div class="page-body"><div class="form">';

  /* text / password fields */
  for (var i = 0; i < FIELD_MAP.length; i++) {
    var f = FIELD_MAP[i];
    var val = esc(readStore(f.key));
    html += '<div class="field">'
      + '<label>' + esc(f.label) + '</label>'
      + '<div class="desc">' + esc(f.desc) + '</div>'
      + '<input id="' + f.id + '" type="' + f.type + '" value="' + val + '" placeholder="' + esc(f.placeholder) + '">'
      + '</div>';
  }

  /* model fields: first two in a row, third below */
  html += '<div class="row2">';
  for (var j = 0; j < 2; j++) {
    var m = MODEL_FIELDS[j];
    var mv = esc(readStore(m.key));
    html += '<div class="field">'
      + '<label>' + esc(m.label) + '</label>'
      + '<input id="' + m.id + '" value="' + mv + '" placeholder="' + m.ph + '">'
      + '</div>';
  }
  html += '</div>';
  /* LLM model below the row */
  var m3 = MODEL_FIELDS[2];
  var m3v = esc(readStore(m3.key));
  html += '<div class="field">'
    + '<label>' + esc(m3.label) + '</label>'
    + '<input id="' + m3.id + '" value="' + m3v + '" placeholder="' + m3.ph + '">'
    + '</div>';

  /* save button */
  html += '<button class="btn-primary" id="s-save"><i data-lucide="check"></i>\u4fdd\u5b58\u8bbe\u7f6e</button>';
  html += '<span id="s-feedback" style="margin-left:12px;font-size:13px;color:var(--rb-green);display:none">\u5df2\u4fdd\u5b58</span>';

  html += '</div></div>';
  return html;
}

/* wire up save */
function bindSave() {
  var btn = document.getElementById('s-save');
  if (!btn) return;
  btn.addEventListener('click', function () {
    /* plain text fields */
    for (var i = 0; i < FIELD_MAP.length; i++) {
      var f = FIELD_MAP[i];
      var el = document.getElementById(f.id);
      writeStore(f.key, el ? el.value.trim() : '');
    }
    /* model fields */
    for (var j = 0; j < MODEL_FIELDS.length; j++) {
      var m = MODEL_FIELDS[j];
      var mel = document.getElementById(m.id);
      writeStore(m.key, mel ? mel.value.trim() : '');
    }
    /* feedback */
    var fb = document.getElementById('s-feedback');
    if (fb) {
      fb.style.display = 'inline';
      clearTimeout(fb._timer);
      fb._timer = setTimeout(function () { fb.style.display = 'none'; }, 2000);
    }
  });
}

export function render(container, api) {
  container.innerHTML = buildForm();
  bindSave();
  if (window.lucide) window.lucide.createIcons();
}
