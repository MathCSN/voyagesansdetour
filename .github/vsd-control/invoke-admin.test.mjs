// Tests du client du panneau vsd-admin, sans réseau ni secret réel.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ControlError, invoke, safeDiagnostic } from './invoke-admin.mjs';

const KEY = Buffer.alloc(32, 5).toString('base64url');
const env = kind => ({ VSD_ADMIN_ORIGIN: 'https://vsd-admin.kartier.workers.dev', VSD_ADMIN_TICK_KEY: KEY, VSD_TICK_KIND: kind });
const reply = (body, status = 200) => async () => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const clock = () => Date.parse('2026-11-10T10:00:00Z');

test('une publication confirmée passe, une seule requête', async () => {
  assert.deepEqual(await invoke({ env: env('publications'), fetcher: reply({ kind: 'publications', status: 'dispatched' }), clock, log: () => {} }), { status: 'confirmed', requests: 1 });
});
test('un moteur resté désactivé après la bascule fait échouer le workflow', async () => {
  await assert.rejects(invoke({ env: env('publications'), fetcher: reply({ kind: 'publications', status: 'disabled' }), clock, log: () => {} }), { code: 'task_attention_required' });
});
test('statut « attention » ou « quota_epuise » du panneau : le workflow de secours échoue, exprès', async () => {
  for (const status of ['attention', 'quota_epuise']) {
    await assert.rejects(invoke({ env: env('publications'), fetcher: reply({ kind: 'publications', status }), clock, log: () => {} }), { code: 'task_attention_required' }, status);
  }
  assert.ok((await invoke({ env: env('publications'), fetcher: reply({ kind: 'publications', status: 'busy_or_recent' }), clock, log: () => {} })).status === 'confirmed');
});
test('configuration incomplète ou origine inattendue : aucun appel', async () => {
  let called = false;
  const fetcher = async () => { called = true; };
  await assert.rejects(invoke({ env: { ...env('health'), VSD_ADMIN_TICK_KEY: '' }, fetcher, clock }), { code: 'configuration' });
  await assert.rejects(invoke({ env: { ...env('health'), VSD_ADMIN_ORIGIN: 'https://evil.example' }, fetcher, clock }), { code: 'configuration' });
  assert.equal(called, false);
});
test('erreur HTTP : diagnostic sans détail du fournisseur', async () => {
  const error = await invoke({ env: env('health'), fetcher: reply({ error: 'x' }, 401), clock }).catch(e => e);
  assert.ok(error instanceof ControlError);
  assert.equal(safeDiagnostic(error), 'Panel task not confirmed: http_non_success (HTTP 401). No automatic retry was made.');
});
test('après la date d\'arrêt, plus aucun appel', async () => {
  assert.deepEqual(await invoke({ env: env('health'), clock: () => Date.parse('2027-09-15T00:00:00Z') }), { status: 'period_ended', requests: 0 });
});
