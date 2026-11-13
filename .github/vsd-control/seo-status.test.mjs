import { test } from 'node:test';
import assert from 'node:assert/strict';
import { checkedSeo, readSeo, SeoError } from './seo-status.mjs';
import { signature } from './invoke-admin.mjs';

const KEY = Buffer.alloc(32, 5).toString('base64url');
const ENV = { VSD_ADMIN_ORIGIN: 'https://vsd-admin.kartier.workers.dev', VSD_ADMIN_TICK_KEY: KEY };
const reply = {
  kind: 'seo', status: 'reported',
  search: { period: { startDate: '2026-10-12', endDate: '2026-11-08' }, clicks: 6, impressions: 771, previousClicks: 1, previousImpressions: 120,
    rising: [{ query: 'sapin rockefeller center 2026', impressions: 37, previousImpressions: 0, position: 10.2 }], observedAt: '2026-11-11T06:00:00.000Z' },
  indexation: { total: 59, inspected: 59, indexed: 40, notIndexedCount: 19, notIndexed: [{ path: '/japon/', state: 'Détectée, actuellement non indexée' }],
    trend: { status: 'drop', indexed: 40, reference: 48, referenceDay: '2026-11-01', lost: 8 }, observedAt: '2026-11-11T07:00:00.000Z' },
};
const respond = (body, status = 200) => async () => new Response(typeof body === 'string' ? body : JSON.stringify(body), { status });

test('the signed seo read returns only the expected figures', async () => {
  let seen;
  const fetcher = async (url, init) => { seen = { url, init }; return new Response(JSON.stringify(reply)); };
  const seo = await readSeo({ env: ENV, fetcher, clock: () => 1794300000000, nonce: () => '11111111-1111-4111-8111-111111111111' });
  assert.equal(seen.url, 'https://vsd-admin.kartier.workers.dev/internal/tick');
  assert.equal(seen.init.body, '{"kind":"seo"}');
  assert.equal(seen.init.headers['X-VSD-Signature'], signature(KEY, { origin: ENV.VSD_ADMIN_ORIGIN, sentAt: '1794300000000', nonce: '11111111-1111-4111-8111-111111111111', body: '{"kind":"seo"}' }));
  assert.deepEqual(seo.search, { period: { startDate: '2026-10-12', endDate: '2026-11-08' }, clicks: 6, impressions: 771, previousClicks: 1, previousImpressions: 120,
    rising: [{ query: 'sapin rockefeller center 2026', impressions: 37, previousImpressions: 0, position: 10.2 }] });
  assert.deepEqual(seo.indexation.trend, { status: 'drop', lost: 8, reference: 48, referenceDay: '2026-11-01' });
  assert.equal(seo.indexation.indexed, 40);
});

test('a panel that does not know the seo read yet, or answers badly, is a soft failure', async () => {
  await assert.rejects(readSeo({ env: ENV, fetcher: respond({ error: 'tick_kind' }, 400) }), { code: 'http_400' });
  await assert.rejects(readSeo({ env: ENV, fetcher: respond('<html>') }), { code: 'response_invalid_json' });
  await assert.rejects(readSeo({ env: ENV, fetcher: respond({ kind: 'health', status: 'healthy' }) }), { code: 'response_unexpected' });
  await assert.rejects(readSeo({ env: ENV, fetcher: async () => { throw new Error('réseau'); } }), { code: 'request_unconfirmed' });
  await assert.rejects(readSeo({ env: ENV, fetcher: respond('x'.repeat(40000)) }), { code: 'response_too_large' });
});

test('no request leaves without the exact panel origin and a well-formed key', async () => {
  const fetcher = async () => { throw new Error('ne doit pas partir'); };
  await assert.rejects(readSeo({ env: { ...ENV, VSD_ADMIN_ORIGIN: 'https://ailleurs.example' }, fetcher }), { code: 'configuration' });
  await assert.rejects(readSeo({ env: { ...ENV, VSD_ADMIN_TICK_KEY: 'court' }, fetcher }), { code: 'configuration' });
  assert.ok(new SeoError('x') instanceof Error);
});

test('missing or malformed parts are dropped instead of trusted', () => {
  assert.deepEqual(checkedSeo({ kind: 'seo', status: 'reported', search: null, indexation: null }), { search: null, indexation: null, publication: null });
  const partial = checkedSeo({ kind: 'seo', status: 'reported', search: { clicks: 'beaucoup', impressions: 3 },
    indexation: { total: 3, inspected: 3, indexed: 2, notIndexed: 'aucune', trend: { status: 'drop', lost: 'x' } } });
  assert.equal(partial.search, null);
  assert.deepEqual(partial.indexation, { total: 3, inspected: 3, indexed: 2, notIndexedCount: 0, notIndexed: [], trend: { status: 'unknown' } });
});

test('nothing Markdown can read survives in a query, a state or a path', () => {
  const hostile = checkedSeo({ kind: 'seo', status: 'reported',
    search: { period: { startDate: '2026-10-12', endDate: '](x)' }, clicks: 1, impressions: 9, rising: [{ query: '@quelquun [gagnez](https://evil.example) ![x](https://evil.example/p.png)\n# titre #12 `code`', impressions: 9 }] },
    indexation: { total: 1, inspected: 1, indexed: 0, notIndexed: [{ path: '/japon/`)<img>', state: 'Détectée, actuellement non indexée <b>@x</b>' }], trend: { status: 'drop', lost: 2, reference: 3, referenceDay: '[lien](x)' } } });
  const query = hostile.search.rising[0].query;
  assert.doesNotMatch(query, /[@\[\]()!#`<>\n]/);
  assert.match(query, /^quelquun gagnez https evil example/);
  assert.equal(hostile.search.period.endDate, '');
  assert.deepEqual(hostile.indexation.notIndexed, [{ path: '/japon/img', state: 'Détectée, actuellement non indexée b x b' }]);
  assert.equal(hostile.indexation.trend.referenceDay, '');
});

const PUBLICATION = {
  enabled: true, channels: { instagram: 'disconnected', facebook: 'connected', tiktok: 'absent' }, channelsCheckedAt: '2026-11-12T08:02:11.000Z', lastPassAt: '2026-11-12T08:37:00.000Z',
  counts: { ready: 4, submitting: 0, scheduled: 2, published: 12, to_verify: 0, held: 1, failed: 0 },
  problems: [{ id: 'reviewed-social:instagram:reel:vietnam_2026-11-25.v1', channel: 'instagram', state: 'held', reason: 'overdue', at: '2026-11-10T17:00:00.000Z' }], problemsCount: 1,
  atRisk: [{ id: 'ig:pret', channel: 'instagram', dueAt: '2026-11-12T17:00:00.000Z', channelState: 'disconnected' }], atRiskCount: 1,
  retiredInBuffer: [{ id: 'vsd-production:instagram:japon-a', channel: 'instagram', dueAt: '2026-11-15T20:00:00.000Z', reason: 'buffer_delete_mutation_error', replacementWaiting: true }],
  retiredInBufferCount: 1,
  retiredPublished: [{ id: 'vsd-production:tiktok:japon-a', channel: 'tiktok', dueAt: '2026-11-11T21:00:00.000Z', at: '2026-11-11T21:07:00.000Z' }], retiredPublishedCount: 1,
  bufferQuota: { observedAt: '2026-11-12T08:37:00.000Z', windows: [{ name: '600-in-1day', remaining: 540, limit: 600, windowSeconds: 86400, resetAt: '2026-11-13T00:00:00.000Z' },
    { name: '3000-in-30days', remaining: 2100, limit: 3000, windowSeconds: 2592000, resetAt: '2026-12-01T00:00:00.000Z' }], lowestRatio: 0.7, pausedUntil: null },
  lastFailure: { at: '2026-11-12T08:22:00.000Z', code: 'quota_epuise' },
  readyStalled: [{ id: 'ig:pret', channel: 'instagram', dueAt: '2026-11-12T17:00:00.000Z' }], readyStalledCount: 1,
};

test('the publication block keeps channel states, the last engine pass, counts and the short post lists', () => {
  const seo = checkedSeo({ ...reply, publication: { ...PUBLICATION, observedAt: '2026-11-12T09:00:00.000Z', organizationId: 'org1' } });
  assert.deepEqual(seo.publication, PUBLICATION);
  assert.equal(seo.indexation.indexed, 40);
});

test('a panel that does not send the publication block yet, or sends a malformed one, gives no publication reading', () => {
  assert.equal(checkedSeo(reply).publication, null);
  for (const publication of [null, 'actif', [], { enabled: 'oui', counts: {} }, { enabled: true }, { enabled: true, counts: 'aucun' }]) {
    assert.equal(checkedSeo({ ...reply, publication }).publication, null, JSON.stringify(publication));
  }
  // No Buffer access recorded in the panel: channels are null, the rest is kept.
  assert.equal(checkedSeo({ ...reply, publication: { ...PUBLICATION, channels: null } }).publication.channels, null);
  // A panel older than the date of the last channel re-reading, or one that never re-read them: no date.
  const { channelsCheckedAt, ...older } = PUBLICATION;
  assert.equal(checkedSeo({ ...reply, publication: older }).publication.channelsCheckedAt, null);
  assert.equal(checkedSeo({ ...reply, publication: { ...PUBLICATION, channelsCheckedAt: null } }).publication.channelsCheckedAt, null);
});

test('nothing Markdown can read survives in the publication block', () => {
  const at = '2026-11-11T10:00:00.000Z';
  const hostile = checkedSeo({ kind: 'seo', status: 'reported', publication: {
    enabled: true,
    channels: { instagram: '[déconnecté](https://evil.example)', facebook: 'connected', pinterest: 'connected', '@x': 'locked' },
    channelsCheckedAt: 'hier [ici](https://evil.example) @mathis',
    lastPassAt: '2026-11-12 08:37 <b>',
    counts: { ready: '4', held: -1, failed: 2, autre: 9 },
    problems: [
      { id: 'ok:1', channel: 'instagram', state: 'failed', reason: 'Voir [ici](https://evil.example) @mathis', at },
      { id: 'mauvais `id` @x', channel: 'instagram', state: 'held', reason: 'overdue', at },
      { id: 'ok:2', channel: 'x.com', state: 'held', reason: 'overdue', at },
      { id: 'ok:3', channel: 'facebook', state: 'published', reason: 'overdue', at },
      { id: 'ok:4', channel: 'facebook', state: 'held', reason: 'overdue', at: 'hier' },
      'texte',
    ],
    problemsCount: 'beaucoup',
    atRisk: [{ id: 'ok:5', channel: 'tiktok', dueAt: '2026-11-12T11:00:00.000Z', channelState: '<img>' }, { id: 'ok:6', channel: 'tiktok', dueAt: 'bientôt', channelState: 'absent' }],
  } }).publication;
  assert.deepEqual(hostile, {
    enabled: true, channels: { instagram: 'unknown', facebook: 'connected', tiktok: 'unknown' }, channelsCheckedAt: null, lastPassAt: null,
    counts: { ready: 0, submitting: 0, scheduled: 0, published: 0, to_verify: 0, held: 0, failed: 2 },
    problems: [{ id: 'ok:1', channel: 'instagram', state: 'failed', reason: 'autre', at }], problemsCount: 1,
    atRisk: [{ id: 'ok:5', channel: 'tiktok', dueAt: '2026-11-12T11:00:00.000Z', channelState: 'unknown' }], atRiskCount: 1,
    retiredInBuffer: [], retiredInBufferCount: 0, retiredPublished: [], retiredPublishedCount: 0, bufferQuota: null,
    lastFailure: null, readyStalled: [], readyStalledCount: 0,
  });
});

test('withdrawn posts and the Buffer quota keep a closed shape: codes, ISO dates, counts, nothing Markdown can read', () => {
  const at = '2026-11-11T10:00:00.000Z';
  const publication = checkedSeo({ ...reply, publication: { ...PUBLICATION,
    retiredInBuffer: [
      { id: 'ok:1', channel: 'instagram', dueAt: at, reason: 'Supprimer [ici](https://evil.example) @mathis', replacementWaiting: 'oui' },
      { id: 'mauvais `id`', channel: 'instagram', dueAt: at, reason: 'trop_tard' },
      { id: 'ok:2', channel: 'x.com', dueAt: at, reason: 'trop_tard' },
      { id: 'ok:3', channel: 'facebook', dueAt: 'demain', reason: 'trop_tard' },
    ],
    retiredInBufferCount: 'beaucoup',
    retiredPublished: [{ id: 'ok:4', channel: 'facebook', dueAt: at, at: 'hier' }, { id: 'ok:5', channel: 'facebook', dueAt: at, at }],
    retiredPublishedCount: 3,
    bufferQuota: { observedAt: at, lowestRatio: 0.99, pausedUntil: 'demain', windows: [{ name: '[x](y)', remaining: 1, limit: 100 }, { name: 42, remaining: 0, limit: 1 },
      { name: '3000-in-30d', remaining: 120, limit: 3000, windowSeconds: '30 jours', resetAt: '[lien](x)' }, { name: 'trop', remaining: 5, limit: 1e12 }] },
    lastFailure: { at, code: 'Voir [ici](https://evil.example)' },
    readyStalled: [{ id: 'ok:6', channel: 'facebook', dueAt: at }, { id: 'ok:7', channel: 'x.com', dueAt: at }],
    readyStalledCount: 1e12,
  } }).publication;
  assert.deepEqual(publication.retiredInBuffer, [{ id: 'ok:1', channel: 'instagram', dueAt: at, reason: 'autre', replacementWaiting: false }]);
  assert.equal(publication.retiredInBufferCount, 1);
  assert.deepEqual(publication.retiredPublished, [{ id: 'ok:5', channel: 'facebook', dueAt: at, at }]);
  assert.equal(publication.retiredPublishedCount, 3);
  // The share left is recomputed from the counts, never taken from the panel.
  // Names that are not strings, counts out of bounds, dates that are not ISO: dropped.
  assert.deepEqual(publication.bufferQuota, { observedAt: at, windows: [{ name: '3000-in-30d', remaining: 120, limit: 3000, windowSeconds: null, resetAt: null },
    { name: 'trop', remaining: 5, limit: null, windowSeconds: null, resetAt: null }], lowestRatio: 0.04, pausedUntil: null });
  assert.deepEqual(publication.lastFailure, { at, code: 'autre' });
  assert.deepEqual([publication.readyStalled, publication.readyStalledCount], [[{ id: 'ok:6', channel: 'facebook', dueAt: at }], 1]);
  // A window at zero is exhausted even without its quota; a pause alone is enough to report.
  assert.equal(checkedSeo({ ...reply, publication: { ...PUBLICATION, bufferQuota: { observedAt: at, windows: [{ name: 'a', remaining: 0 }] } } }).publication.bufferQuota.lowestRatio, 0);
  assert.deepEqual(checkedSeo({ ...reply, publication: { ...PUBLICATION, bufferQuota: { observedAt: null, windows: [], pausedUntil: at } } }).publication.bufferQuota,
    { observedAt: null, windows: [], lowestRatio: 0, pausedUntil: at });
  for (const bufferQuota of [null, 'bas', { observedAt: 'hier', windows: [{ name: 'a', remaining: 1, limit: 2 }] }, { observedAt: at, windows: [{ name: 'a', remaining: 1 }] }]) {
    assert.equal(checkedSeo({ ...reply, publication: { ...PUBLICATION, bufferQuota } }).publication.bufferQuota, null, JSON.stringify(bufferQuota));
  }
});

test('the post lists are bounded and their totals never fall below what is listed', () => {
  const problems = Array.from({ length: 14 }, (_, i) => ({ id: 'post-' + i, channel: 'facebook', state: 'held', reason: 'overdue', at: '2026-11-11T10:00:00.000Z' }));
  const publication = checkedSeo({ ...reply, publication: { ...PUBLICATION, problems, problemsCount: 14, atRiskCount: 0 } }).publication;
  assert.equal(publication.problems.length, 10);
  assert.equal(publication.problemsCount, 14);
  assert.equal(publication.atRiskCount, 1);
});

