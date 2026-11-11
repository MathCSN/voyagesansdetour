import {test} from 'node:test';
import assert from 'node:assert/strict';
import {socialQueue,guideQueue,parsePinterestRss,summarizeRuns,computeAlerts,renderReport,seoLines} from './weekly-report.mjs';
import {publicationLines} from './publication-report.mjs';

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

const QUIET={social:{horizon:{instagram:'2026-12-01T00:00:00Z',facebook:'2026-12-01T00:00:00Z'}},guides:{nextGuideAt:'2026-11-10T00:00:00Z'},runs:[],stopAt:'2027-09-14T21:59:59Z',now:NOW};
const SEO={search:{period:{startDate:'2026-10-12',endDate:'2026-11-08'},clicks:6,impressions:771,previousClicks:1,previousImpressions:120,rising:[{query:'sapin rockefeller center 2026',impressions:37,previousImpressions:0,position:10.2}]},
  indexation:{total:59,inspected:59,indexed:40,notIndexedCount:19,notIndexed:[{path:'/japon/',state:'Détectée, actuellement non indexée'},{path:'/guides/',state:''}],trend:{status:'stable'}}};

test('search figures are reported with the previous period, indexed pages and rising queries',()=>{
  const lines=seoLines(SEO).join('\n');
  assert.ok(lines.includes('6 clics et 771 impressions du 2026-10-12 au 2026-11-08 (28 jours précédents : 1 clic et 120 impressions)'),lines);
  assert.ok(lines.includes('40 pages indexées sur 59 inspectées (59 dans le plan du site)'),lines);
  assert.ok(lines.includes('Pas encore indexées (19) : `/japon/` (Détectée, actuellement non indexée), `/guides/`'),lines);
  assert.ok(lines.includes('« sapin rockefeller center 2026 » (37 impressions, 0 avant, position 10,2)'),lines);
  const md=renderReport({now:NOW,social:{items:[],horizon:{},lastWeek:[]},guides:{published:[],upcomingGuides:[],upcomingUpdates:[],nextGuideAt:null},pins:[],runs:[],alerts:[],waiting:[],seo:SEO});
  assert.ok(md.includes('## Référencement Google'));
  assert.ok(md.indexOf('## Référencement Google')<md.indexOf('## File à venir'));
});

test('a missing search reading is said plainly and never raises an alert',()=>{
  assert.deepEqual(seoLines(null),['- Relevé Search Console indisponible cette semaine (panneau privé injoignable ou pas encore à jour).']);
  assert.ok(seoLines({search:null,indexation:null}).join('\n').includes('pas encore relevé'));
  assert.deepEqual(computeAlerts({...QUIET,seo:null}),[]);
  assert.deepEqual(computeAlerts({...QUIET,seo:SEO}),[]);
  // An incomplete first inspection round is not a regression.
  assert.ok(seoLines({search:null,indexation:{...SEO.indexation,inspected:16}}).join('\n').includes('tournée d’inspection en cours'));
});

test('alerts fire when indexed pages or impressions fall',()=>{
  const dropped={...SEO,indexation:{...SEO.indexation,trend:{status:'drop',lost:8,reference:48,referenceDay:'2026-11-01'}}};
  const alerts=computeAlerts({...QUIET,seo:dropped});
  assert.deepEqual(alerts.map(a=>a.code),['indexation_drop']);
  assert.ok(alerts[0].message.includes('8 pages de moins qu’au 2026-11-01 (48 puis 40)'),alerts[0].message);
  const fewer=computeAlerts({...QUIET,seo:{...SEO,search:{...SEO.search,impressions:300,previousImpressions:900}}});
  assert.deepEqual(fewer.map(a=>a.code),['search_impressions_drop']);
  // A small site moves a lot from week to week: tiny volumes never alert.
  assert.deepEqual(computeAlerts({...QUIET,seo:{...SEO,search:{...SEO.search,impressions:40,previousImpressions:120}}}),[]);
});

const AT=Date.parse('2026-11-12T09:00:00Z');
const PUBLICATION={enabled:true,channels:{instagram:'connected',facebook:'connected',tiktok:'absent'},lastPassAt:'2026-11-12T08:37:00.000Z',
  counts:{ready:4,submitting:0,scheduled:2,published:12,to_verify:0,held:0,failed:0},problems:[],problemsCount:0,atRisk:[],atRiskCount:0};
const publicationAlerts=publication=>computeAlerts({...QUIET,now:AT,seo:{search:null,indexation:null,publication}});
const held=(id,at,reason='overdue')=>({id,channel:'instagram',state:'held',reason,at});

test('the publication section gives the engine, the channels, the register and the posts in trouble',()=>{
  const lines=publicationLines({...PUBLICATION,channels:{instagram:'disconnected',facebook:'connected',tiktok:'absent'},counts:{...PUBLICATION.counts,held:1,failed:1},
    problems:[held('ig:retenu','2026-11-10T17:00:00.000Z'),{id:'fb:echec',channel:'facebook',state:'failed',reason:'http_500',at:'2026-11-11T10:00:00.000Z'}],problemsCount:2,
    atRisk:[{id:'ig:pret',channel:'instagram',dueAt:'2026-11-12T17:00:00.000Z',channelState:'disconnected'}],atRiskCount:1}).join('\n');
  assert.ok(lines.includes('- Moteur du panneau : actif, dernier passage le 2026-11-12 à 09:37, heure de Paris.'),lines);
  assert.ok(lines.includes('- Canaux Buffer : Instagram déconnecté de Buffer, Facebook connecté, TikTok absent de Buffer.'),lines);
  assert.ok(lines.includes('- Registre : 4 prêts, 2 programmés dans Buffer, 12 publiés, 1 retenu, 1 en échec.'),lines);
  assert.ok(lines.includes('- Retenus ou en échec depuis 7 jours (2) : `ig:retenu` (Instagram, retenu, échéance dépassée, 2026-11-10) ; `fb:echec` (Facebook, en échec, code `http_500`, 2026-11-11).'),lines);
  assert.ok(lines.includes('- Prêts à moins de 24 h sur un canal qui ne reçoit rien (1) : `ig:pret` (Instagram déconnecté de Buffer, échéance le 2026-11-12 à 18:00, heure de Paris).'),lines);
  const md=renderReport({now:AT,social:{items:[],horizon:{},lastWeek:[]},guides:{published:[],upcomingGuides:[],upcomingUpdates:[],nextGuideAt:null},pins:[],runs:[],alerts:[],waiting:[],seo:{search:null,indexation:null,publication:PUBLICATION}});
  assert.ok(md.indexOf('## Publié cette semaine')<md.indexOf('## Publication')&&md.indexOf('## Publication')<md.indexOf('## Référencement Google'));
  assert.ok(md.includes('- Moteur du panneau : actif'));
});

test('a healthy or empty register is said in one line each',()=>{
  const lines=publicationLines({...PUBLICATION,enabled:false,channels:null,lastPassAt:null,counts:{ready:0,submitting:0,scheduled:0,published:0,to_verify:0,held:0,failed:0}});
  assert.deepEqual(lines,['- Moteur du panneau : désactivé, aucun passage enregistré.','- Canaux Buffer : aucun accès Buffer enregistré dans le panneau.','- Registre : vide.']);
  assert.equal(publicationLines(PUBLICATION).length,3);
});

test('a missing publication reading is said plainly and never raises an alert',()=>{
  assert.deepEqual(publicationLines(null),['- État du moteur de publication indisponible (panneau privé injoignable ou pas encore à jour).']);
  const md=renderReport({now:AT,social:{items:[],horizon:{},lastWeek:[]},guides:{published:[],upcomingGuides:[],upcomingUpdates:[],nextGuideAt:null},pins:[],runs:[],alerts:[],waiting:[]});
  assert.ok(md.includes('## Publication\n\n- État du moteur de publication indisponible'));
  assert.deepEqual(computeAlerts({...QUIET,now:AT,seo:null}),[]);
  assert.deepEqual(publicationAlerts(null),[]);
  assert.deepEqual(publicationAlerts(PUBLICATION),[]);
});

test('alerts name the channel that no longer receives posts and say what to do, then clear once it is back',()=>{
  const alerts=publicationAlerts({...PUBLICATION,channels:{instagram:'disconnected',facebook:'locked',tiktok:'paused'}});
  assert.deepEqual(alerts.map(a=>a.code),['publication_channel:instagram','publication_channel:facebook','publication_channel:tiktok']);
  assert.ok(alerts[0].message.startsWith('Instagram déconnecté de Buffer : ses posts ne partent plus.'),alerts[0].message);
  for(const alert of alerts)assert.ok(alert.message.includes('publish.buffer.com > Channels'),alert.message);
  assert.ok(alerts[1].message.includes('Facebook verrouillé par Buffer'),alerts[1].message);
  assert.ok(alerts[2].message.includes('TikTok en pause dans Buffer'),alerts[2].message);
  // TikTok is optional: absent is not a fault. Instagram and Facebook are not.
  assert.deepEqual(publicationAlerts({...PUBLICATION,channels:{instagram:'absent',facebook:'unknown',tiktok:'absent'}}).map(a=>a.code),['publication_channel:instagram']);
  assert.deepEqual(publicationAlerts({...PUBLICATION,channels:null}).map(a=>a.code),['publication_buffer_access']);
  assert.deepEqual(publicationAlerts(PUBLICATION),[]);
});

test('an alert fires when the engine has not passed for more than six hours, or is switched off',()=>{
  const silent=publicationAlerts({...PUBLICATION,lastPassAt:'2026-11-12T02:59:00.000Z'});
  assert.deepEqual(silent.map(a=>a.code),['publication_engine_silent']);
  assert.ok(silent[0].message.includes('depuis le 2026-11-12 à 03:59, heure de Paris (plus de 6 heures)'),silent[0].message);
  assert.deepEqual(publicationAlerts({...PUBLICATION,lastPassAt:'2026-11-12T03:00:00.000Z'}),[]);
  const never=publicationAlerts({...PUBLICATION,lastPassAt:null});
  assert.deepEqual(never.map(a=>a.code),['publication_engine_silent']);
  assert.ok(never[0].message.includes('n’a encore enregistré aucun passage'),never[0].message);
  assert.deepEqual(publicationAlerts({...PUBLICATION,enabled:false,lastPassAt:null}).map(a=>a.code),['publication_engine_disabled']);
});

test('posts held or failed within seven days raise one alert; a retired or older one does not',()=>{
  const alerts=publicationAlerts({...PUBLICATION,problems:[held('ig:retenu','2026-11-10T17:00:00.000Z'),{id:'fb:echec',channel:'facebook',state:'failed',reason:'buffer_mutation_error',at:'2026-11-11T10:00:00.000Z'}],problemsCount:2});
  assert.deepEqual(alerts.map(a=>a.code),['publication_posts_blocked']);
  assert.ok(alerts[0].message.startsWith('2 posts retenus ou en échec depuis moins de 7 jours : `ig:retenu` (Instagram, retenu, échéance dépassée) ; `fb:echec` (Facebook, en échec, refusé par Buffer).'),alerts[0].message);
  assert.deepEqual(publicationAlerts({...PUBLICATION,problems:[held('ig:retire','2026-11-11T10:00:00.000Z','retired'),held('ig:vieux','2026-11-05T08:59:59.000Z')],problemsCount:2}),[]);
  const many=publicationAlerts({...PUBLICATION,problems:Array.from({length:7},(_,i)=>held('post-'+i,'2026-11-11T10:00:00.000Z')),problemsCount:9});
  assert.ok(many[0].message.startsWith('9 posts retenus ou en échec'),many[0].message);
  assert.ok(many[0].message.includes('`post-4` (Instagram, retenu, échéance dépassée) et 4 autres.'),many[0].message);
  assert.ok(!many[0].message.includes('post-5'));
  assert.ok(publicationAlerts({...PUBLICATION,problems:[held('seul','2026-11-11T10:00:00.000Z')],problemsCount:1})[0].message.startsWith('1 post retenu ou en échec depuis moins de 7 jours : '));
});

test('ready posts close to their due date on a channel that receives nothing raise an alert',()=>{
  const paused={...PUBLICATION,channels:{...PUBLICATION.channels,tiktok:'paused'},atRisk:[{id:'tk:pret',channel:'tiktok',dueAt:'2026-11-12T11:00:00.000Z',channelState:'paused'}],atRiskCount:1};
  const alerts=publicationAlerts(paused);
  assert.deepEqual(alerts.map(a=>a.code),['publication_channel:tiktok','publication_posts_at_risk']);
  assert.ok(alerts[1].message.startsWith('1 post prêt à moins de 24 h'),alerts[1].message);
  assert.ok(alerts[1].message.includes('`tk:pret` (TikTok en pause dans Buffer, échéance le 2026-11-12 à 12:00, heure de Paris)'),alerts[1].message);
});

test('TikTok left out of Buffer on purpose never alerts, for its channel or for its posts',()=>{
  // The panel imports TikTok batches even when no TikTok channel exists in Buffer: they wait, then are held.
  const leftOut={...PUBLICATION,atRisk:[{id:'tk:pret',channel:'tiktok',dueAt:'2026-11-12T11:00:00.000Z',channelState:'absent'}],atRiskCount:1,
    problems:[{id:'tk:retenu',channel:'tiktok',state:'held',reason:'overdue',at:'2026-11-11T10:00:00.000Z'}],problemsCount:1};
  assert.deepEqual(publicationAlerts(leftOut),[]);
  assert.ok(publicationLines(leftOut).join('\n').includes('`tk:retenu`'));
  // Instagram is required: the same situation alerts.
  const required={...leftOut,channels:{...PUBLICATION.channels,instagram:'absent'},atRisk:[{id:'ig:pret',channel:'instagram',dueAt:'2026-11-12T11:00:00.000Z',channelState:'absent'}],problems:[held('ig:retenu','2026-11-11T10:00:00.000Z')]};
  assert.deepEqual(publicationAlerts(required).map(a=>a.code),['publication_channel:instagram','publication_posts_blocked','publication_posts_at_risk']);
});

test('a short list filled with posts of a left-out network never hides the posts beyond it',()=>{
  // The panel sends ten posts at most: here all ten are TikTok while TikTok is out of Buffer, and one more exists.
  const tiktok=i=>({id:'tk:'+i,channel:'tiktok',dueAt:'2026-11-12T11:00:00.000Z',channelState:'absent'});
  const risk=publicationAlerts({...PUBLICATION,atRisk:Array.from({length:10},(_,i)=>tiktok(i)),atRiskCount:11});
  assert.deepEqual(risk.map(a=>a.code),['publication_posts_at_risk']);
  assert.ok(risk[0].message.startsWith('1 post prêt à moins de 24 h de l’échéance sur un canal qui ne reçoit rien : non détaillés ici'),risk[0].message);
  const heldTiktok=i=>({id:'tk:'+i,channel:'tiktok',state:'held',reason:'overdue',at:'2026-11-11T10:00:00.000Z'});
  const blocked=publicationAlerts({...PUBLICATION,problems:Array.from({length:10},(_,i)=>heldTiktok(i)),problemsCount:12});
  assert.deepEqual(blocked.map(a=>a.code),['publication_posts_blocked']);
  assert.ok(blocked[0].message.startsWith('2 posts retenus ou en échec depuis moins de 7 jours : non détaillés ici'),blocked[0].message);
  // Fewer names than posts: the remainder is always said.
  const mixed=publicationAlerts({...PUBLICATION,problems:[held('ig:retenu','2026-11-11T10:00:00.000Z'),...Array.from({length:9},(_,i)=>heldTiktok(i))],problemsCount:13});
  assert.ok(mixed[0].message.startsWith('4 posts retenus ou en échec depuis moins de 7 jours : `ig:retenu` (Instagram, retenu, échéance dépassée) et 3 autres.'),mixed[0].message);
});

test('publication alerts come first and leave the other alerts untouched',()=>{
  const dropped={...SEO,indexation:{...SEO.indexation,trend:{status:'drop',lost:8,reference:48,referenceDay:'2026-11-01'}},publication:{...PUBLICATION,channels:{...PUBLICATION.channels,instagram:'disconnected'}}};
  assert.deepEqual(computeAlerts({...QUIET,now:AT,seo:dropped}).map(a=>a.code),['publication_channel:instagram','indexation_drop']);
  for(const alert of publicationAlerts({...PUBLICATION,channels:null,enabled:false,problems:[held('a','2026-11-11T10:00:00.000Z')],atRisk:[{id:'b',channel:'facebook',dueAt:'2026-11-12T11:00:00.000Z',channelState:'unknown'}]}))assert.doesNotMatch(alert.message,/[@\[\]<#!]|https?:/,alert.message);
});

