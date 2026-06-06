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
      '<button id="export" class="btn-primary">导出 notes.json</button>'
    );
    document.getElementById("export").addEventListener("click", async () => {
      await execInPage(tab.id, triggerDump);
      window.close();
    });
    return;
  }

  // count>0 且未到底
  render(
    '已抓 <span class="count">' + count + "</span> 条，还没到底。<div class=\"hint\">请继续往下滑到页面底部，抓全后再导出。</div>",
    '<button id="export-partial" class="btn-secondary">仍导出这半份</button>'
  );
  document.getElementById("export-partial").addEventListener("click", async () => {
    await execInPage(tab.id, triggerDump);
    window.close();
  });
}

main();
