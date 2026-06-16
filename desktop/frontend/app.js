// 入口：开发期读 sample 渲染；联调期点"跑引擎"调 Tauri sidecar。
import { renderAll } from "./render.js";

const root = document.getElementById("three-forms");

// 开发期固定喂契约样例（与 docs/contracts/0.6-digest-json-sample.json 同源）。
// build.sh 会把 sample 拷进来；这里用 fetch 兜底，失败则用内联副本。
async function loadSample() {
  try {
    const res = await fetch("./sample.json");
    if (res.ok) return await res.json();
  } catch (_) { /* 文件协议 / 离线，走内联 */ }
  return INLINE_SAMPLE;
}

// 是否在 Tauri 壳里（有 __TAURI__ 注入）
function inTauri() {
  return typeof window !== "undefined" && !!window.__TAURI__;
}

// 联调期：调 sidecar（Tauri command run_digest）跑真实引擎
async function runEngine(text) {
  if (!inTauri()) {
    alert("不在 Tauri 壳里：开发期用样例渲染。打 tauri build 后此按钮才会调 sidecar。");
    return;
  }
  const { invoke } = window.__TAURI__.core;
  const raw = await invoke("run_digest", { text });
  return JSON.parse(raw);
}

async function main() {
  const payload = await loadSample();
  renderAll(root, payload);

  const btn = document.getElementById("run-sidecar");
  btn.addEventListener("click", async () => {
    const text = payload.extract.canonical_text;
    const out = await runEngine(text);
    if (out) renderAll(root, out);
  });
}

// 与 sample.json 形状一致的内联副本（file:// 下 fetch 可能被拦时兜底）。
const INLINE_SAMPLE = {
  extract: {
    canonical_text: "今天聊大模型推理加速。核心瓶颈是显存带宽。投机解码能提速两到三倍。",
    text_sha256: "557749a39d38303c369db005974823fac8b6d8c32e3ac37abea81c4fd95f0fac",
    segments: [
      { text: "今天聊大模型推理加速。", speaker_id: "0", start_sec: 0.0, end_sec: 3.2, char_start: 0, char_end: 11 },
      { text: "核心瓶颈是显存带宽。", speaker_id: "0", start_sec: 3.2, end_sec: 7.0, char_start: 11, char_end: 21 },
      { text: "投机解码能提速两到三倍。", speaker_id: "0", start_sec: 7.0, end_sec: 11.5, char_start: 21, char_end: 33 },
    ],
  },
  digest: {
    highlights: [
      { span_start: 11, span_end: 21, weight: 0.95, source: { char_start: 11, char_end: 21, seconds: 3.2, image_index: null, anchoring_status: "exact", confidence: 1.0 } },
      { span_start: 21, span_end: 33, weight: 0.9, source: { char_start: 21, char_end: 33, seconds: 7.0, image_index: null, anchoring_status: "exact", confidence: 1.0 } },
    ],
    cards: [
      { quote: "核心瓶颈是显存带宽。", source: { char_start: 11, char_end: 21, seconds: 3.2, image_index: null, anchoring_status: "exact", confidence: 1.0 } },
      { quote: "原文没有的金句", source: null },
    ],
    outline: [
      { title: "推理加速要点", source: { char_start: 0, char_end: 11, seconds: 0.0, image_index: null, anchoring_status: "exact", confidence: 1.0 }, children: [
        { title: "瓶颈", source: { char_start: 11, char_end: 21, seconds: 3.2, image_index: null, anchoring_status: "exact", confidence: 1.0 }, children: [] },
        { title: "优化", source: { char_start: 21, char_end: 33, seconds: 7.0, image_index: null, anchoring_status: "exact", confidence: 1.0 }, children: [] },
      ] },
    ],
    model: "qwen-plus",
    source_text_sha256: "557749a39d38303c369db005974823fac8b6d8c32e3ac37abea81c4fd95f0fac",
    coordinate_space: "python_codepoint",
    normalization_version: "v1",
    diagnostics: [],
  },
};

main();
