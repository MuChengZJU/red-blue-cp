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
  getBatches()               { return _fetch("GET",  "/api/batches"); },
  getBatchItems(batchId)     { return _fetch("GET",  "/api/batches/" + batchId + "/items"); },
  importList(payload)        { return _fetch("POST", "/api/import-list", payload); },
  downloadUrl(id)            { return _base + "/api/jobs/" + id + "/download"; },
};

