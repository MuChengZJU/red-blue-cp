import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { segmentByHighlights } from '../highlight.js';

describe('segmentByHighlights', () => {
  it('emoji/astral: span covers only the emoji codepoint', () => {
    // text = a 😀 b  → codepoints: [a, 😀, b]
    // span {s:1, e:2} should capture exactly "😀"
    const text = 'a😀b';
    const result = segmentByHighlights(text, [{ s: 1, e: 2 }]);
    assert.deepStrictEqual(result, [
      { text: 'a', highlighted: false },
      { text: '😀', highlighted: true },
      { text: 'b', highlighted: false },
    ]);
  });

  it('unsorted input is sorted before processing', () => {
    const text = 'abcdef';
    // spans out of order: [3-4) then [1-2)
    const result = segmentByHighlights(text, [{ s: 3, e: 4 }, { s: 1, e: 2 }]);
    assert.deepStrictEqual(result, [
      { text: 'a', highlighted: false },
      { text: 'b', highlighted: true },
      { text: 'c', highlighted: false },
      { text: 'd', highlighted: true },
      { text: 'ef', highlighted: false },
    ]);
  });

  it('out-of-bounds: s<0 is clamped to 0', () => {
    const text = 'abc';
    const result = segmentByHighlights(text, [{ s: -2, e: 1 }]);
    assert.deepStrictEqual(result, [
      { text: 'a', highlighted: true },
      { text: 'bc', highlighted: false },
    ]);
  });

  it('out-of-bounds: e>len is clamped to len', () => {
    const text = 'abc';
    const result = segmentByHighlights(text, [{ s: 1, e: 99 }]);
    assert.deepStrictEqual(result, [
      { text: 'a', highlighted: false },
      { text: 'bc', highlighted: true },
    ]);
  });

  it('invalid span: s>=e after clamping is discarded', () => {
    const text = 'abc';
    const result = segmentByHighlights(text, [{ s: 5, e: 5 }]);
    assert.deepStrictEqual(result, [
      { text: 'abc', highlighted: false },
    ]);
  });

  it('empty spans → single non-highlighted segment', () => {
    const text = 'hello world';
    const result = segmentByHighlights(text, []);
    assert.deepStrictEqual(result, [
      { text: 'hello world', highlighted: false },
    ]);
  });

  it('拼回所有段 text === 原文 (mixed emoji)', () => {
    const text = '你好🌍世界⭐end';
    const result = segmentByHighlights(text, [
      { s: 0, e: 1 },
      { s: 3, e: 5 },
    ]);
    const reassembled = result.map(r => r.text).join('');
    assert.strictEqual(reassembled, text);
  });
});
