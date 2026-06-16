/**
 * segmentByHighlights — codepoint-safe text segmentation by highlight spans.
 * Uses Array.from() for codepoint-correct slicing (emoji/astral safe).
 *
 * @param {string} canonicalText
 * @param {{ s: number, e: number }[]} spans  codepoint offsets [s, e)
 * @returns {{ text: string, highlighted: boolean }[]}
 */
export function segmentByHighlights(canonicalText, spans) {
  const chars = Array.from(canonicalText);
  const len = chars.length;

  if (!spans || spans.length === 0) {
    return [{ text: canonicalText, highlighted: false }];
  }

  // Sort by start ascending, then by end ascending
  const sorted = [...spans]
    .map(({ s, e }) => ({ s, e }))
    .sort((a, b) => a.s - b.s || a.e - b.e);

  // Clamp to [0, len] and discard invalid (s >= e after clamping)
  const valid = [];
  for (const span of sorted) {
    const s = Math.max(0, Math.min(span.s, len));
    const e = Math.max(0, Math.min(span.e, len));
    if (s < e) {
      valid.push({ s, e });
    }
  }

  if (valid.length === 0) {
    return [{ text: canonicalText, highlighted: false }];
  }

  // Merge overlapping spans (no double-highlight)
  const merged = [valid[0]];
  for (let i = 1; i < valid.length; i++) {
    const last = merged[merged.length - 1];
    const cur = valid[i];
    if (cur.s < last.e) {
      last.e = Math.max(last.e, cur.e);
    } else {
      merged.push({ ...cur });
    }
  }

  // Build segments: highlighted and non-highlighted alternating
  const result = [];
  let cursor = 0;
  for (const { s, e } of merged) {
    if (cursor < s) {
      result.push({ text: chars.slice(cursor, s).join(''), highlighted: false });
    }
    result.push({ text: chars.slice(s, e).join(''), highlighted: true });
    cursor = e;
  }
  if (cursor < len) {
    result.push({ text: chars.slice(cursor).join(''), highlighted: false });
  }

  // Merge adjacent same-type segments
  const mergedResult = [];
  for (const seg of result) {
    if (mergedResult.length > 0 && mergedResult[mergedResult.length - 1].highlighted === seg.highlighted) {
      mergedResult[mergedResult.length - 1].text += seg.text;
    } else {
      mergedResult.push({ ...seg });
    }
  }

  return mergedResult;
}
