// Appel signé du panneau privé vsd-admin (Cloudflare) : une requête, réponse bornée, aucun secret journalisé.
import { createHash, createHmac, randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';
const STOP = Date.parse('2027-09-14T21:59:59Z');
const ORIGIN = 'https://vsd-admin.kartier.workers.dev';
const allowed = { health: ['healthy'], metrics: ['finished'], publications: ['idle', 'busy_or_recent', 'dispatched', 'reconciled'], stock: ['stock_imported', 'stock_settled'] };
export class ControlError extends Error {
  constructor(code, httpStatus) { super(code); this.code = code; this.httpStatus = httpStatus; }
}
async function boundedBody(response) {
  if (!response.body) throw new ControlError('response_empty');
  const reader = response.body.getReader(); let length = 0; const chunks = [];
  try {
    for (;;) { const { done, value } = await reader.read(); if (done) break; length += value.byteLength;
      if (length > 1024) { await reader.cancel(); throw new ControlError('response_too_large'); } chunks.push(value); }
  } finally { reader.releaseLock(); }
  try { return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks))); }
  catch { throw new ControlError('response_invalid_json'); }
}
export function signature(key, { origin, sentAt, nonce, body }) {
  const digest = createHash('sha256').update(body).digest('hex');
  return createHmac('sha256', Buffer.from(key, 'base64url')).update(['vsd-admin-v1', origin, 'POST', '/internal/tick', sentAt, nonce, digest].join('\n')).digest('hex');
}
export async function invoke({ env = process.env, fetcher = fetch, clock = Date.now, nonce = randomUUID, log = console.log } = {}) {
  if (clock() >= STOP) return { status: 'period_ended', requests: 0 };
  const origin = env.VSD_ADMIN_ORIGIN, key = env.VSD_ADMIN_TICK_KEY, kind = env.VSD_TICK_KIND || 'health';
  if (origin !== ORIGIN || !/^[A-Za-z0-9_-]{43}$/.test(key ?? '') || !Object.hasOwn(allowed, kind)) throw new ControlError('configuration');
  const body = JSON.stringify({ kind }), sentAt = String(clock()), requestNonce = nonce();
  let response;
  try {
    response = await fetcher(origin + '/internal/tick', { method: 'POST', redirect: 'error', signal: AbortSignal.timeout(60000),
      headers: { 'Content-Type': 'application/json', 'X-VSD-Sent-At': sentAt, 'X-VSD-Nonce': requestNonce, 'X-VSD-Signature': signature(key, { origin, sentAt, nonce: requestNonce, body }) }, body });
  } catch (error) { throw new ControlError(error?.name === 'TimeoutError' ? 'request_timeout' : 'request_unconfirmed'); }
  if (response.status !== 200) { await response.body?.cancel(); throw new ControlError('http_non_success', response.status); }
  if (!response.headers.get('content-type')?.includes('application/json')) { await response.body?.cancel(); throw new ControlError('response_content_type'); }
  const data = await boundedBody(response);
  if (!data || data.kind !== kind || !allowed[kind].includes(data.status)) throw new ControlError('task_attention_required');
  log('Panel receipt: ' + kind + ' / ' + data.status + '.');
  return { status: 'confirmed', requests: 1 };
}
export function safeDiagnostic(error) {
  const codes = new Set(['configuration', 'request_timeout', 'request_unconfirmed', 'http_non_success', 'response_empty', 'response_too_large', 'response_invalid_json', 'response_content_type', 'task_attention_required']);
  const code = error instanceof ControlError && codes.has(error.code) ? error.code : 'operation_unconfirmed';
  return 'Panel task not confirmed: ' + code + (code === 'http_non_success' && Number.isInteger(error.httpStatus) ? ' (HTTP ' + error.httpStatus + ')' : '') + '. No automatic retry was made.';
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try { const result = await invoke(); if (result.status === 'period_ended') console.log('Follow-up period ended; no further request sent.'); }
  catch (error) { console.error(safeDiagnostic(error)); process.exitCode = 1; }
}
