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

const kindOf=code=>String(code).split(':')[0];
// The table above goes from the most urgent kind to the least.
const rank=code=>{const at=Object.keys(TITLES).indexOf(kindOf(code));return at<0?Infinity:at;};

// The record is kept in an HTML comment. Each entry is a percent-encoded code, followed by `=number` when
// the alert counts posts or guides: no code can close the comment or reach Markdown.
const COUNT_MAX=999999;
const ENTRY="[A-Za-z0-9%_.~!*'()-]+(?:=\\d{1,6})?";
const MARKER=new RegExp(`<!-- vsd-alert-codes: (${ENTRY}(?:,${ENTRY})*)? ?-->`);
const counted=alert=>Number.isInteger(alert.count)&&alert.count>=0;
const entry=alert=>encodeURIComponent(alert.code)+(counted(alert)?'='+Math.min(alert.count,COUNT_MAX):'');

/**
 * Alerts recorded by the previous run: code, number when it had one, and wording. null when there is no
 * record (no issue yet, an issue older than the record, a record that was tampered with).
 */
function previousAlerts(body){
  const found=MARKER.exec(body??'');
  if(!found)return null;
  try{
    const entries=(found[1]?found[1].split(','):[]).map(text=>{
      const [code,count]=text.split('=');
      return {code:decodeURIComponent(code),count:count===undefined?null:Number(count)};
    });
    // The body has one line per alert, in the order of the record. Otherwise the wording is unknown.
    const lines=body.split('\n').filter(line=>line.startsWith('- ')).map(line=>line.slice(2));
    return entries.map((alert,index)=>({...alert,message:lines.length===entries.length?lines[index]:null}));
  }catch{return null;}
}

/** Codes recorded by the previous run; null when there is no issue yet or it predates the record. */
export function previousCodes(body){
  return previousAlerts(body)?.map(alert=>alert.code)??null;
}

const CARRIED_NOTE='Non relues à ce passage (panneau privé ou recherche GitHub illisible), gardées telles qu’au dernier relevé :';

/**
 * Title, body and comment of the alert issue; null when nothing is left, so the workflow closes it.
 * `unread` lists the kinds of alerts this run could not re-read: those the previous run recorded stay as
 * they were known, neither lifted nor announced again.
 */
export function planAlertIssue({alerts,unread=[],previousBody=null,today,runUrl,owner=''}){
  const known=previousBody===null?null:previousAlerts(previousBody);
  const before=new Map((known??[]).map(alert=>[alert.code,alert]));
  const current=new Set(alerts.map(alert=>alert.code));
  const carried=(known??[]).filter(alert=>alert.message!==null&&unread.includes(kindOf(alert.code))&&!current.has(alert.code));
  const all=[...alerts,...carried];
  if(!all.length)return null;
  const fresh=alerts.filter(alert=>!before.has(alert.code));
  // A number that grows is news; a number that falls is not. Without a recorded number, nothing can be said.
  const worse=alerts.filter(alert=>counted(alert)&&Number.isInteger(before.get(alert.code)?.count)&&alert.count>before.get(alert.code).count);
  const gone=(known??[]).filter(alert=>!all.some(kept=>kept.code===alert.code));
  const lead=carried.reduce((best,alert)=>!best||rank(alert.code)<rank(best.code)?alert:best,alerts[0]);
  const others=all.length-1;
  const title=`⚠️ ${capital(alertTitle(lead.code))}`+(others>0?` et ${others} ${others>1?'autres alertes':'autre alerte'}`:'');
  const list=items=>items.map(alert=>'- '+alert.message).join('\n');
  const body=[`Alertes au ${today} :`,list(alerts),carried.length?CARRIED_NOTE+'\n\n'+list(carried):'',
    'Chaque alerte nouvelle, ou dont le nombre augmente, est annoncée par un commentaire sur cette issue. L’issue se ferme seule quand plus aucune alerte ne tient.',
    `Rapport complet : ${runUrl}`,`<!-- vsd-alert-codes: ${all.map(entry).join(',')} -->`].filter(Boolean).join('\n\n');
  // Opening an issue notifies by itself; a comment is only needed on an issue that is already open.
  if(previousBody===null||!(fresh.length+worse.length))return {title,body,comment:null,total:all.length};
  const mention=/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/.test(owner)?'@'+owner:'';
  const section=(items,one,many)=>items.length?[items.length>1?many:one,list(items)]:[];
  const comment=[...section(fresh,'Nouvelle alerte :','Nouvelles alertes :'),...section(worse,'Alerte aggravée :','Alertes aggravées :'),
    gone.length?`Levées depuis le passage précédent : ${gone.map(alert=>alertTitle(alert.code)).join(' ; ')}.`:'',mention].filter(Boolean).join('\n\n');
  return {title,body,comment,total:all.length};
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
  // Kinds of alerts the report could not re-read at this run (weekly-report.mjs); no file, nothing unread.
  const unread=await readFile(join(out,'vsd-alerts-unread.json'),'utf8').then(JSON.parse).catch(()=>[]);
  // The body of the open alert issue, saved by the workflow; no file when no issue is open.
  const previousBody=env.VSD_ALERT_PREVIOUS?await readFile(env.VSD_ALERT_PREVIOUS,'utf8').catch(()=>null):null;
  const plan=planAlertIssue({alerts,unread:Array.isArray(unread)?unread:[],previousBody,today:new Date(now).toISOString().slice(0,10),
    runUrl:`${env.GITHUB_SERVER_URL}/${env.GITHUB_REPOSITORY}/actions/runs/${env.GITHUB_RUN_ID}`,owner:env.GITHUB_REPOSITORY_OWNER??''});
  // No body written: the workflow closes the alert issue, if one is open.
  if(!plan)return {alerts:0,comment:false};
  await writeFile(join(out,'alert-title.txt'),plan.title+'\n');
  await writeFile(join(out,'alert-body.md'),plan.body+'\n');
  if(plan.comment)await writeFile(join(out,'alert-comment.md'),plan.comment+'\n');
  return {alerts:plan.total,comment:Boolean(plan.comment)};
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{const result=await main();console.log(`Issues préparées : ${result.alerts} alerte(s)${result.comment?', dont au moins une nouvelle':''}.`);}
  catch(error){console.error('Issues non préparées : '+(error?.code??error?.name??'erreur'));process.exitCode=1;}
}
