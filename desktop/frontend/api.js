let _base = "http://127.0.0.1:8000";
let _token = null;

export function configure({ base, token }) {
  if (base) _base = base;
  if (token !== undefined) _token = token;
}

async function _fetch(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  if (_token) headers["Authorization"] = "Bearer " + _token;
  const opts = { method, headers };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(_base + path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = j.detail || j.message || JSON.stringify(j); } catch (_e) { /* ignore */ }
    throw { status: res.status, detail };
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.text();
}

export const api = {
  getJobs()                  { return _fetch("GET",  "/api/jobs"); },
  createJob(url)             { return _fetch("POST", "/api/jobs", { url }); },
  retryJob(id)               { return _fetch("POST", "/api/jobs/" + id + "/retry"); },
  getJob(id)                 { return _fetch("GET",  "/api/jobs/" + id); },
  getMarkdown(id)            { return _fetch("GET",  "/api/jobs/" + id + "/markdown"); },
  getDigest(id)              { return _fetch("GET",  "/api/jobs/" + id + "/digest"); },
  deleteJob(id)              { return _fetch("DELETE", "/api/jobs/" + id); },
  getStats()                 { return _fetch("GET",  "/api/stats"); },
  getBatches()               { return _fetch("GET",  "/api/batches").then(function (r) { return (r && r.batches) || []; }); },
  getBatchItems(batchId)     { return _fetch("GET",  "/api/batches/" + batchId + "/items").then(function (r) { return (r && r.items) || []; }); },
  importList(payload)        { return _fetch("POST", "/api/import-list", payload); },
  getConfig()                { return _fetch("GET",  "/api/config"); },
  setConfig(payload)         { return _fetch("POST", "/api/config", payload); },
  downloadUrl(id)            { return _base + "/api/jobs/" + id + "/download"; },
  // 导出 .md：必须带 Authorization 头去取（<a href> 跳转不带头 → 后端 401「Not
  // authenticated」，且会把 webview 整个导航到 401 JSON 页、没退路）。这里 fetch 成
  // blob 交给前端触发保存，不导航。
  async downloadMarkdown(id) {
    const headers = {};
    if (_token) headers["Authorization"] = "Bearer " + _token;
    const res = await fetch(_base + "/api/jobs/" + id + "/download", { headers });
    if (!res.ok) {
      let detail = res.statusText;
      try { const j = await res.json(); detail = j.detail || j.message || detail; } catch (_e) { /* ignore */ }
      throw { status: res.status, detail };
    }
    return res.blob();
  },
  // 封面缩略图：带 token 取（<img src> 不带头会 401）。404=无缩略图 → 返回 null，前端降级首字母。
  async fetchThumbnail(id) {
    const headers = {};
    if (_token) headers["Authorization"] = "Bearer " + _token;
    try {
      const res = await fetch(_base + "/api/jobs/" + id + "/thumbnail", { headers });
      if (!res.ok) return null;
      return await res.blob();
    } catch (_e) { return null; }
  },
};

