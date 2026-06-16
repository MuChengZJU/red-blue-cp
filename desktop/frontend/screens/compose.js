import { validateNotes } from '../lib/notes-schema.js';

// ── helpers ──────────────────────────────────────────────────────────

function escapeHtml(s) {
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function goToJobs() {
  var nav = document.querySelector('.nav-item[data-s=jobs]');
  if (nav) nav.click();
}

// ── A. single submit ─────────────────────────────────────────────────

export async function render(mount, api, url) {
  if (!url || !url.trim()) {
    mount.innerHTML = '<div class="compose-msg compose-warn">请输入链接</div>';
    return;
  }

  mount.innerHTML = '<div class="compose-msg">正在提交…</div>';

  try {
    await api.createJob(url.trim());
    mount.innerHTML = '<div class="compose-msg compose-ok">已加入队列</div>';
    goToJobs();
  } catch (err) {
    if (err && err.status === 409) {
      mount.innerHTML =
        '<div class="compose-msg compose-warn">这篇已经转录过或已在队列中</div>';
    } else {
      var detail = (err && err.detail) || '未知错误，请稍后重试';
      mount.innerHTML =
        '<div class="compose-msg compose-error">提交失败：' +
        escapeHtml(detail) +
        '</div>';
    }
  }
}

// ── B. batch import (self-init) ──────────────────────────────────────

function initBatch() {
  var modal = document.getElementById('modal');
  if (!modal) return;
  var box = modal.querySelector('.modal-mount');
  if (!box || box.dataset.composeInit) return;
  box.dataset.composeInit = '1';

  box.innerHTML =
    '<div class="batch-import">' +
      '<label class="batch-label">选择文件</label>' +
      '<input type="file" accept=".json" class="batch-file">' +
      '<label class="batch-label" style="margin-top:8px">或粘贴 JSON</label>' +
      '<textarea class="batch-textarea" rows="6" placeholder="粘贴 notes.json 内容…"></textarea>' +
      '<button class="btn-primary batch-go" style="margin-top:10px">导入并转录</button>' +
      '<div class="batch-result"></div>' +
    '</div>';

  var fileInput = box.querySelector('.batch-file');
  var textarea  = box.querySelector('.batch-textarea');
  var goBtn     = box.querySelector('.batch-go');
  var resultDiv = box.querySelector('.batch-result');

  fileInput.addEventListener('change', function () {
    var file = fileInput.files && fileInput.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function () {
      textarea.value = reader.result;
    };
    reader.readAsText(file);
  });

  goBtn.addEventListener('click', async function () {
    resultDiv.textContent = '';
    var raw = textarea.value.trim();
    if (!raw) {
      resultDiv.innerHTML =
        '<span class="compose-warn">请先选择文件或粘贴 JSON 内容</span>';
      return;
    }

    var parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (_e) {
      resultDiv.innerHTML =
        '<span class="compose-error">JSON 解析失败，请检查格式是否正确</span>';
      return;
    }

    var v = validateNotes(parsed);
    if (!v.ok) {
      resultDiv.innerHTML =
        '<div class="compose-error">校验未通过：<br>' +
        v.errors.map(function (e) { return '· ' + escapeHtml(e); }).join('<br>') +
        '</div>';
      return;
    }

    goBtn.disabled = true;
    goBtn.textContent = '导入中…';

    try {
      var res = await api.importList(parsed);
      var count = res && (res.imported || res.count || (res.notes && res.notes.length));
      resultDiv.innerHTML =
        '<span class="compose-ok">成功导入 ' +
        (count != null ? count : '全部') +
        ' 条</span>';
      modal.classList.remove('on');
      goToJobs();
    } catch (err) {
      var detail = (err && err.detail) || '未知错误，请稍后重试';
      resultDiv.innerHTML =
        '<span class="compose-error">导入失败：' + escapeHtml(detail) + '</span>';
    } finally {
      goBtn.disabled = false;
      goBtn.textContent = '导入并转录';
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initBatch);
} else {
  initBatch();
}
