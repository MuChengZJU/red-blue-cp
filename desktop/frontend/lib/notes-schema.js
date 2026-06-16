/**
 * validateNotes — early validation for batch note import.
 *
 * @param {unknown} obj — parsed JSON object to validate
 * @returns {{ ok: boolean, errors: string[] }}
 */
export function validateNotes(obj) {
  const errors = [];

  if (obj == null || typeof obj !== 'object') {
    return { ok: false, errors: ['输入不是有效对象'] };
  }

  // schema_version: must exist and be string or number
  if (obj.schema_version === undefined || obj.schema_version === null) {
    errors.push('缺少 schema_version 字段');
  } else if (typeof obj.schema_version !== 'string' && typeof obj.schema_version !== 'number') {
    errors.push('schema_version 必须是字符串或数字');
  }

  // notes: must be an array
  if (!Array.isArray(obj.notes)) {
    errors.push('notes 字段必须是数组');
  } else {
    // Each note must have at least one link field (url or share_url)
    for (let i = 0; i < obj.notes.length; i++) {
      const note = obj.notes[i];
      if (!note || (typeof note !== 'object')) {
        errors.push(`notes[${i}] 不是有效对象`);
        continue;
      }
      if (!note.url && !note.share_url) {
        errors.push(`notes[${i}] 缺少 url 或 share_url 链接字段`);
      }
    }
  }

  return errors.length === 0
    ? { ok: true, errors: [] }
    : { ok: false, errors };
}
