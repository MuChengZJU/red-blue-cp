// Red Blue CP popup：读当前页抓取状态，按需触发导出。
// 不自动下载——只有用户点按钮才导出，避免弹下载烦人。

const statusEl = document.getElementById("status");
const actionsEl = document.getElementById("actions");

const XHS_HOST = "www.xiaohongshu.com";

// 在页面主世界读 __rbcpEnvelope() 的轻量字段（不取 notes 数组，省得序列化整份）
function readState() {
  const env = window.__rbcpEnvelope && window.__rbcpEnvelope();
  if (!env) return { ready: false };
  return {
    ready: true,
    count: env.count || 0,
    complete: !!env.complete,
    user_id: env.user_id || "",
  };
}

// 在页面主世界触发下载
function triggerDump() {
  if (window.__rbcpDump) {
    window.__rbcpDump();
    return true;
  }
  return false;
}

// 在页面主世界取完整信封对象（含 notes 数组），序列化回 popup 用于复制
function readEnvelope() {
  const env = window.__rbcpEnvelope && window.__rbcpEnvelope();
  return env || null;
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function isXhs(tab) {
  if (!tab || !tab.url) return false;
  try {
    return new URL(tab.url).hostname === XHS_HOST;
  } catch (e) {
    return false;
  }
}

async function execInPage(tabId, func) {
  const [res] = await chrome.scripting.executeScript({
    target: { tabId },
    world: "MAIN",
    func,
  });
  return res && res.result;
}

function render(html, actionsHtml) {
  statusEl.innerHTML = html;
  actionsEl.innerHTML = actionsHtml || "";
}

// 复制完整信封 JSON 到剪贴板。partial=true 时附「半份」提示。
async function doCopy(tab, partial) {
  const toast = document.getElementById("toast");
  if (toast) toast.textContent = "复制中…";
  try {
    const env = await execInPage(tab.id, readEnvelope);
    if (!env) {
      if (toast) toast.textContent = "读取失败，请刷新小红书页面后重试。";
      return;
    }
    await navigator.clipboard.writeText(JSON.stringify(env, null, 2));
    const n = env.count || 0;
    if (toast) {
      toast.innerHTML =
        '<span class="ok">✓</span> 已复制 ' + n + " 条到剪贴板" +
        (partial ? "（半份，还没到底）" : "");
    }
  } catch (e) {
    if (toast) {
      toast.textContent =
        "复制失败：" + String((e && e.message) || e) +
        "。可改用「导出 notes.json」，或在 Console 跑 copy(JSON.stringify(__rbcpEnvelope()))。";
    }
  }
}

async function main() {
  const tab = await getActiveTab();

  if (!isXhs(tab)) {
    render('请在<strong>小红书页面</strong>使用本插件。', "");
    return;
  }

  let state;
  try {
    state = await execInPage(tab.id, readState);
  } catch (e) {
    render(
      '读取失败，请刷新小红书页面后重试。',
      '<div class="hint">' + String(e && e.message || e) + "</div>"
    );
    return;
  }

  if (!state || !state.ready) {
    render(
      "钩子还没就绪，请刷新本页后再打开插件。",
      ""
    );
    return;
  }

  const { count, complete } = state;

  if (count === 0) {
    render(
      '请在<strong>小红书博主主页</strong>打开，向下滑动开始抓取。',
      ""
    );
    return;
  }

  if (complete) {
    render(
      '已抓 <span class="count">' + count + "</span> 条 <span class=\"ok\">✓ 已到底</span>",
      '<button id="export" class="btn-primary">导出 notes.json</button>' +
        '<button id="copy" class="btn-blue">复制 JSON</button>' +
        '<div id="toast" class="hint"></div>'
    );
    document.getElementById("export").addEventListener("click", async () => {
      await execInPage(tab.id, triggerDump);
      window.close();
    });
    document.getElementById("copy").addEventListener("click", () => doCopy(tab, false));
    return;
  }

  // count>0 且未到底
  render(
    '已抓 <span class="count">' + count + "</span> 条，还没到底。<div class=\"hint\">请继续往下滑到页面底部，抓全后再导出。</div>",
    '<button id="export-partial" class="btn-secondary">仍导出这半份</button>' +
      '<button id="copy-partial" class="btn-blue">复制这半份 JSON</button>' +
      '<div id="toast" class="hint"></div>'
  );
  document.getElementById("export-partial").addEventListener("click", async () => {
    await execInPage(tab.id, triggerDump);
    window.close();
  });
  document.getElementById("copy-partial").addEventListener("click", () => doCopy(tab, true));
}

main();
