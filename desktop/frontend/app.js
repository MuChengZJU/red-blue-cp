import { api } from './api.js';
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

function show(s) {
  document.querySelectorAll('.screen').forEach(function (el) {
    el.classList.toggle('active', el.id === s);
  });
  document.querySelectorAll('.nav-item').forEach(function (el) {
    el.classList.toggle('active', el.dataset.s === s);
  });
  if (SCREENS[s]) {
    var mount = document.querySelector('#' + s + ' .screen-mount');
    if (mount) SCREENS[s](mount, api);
  }
}

// Bind nav items
document.querySelectorAll('.nav-item[data-s]').forEach(function (el) {
  el.addEventListener('click', function () {
    show(el.dataset.s);
  });
});

// Bind compose (new URL submit)
var urlInput = document.querySelector('.url-row input');
var submitBtn = document.querySelector('.url-row .btn-primary');
if (submitBtn && urlInput) {
  submitBtn.addEventListener('click', function () {
    var mount = document.querySelector('#compose-mount');
    if (mount) renderCompose(mount, api, urlInput.value);
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

// Boot
show('jobs');

