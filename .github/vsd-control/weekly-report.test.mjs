import {test} from 'node:test';
import assert from 'node:assert/strict';
import {socialQueue,guideQueue,parsePinterestRss,summarizeRuns,computeAlerts,renderReport} from './weekly-report.mjs';

const NOW=Date.parse('2026-10-26T07:00:00Z');
const batch=(batchId,channel,dueAt,title='Titre')=>({batchId,items:[{title,dueAt,payload:{channel,kind:'reel'}}]});
const index=ids=>({schemaVersion:1,items:ids.map(batchId=>({batchId})),retirements:[{batchId:'retire'}]});

test('social queue marks imported, pending and retired batches and computes the horizon per channel',()=>{
  const batches=[batch('a','instagram','2026-10-25T17:00:00Z'),batch('b','instagram','2026-11-01T17:00:00Z'),batch('c','facebook','2026-11-08T17:00:00Z'),batch('retire','facebook','2026-11-15T17:00:00Z')];
  const queue=socialQueue({index:index(['a','b','c','retire']),batches,importedIds:['a','b'],now:NOW});
  assert.deepEqual(queue.items.map(i=>[i.batchId,i.state]),[['a','importé'],['b','importé'],['c','en attente d’import'],['retire','retiré']]);
  assert.equal(queue.horizon.instagram,'2026-11-01T17:00:00Z');
  assert.equal(queue.horizon.facebook,'2026-11-08T17:00:00Z');
  assert.deepEqual(queue.lastWeek.map(i=>i.batchId),['a']);
});

test('social queue without cloud evidence keeps batches unknown instead of claiming an import',()=>{
  const queue=socialQueue({index:index(['b']),batches:[batch('b','instagram','2026-11-01T17:00:00Z')],importedIds:null,now:NOW});
  assert.equal(queue.items[0].state,'état cloud inconnu');
  assert.equal(queue.horizon.instagram,'2026-11-01T17:00:00Z');
});

test('guide queue separates new guides from updates and lists recent publications',()=>{
  const guides=guideQueue({
    articles:[{slug:'old',title:'Ancien',publishedOn:'2026-09-27'},{slug:'new',title:'Nouveau',publishedOn:'2026-10-25'}],
    drafts:[{id:'guimaraes-2026-10-25',releaseAt:'2026-10-25T08:00:00Z',article:{slug:'guimaraes',title:'Guimarães'}}],
    candidates:[{id:'ou-dormir-porto-2026-11-22',releaseAt:'2026-11-22T08:00:00Z',article:{title:'Où dormir à Porto'}},{id:'auto-mise-a-jour-x-2026-12-06',releaseAt:'2026-12-06T08:00:00Z',article:{title:'X'}}],
    now:NOW});
  assert.deepEqual(guides.published.map(g=>g.slug),['new']);
  assert.deepEqual(guides.upcomingGuides.map(g=>g.id),['ou-dormir-porto-2026-11-22']);
  assert.deepEqual(guides.upcomingUpdates.map(g=>g.id),['auto-mise-a-jour-x-2026-12-06']);
  assert.equal(guides.nextGuideAt,'2026-11-22T08:00:00Z');
});

test('pinterest rss is parsed and filtered to the window',()=>{
  const xml='<rss><channel><item><title><![CDATA[Pin récent]]></title><link>https://fr.pinterest.com/pin/2/</link><pubDate>Sun, 25 Oct 2026 10:00:00 GMT</pubDate></item><item><title>Vieux</title><link>https://fr.pinterest.com/pin/1/</link><pubDate>Tue, 29 Sep 2026 10:12:34 GMT</pubDate></item></channel></rss>';
  const pins=parsePinterestRss(xml,NOW-7*864e5);
  assert.deepEqual(pins,[{title:'Pin récent',url:'https://fr.pinterest.com/pin/2/',publishedAt:'2026-10-25T10:00:00.000Z'}]);
});

test('workflow runs are summarised with failures first',()=>{
  const runs=[{workflowName:'A',conclusion:'success',createdAt:'2026-10-25T00:00:00Z',url:'u1'},{workflowName:'A',conclusion:'failure',createdAt:'2026-10-24T00:00:00Z',url:'u2'},{workflowName:'B',conclusion:'success',createdAt:'2026-10-10T00:00:00Z',url:'u3'}];
  const summary=summarizeRuns(runs,NOW-7*864e5);
  assert.deepEqual(summary,[{workflow:'A',total:2,failures:1,lastFailureUrl:'u2'}]);
});

test('alerts fire when the social or guide queue runs dry, and stay quiet otherwise',()=>{
  const dry=computeAlerts({social:{horizon:{instagram:'2026-11-01T17:00:00Z'}},guides:{nextGuideAt:null},runs:[],stopAt:'2027-09-14T21:59:59Z',now:NOW});
  assert.deepEqual(dry.map(a=>a.code),['social_queue_low:instagram','social_queue_empty:facebook','guide_queue_empty']);
  const full=computeAlerts({social:{horizon:{instagram:'2026-12-01T00:00:00Z',facebook:'2026-12-01T00:00:00Z'}},guides:{nextGuideAt:'2026-11-10T00:00:00Z'},runs:[],stopAt:'2027-09-14T21:59:59Z',now:NOW});
  assert.deepEqual(full,[]);
});

test('alerts flag repeated workflow failures and the approaching authorisation end',()=>{
  const alerts=computeAlerts({social:{horizon:{instagram:'2026-12-01T00:00:00Z',facebook:'2026-12-01T00:00:00Z'}},guides:{nextGuideAt:'2026-11-10T00:00:00Z'},runs:[{workflow:'Cloud',total:4,failures:2,lastFailureUrl:'u'}],stopAt:'2026-12-01T00:00:00Z',now:NOW});
  assert.deepEqual(alerts.map(a=>a.code),['workflow_failures:Cloud','authorisation_end']);
});

test('report renders every section in French with the waiting list',()=>{
  const md=renderReport({now:NOW,social:{items:[],horizon:{},lastWeek:[]},guides:{published:[],upcomingGuides:[],upcomingUpdates:[],nextGuideAt:null},pins:null,runs:[],alerts:[{code:'guide_queue_empty',message:'Aucun guide'}],waiting:[{title:'Reconnecter Buffer',action:'Ouvrir Buffer',url:'https://publish.buffer.com'}]});
  for(const heading of ['## Publié cette semaine','## File à venir','## Échecs','## Alertes','## Ce qui attend Mathis'])assert.ok(md.includes(heading),heading);
  assert.ok(md.includes('Pinterest : flux public illisible'));
  assert.ok(md.includes('[Reconnecter Buffer](https://publish.buffer.com)'));
});
