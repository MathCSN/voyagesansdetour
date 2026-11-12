// Health of the guides, read from the catalogue and from the workflow runs: sources about to be too old
// for the post chain, no guide published for a while, an automatic writer that runs without any result.
const DAY=864e5;
// Same limit as MAX_GUIDE_SOURCE_AGE in .github/vsd-production/auto_social.py (a test compares them):
// past it, the chain draws no more posts from the guide.
export const SOURCES_MAX_AGE_DAYS=45;
const SOURCES_WARNING_DAYS=10;
// Guides come out every two or three days: ten days without one means the writing has stopped.
const GUIDE_SILENCE_DAYS=10;
// vsd-writing-guide.yml: scheduled twice a day since this date; it commits with this message when it admits a guide.
export const WRITER_WORKFLOW='Qualify a source-grounded new VSD guide';
const WRITER_SINCE='2026-10-12',WRITER_IDLE_DAYS=14;

const day=value=>new Date(value).toISOString().slice(0,10);
const isDay=value=>typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(Date.parse(value));
const count=(n,one,many)=>`${n} ${n>1?many:one}`;
const slugs=guides=>guides.map(guide=>'`'+guide.slug+'`').join(', ');

/** Guides whose sources are, or will be within the warning window, too old for the post chain. */
export function sourceFreshness(articles,now){
  // Like the chain (eligible_articles), a guide without its title, card title or destination is not counted:
  // the chain already ignores it, whatever its sources.
  const complete=article=>['title','shortTitle','destination'].every(key=>typeof article[key]==='string'&&article[key]);
  return articles.filter(article=>isDay(article.sourcesCheckedOn)&&/^[a-z0-9-]{1,120}$/.test(article.slug??'')&&complete(article)).map(article=>{
    const expiresAt=Date.parse(article.sourcesCheckedOn)+SOURCES_MAX_AGE_DAYS*DAY;
    return {slug:article.slug,checkedOn:article.sourcesCheckedOn,expiresOn:day(expiresAt),expired:now>expiresAt};
  }).filter(guide=>Date.parse(guide.expiresOn)<=now+SOURCES_WARNING_DAYS*DAY)
    .sort((a,b)=>a.expiresOn.localeCompare(b.expiresOn)||a.slug.localeCompare(b.slug));
}

export function sourceLines(due){
  if(!due.length)return [`- Aucun guide n’atteint ${SOURCES_MAX_AGE_DAYS} jours sans revérification de ses sources dans les ${SOURCES_WARNING_DAYS} jours.`];
  const byDay=new Map();
  for(const guide of due)byDay.set(guide.expiresOn,[...(byDay.get(guide.expiresOn)??[]),guide]);
  return [`Au-delà de ${SOURCES_MAX_AGE_DAYS} jours sans revérification des sources (\`sourcesCheckedOn\`), la chaîne ne tire plus de posts d’un guide.`,
    ...[...byDay].map(([expiresOn,guides])=>`- ${guides[0].expired?'Déjà dépassé depuis le':'Le'} ${expiresOn} (${count(guides.length,'guide','guides')}) : ${slugs(guides)}.`)];
}

/** null when the last admission could not be read: unknown is not « never ». */
export function writerActivity(runs,lastAdmission,now){
  const value=String(lastAdmission??'').trim();
  if(value&&!Number.isFinite(Date.parse(value)))return null;
  const runsThisWeek=runs.filter(run=>run.workflowName===WRITER_WORKFLOW&&Date.parse(run.createdAt)>now-7*DAY).length;
  return {runsThisWeek,lastAdmissionAt:value||null};
}

export function guideAlerts({articles,writer,now}){
  const alerts=[];
  const expired=sourceFreshness(articles,now).filter(guide=>guide.expired);
  if(expired.length)alerts.push({code:'guide_sources_expired',count:expired.length,message:`${expired.length>1?expired.length+' guides ont':'1 guide a'} des sources vérifiées il y a plus de ${SOURCES_MAX_AGE_DAYS} jours : la chaîne n’en tire plus de posts (${slugs(expired)}). Revérifier leurs sources, puis mettre à jour sourcesCheckedOn.`});
  const published=articles.map(article=>article.publishedOn).filter(isDay).sort();
  const last=published.at(-1);
  // Whole days: a guide dated ten days ago does not alert, whatever the hour of the run.
  const idleDays=last?Math.floor((now-Date.parse(last))/DAY):0;
  if(idleDays>GUIDE_SILENCE_DAYS)alerts.push({code:'guide_publication_stalled',message:`Aucun guide publié depuis le ${last} (${idleDays} jours) : les routines de rédaction ne sortent plus rien.`});
  // A writer put to sleep has no run this week: nothing to report.
  if(writer?.runsThisWeek>0&&now-Date.parse(writer.lastAdmissionAt??WRITER_SINCE)>WRITER_IDLE_DAYS*DAY){
    const since=writer.lastAdmissionAt?`n’a admis aucun guide depuis le ${day(writer.lastAdmissionAt)}`:`n’a jamais admis de guide depuis sa mise en route le ${WRITER_SINCE}`;
    alerts.push({code:'guide_writer_idle',message:`Le rédacteur automatique de guides (vsd-writing-guide) ${since} : ${count(writer.runsThisWeek,'passage','passages')} cette semaine, sans résultat. Lire l’artefact new-guide-proposal de son dernier passage, ou le mettre en sommeil.`});
  }
  return alerts;
}
