// What the report workflow does with its two issues. GitHub notifies nobody when the body of an issue
// is edited: the alert issue therefore records the codes of its alerts, a comment announces every alert
// that was not there at the previous run, and the title says what is wrong. The issue is public.
import {readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';

const DAY=864e5,WEEK=7*DAY;
// The weekly report opens from Sunday noon UTC, so it exists before the Monday routines read it.
const REPORT_WEEKDAY=0,REPORT_HOUR_UTC=12;
const NETWORK={instagram:'Instagram',facebook:'Facebook',tiktok:'TikTok'};
const network=name=>NETWORK[name]??'un réseau';
// Short name of an alert, from its code: `kind` or `kind:subject`. A workflow name never enters a title.
const TITLES={
  publication_channel:name=>`${network(name)} coupé de Buffer`,
  publication_buffer_access:()=>'accès Buffer absent du panneau',
  publication_engine_disabled:()=>'moteur de publication désactivé',
  publication_engine_silent:()=>'moteur de publication silencieux',
  publication_reading_missing:()=>'état du moteur de publication illisible',
  publication_posts_blocked:()=>'posts retenus ou en échec',
  publication_posts_at_risk:()=>'posts prêts menacés',
  social_queue_empty:name=>`file ${network(name)} vide`,
  social_queue_low:name=>`file ${network(name)} presque vide`,
  guide_publication_stalled:()=>'aucun guide publié',
  guide_writer_idle:()=>'rédacteur automatique sans résultat',
  guide_sources_expired:()=>'sources de guides périmées',
  workflow_failures:()=>'échecs répétés d’un workflow',
  indexation_drop:()=>'indexation Google en recul',
  search_impressions_drop:()=>'impressions Google en chute',
  authorisation_end:()=>'fin d’autorisation de la chaîne',
};
const capital=text=>text.charAt(0).toUpperCase()+text.slice(1);

export function alertTitle(code){
  const [kind,...subject]=String(code).split(':');
  return Object.hasOwn(TITLES,kind)?TITLES[kind](subject.join(':')):'alerte';
}

// Codes are kept percent-encoded in an HTML comment: no code can close the comment or reach Markdown.
const MARKER=/<!-- vsd-alert-codes: ([A-Za-z0-9%_.~!*'()-]+(?:,[A-Za-z0-9%_.~!*'()-]+)*)? ?-->/;

/** Codes recorded by the previous run; null when there is no issue yet or it predates the record. */
export function previousCodes(body){
  const found=MARKER.exec(body??'');
  if(!found)return null;
  try{return found[1]?found[1].split(',').map(decodeURIComponent):[];}catch{return null;}
}

export function planAlertIssue({alerts,previousBody=null,today,runUrl,owner=''}){
  const codes=alerts.map(alert=>alert.code);
  const known=previousBody===null?null:previousCodes(previousBody);
  const fresh=alerts.filter(alert=>!known?.includes(alert.code));
  const gone=(known??[]).filter(code=>!codes.includes(code));
  const others=alerts.length-1;
  const title=`⚠️ ${capital(alertTitle(codes[0]))}`+(others>0?` et ${others} ${others>1?'autres alertes':'autre alerte'}`:'');
  const list=items=>items.map(alert=>'- '+alert.message).join('\n');
  const body=[`Alertes au ${today} :`,list(alerts),
    'Chaque alerte nouvelle est annoncée par un commentaire sur cette issue. L’issue se ferme seule quand plus aucune alerte ne tient.',
    `Rapport complet : ${runUrl}`,`<!-- vsd-alert-codes: ${codes.map(encodeURIComponent).join(',')} -->`].join('\n\n');
  // Opening an issue notifies by itself; a comment is only needed on an issue that is already open.
  if(previousBody===null||!fresh.length)return {title,body,comment:null};
  const mention=/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/.test(owner)?'@'+owner:'';
  const comment=[fresh.length>1?'Nouvelles alertes :':'Nouvelle alerte :',list(fresh),
    gone.length?`Levées depuis le passage précédent : ${gone.map(alertTitle).join(' ; ')}.`:'',mention].filter(Boolean).join('\n\n');
  return {title,body,comment};
}

/** Start of the current report week: the latest Sunday noon UTC that is not in the future. */
function weekStart(now){
  const date=new Date(now);
  const start=Date.UTC(date.getUTCFullYear(),date.getUTCMonth(),date.getUTCDate()-((date.getUTCDay()-REPORT_WEEKDAY+7)%7),REPORT_HOUR_UTC);
  return start<=now?start:start-WEEK;
}

/** True when no report issue has been opened since the week began: a skipped run is caught up by the next one. */
export function reportDue({now,lastReportAt}){
  const last=Date.parse(lastReportAt);
  return !Number.isFinite(last)||last<weekStart(now);
}

export async function main({env=process.env,now=Date.now()}={}){
  const out=env.VSD_REPORT_OUT;
  const alerts=JSON.parse(await readFile(join(out,'vsd-alerts.json'),'utf8'));
  await writeFile(join(out,'report-due.txt'),reportDue({now,lastReportAt:env.VSD_REPORT_LAST_ISSUE_AT??''})?'yes\n':'no\n');
  if(!alerts.length)return {alerts:0,comment:false};
  // The body of the open alert issue, saved by the workflow; no file when no issue is open.
  const previousBody=env.VSD_ALERT_PREVIOUS?await readFile(env.VSD_ALERT_PREVIOUS,'utf8').catch(()=>null):null;
  const plan=planAlertIssue({alerts,previousBody,today:new Date(now).toISOString().slice(0,10),
    runUrl:`${env.GITHUB_SERVER_URL}/${env.GITHUB_REPOSITORY}/actions/runs/${env.GITHUB_RUN_ID}`,owner:env.GITHUB_REPOSITORY_OWNER??''});
  await writeFile(join(out,'alert-title.txt'),plan.title+'\n');
  await writeFile(join(out,'alert-body.md'),plan.body+'\n');
  if(plan.comment)await writeFile(join(out,'alert-comment.md'),plan.comment+'\n');
  return {alerts:alerts.length,comment:Boolean(plan.comment)};
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{const result=await main();console.log(`Issues préparées : ${result.alerts} alerte(s)${result.comment?', dont au moins une nouvelle':''}.`);}
  catch(error){console.error('Issues non préparées : '+(error?.code??error?.name??'erreur'));process.exitCode=1;}
}
