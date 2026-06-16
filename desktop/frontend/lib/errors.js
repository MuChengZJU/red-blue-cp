/**
 * classifyError — split error info into human-facing and technical messages.
 *
 * Never throws; gracefully handles missing fields.
 *
 * @param {{ error_message?: string, log_excerpt?: string }} params
 * @returns {{ human: string, technical: string }}
 */
export function classifyError({ error_message, log_excerpt } = {}) {
  const human = (error_message && error_message.trim())
    ? error_message
    : '发生了一个未知错误，请稍后再试或联系技术支持';

  const technical = (log_excerpt && log_excerpt.trim())
    ? log_excerpt
    : '';

  return { human, technical };
}
