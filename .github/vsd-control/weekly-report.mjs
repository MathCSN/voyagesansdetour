// Weekly publication report and empty-queue alerts. Read-only: no provider call, no publication.
import {readFile,readdir,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';

const DAY=864e5;
export const STOP_AT='2027-09-14T21:59:59Z';
export const SOCIAL_CHANNELS=['instagram','facebook'];
const SOCIAL_LOW_DAYS=14,GUIDE_LOW_DAYS=28,STOP_WARNING_DAYS=60,REPEATED_FAILURES=2;
const PINTEREST_RSS='https://fr.pinterest.com/voyagesansdetour/feed.rss';
const PROFILES={instagram:'https://www.instagram.com/voyagesansdetour.fr/',facebook:'https://business.facebook.com/latest/posts/published_posts?asset_id=1331092223422242',pinterest:'https://fr.pinterest.com/voyagesansdetour/'};
const UPDATE_PREFIX='auto-mise-a-jour-';

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
  const upcoming=[...drafts,...candidates].filter(c=>Date.parse(c.releaseAt)>now).map(c=>({id:c.id,title:c.article?.title??c.id,releaseAt:c.releaseAt})).sort((a,b)=>Date.parse(a.releaseAt)-Date.parse(b.releaseAt));
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

export function computeAlerts({social,guides,runs,stopAt=STOP_AT,now}){
  const alerts=[];
  for(const channel of SOCIAL_CHANNELS){
    const horizon=social.horizon[channel];
    if(!horizon||Date.parse(horizon)<=now)alerts.push({code:`social_queue_empty:${channel}`,message:`File ${channel} vide : plus aucun post programmé. Ajouter des lots dans .github/vsd-production/reviewed-social/.`});
    else if(Date.parse(horizon)<now+SOCIAL_LOW_DAYS*DAY)alerts.push({code:`social_queue_low:${channel}`,message:`File ${channel} presque vide : dernier post programmé le ${day(horizon)}.`});
  }
  if(!guides.nextGuideAt)alerts.push({code:'guide_queue_empty',message:'File des guides vide : aucun nouveau guide programmé (site-src/editorial-queue.json ou editorial-candidates/).'});
  else if(Date.parse(guides.nextGuideAt)>now+GUIDE_LOW_DAYS*DAY)alerts.push({code:'guide_queue_low',message:`Prochain nouveau guide seulement le ${day(guides.nextGuideAt)}.`});
  for(const run of runs.filter(r=>r.failures>=REPEATED_FAILURES))alerts.push({code:`workflow_failures:${run.workflow}`,message:`${run.workflow} : ${run.failures} échecs sur ${run.total} exécutions cette semaine (${run.lastFailureUrl}).`});
  if(Date.parse(stopAt)-now<STOP_WARNING_DAYS*DAY)alerts.push({code:'authorisation_end',message:`La chaîne s’arrête d’elle-même le ${day(stopAt)} (date STOP dans invoke.mjs, stock-control.mjs et pin_intake.py) : la prolonger.`});
  return alerts;
}

export function renderReport({now,social,guides,pins,runs,alerts,waiting}){
  const line=(items,format,empty)=>items.length?items.map(format).join('\n'):empty;
  return [`# Voyage Sans Détour — rapport du ${day(now)}`,
    '## Publié cette semaine',
    `Instagram (@voyagesansdetour.fr) et Facebook : posts dont l’échéance est passée cette semaine, envoyés par le serveur via Buffer à l’échéance. La preuve de publication n’est pas lisible depuis GitHub : vérifier sur [Instagram](${PROFILES.instagram}) et [Meta Business Suite](${PROFILES.facebook}).`,
    line(social.lastWeek,i=>`- ${day(i.dueAt)} · ${i.channel} · ${i.title} (${i.state})`,'- Aucun post Instagram ou Facebook prévu cette semaine.'),
    pins===null?'- Pinterest : flux public illisible cette semaine, vérifier le profil.':line(pins,p=>`- Pinterest · ${day(p.publishedAt)} · [${p.title.slice(0,90)}](${p.url})`,`- Pinterest : aucune nouvelle épingle ([profil](${PROFILES.pinterest})).`),
    line(guides.published,g=>`- Guide · ${g.publishedOn} · ${g.title}`,'- Aucun nouveau guide publié.'),
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
  const guides=guideQueue({articles:await readJson(join(site,'articles.json')),drafts:(await readJson(join(site,'editorial-queue.json'))).drafts,
    candidates:await Promise.all(candidateFiles.map(f=>readJson(join(site,'editorial-candidates',f)))),now});
  const queue=socialQueue({index,batches,importedIds:importedFrom(stockOutput),now});
  const runs=summarizeRuns(env.VSD_REPORT_RUNS?await readJson(env.VSD_REPORT_RUNS):[],now-7*DAY);
  const alerts=computeAlerts({social:queue,guides,runs,now});
  const waiting=(await readJson(join(root,'.github/vsd-control/attente-mathis.json'))).items;
  const report=renderReport({now,social:queue,guides,pins:await fetchPinterest(now-7*DAY),runs,alerts,waiting});
  const out=env.VSD_REPORT_OUT??root;
  await writeFile(join(out,'vsd-report.md'),report);
  await writeFile(join(out,'vsd-alerts.json'),JSON.stringify(alerts,null,2)+'\n');
  return {alerts:alerts.length};
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{const result=await main();console.log(`Rapport écrit ; ${result.alerts} alerte(s).`);}
  catch(error){console.error('Rapport non produit : '+(error?.code??error?.name??'erreur'));process.exitCode=1;}
}
