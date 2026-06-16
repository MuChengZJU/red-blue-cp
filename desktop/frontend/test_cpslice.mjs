// codepoint 切片正确性自检（关键不变量：astral 字符不错位）。
// 跑：node test_cpslice.mjs
import { cpSlice, cpLength } from "./render.js";

let pass = 0, fail = 0;
function eq(name, got, want) {
  if (got === want) { pass++; }
  else { fail++; console.error(`FAIL ${name}: got=${JSON.stringify(got)} want=${JSON.stringify(want)}`); }
}

// 1. BMP 中文：codepoint == UTF-16，两种切法一致
const t1 = "今天聊大模型推理加速。核心瓶颈是显存带宽。";
eq("bmp slice 0-11", cpSlice(t1, 0, 11), "今天聊大模型推理加速。");
eq("bmp slice == native slice", cpSlice(t1, 0, 11), t1.slice(0, 11));

// 2. astral（emoji）：codepoint != UTF-16，必须用 cpSlice
const t2 = "🚀加速真快🔥结束";  // 🚀 与 🔥 各占 1 codepoint = 2 UTF-16 码元
eq("astral len (codepoint)", cpLength(t2), 8);          // 🚀 加 速 真 快 🔥 结 束
eq("astral len (utf16)", t2.length, 10);                 // 证明 UTF-16 会多算 2
eq("astral cpSlice 1-5", cpSlice(t2, 1, 5), "加速真快");  // 正确：跳过 🚀(1cp)
eq("native slice WRONG", t2.slice(1, 5), "\uDE80加速真");  // 证明 string.slice 会从 🚀 中间切，错位
// 关键：cpSlice 取到的就是契约 span 想要的那段
eq("cpSlice != native (astral)", cpSlice(t2, 1, 5) !== t2.slice(1, 5), true);

console.log(`\ncpSlice tests: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
