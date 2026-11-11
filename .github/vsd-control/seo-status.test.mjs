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
  assert.deepEqual(checkedSeo({ kind: 'seo', status: 'reported', search: null, indexation: null }), { search: null, indexation: null });
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

