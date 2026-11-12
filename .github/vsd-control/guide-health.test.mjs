import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {SOURCES_MAX_AGE_DAYS,WRITER_WORKFLOW,guideAlerts,sourceFreshness,sourceLines,writerActivity} from './guide-health.mjs';

const NOW=Date.parse('2026-11-30T09:00:00Z');
const guide=(slug,sourcesCheckedOn,publishedOn='2026-11-25')=>({slug,shortTitle:'Guide '+slug,title:'Titre long '+slug,destination:'Lieu',publishedOn,sourcesCheckedOn});
const ARTICLES=[guide('lisbonne','2026-10-24'),guide('porto','2026-10-24'),guide('sintra','2026-10-26'),guide('japon','2026-11-11'),guide('vieux','2026-10-10'),{slug:'sans-date',shortTitle:'x',publishedOn:'2026-11-01'}];
const codes=input=>guideAlerts({articles:ARTICLES,writer:null,now:NOW,...input}).map(a=>a.code);

test('the freshness limit is the one the post chain applies',async()=>{
  const chain=await readFile(new URL('../vsd-production/auto_social.py',import.meta.url),'utf8');
  assert.equal(Number(/MAX_GUIDE_SOURCE_AGE = dt\.timedelta\(days=(\d+)\)/.exec(chain)[1]),SOURCES_MAX_AGE_DAYS);
});

test('guides whose sources pass 45 days within 10 days are listed with their date, expired ones first',()=>{
  const due=sourceFreshness(ARTICLES,NOW);
  assert.deepEqual(due.map(g=>[g.slug,g.expiresOn,g.expired]),[['vieux','2026-11-24',true],['lisbonne','2026-12-08',false],['porto','2026-12-08',false],['sintra','2026-12-10',false]]);
  // The chain holds a guide as soon as 45 full days have passed since the check, counted from midnight UTC.
  assert.equal(sourceFreshness([guide('a','2026-10-16')],NOW)[0].expired,true);
  assert.equal(sourceFreshness([guide('a','2026-10-17')],NOW)[0].expired,false);
  assert.deepEqual(sourceFreshness([guide('a','2026-11-11')],NOW),[]);
  // A guide the chain already ignores (no destination) is not reported as stale.
  assert.deepEqual(sourceFreshness([{...guide('a','2026-10-01'),destination:''}],NOW),[]);
});

test('the report section groups the guides by the day their posts stop',()=>{
  const lines=sourceLines(sourceFreshness(ARTICLES,NOW));
  assert.ok(lines[0].startsWith('Au-delà de 45 jours sans revérification'),lines[0]);
  assert.deepEqual(lines.slice(1),['- Déjà dépassé depuis le 2026-11-24 (1 guide) : `vieux`.','- Le 2026-12-08 (2 guides) : `lisbonne`, `porto`.','- Le 2026-12-10 (1 guide) : `sintra`.']);
  assert.deepEqual(sourceLines([]),['- Aucun guide n’atteint 45 jours sans revérification de ses sources dans les 10 jours.']);
});

test('expired sources raise an alert; guides only close to the limit do not',()=>{
  assert.deepEqual(codes({}),['guide_sources_expired']);
  const alert=guideAlerts({articles:ARTICLES,writer:null,now:NOW})[0];
  assert.ok(alert.message.startsWith('1 guide a des sources vérifiées il y a plus de 45 jours : la chaîne n’en tire plus de posts (`vieux`).'),alert.message);
  assert.deepEqual(codes({articles:ARTICLES.filter(a=>a.slug!=='vieux')}),[]);
});

test('an alert fires when no guide has been published for more than ten days',()=>{
  const quiet=[guide('a','2026-11-25','2026-11-19'),guide('b','2026-11-25','2026-10-01')];
  const alerts=guideAlerts({articles:quiet,writer:null,now:NOW});
  assert.deepEqual(alerts.map(a=>a.code),['guide_publication_stalled']);
  assert.ok(alerts[0].message.includes('depuis le 2026-11-19 (11 jours)'),alerts[0].message);
  assert.deepEqual(guideAlerts({articles:[guide('a','2026-11-25','2026-11-20')],writer:null,now:NOW}),[]);
  assert.deepEqual(guideAlerts({articles:[],writer:null,now:NOW}),[]);
});

test('the automatic writer is counted from the runs of the week',()=>{
  const run=(workflowName,createdAt)=>({workflowName,createdAt,conclusion:'success'});
  const runs=[run(WRITER_WORKFLOW,'2026-11-29T06:23:00Z'),run(WRITER_WORKFLOW,'2026-11-28T15:23:00Z'),run(WRITER_WORKFLOW,'2026-11-01T06:23:00Z'),run('Autre','2026-11-29T06:23:00Z')];
  assert.deepEqual(writerActivity(runs,'',NOW),{runsThisWeek:2,lastAdmissionAt:null});
  assert.deepEqual(writerActivity(runs,'2026-11-20T08:00:00Z\n',NOW),{runsThisWeek:2,lastAdmissionAt:'2026-11-20T08:00:00Z'});
  // The search could not be read: unknown, which is not « never ».
  assert.equal(writerActivity(runs,'unknown',NOW),null);
  assert.equal(writerActivity(runs,'n’importe quoi',NOW),null);
});

test('a writer that runs without admitting any guide for 14 days raises an alert, a sleeping one does not',()=>{
  const fresh=[guide('a','2026-11-25')];
  const never=guideAlerts({articles:fresh,writer:{runsThisWeek:14,lastAdmissionAt:null},now:NOW});
  assert.deepEqual(never.map(a=>a.code),['guide_writer_idle']);
  assert.ok(never[0].message.includes('n’a jamais admis de guide depuis sa mise en route le 2026-10-12'),never[0].message);
  assert.ok(never[0].message.includes('14 passages cette semaine'),never[0].message);
  const stale=guideAlerts({articles:fresh,writer:{runsThisWeek:3,lastAdmissionAt:'2026-11-10T08:00:00Z'},now:NOW});
  assert.ok(stale[0].message.includes('n’a admis aucun guide depuis le 2026-11-10'),stale[0].message);
  assert.deepEqual(guideAlerts({articles:fresh,writer:{runsThisWeek:3,lastAdmissionAt:'2026-11-20T08:00:00Z'},now:NOW}),[]);
  assert.deepEqual(guideAlerts({articles:fresh,writer:{runsThisWeek:0,lastAdmissionAt:null},now:NOW}),[]);
  assert.deepEqual(guideAlerts({articles:fresh,writer:null,now:NOW}),[]);
});
