import { api, configure } from './api.js';
import { render as renderLibrary } from './screens/library.js';
import { render as renderJobs } from './screens/jobs.js';
import { render as renderReader } from './screens/reader.js';
import { render as renderUsage } from './screens/usage.js';
import { render as renderSettings } from './screens/settings.js';
import { render as renderCompose } from './screens/compose.js';

const SCREENS = {
  library: renderLibrary,
  jobs: renderJobs,
  reader: renderReader,
  usage: renderUsage,
  settings: renderSettings,
};

let _readerJob = null;

function show(s) {
  document.querySelectorAll('.screen').forEach(function (el) {
    el.classList.toggle('active', el.id === s);
  });
  document.querySelectorAll('.nav-item').forEach(function (el) {
    el.classList.toggle('active', el.dataset.s === s);
  });
  if (SCREENS[s]) {
    var mount = document.querySelector('#' + s + ' .screen-mount');
    if (mount) SCREENS[s](mount, api, s === 'reader' ? _readerJob : undefined);
  }
}

// 跨屏契约：文件库/任务列表点条目 → 打开阅读器并传 jobId。
window.rbcpOpenReader = function (jobId) {
  _readerJob = jobId;
  show('reader');
};

// Bind nav items
document.querySelectorAll('.nav-item[data-s]').forEach(function (el) {
  el.addEventListener('click', function () {
    show(el.dataset.s);
  });
});

// 转录输入：表单提交（回车也触发）+ 实时平台检测提示
var urlForm = document.getElementById('url-form');
var urlInput = document.getElementById('url-input');
var submitHint = document.getElementById('submit-hint');

function detectPlatform(text) {
  var t = (text || '').toLowerCase();
  if (/bilibili\.com|b23\.tv|\bbv[0-9a-z]{8,}/.test(t)) return 'bilibili';
  if (/xiaohongshu\.com|xhslink\.com|xhs\.cn/.test(t)) return 'xiaohongshu';
  return null;
}

function updateHint() {
  if (!submitHint) return;
  var v = (urlInput && urlInput.value || '').trim();
  if (!v) { submitHint.className = 'submit-hint'; submitHint.textContent = ''; return; }
  var p = detectPlatform(v);
  if (p === 'bilibili') { submitHint.className = 'submit-hint ok'; submitHint.innerHTML = '<span class="plat b">B站</span> 识别成功，回车转录'; }
  else if (p === 'xiaohongshu') { submitHint.className = 'submit-hint ok'; submitHint.innerHTML = '<span class="plat x">小红书</span> 识别成功，回车转录'; }
  else { submitHint.className = 'submit-hint warn'; submitHint.textContent = '未识别链接 · 仅支持 B 站 / 小红书'; }
}

if (urlForm && urlInput) {
  var _submitting = false;  // 防连续回车重复建任务（后端 409 去重只拦"已完成"，挡不住并发中的）
  urlInput.addEventListener('input', updateHint);
  urlForm.addEventListener('submit', function (e) {
    e.preventDefault();
    if (_submitting || !urlInput.value.trim()) return;
    _submitting = true;
    var mount = document.querySelector('#compose-mount');
    if (mount) renderCompose(mount, api, urlInput.value);
    setTimeout(function () { _submitting = false; }, 1500);
  });
}

// Bind batch import button
var batchBtn = document.querySelector('.newblock .btn-soft');
if (batchBtn) {
  batchBtn.addEventListener('click', function () {
    var modal = document.getElementById('modal');
    if (modal) modal.classList.add('on');
  });
}

// Modal close
var modalBg = document.getElementById('modal');
if (modalBg) {
  modalBg.addEventListener('click', function (e) {
    if (e.target === modalBg) modalBg.classList.remove('on');
  });
  var cancelBtns = modalBg.querySelectorAll('.toggle, .btn-primary');
  cancelBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      modalBg.classList.remove('on');
    });
  });
}

// Boot：Tauri 环境先拿 serve 的 port/token 配好 api，再渲染首屏；
// 普通浏览器 dev 无 __TAURI__，走 api.js 默认 base（127.0.0.1:8000）。
async function boot() {
  var tauri = window.__TAURI__;
  if (tauri && tauri.core && typeof tauri.core.invoke === 'function') {
    // serve 后台异步起，config 可能没立即就绪 → 轮询直到拿到 port/token（最多 ~20s）。
    for (var i = 0; i < 40; i++) {
      try {
        var cfg = await tauri.core.invoke('get_api_config');
        if (cfg && cfg.port) {
          configure({ base: 'http://127.0.0.1:' + cfg.port, token: cfg.token });
          break;
        }
      } catch (e) { /* serve 还没就绪，稍后重试 */ }
      await new Promise(function (r) { setTimeout(r, 500); });
    }
  }
  show('jobs');
}
boot();

