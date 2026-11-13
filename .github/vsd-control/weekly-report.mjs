// Weekly publication report and empty-queue alerts. Read-only: no provider call, no publication.
import {mkdir,readFile,readdir,writeFile} from 'node:fs/promises';
import {dirname,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {guideAlerts,sourceFreshness,sourceLines,writerActivity} from './guide-health.mjs';
import {PUBLICATION_KINDS,READING_KIND,publicationAlerts,publicationLines,readingState} from './publication-report.mjs';

const DAY=864e5;
export const STOP_AT='2027-09-14T21:59:59Z';
export const SOCIAL_CHANNELS=['instagram','facebook'];
const SOCIAL_LOW_DAYS=14,STOP_WARNING_DAYS=60,REPEATED_FAILURES=2;
const PINTEREST_RSS='https://fr.pinterest.com/voyagesansdetour/feed.rss';
const PROFILES={instagram:'https://www.instagram.com/voyagesansdetour.fr/',facebook:'https://business.facebook.com/latest/posts/published_posts?asset_id=1331092223422242',pinterest:'https://fr.pinterest.com/voyagesansdetour/'};
const UPDATE_PREFIX='auto-mise-a-jour-';
// Candidates of the retired maintenance generator: the build sets them aside (autonomous_editorial.py,
// « source_recheck_is_not_original_editorial_review »), so they are never a coming update.
const RECHECK_ONLY='deterministic-source-recheck-v1';
// Below this volume, a fall in impressions is noise on a young site; at half the previous period it is a signal.
const SEARCH_ALERT_MIN_IMPRESSIONS=300,SEARCH_ALERT_SHARE=0.5;

const day=value=>new Date(value).toISOString().slice(0,10);
const latest=values=>values.reduce((max,value)=>(!max||Date.parse(value)>Date.parse(max)?value:max),null);

export function socialQueue({index,batches,importedIds,now}){
  const retired=new Set((index.retirements??[]).map(r=>r.batchId));
  const imported=importedIds?new Set(importedIds):null;
  const byId=new Map(batches.map(b=>[b.batchId,b]));
  const items=index.items.map(({batchId})=>{
    const item=byId.get(batchId)?.items?.[0];
    if(!item)return {batchId,channel:'inconnu',title:'Lot illisible',dueAt:null,state:'illisible'};
    const state=retired.has(batchId)?'retiré':!imported?'état cloud inconnu':imported.has(batchId)?'importé':'en attente d’import';
    return {batchId,channel:item.payload.channel,title:item.title,dueAt:item.dueAt,state};
  }).sort((a,b)=>Date.parse(a.dueAt??0)-Date.parse(b.dueAt??0));
  const live=items.filter(i=>i.dueAt&&i.state!=='retiré'&&i.state!=='illisible');
  const horizon=Object.fromEntries(SOCIAL_CHANNELS.map(c=>[c,latest(live.filter(i=>i.channel===c).map(i=>i.dueAt))]).filter(([,v])=>v));
  const lastWeek=live.filter(i=>Date.parse(i.dueAt)<=now&&Date.parse(i.dueAt)>now-7*DAY);
  return {items,horizon,lastWeek};
}

export function guideQueue({articles,drafts,candidates,now}){
  const published=articles.filter(a=>a.publishedOn&&Date.parse(a.publishedOn)>now-7*DAY).map(a=>({slug:a.slug,title:a.title,publishedOn:a.publishedOn}));
  const upcoming=[...drafts,...candidates].filter(c=>Date.parse(c.releaseAt)>now&&c.review?.method!==RECHECK_ONLY).map(c=>({id:c.id,title:c.article?.title??c.id,releaseAt:c.releaseAt})).sort((a,b)=>Date.parse(a.releaseAt)-Date.parse(b.releaseAt));
  const upcomingGuides=upcoming.filter(c=>!c.id.startsWith(UPDATE_PREFIX)),upcomingUpdates=upcoming.filter(c=>c.id.startsWith(UPDATE_PREFIX));
  return {published,upcomingGuides,upcomingUpdates,nextGuideAt:upcomingGuides[0]?.releaseAt??null};
}

const text=(xml,tag)=>(xml.match(new RegExp(`<${tag}>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?</${tag}>`))?.[1]??'').trim();
export function parsePinterestRss(xml,since){
  return [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].map(([,item])=>({title:text(item,'title'),url:text(item,'link'),publishedAt:Date.parse(text(item,'pubDate'))}))
    .filter(p=>Number.isFinite(p.publishedAt)&&p.publishedAt>since).map(p=>({...p,publishedAt:new Date(p.publishedAt).toISOString()}));
}

export function summarizeRuns(runs,since){
  const groups=new Map();
  for(const run of runs.filter(r=>Date.parse(r.createdAt)>since)){
    const g=groups.get(run.workflowName)??{workflow:run.workflowName,total:0,failures:0,lastFailureUrl:null};
    g.total++;
    if(run.conclusion==='failure'||run.conclusion==='timed_out'){g.failures++;g.lastFailureUrl??=run.url;}
    groups.set(run.workflowName,g);
  }
  return [...groups.values()].filter(g=>g.failures>0).sort((a,b)=>b.failures-a.failures);
}

const fr=value=>String(value).replace('.',',');
const plural=(count,word)=>`${count} ${word}${count>1?'s':''}`;
/** Search Console figures relayed by the private panel (docs/seo.md); null when the reading is missing. */
export function seoLines(seo){
  if(!seo)return ['- Relevé Search Console indisponible cette semaine (panneau privé injoignable ou pas encore à jour).'];
  const lines=[];
  const {search,indexation}=seo;
  if(search){
    const before=search.previousImpressions===null?'':` (28 jours précédents : ${plural(search.previousClicks??0,'clic')} et ${plural(search.previousImpressions,'impression')})`;
    lines.push(`- Recherche Google : ${plural(search.clicks,'clic')} et ${plural(search.impressions,'impression')} du ${search.period.startDate} au ${search.period.endDate}${before}.`);
    const position=q=>q.position?', position '+fr(q.position):'';
    if(search.rising.length)lines.push('- Requêtes en hausse : '+search.rising.map(q=>`« ${q.query} » (${plural(q.impressions,'impression')}, ${q.previousImpressions} avant${position(q)})`).join(' ; ')+'.');
  }else lines.push('- Clics et impressions : pas encore relevé.');
  if(indexation){
    const round=indexation.inspected<indexation.total*0.9?' ; tournée d’inspection en cours':'';
    lines.push(`- Indexation : ${indexation.indexed} pages indexées sur ${indexation.inspected} inspectées (${indexation.total} dans le plan du site)${round}.`);
    if(indexation.notIndexed.length)lines.push(`- Pas encore indexées (${indexation.notIndexedCount}) : `+indexation.notIndexed.map(p=>'`'+p.path+'`'+(p.state?` (${p.state})`:'')).join(', ')+'.');
  }else lines.push('- Pages indexées : pas encore relevé.');
  return lines;
}

export function computeAlerts({social,runs,seo=null,articles=[],writer=null,reading=null,stopAt=STOP_AT,now}){
  // A channel cut off from Buffer or a silent engine stops every post: said first.
  const alerts=[...publicationAlerts(seo?.publication??null,now,reading)];
  for(const channel of SOCIAL_CHANNELS){
    const horizon=social.horizon[channel];
    if(!horizon||Date.parse(horizon)<=now)alerts.push({code:`social_queue_empty:${channel}`,message:`File ${channel} vide : plus aucun post programmé. Ajouter des lots dans .github/vsd-production/reviewed-social/.`});
    else if(Date.parse(horizon)<now+SOCIAL_LOW_DAYS*DAY)alerts.push({code:`social_queue_low:${channel}`,message:`File ${channel} presque vide : dernier post programmé le ${day(horizon)}.`});
  }
  // Guides are written straight into the catalogue, not through the queue: what counts is what is published.
  alerts.push(...guideAlerts({articles,writer,now}));
  for(const run of runs.filter(r=>r.failures>=REPEATED_FAILURES))alerts.push({code:`workflow_failures:${run.workflow}`,message:`${run.workflow} : ${run.failures} échecs sur ${run.total} exécutions cette semaine (${run.lastFailureUrl}).`});
  const trend=seo?.indexation?.trend;
  if(trend?.status==='drop')alerts.push({code:'indexation_drop',message:`Indexation Google en recul : ${trend.lost} pages de moins qu’au ${trend.referenceDay} (${trend.reference} puis ${seo.indexation.indexed}). Marche à suivre : docs/seo.md.`});
  const search=seo?.search;
  if(search&&search.previousImpressions>=SEARCH_ALERT_MIN_IMPRESSIONS&&search.impressions<search.previousImpressions*SEARCH_ALERT_SHARE)alerts.push({code:'search_impressions_drop',message:`Impressions Google divisées par deux en 28 jours : ${search.impressions} contre ${search.previousImpressions}. Marche à suivre : docs/seo.md.`});
  if(Date.parse(stopAt)-now<STOP_WARNING_DAYS*DAY)alerts.push({code:'authorisation_end',message:`La chaîne s’arrête d’elle-même le ${day(stopAt)} (date STOP dans invoke-admin.mjs, stock-control.mjs et pin_intake.py) : la prolonger.`});
  return alerts;
}

/**
 * Kinds of alerts this run could not re-read, because their source did not answer. The alert issue keeps
 * those it already had as they were known (issue-plan.mjs): a missed reading neither lifts nor announces.
 */
export function unreadKinds({seo,writer}){
  const kinds=[];
  // While the delay of the « unreadable » alert runs again, an alert already raised stays too.
  if(!seo?.publication)kinds.push(...PUBLICATION_KINDS,READING_KIND);
  // A trend the panel could not work out (« unknown ») says nothing: a drop already announced stays until
  // the panel reads « stable » again.
  if(!['stable','drop'].includes(seo?.indexation?.trend?.status))kinds.push('indexation_drop');
  if(!seo?.search)kinds.push('search_impressions_drop');
  if(!writer)kinds.push('guide_writer_idle');
  return kinds;
}

/** Number GitHub gives this run of the workflow (`github.run_number`, passed by the workflow); null elsewhere. */
export function runNumber(env){
  const value=env.VSD_REPORT_RUN;
  return typeof value==='string'&&/^[1-9]\d{0,8}$/.test(value)?Number(value):null;
}

/**
 * A memory kept without a run number never follows another, so the alert on a mute panel could not be raised.
 * Said as a GitHub warning in the log of the run, instead of failing in silence. null when all is in order.
 */
export function memoryWarning(env){
  if(!env.VSD_REPORT_STATE||runNumber(env)!==null)return null;
  return '::warning::Mémoire du rapport sans numéro de passage (VSD_REPORT_RUN absent ou illisible) : l’alerte « état du moteur de publication illisible » ne peut pas se lever.';
}

export function renderReport({now,social,guides,pins,runs,alerts,waiting,seo=null,sources=[]}){
  const line=(items,format,empty)=>items.length?items.map(format).join('\n'):empty;
  return [`# Voyage Sans Détour — rapport du ${day(now)}`,
    '## Publié cette semaine',
    `Instagram (@voyagesansdetour.fr) et Facebook : posts dont l’échéance est passée cette semaine, envoyés par le serveur via Buffer à l’échéance. La preuve de publication n’est pas lisible depuis GitHub : vérifier sur [Instagram](${PROFILES.instagram}) et [Meta Business Suite](${PROFILES.facebook}).`,
    line(social.lastWeek,i=>`- ${day(i.dueAt)} · ${i.channel} · ${i.title} (${i.state})`,'- Aucun post Instagram ou Facebook prévu cette semaine.'),
    pins===null?'- Pinterest : flux public illisible cette semaine, vérifier le profil.':line(pins,p=>`- Pinterest · ${day(p.publishedAt)} · [${p.title.slice(0,90)}](${p.url})`,`- Pinterest : aucune nouvelle épingle ([profil](${PROFILES.pinterest})).`),
    line(guides.published,g=>`- Guide · ${g.publishedOn} · ${g.title}`,'- Aucun nouveau guide publié.'),
    '## Publication',
    publicationLines(seo?.publication??null).join('\n'),
    '## Référencement Google',
    seoLines(seo).join('\n'),
    '## Sources des guides',
    sourceLines(sources).join('\n'),
    '## File à venir',
    line(social.items.filter(i=>i.dueAt&&Date.parse(i.dueAt)>now),i=>`- ${day(i.dueAt)} · ${i.channel} · ${i.title} (${i.state})`,'- Aucun post programmé.'),
    line(guides.upcomingGuides,g=>`- ${day(g.releaseAt)} · nouveau guide · ${g.title}`,'- Aucun nouveau guide programmé.'),
    `- Mises à jour de guides programmées : ${guides.upcomingUpdates.length}.`,
    '## Échecs',
    line(runs,r=>`- ${r.workflow} : ${r.failures} échec(s) sur ${r.total} — [dernier échec](${r.lastFailureUrl})`,'- Aucun workflow en échec cette semaine.'),
    '## Alertes',
    line(alerts,a=>`- ⚠️ ${a.message}`,'- Aucune alerte.'),
    '## Ce qui attend Mathis',
    line(waiting,w=>`- [${w.title}](${w.url}) — ${w.action}`,'- Rien.'),
    ''].join('\n\n');
}

async function readJson(path){return JSON.parse(await readFile(path,'utf8'));}
async function fetchPinterest(since){
  try{
    const response=await fetch(PINTEREST_RSS,{redirect:'follow',signal:AbortSignal.timeout(15000),headers:{'User-Agent':'Mozilla/5.0 (VSD weekly report)'}});
    if(!response.ok)return null;
    return parsePinterestRss((await response.text()).slice(0,1_000_000),since);
  }catch{return null;}
}
function importedFrom(stockOutput){
  // stock-control prints its receipt line then one evidence JSON line.
  const evidence=stockOutput.split('\n').filter(l=>l.startsWith('{')).map(l=>{try{return JSON.parse(l);}catch{return null;}}).find(e=>Array.isArray(e?.importedBatchIds));
  return evidence?evidence.importedBatchIds:null;
}

export async function main({root=process.cwd(),env=process.env,now=Date.now()}={}){
  const social=join(root,'.github/vsd-production/reviewed-social'),site=join(root,'site-src');
  const index=await readJson(join(social,'index.json'));
  const batches=await Promise.all(index.items.map(i=>readJson(join(root,i.path)).catch(()=>({batchId:i.batchId}))));
  const stockOutput=env.VSD_REPORT_STOCK_EVIDENCE?await readFile(env.VSD_REPORT_STOCK_EVIDENCE,'utf8').catch(()=>''):'';
  const candidateFiles=(await readdir(join(site,'editorial-candidates'))).filter(f=>f.endsWith('.json'));
  const articles=await readJson(join(site,'articles.json'));
  const guides=guideQueue({articles,drafts:(await readJson(join(site,'editorial-queue.json'))).drafts,
    candidates:await Promise.all(candidateFiles.map(f=>readJson(join(site,'editorial-candidates',f)))),now});
  const queue=socialQueue({index,batches,importedIds:importedFrom(stockOutput),now});
  const allRuns=env.VSD_REPORT_RUNS?await readJson(env.VSD_REPORT_RUNS):[];
  const runs=summarizeRuns(allRuns,now-7*DAY);
  // Date of the last commit by which the automatic writer admitted a guide, found by the workflow:
  // empty when there is none, « unknown » when the search failed. No file, no alert on the writer.
  const writer=env.VSD_REPORT_LAST_ADMISSION?writerActivity(allRuns,await readFile(env.VSD_REPORT_LAST_ADMISSION,'utf8').catch(()=>'unknown'),now):null;
  // Written by seo-status.mjs just before; absent when the private panel could not be read.
  const seo=env.VSD_REPORT_SEO?await readJson(env.VSD_REPORT_SEO).catch(()=>null):null;
  // Kept by the workflow from one run to the next, with the number of the run: a single missed reading of
  // the panel is not an alert, two runs in a row are.
  const statePath=env.VSD_REPORT_STATE;
  const reading=statePath?readingState((await readJson(statePath).catch(()=>null))?.publicationReading,seo,now,runNumber(env)):null;
  const alerts=computeAlerts({social:queue,guides,runs,seo,articles,writer,reading,now});
  const waiting=(await readJson(join(root,'.github/vsd-control/attente-mathis.json'))).items;
  const report=renderReport({now,social:queue,guides,pins:await fetchPinterest(now-7*DAY),runs,alerts,waiting,seo,sources:sourceFreshness(articles,now)});
  if(statePath){
    await mkdir(dirname(statePath),{recursive:true});
    await writeFile(statePath,JSON.stringify({publicationReading:reading})+'\n');
  }
  const out=env.VSD_REPORT_OUT??root;
  await writeFile(join(out,'vsd-report.md'),report);
  await writeFile(join(out,'vsd-alerts.json'),JSON.stringify(alerts,null,2)+'\n');
  await writeFile(join(out,'vsd-alerts-unread.json'),JSON.stringify(unreadKinds({seo,writer}))+'\n');
  return {alerts:alerts.length,warning:memoryWarning(env)};
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{
    const result=await main();
    if(result.warning)console.log(result.warning);
    console.log(`Rapport écrit ; ${result.alerts} alerte(s).`);
  }
  catch(error){console.error('Rapport non produit : '+(error?.code??error?.name??'erreur'));process.exitCode=1;}
}
