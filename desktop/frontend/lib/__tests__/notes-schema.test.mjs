import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { validateNotes } from '../notes-schema.js';

describe('validateNotes', () => {
  it('合规对象 → ok:true', () => {
    const obj = {
      schema_version: '1.0',
      notes: [
        { url: 'https://example.com/1' },
        { share_url: 'https://share.example.com/2' },
      ],
    };
    const result = validateNotes(obj);
    assert.deepStrictEqual(result, { ok: true, errors: [] });
  });

  it('缺 schema_version → error', () => {
    const obj = { notes: [{ url: 'https://example.com' }] };
    const result = validateNotes(obj);
    assert.strictEqual(result.ok, false);
    assert.ok(result.errors.some(e => e.includes('schema_version')));
  });

  it('notes 非数组 → error', () => {
    const obj = { schema_version: '1.0', notes: 'not-array' };
    const result = validateNotes(obj);
    assert.strictEqual(result.ok, false);
    assert.ok(result.errors.some(e => e.includes('notes')));
  });

  it('某条 note 缺 url/share_url → error', () => {
    const obj = {
      schema_version: '1.0',
      notes: [
        { url: 'https://ok.com' },
        { title: 'no link here' },
      ],
    };
    const result = validateNotes(obj);
    assert.strictEqual(result.ok, false);
    assert.ok(result.errors.some(e => e.includes('url') || e.includes('链接')));
  });
});
