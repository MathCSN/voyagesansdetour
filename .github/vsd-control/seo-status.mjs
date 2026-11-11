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

// These strings end up in a public GitHub issue: a search query is typed by strangers, so nothing
// that Markdown reads (links, bare addresses, images, mentions, issue references, line breaks) is kept.
const text = (value, max) => String(value ?? '').replace(/[^\p{L}\p{N} '’,;%€$£°+-]/gu, ' ').replace(/\s+/g, ' ').trim().slice(0, max);
const day = value => (/^\d{4}-\d{2}-\d{2}$/.test(value ?? '') ? value : '');
const countOr = (value, fallback) => (isCount(value) ? value : fallback);
const list = (value, max) => (Array.isArray(value) ? value : []).slice(0, max);

function checkedSearch(search) {
  if (!isCount(search?.clicks) || !isCount(search?.impressions)) return null;
  return {
    period: { startDate: day(search.period?.startDate), endDate: day(search.period?.endDate) },
    clicks: search.clicks, impressions: search.impressions,
    previousClicks: countOr(search.previousClicks, null), previousImpressions: countOr(search.previousImpressions, null),
    rising: list(search.rising, 5).filter(q => isCount(q?.impressions))
      .map(q => ({ query: text(q.query, 120), impressions: q.impressions, previousImpressions: countOr(q.previousImpressions, 0), position: Number(q.position) || null })),
  };
}

function checkedTrend(trend) {
  if (trend?.status === 'drop' && isCount(trend.lost) && isCount(trend.reference)) return { status: 'drop', lost: trend.lost, reference: trend.reference, referenceDay: day(trend.referenceDay) };
  return { status: trend?.status === 'stable' ? 'stable' : 'unknown' };
}

function checkedIndexation(index) {
  if (!isCount(index?.indexed) || !isCount(index?.inspected) || !isCount(index?.total)) return null;
  return {
    total: index.total, inspected: index.inspected, indexed: index.indexed,
    notIndexedCount: countOr(index.notIndexedCount, 0),
    notIndexed: list(index.notIndexed, 15).map(p => ({ path: String(p?.path ?? '').replace(/[^A-Za-z0-9/._-]/g, '').slice(0, 200), state: text(p?.state, 120) })),
    trend: checkedTrend(index.trend),
  };
}

/** Garde les seuls champs attendus, avec leurs types : la réponse ne porte aucune consigne. */
export function checkedSeo(data) {
  if (data?.kind !== 'seo' || data.status !== 'reported') throw new SeoError('response_unexpected');
  return { search: checkedSearch(data.search), indexation: checkedIndexation(data.indexation) };
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
