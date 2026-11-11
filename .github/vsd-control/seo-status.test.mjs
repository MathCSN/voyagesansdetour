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
  enabled: true, channels: { instagram: 'disconnected', facebook: 'connected', tiktok: 'absent' }, lastPassAt: '2026-11-12T08:37:00.000Z',
  counts: { ready: 4, submitting: 0, scheduled: 2, published: 12, to_verify: 0, held: 1, failed: 0 },
  problems: [{ id: 'reviewed-social:instagram:reel:vietnam_2026-11-25.v1', channel: 'instagram', state: 'held', reason: 'overdue', at: '2026-11-10T17:00:00.000Z' }], problemsCount: 1,
  atRisk: [{ id: 'ig:pret', channel: 'instagram', dueAt: '2026-11-12T17:00:00.000Z', channelState: 'disconnected' }], atRiskCount: 1,
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
});

test('nothing Markdown can read survives in the publication block', () => {
  const at = '2026-11-11T10:00:00.000Z';
  const hostile = checkedSeo({ kind: 'seo', status: 'reported', publication: {
    enabled: true,
    channels: { instagram: '[déconnecté](https://evil.example)', facebook: 'connected', pinterest: 'connected', '@x': 'locked' },
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
    enabled: true, channels: { instagram: 'unknown', facebook: 'connected', tiktok: 'unknown' }, lastPassAt: null,
    counts: { ready: 0, submitting: 0, scheduled: 0, published: 0, to_verify: 0, held: 0, failed: 2 },
    problems: [{ id: 'ok:1', channel: 'instagram', state: 'failed', reason: 'autre', at }], problemsCount: 1,
    atRisk: [{ id: 'ok:5', channel: 'tiktok', dueAt: '2026-11-12T11:00:00.000Z', channelState: 'unknown' }], atRiskCount: 1,
  });
});

test('the post lists are bounded and their totals never fall below what is listed', () => {
  const problems = Array.from({ length: 14 }, (_, i) => ({ id: 'post-' + i, channel: 'facebook', state: 'held', reason: 'overdue', at: '2026-11-11T10:00:00.000Z' }));
  const publication = checkedSeo({ ...reply, publication: { ...PUBLICATION, problems, problemsCount: 14, atRiskCount: 0 } }).publication;
  assert.equal(publication.problems.length, 10);
  assert.equal(publication.problemsCount, 14);
  assert.equal(publication.atRiskCount, 1);
});

