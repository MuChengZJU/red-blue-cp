import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { classifyError } from '../errors.js';

describe('classifyError', () => {
  it('两字段都有 → 分别返回', () => {
    const result = classifyError({
      error_message: '数据库连接超时',
      log_excerpt: 'Error: connect ECONNREFUSED 127.0.0.1:5432',
    });
    assert.strictEqual(result.human, '数据库连接超时');
    assert.strictEqual(result.technical, 'Error: connect ECONNREFUSED 127.0.0.1:5432');
  });

  it('error_message 为空 → 兜底文案', () => {
    const result = classifyError({
      error_message: '',
      log_excerpt: 'some log',
    });
    assert.ok(result.human.length > 0, 'human should not be empty');
    assert.ok(result.human.includes('错误') || result.human.includes('异常') || result.human.includes('问题'),
      'fallback message should be user-friendly Chinese');
    assert.strictEqual(result.technical, 'some log');
  });

  it('log_excerpt 为空 → technical 为空串', () => {
    const result = classifyError({
      error_message: '文件未找到',
      log_excerpt: '',
    });
    assert.strictEqual(result.human, '文件未找到');
    assert.strictEqual(result.technical, '');
  });

  it('传入 {} → 不抛异常，返回兜底', () => {
    const result = classifyError({});
    assert.ok(typeof result.human === 'string' && result.human.length > 0);
    assert.strictEqual(result.technical, '');
  });
});
