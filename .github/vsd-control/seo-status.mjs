// Lecture signée du résumé de référencement tenu par le panneau privé : clics, impressions,
// requêtes en hausse et pages indexées. Lecture seule ; un échec n'arrête jamais le rapport.
import { randomUUID } from 'node:crypto';
import { writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { signature } from './invoke-admin.mjs';

const ORIGIN = 'https://vsd-admin.kartier.workers.dev';
const MAX_BYTES = 32768;
const TIMEOUT_MS = 30000;
const isCount = value => Number.isInteger(value) && value >= 0;

export class SeoError extends Error {
  constructor(code) { super(code); this.code = code; }
}

/** Garde les seuls champs attendus, avec leurs types : la réponse ne porte aucune consigne. */
export function checkedSeo(data) {
  if (!data || data.kind !== 'seo' || data.status !== 'reported') throw new SeoError('response_unexpected');
  const text = (value, max) => String(value ?? '').slice(0, max);
  const search = data.search && isCount(data.search.clicks) && isCount(data.search.impressions) ? {
    period: { startDate: text(data.search.period?.startDate, 10), endDate: text(data.search.period?.endDate, 10) },
    clicks: data.search.clicks, impressions: data.search.impressions,
    previousClicks: isCount(data.search.previousClicks) ? data.search.previousClicks : null,
    previousImpressions: isCount(data.search.previousImpressions) ? data.search.previousImpressions : null,
    rising: (Array.isArray(data.search.rising) ? data.search.rising : []).slice(0, 5).filter(q => isCount(q?.impressions))
      .map(q => ({ query: text(q.query, 120), impressions: q.impressions, previousImpressions: isCount(q.previousImpressions) ? q.previousImpressions : 0, position: Number(q.position) || null })),
  } : null;
  const index = data.indexation;
  const indexation = index && isCount(index.indexed) && isCount(index.inspected) && isCount(index.total) ? {
    total: index.total, inspected: index.inspected, indexed: index.indexed,
    notIndexedCount: isCount(index.notIndexedCount) ? index.notIndexedCount : 0,
    notIndexed: (Array.isArray(index.notIndexed) ? index.notIndexed : []).slice(0, 15).map(p => ({ path: text(p?.path, 200), state: text(p?.state, 120) })),
    trend: index.trend?.status === 'drop' && isCount(index.trend.lost) && isCount(index.trend.reference)
      ? { status: 'drop', lost: index.trend.lost, reference: index.trend.reference, referenceDay: text(index.trend.referenceDay, 10) }
      : { status: index.trend?.status === 'stable' ? 'stable' : 'unknown' },
  } : null;
  return { search, indexation };
}

export async function readSeo({ env = process.env, fetcher = fetch, clock = Date.now, nonce = randomUUID } = {}) {
  const origin = env.VSD_ADMIN_ORIGIN, key = env.VSD_ADMIN_TICK_KEY;
  if (origin !== ORIGIN || !/^[A-Za-z0-9_-]{43}$/.test(key ?? '')) throw new SeoError('configuration');
  const body = JSON.stringify({ kind: 'seo' }), sentAt = String(clock()), requestNonce = nonce();
  let response;
  try {
    response = await fetcher(origin + '/internal/tick', { method: 'POST', redirect: 'error', signal: AbortSignal.timeout(TIMEOUT_MS),
      headers: { 'Content-Type': 'application/json', 'X-VSD-Sent-At': sentAt, 'X-VSD-Nonce': requestNonce, 'X-VSD-Signature': signature(key, { origin, sentAt, nonce: requestNonce, body }) }, body });
  } catch { throw new SeoError('request_unconfirmed'); }
  if (response.status !== 200) { await response.body?.cancel(); throw new SeoError('http_' + response.status); }
  const text = await response.text();
  if (text.length > MAX_BYTES) throw new SeoError('response_too_large');
  let data;
  try { data = JSON.parse(text); } catch { throw new SeoError('response_invalid_json'); }
  return checkedSeo(data);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const seo = await readSeo();
    await writeFile(process.env.VSD_REPORT_SEO, JSON.stringify(seo) + '\n');
    console.log(`Référencement relevé : ${seo.search ? seo.search.clicks + ' clics' : 'clics indisponibles'}, ${seo.indexation ? seo.indexation.indexed + ' pages indexées' : 'indexation indisponible'}.`);
  } catch (error) {
    // Le rapport s'écrit quand même ; il dira que le relevé manque.
    console.log('Référencement non relevé : ' + (error instanceof SeoError ? error.code : 'erreur') + '.');
  }
}
