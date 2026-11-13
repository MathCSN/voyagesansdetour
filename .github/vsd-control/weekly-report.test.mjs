import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {socialQueue,guideQueue,parsePinterestRss,summarizeRuns,computeAlerts,renderReport,seoLines,unreadKinds,runNumber,memoryWarning} from './weekly-report.mjs';
import {PUBLICATION_KINDS,publicationLines,readingState} from './publication-report.mjs';

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
    candidates:[{id:'ou-dormir-porto-2026-11-22',releaseAt:'2026-11-22T08:00:00Z',article:{title:'Où dormir à Porto'}},{id:'auto-mise-a-jour-x-2026-12-06',releaseAt:'2026-12-06T08:00:00Z',article:{title:'X'}},
      // The build never releases a candidate that is only a source recheck: it is not a coming update.
      {id:'auto-mise-a-jour-y-2026-12-20',releaseAt:'2026-12-20T08:00:00Z',article:{title:'Y'},review:{method:'deterministic-source-recheck-v1'}}],
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

test('alerts fire when the social queue runs dry, and stay quiet otherwise',()=>{
  // Guides are written straight into the catalogue: an empty guide queue is the normal state, not an alert.
  const dry=computeAlerts({social:{horizon:{instagram:'2026-11-01T17:00:00Z'}},guides:{nextGuideAt:null},runs:[],stopAt:'2027-09-14T21:59:59Z',now:NOW});
  assert.deepEqual(dry.map(a=>a.code),['social_queue_low:instagram','social_queue_empty:facebook']);
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
const PUBLICATION={enabled:true,channels:{instagram:'connected',facebook:'connected',tiktok:'absent'},channelsCheckedAt:'2026-11-12T08:02:00.000Z',lastPassAt:'2026-11-12T08:37:00.000Z',
  counts:{ready:4,submitting:0,scheduled:2,published:12,to_verify:0,held:0,failed:0},problems:[],problemsCount:0,atRisk:[],atRiskCount:0};
const publicationAlerts=publication=>computeAlerts({...QUIET,now:AT,seo:{search:null,indexation:null,publication}});
const held=(id,at,reason='overdue')=>({id,channel:'instagram',state:'held',reason,at});

test('the publication section gives the engine, the channels, the register and the posts in trouble',()=>{
  const lines=publicationLines({...PUBLICATION,channels:{instagram:'disconnected',facebook:'connected',tiktok:'absent'},counts:{...PUBLICATION.counts,held:1,failed:1},
    problems:[held('ig:retenu','2026-11-10T17:00:00.000Z'),{id:'fb:echec',channel:'facebook',state:'failed',reason:'http_500',at:'2026-11-11T10:00:00.000Z'}],problemsCount:2,
    atRisk:[{id:'ig:pret',channel:'instagram',dueAt:'2026-11-12T17:00:00.000Z',channelState:'disconnected'}],atRiskCount:1}).join('\n');
  assert.ok(lines.includes('- Moteur du panneau : actif, dernier passage le 2026-11-12 à 09:37, heure de Paris.'),lines);
  assert.ok(lines.includes('- Canaux Buffer : Instagram déconnecté de Buffer, Facebook connecté, TikTok absent de Buffer ; relus par le panneau le 2026-11-12 à 09:02, heure de Paris.'),lines);
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
  // The panel gave no date for its last re-reading of the channels: said, not guessed.
  assert.equal(publicationLines({...PUBLICATION,channelsCheckedAt:null})[1],'- Canaux Buffer : Instagram connecté, Facebook connecté, TikTok absent de Buffer ; date de leur dernière relecture non donnée par le panneau.');
});

test('channels the panel has not re-read for more than a day raise an alert, whatever the engine does',()=>{
  const stale=publicationAlerts({...PUBLICATION,channelsCheckedAt:'2026-11-11T08:59:00.000Z'});
  assert.deepEqual(stale.map(a=>a.code),['publication_channels_stale']);
  assert.ok(stale[0].message.startsWith('Le panneau n’a pas relu les canaux Buffer depuis le 2026-11-11 à 09:59, heure de Paris (plus de 24 heures)'),stale[0].message);
  assert.ok(stale[0].message.includes('page Connexions du panneau'),stale[0].message);
  assert.equal(stale[0].count,undefined);
  // The panel rewrites the date every six hours at most: a day is well beyond a late run. Exactly a day is not late yet.
  assert.deepEqual(publicationAlerts({...PUBLICATION,channelsCheckedAt:'2026-11-11T09:00:00.000Z'}),[]);
  // No date (an older panel, a key just saved) or a date ahead of the clock: unknown is not late.
  assert.deepEqual(publicationAlerts({...PUBLICATION,channelsCheckedAt:null}),[]);
  assert.deepEqual(publicationAlerts({...PUBLICATION,channelsCheckedAt:'2026-11-13T09:00:00.000Z'}),[]);
  // Without a Buffer access there are no channels to re-read: only the missing access is said.
  assert.deepEqual(publicationAlerts({...PUBLICATION,channels:null,channelsCheckedAt:'2026-11-01T09:00:00.000Z'}).map(a=>a.code),['publication_buffer_access']);
  // The channel states shown are then old ones: said after the channel and the engine, before the posts.
  const all=publicationAlerts({...PUBLICATION,channels:{instagram:'disconnected',facebook:'connected',tiktok:'absent'},channelsCheckedAt:'2026-11-10T09:00:00.000Z',lastPassAt:'2026-11-12T02:00:00.000Z',
    problems:[held('ig:a','2026-11-10T17:00:00.000Z')],problemsCount:1});
  assert.deepEqual(all.map(a=>a.code),['publication_channel:instagram','publication_engine_silent','publication_channels_stale','publication_posts_blocked']);
  assert.deepEqual(publicationAlerts({...PUBLICATION,enabled:false,channelsCheckedAt:'2026-11-10T09:00:00.000Z'}).map(a=>a.code),['publication_engine_disabled','publication_channels_stale']);
});

test('a missing publication reading is said plainly in the report',()=>{
  assert.deepEqual(publicationLines(null),['- État du moteur de publication indisponible (panneau privé injoignable ou pas encore à jour).']);
  const md=renderReport({now:AT,social:{items:[],horizon:{},lastWeek:[]},guides:{published:[],upcomingGuides:[],upcomingUpdates:[],nextGuideAt:null},pins:[],runs:[],alerts:[],waiting:[]});
  assert.ok(md.includes('## Publication\n\n- État du moteur de publication indisponible'));
  assert.deepEqual(publicationAlerts(PUBLICATION),[]);
});

test('a panel that stops giving the engine state is an alert at the second run in a row, not at the first miss',()=>{
  const HOUR=36e5,iso=value=>new Date(value).toISOString();
  const alerts=(seo,reading,now)=>computeAlerts({...QUIET,now,seo,reading});
  // First miss, at run 7: remembered with the number of the run, no alert.
  const first=readingState(null,null,AT,7);
  assert.deepEqual(first,{missingSince:iso(AT),reason:'panel_unreadable',run:7});
  assert.deepEqual(alerts(null,first,AT),[]);
  // Still missing at the next run: the alert says since when and why it matters.
  const second=readingState(first,null,AT+6*HOUR,8);
  assert.deepEqual(second,{missingSince:iso(AT),reason:'panel_unreadable',run:8});
  const raised=alerts(null,second,AT+6*HOUR);
  assert.deepEqual(raised.map(a=>a.code),['publication_reading_missing']);
  assert.ok(raised[0].message.startsWith('Le panneau ne répond plus au rapport depuis le 2026-11-12 à 10:00, heure de Paris'),raised[0].message);
  assert.ok(raised[0].message.includes('aveugles'),raised[0].message);
  // The panel answers but without the publication block: same alert, another cause.
  const noBlock={search:null,indexation:null,publication:null};
  const absent=readingState(readingState(null,noBlock,AT,7),noBlock,AT+6*HOUR,8);
  assert.equal(absent.reason,'block_absent');
  assert.ok(alerts(noBlock,absent,AT+6*HOUR)[0].message.startsWith('Le panneau répond sans l’état du moteur de publication'));
  // A good reading clears the memory, and the alert with it.
  const back={search:null,indexation:null,publication:{...PUBLICATION,channelsCheckedAt:iso(AT+12*HOUR-HOUR),lastPassAt:iso(AT+12*HOUR-20*6e4)}};
  assert.deepEqual(readingState(second,back,AT+12*HOUR,9),{missingSince:null,run:9});
  assert.deepEqual(alerts(back,readingState(second,back,AT+12*HOUR,9),AT+12*HOUR),[]);
  // A lost, malformed or future memory starts the delay again instead of alerting on its own.
  for(const previous of [undefined,{},{run:6},{missingSince:'hier',run:6},{missingSince:iso(AT+48*HOUR),run:6},{missingSince:42,run:6}])assert.equal(readingState(previous,null,AT,7).missingSince,iso(AT));
  // Without any memory (an older caller), a missing reading stays silent.
  assert.deepEqual(computeAlerts({...QUIET,now:AT,seo:null}),[]);
});

test('the run before is known by its number, however late GitHub starts the runs',()=>{
  const HOUR=36e5,iso=value=>new Date(value).toISOString();
  const codes=(reading,now)=>computeAlerts({...QUIET,now,seo:null,reading}).map(a=>a.code);
  const k=readingState(null,null,AT,7);
  // GitHub starts scheduled runs hours late: the next run comes 27 hours after, and the panel is still mute.
  const late=readingState(k,null,AT+27*HOUR,8);
  assert.equal(late.missingSince,iso(AT));
  assert.deepEqual(codes(late,AT+27*HOUR),['publication_reading_missing']);
  // Run 7 misses; run 8 reads the panel but its memory is not saved; run 9 misses: only one miss is known.
  const afterGap=readingState(k,null,AT+12*HOUR,9);
  assert.deepEqual(afterGap,{missingSince:iso(AT+12*HOUR),reason:'panel_unreadable',run:9});
  assert.deepEqual(codes(afterGap,AT+12*HOUR),[]);
  // Run 10 misses too: two misses in a row, the alert is due, dated from run 9.
  const next=readingState(afterGap,null,AT+18*HOUR,10);
  assert.equal(next.missingSince,iso(AT+12*HOUR));
  assert.deepEqual(codes(next,AT+18*HOUR),['publication_reading_missing']);
  // The same run started again (« Re-run ») keeps its number: it follows its own first attempt.
  assert.equal(readingState(k,null,AT+5*HOUR,7).missingSince,iso(AT));
  // Two runs in a row a few minutes apart (a manual run after a scheduled one) are one outage, not yet an alert.
  const close=readingState(k,null,AT+10*6e4,8);
  assert.equal(close.missingSince,iso(AT));
  assert.deepEqual(codes(close,AT+10*6e4),[]);
  // A memory from a run older than the one before, or without a usable number, does not count.
  for(const run of [5,6,'7',7.5,null,undefined])assert.equal(readingState({...k,run},null,AT+6*HOUR,8).missingSince,iso(AT+6*HOUR),String(run));
  // An earlier run started again after a later one reads the panel after it: the memory is not set back,
  // and keeps the number of the latest run so that the next one still follows.
  const nine={missingSince:iso(AT),reason:'panel_unreadable',run:9};
  const again=readingState(nine,null,AT+5*HOUR,7);
  assert.deepEqual(again,{missingSince:iso(AT),reason:'panel_unreadable',run:9});
  assert.deepEqual(codes(again,AT+5*HOUR),['publication_reading_missing']);
  assert.equal(readingState(again,null,AT+11*HOUR,10).missingSince,iso(AT));
  // Run 9 had read the panel; run 7 started again misses: a first miss, which run 10 then follows.
  const fresh=readingState({missingSince:null,run:9},null,AT+5*HOUR,7);
  assert.deepEqual(fresh,{missingSince:iso(AT+5*HOUR),reason:'panel_unreadable',run:9});
  assert.deepEqual(codes(fresh,AT+5*HOUR),[]);
  assert.equal(readingState(fresh,null,AT+11*HOUR,10).missingSince,iso(AT+5*HOUR));
  // Started again and the panel answers: the outage is over, whatever the number of the run.
  assert.deepEqual(readingState(nine,{search:null,indexation:null,publication:PUBLICATION},AT+5*HOUR,7),{missingSince:null,run:9});
  // No run number at all (a run outside GitHub Actions): nothing follows, the delay starts again each time.
  assert.deepEqual(readingState(k,null,AT+6*HOUR),{missingSince:iso(AT+6*HOUR),reason:'panel_unreadable',run:null});
  assert.equal(readingState({missingSince:iso(AT),reason:'panel_unreadable',run:null},null,AT+6*HOUR,null).missingSince,iso(AT+6*HOUR));
});

test('the run number comes from the workflow, and anything else is no number',()=>{
  assert.equal(runNumber({VSD_REPORT_RUN:'412'}),412);
  for(const value of [undefined,'','0','-3','1.5','12abc','1e3',' 7'])assert.equal(runNumber({VSD_REPORT_RUN:value}),null,String(value));
});

/** Variables of the `env` block of the one step that runs the report; a commented line is not a variable. */
function reportStepEnv(workflow){
  const runsReport=line=>/^(?:- )?(?:run: )?node \.github\/vsd-control\/weekly-report\.mjs(?:\s|$)/.test(line.trim());
  const steps=workflow.split(/\r?\n(?=      - )/).map(step=>step.split(/\r?\n/)).filter(lines=>lines.some(runsReport));
  assert.equal(steps.length,1,'one step runs the report');
  const lines=steps[0],at=lines.findIndex(line=>/^ +env: *$/.test(line));
  if(at<0)return [];
  const inside=line=>!line.trim()||line.search(/\S/)>lines[at].search(/\S/);
  const end=lines.findIndex((line,index)=>index>at&&!inside(line));
  return lines.slice(at+1,end<0?undefined:end).map(line=>line.trim()).filter(Boolean);
}

test('the workflow gives the run number to the step that writes the report, and a missing number is said in the log',async()=>{
  // Without this variable the alert on a mute panel would never be raised.
  const line='VSD_REPORT_RUN: ${{ github.run_number }}';
  const workflow=await readFile(new URL('../workflows/vsd-weekly-report.yml',import.meta.url),'utf8');
  assert.ok(reportStepEnv(workflow).includes(line),'run number not passed to the step that writes the report');
  assert.ok(reportStepEnv(workflow).includes('VSD_REPORT_STATE: .vsd-report-state/state.json'));
  // The guard itself: the line commented out, or moved to another step, is not seen as passed.
  assert.ok(!reportStepEnv(workflow.replace(line,'# '+line)).includes(line));
  const moved=workflow.replace('          '+line+'\n','').replace('          VSD_ALERT_PREVIOUS:','          '+line+'\n          VSD_ALERT_PREVIOUS:');
  assert.ok(moved.includes(line)&&!reportStepEnv(moved).includes(line));
  // Windows line ends change nothing; a step whose command is only a comment does not run the report.
  assert.ok(reportStepEnv(workflow.replaceAll('\n','\r\n')).includes(line));
  assert.throws(()=>reportStepEnv(workflow.replace('          node .github/vsd-control/weekly-report.mjs','          # node .github/vsd-control/weekly-report.mjs')),/one step runs the report/);
  // A memory kept without a run number can never raise that alert: the report says so, as a GitHub warning.
  const warning=memoryWarning({VSD_REPORT_STATE:'.vsd-report-state/state.json'});
  assert.ok(warning.startsWith('::warning::')&&warning.includes('VSD_REPORT_RUN')&&!warning.includes('\n'),warning);
  assert.equal(memoryWarning({VSD_REPORT_STATE:'.vsd-report-state/state.json',VSD_REPORT_RUN:'abc'}),warning);
  assert.equal(memoryWarning({VSD_REPORT_STATE:'.vsd-report-state/state.json',VSD_REPORT_RUN:'412'}),null);
  // No memory asked for (a run by hand, outside the workflow): nothing to warn about.
  assert.equal(memoryWarning({}),null);
});

test('the report says which alerts it could not re-read, so a missed reading neither lifts nor announces them',()=>{
  const read={...SEO,publication:PUBLICATION},writer={runsThisWeek:0,lastAdmissionAt:null};
  assert.deepEqual(unreadKinds({seo:read,writer}),[]);
  assert.deepEqual(unreadKinds({seo:null,writer:null}),[...PUBLICATION_KINDS,'publication_reading_missing','indexation_drop','search_impressions_drop','guide_writer_idle']);
  // The panel answers without the publication block, or without one of the two search readings.
  assert.deepEqual(unreadKinds({seo:{...read,publication:null},writer}),[...PUBLICATION_KINDS,'publication_reading_missing']);
  assert.deepEqual(unreadKinds({seo:{...read,search:null},writer}),['search_impressions_drop']);
  assert.deepEqual(unreadKinds({seo:{...read,indexation:{...SEO.indexation,trend:{status:'unknown'}}},writer}),['indexation_drop']);
  assert.deepEqual(unreadKinds({seo:{...read,indexation:{...SEO.indexation,trend:{status:'drop',lost:8,reference:48,referenceDay:'2026-11-01'}}},writer}),[]);
  // The search for the writer's last admission failed.
  assert.deepEqual(unreadKinds({seo:read,writer:null}),['guide_writer_idle']);
});

test('every alert drawn from the engine state has a kind the report can declare unread',()=>{
  const troubled={...PUBLICATION,channels:{instagram:'disconnected',facebook:'connected',tiktok:'absent'},channelsCheckedAt:'2026-11-10T09:00:00.000Z',lastPassAt:'2026-11-12T02:00:00.000Z',
    problems:[held('ig:a','2026-11-10T17:00:00.000Z')],problemsCount:1,atRisk:[{id:'ig:b',channel:'instagram',dueAt:'2026-11-12T17:00:00.000Z',channelState:'disconnected'}],atRiskCount:1};
  const kinds=[troubled,{...PUBLICATION,channels:null},{...PUBLICATION,enabled:false}].flatMap(publicationAlerts).map(a=>a.code.split(':')[0]);
  assert.deepEqual([...new Set(kinds)].sort(),[...PUBLICATION_KINDS].sort());
});

test('alerts that count posts or guides carry their number, so a growing one can be announced',()=>{
  const two=publicationAlerts({...PUBLICATION,problems:[held('ig:a','2026-11-10T17:00:00.000Z'),held('ig:b','2026-11-11T17:00:00.000Z')],problemsCount:4,
    atRisk:[{id:'ig:c',channel:'instagram',dueAt:'2026-11-12T17:00:00.000Z',channelState:'disconnected'}],atRiskCount:1});
  assert.deepEqual(two.map(a=>[a.code,a.count]),[['publication_posts_blocked',4],['publication_posts_at_risk',1]]);
  const articles=['a','b'].map(slug=>({slug,title:'T',shortTitle:'T',destination:'Lieu',publishedOn:'2026-11-10',sourcesCheckedOn:'2026-09-20'}));
  assert.deepEqual(computeAlerts({...QUIET,now:AT,articles}).map(a=>[a.code,a.count]),[['guide_sources_expired',2]]);
});

test('guide alerts join the others: stale sources, no publication, idle writer',()=>{
  const articles=[{slug:'vieux',title:'Vieux guide',shortTitle:'Vieux',destination:'Lieu',publishedOn:'2026-10-01',sourcesCheckedOn:'2026-09-20'}];
  const alerts=computeAlerts({...QUIET,now:AT,articles,writer:{runsThisWeek:14,lastAdmissionAt:null}});
  assert.deepEqual(alerts.map(a=>a.code),['guide_sources_expired','guide_publication_stalled','guide_writer_idle']);
});

test('the report lists the guides whose sources are about to be too old for the post chain',()=>{
  const sources=[{slug:'lisbonne',checkedOn:'2026-10-24',expiresOn:'2026-12-08',expired:false}];
  const md=renderReport({now:AT,social:{items:[],horizon:{},lastWeek:[]},guides:{published:[],upcomingGuides:[],upcomingUpdates:[],nextGuideAt:null},pins:[],runs:[],alerts:[],waiting:[],sources});
  assert.ok(md.includes('## Sources des guides\n\nAu-delà de 45 jours'),md);
  assert.ok(md.includes('- Le 2026-12-08 (1 guide) : `lisbonne`.'));
  assert.ok(md.indexOf('## Référencement Google')<md.indexOf('## Sources des guides')&&md.indexOf('## Sources des guides')<md.indexOf('## File à venir'));
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

