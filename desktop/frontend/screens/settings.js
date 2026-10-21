/* settings screen —— 自定义模型服务商（ASR / VLM / LLM 分能力配置）
 *
 * 后端契约：
 *   GET  /api/config        生效值（key 打码）+ presets
 *   POST /api/config        写 os.environ + 配置 .env
 *   POST /api/config/test   用当前生效配置探测某个能力
 *
 * 设计取舍：
 * - 测试连接前先保存（否则测的是旧配置），按钮文案直接说明。
 * - key 永远只以打码形式回显；输入框留空 = 不改。
 * - VLM 默认继承 LLM 的 base_url/key，但表单里显式展示生效值，避免"看不见的继承"。
 */

function esc(s) {
  if (s == null) return '';
  var d = document.createElement('div');
  d.appendChild(document.createTextNode(String(s)));
  return d.innerHTML;
}

// 后端不可达时的兜底默认（与 app/model_endpoints.py 保持一致）
var FALLBACK = {
  provider_preset: 'qianwen',
  asr_base_url: 'https://cn-beijing.maas.qianwenaiapi.com/api/v1',
  asr_model: 'paraformer-v2',
  vlm_base_url: 'https://cn-beijing.maas.qianwenaiapi.com/compatible-mode/v1',
  vlm_model: 'qwen3.7-flash',
  llm_base_url: 'https://cn-beijing.maas.qianwenaiapi.com/compatible-mode/v1',
  llm_model: 'qwen3.7-flash',
  image_mode: 'auto',
  llm_thinking: false,
  vlm_thinking: false,
  output_dir: '',
  proxy: '',
  presets: [
    { id: 'qianwen', label: '千问AI平台（默认）',
      asr_base_url: 'https://cn-beijing.maas.qianwenaiapi.com/api/v1',
      llm_base_url: 'https://cn-beijing.maas.qianwenaiapi.com/compatible-mode/v1',
      asr_model: 'paraformer-v2', vlm_model: 'qwen3.7-flash', llm_model: 'qwen3.7-flash' },
    { id: 'custom', label: '自定义 OpenAI 兼容', asr_base_url: '', llm_base_url: '',
      asr_model: '', vlm_model: '', llm_model: '' }
  ]
};

var CAPABILITIES = [
  {
    prefix: 'asr', label: '语音转写 · ASR', badge: '异步任务',
    desc: '走 DashScope 原生异步转写协议（上传→提交→轮询）。需服务商兼容该协议；说话人分离依赖此协议。',
    modelHints: ['paraformer-v2', 'qwen3-asr-flash-filetrans', 'fun-asr']
  },
  {
    prefix: 'vlm', label: '图片理解 · VLM', badge: '多模态',
    desc: '小红书图文用它识图；OpenAI 兼容 /chat/completions。第三方服务商默认先下载图片转 base64，避免防盗链。',
    modelHints: ['qwen3.7-flash', 'qwen3.8-flash', 'qwen3.5-flash', 'qwen3-vl-plus']
  },
  {
    prefix: 'llm', label: '文本清洗 / 速览 · LLM', badge: '文本',
    desc: '字幕清洗与速览 JSON 生成；OpenAI 兼容 /chat/completions。',
    modelHints: ['qwen3.7-flash', 'qwen3.8-flash', 'qwen-plus', 'qwen3.5-flash']
  }
];

function cfgValue(cfg, key) {
  var v = cfg && cfg[key];
  if (v === undefined || v === null) v = FALLBACK[key];
  return v == null ? '' : String(v);
}

function presetsOf(cfg) {
  var list = (cfg && cfg.presets) || FALLBACK.presets;
  return list && list.length ? list : FALLBACK.presets;
}

function keyPlaceholder(cfg, prefix, genericLabel) {
  var set = cfg && cfg[prefix + '_api_key_set'];
  var masked = (cfg && cfg[prefix + '_api_key_masked']) || '';
  var source = (cfg && cfg[prefix + '_api_key_source']) || 'none';
  if (!set) return '可留空 · 使用' + genericLabel;
  if (source === 'shared') return '继承' + genericLabel + ' ' + masked + '（留空不改）';
  return '已配置 ' + masked + '（留空不改）';
}

function sectionHtml(cfg, cap) {
  var p = cap.prefix;
  var hints = cap.modelHints.map(function (m) { return '<option value="' + m + '">'; }).join('');
  var html = '<div class="settings-section">'
    + '<div class="settings-section-head"><h3>' + esc(cap.label) + '</h3>'
    + '<span class="settings-badge">' + esc(cap.badge) + '</span></div>'
    + '<div class="desc">' + esc(cap.desc) + '</div>';

  html += '<div class="field"><label>服务地址（base_url）</label>'
    + '<input id="s-' + p + '-base" type="text" value="' + esc(cfgValue(cfg, p + '_base_url')) + '"'
    + ' placeholder="https://.../v1">'
    + '</div>';

  html += '<div class="row2">'
    + '<div class="field"><label>模型名</label>'
    + '<input id="s-' + p + '-model" list="s-' + p + '-models" value="'
    + esc(cfgValue(cfg, p + '_model')) + '" placeholder="' + esc(cap.modelHints[0]) + '">'
    + '<datalist id="s-' + p + '-models">' + hints + '</datalist></div>';

  html += '<div class="field"><label>专用 API Key（可选）</label>'
    + '<input id="s-' + p + '-key" type="password" value="" placeholder="'
    + esc(keyPlaceholder(cfg, p, '通用 Key')) + '"></div>'
    + '</div>';

  if (p === 'vlm') {
    var mode = cfgValue(cfg, 'image_mode') || 'auto';
    html += '<div class="field"><label>图片传法</label>'
      + '<select id="s-image-mode">'
      + '<option value="auto"' + (mode === 'auto' ? ' selected' : '') + '>自动（推荐）</option>'
      + '<option value="url"' + (mode === 'url' ? ' selected' : '') + '>始终传 URL</option>'
      + '<option value="base64"' + (mode === 'base64' ? ' selected' : '') + '>始终转 base64</option>'
      + '</select><div class="desc">自动：千问/百炼传 URL，第三方服务商先下载转 base64；'
      + '服务端取图失败会自动回退一次。</div></div>';
  }

  if (p === 'vlm' || p === 'llm') {
    var thinkingOn = !!(cfg && cfg[p + '_thinking']);
    html += '<label class="settings-check">'
      + '<input type="checkbox" id="s-' + p + '-thinking"' + (thinkingOn ? ' checked' : '')
      + '> 开启思考模式（默认关：更便宜更快；复杂速览/识图再开）'
      + '</label>';
  }

  html += '<div class="settings-test">'
    + '<button class="btn-soft" id="s-' + p + '-test" type="button">测试连接（先保存）</button>'
    + '<span class="settings-test-out" id="s-' + p + '-test-out"></span>'
    + '</div>';

  return html + '</div>';
}

function buildForm(cfg) {
  var presets = presetsOf(cfg);
  var current = (cfg && cfg.provider_preset) || FALLBACK.provider_preset;
  var presetOpts = presets.map(function (p) {
    return '<option value="' + esc(p.id) + '"' + (p.id === current ? ' selected' : '') + '>'
      + esc(p.label) + '</option>';
  }).join('');

  var html = '';
  html += '<div class="page-head">'
    + '<img class="ph-ic" src="https://api.iconify.design/flat-color-icons/settings.svg" alt="">'
    + '<h2>设置</h2>'
    + '<span class="sub">存在本机 · 不上传</span>'
    + '</div>';
  html += '<div class="page-body"><div class="form">';

  html += '<div class="settings-section settings-provider">'
    + '<div class="settings-section-head"><h3>服务商</h3>'
    + '<span class="settings-badge">一键切换</span></div>'
    + '<div class="field"><label>预设</label>'
    + '<select id="s-preset">' + presetOpts + '</select>'
    + '<div class="desc">切换预设会同时改写 ASR / VLM / LLM 的服务地址；选「自定义」后可逐项填写。</div>'
    + '</div>'
    + '<div class="field"><label>通用 API Key</label>'
    + '<div class="desc">三个能力默认共用这个 key（DASHSCOPE_API_KEY）。只存本机，不上传。</div>'
    + '<input id="s-key" type="password" value="" placeholder="'
    + (cfg && cfg.dashscope_key_set
        ? '已配置 ' + esc(cfg.dashscope_key_masked) + '（留空不改）'
        : 'sk-xxxxxx')
    + '"></div>'
    + '</div>';

  for (var i = 0; i < CAPABILITIES.length; i++) {
    html += sectionHtml(cfg, CAPABILITIES[i]);
  }

  // 本地存储 / 网络
  html += '<div class="settings-section">'
    + '<div class="settings-section-head"><h3>本地与网络</h3></div>'
    + '<div class="field"><label>知识库输出目录</label>'
    + '<div class="desc">Markdown 存放处（只放 .md + 索引，不混媒体）。</div>'
    + '<input id="s-output" type="text" value="' + esc(cfgValue(cfg, 'output_dir')) + '" placeholder="~/transcript">'
    + '<button class="btn-soft" id="s-output-pick" type="button" style="margin-top:6px">选择文件夹…</button>'
    + '</div>'
    + '<div class="field"><label>代理（可选）</label>'
    + '<div class="desc">RBCP_PROXY，批量下载护 IP 用；留空=直连。</div>'
    + '<input id="s-proxy" type="text" value="' + esc(cfgValue(cfg, 'proxy')) + '" placeholder="http://127.0.0.1:7897">'
    + '</div>'
    + '</div>';

  html += '<div class="settings-actions">'
    + '<button class="btn-primary" id="s-save"><i data-lucide="check"></i>保存设置</button>'
    + '<span id="s-fb" class="settings-fb"></span>'
    + '</div>';
  html += '</div></div>';
  return html;
}

function feedback(msg, ok) {
  var fb = document.getElementById('s-fb');
  if (!fb) return;
  fb.textContent = msg;
  fb.className = 'settings-fb ' + (ok ? 'ok' : 'fail');
  clearTimeout(fb._t);
  fb._t = setTimeout(function () { fb.className = 'settings-fb'; }, 3200);
}

function testFeedback(prefix, msg, ok) {
  var out = document.getElementById('s-' + prefix + '-test-out');
  if (!out) return;
  out.textContent = msg;
  out.className = 'settings-test-out ' + (ok ? 'ok' : 'fail');
}

function collectPayload() {
  var payload = {};
  var key = document.getElementById('s-key');
  if (key && key.value.trim()) payload.dashscope_key = key.value.trim();

  for (var i = 0; i < CAPABILITIES.length; i++) {
    var p = CAPABILITIES[i].prefix;
    var base = document.getElementById('s-' + p + '-base');
    var model = document.getElementById('s-' + p + '-model');
    var capKey = document.getElementById('s-' + p + '-key');
    if (base) payload[p + '_base_url'] = base.value.trim();
    if (model) payload[p + '_model'] = model.value.trim();
    if (capKey && capKey.value.trim()) payload[p + '_api_key'] = capKey.value.trim();
    var think = document.getElementById('s-' + p + '-thinking');
    if (think) payload[p + '_thinking'] = think.checked;
  }
  var mode = document.getElementById('s-image-mode');
  if (mode) payload.image_mode = mode.value;

  var output = document.getElementById('s-output');
  var proxy = document.getElementById('s-proxy');
  if (output) payload.output_dir = output.value.trim();
  if (proxy) payload.proxy = proxy.value.trim();
  return payload;
}

function clearSecretInputs() {
  var key = document.getElementById('s-key');
  if (key) key.value = '';
  for (var i = 0; i < CAPABILITIES.length; i++) {
    var capKey = document.getElementById('s-' + CAPABILITIES[i].prefix + '-key');
    if (capKey) capKey.value = '';
  }
}

function save(api) {
  return api.setConfig(collectPayload()).then(function () {
    clearSecretInputs();
  });
}

function bindPreset(cfg) {
  var select = document.getElementById('s-preset');
  if (!select) return;
  var presets = presetsOf(cfg);
  select.addEventListener('change', function () {
    var chosen = null;
    for (var i = 0; i < presets.length; i++) {
      if (presets[i].id === select.value) chosen = presets[i];
    }
    if (!chosen || chosen.id === 'custom') return;
    var asr = document.getElementById('s-asr-base');
    var llm = document.getElementById('s-llm-base');
    var vlm = document.getElementById('s-vlm-base');
    if (asr && chosen.asr_base_url) asr.value = chosen.asr_base_url;
    if (llm && chosen.llm_base_url) llm.value = chosen.llm_base_url;
    if (vlm && chosen.llm_base_url) vlm.value = chosen.llm_base_url;
    // 预设同时带推荐模型（旧百炼的 VLM 必须回 qwen3-vl-flash）
    var models = { asr: chosen.asr_model, vlm: chosen.vlm_model, llm: chosen.llm_model };
    Object.keys(models).forEach(function (p) {
      var el = document.getElementById('s-' + p + '-model');
      if (el && models[p]) el.value = models[p];
    });
  });
}

function bindTestButtons(api) {
  for (var i = 0; i < CAPABILITIES.length; i++) {
    (function (cap) {
      var btn = document.getElementById('s-' + cap.prefix + '-test');
      if (!btn) return;
      btn.addEventListener('click', function () {
        btn.disabled = true;
        testFeedback(cap.prefix, '保存并测试中…', true);
        save(api).then(function () {
          return api.testConfig(cap.prefix);
        }).then(function (res) {
          if (res && res.ok) {
            var extra = res.elapsed_ms ? ' · ' + res.elapsed_ms + 'ms' : '';
            testFeedback(cap.prefix, '✓ ' + (res.model || '') + extra, true);
          } else {
            testFeedback(cap.prefix, '✗ ' + ((res && (res.detail || res.error)) || '未知错误'), false);
          }
        }).catch(function (e) {
          testFeedback(cap.prefix, '✗ ' + ((e && e.detail) || '后端未响应'), false);
        }).then(function () { btn.disabled = false; });
      });
    })(CAPABILITIES[i]);
  }
}

function bind(api, cfg) {
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

  bindPreset(cfg);
  bindTestButtons(api);

  var btn = document.getElementById('s-save');
  if (!btn) return;
  btn.addEventListener('click', function () {
    btn.disabled = true;
    save(api).then(function () {
      feedback('已保存（立即生效）', true);
    }).catch(function (e) {
      feedback('保存失败：' + ((e && e.detail) || '后端未响应'), false);
    }).then(function () { btn.disabled = false; });
  });
}

export function render(container, api) {
  container.innerHTML = '<div class="placeholder">加载设置…</div>';
  api.getConfig().then(function (cfg) {
    container.innerHTML = buildForm(cfg);
    bind(api, cfg);
    if (window.lucide) window.lucide.createIcons();
  }).catch(function () {
    // 后端拿不到也给空表单（至少能填）；测试连接会提示后端未响应
    container.innerHTML = buildForm(null);
    bind(api, null);
    if (window.lucide) window.lucide.createIcons();
  });
}
