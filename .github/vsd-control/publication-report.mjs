// Publication section and alerts of the report, from the engine state relayed by the private panel.
// seo-status.mjs has already reduced that state to booleans, counts, dates and closed lists of codes;
// post identifiers and unknown codes are only ever written inside a code span.
const HOUR=36e5,DAY=24*HOUR;
export const ENGINE_SILENCE_HOURS=6,POST_TROUBLE_DAYS=7;
// Two runs in a row can be minutes apart (a manual run after a scheduled one, a run started again): the
// engine state must also have been missing for this long before the alert is raised.
const READING_GRACE_HOURS=4;
// Kinds of the alerts drawn from the engine state. When that state is missing, the report says so and the
// alert issue keeps those it already had (issue-plan.mjs) instead of dropping them.
export const PUBLICATION_KINDS=['publication_channel','publication_buffer_access','publication_engine_disabled','publication_engine_silent','publication_channels_stale','publication_posts_blocked','publication_posts_at_risk',
  'publication_retired_published','publication_retired_in_buffer','publication_buffer_quota'];
// The panel re-reads the Buffer channels when its last re-reading is more than six hours old (the Buffer API
// quota is shared and every request counts): a day without one is a fault, not a late run.
const CHANNELS_CHECK_MAX_HOURS=24;
export const READING_KIND='publication_reading_missing';
const NAMED_IN_ALERT=5;
// TikTok is optional: its absence from Buffer is a choice, not a fault.
const REQUIRED_CHANNELS=['instagram','facebook'];
const NETWORK={instagram:'Instagram',facebook:'Facebook',tiktok:'TikTok'};
const CHANNEL_STATE={connected:'connecté',absent:'absent de Buffer',disconnected:'déconnecté de Buffer',locked:'verrouillé par Buffer',paused:'en pause dans Buffer',unknown:'dans un état inconnu'};
const BUFFER_CHANNELS='publish.buffer.com > Channels';
const CHANNEL_FIX={
  disconnected:`Le reconnecter dans Buffer (${BUFFER_CHANNELS}).`,
  locked:`L’offre Buffer ne couvre plus ce canal : le déverrouiller dans Buffer (${BUFFER_CHANNELS}) ou y retirer un canal inutile.`,
  paused:`Relancer sa file dans Buffer (${BUFFER_CHANNELS}).`,
  absent:`Le connecter dans Buffer (${BUFFER_CHANNELS}).`};
const JOB_STATE={ready:['prêt','prêts'],submitting:['en cours d’envoi','en cours d’envoi'],scheduled:['programmé dans Buffer','programmés dans Buffer'],
  published:['publié','publiés'],to_verify:['à vérifier','à vérifier'],held:['retenu','retenus'],failed:['en échec','en échec']};
const REASON={overdue:'échéance dépassée',max_attempts:'trop de tentatives',buffer_post_removed:'post retiré de Buffer',retired:'retiré du stock',
  buffer_mutation_error:'refusé par Buffer',refused:'accès refusé par Buffer',rate_limited:'quota Buffer atteint',inconnu:'motif inconnu',autre:'motif non reconnu',
  suppression_en_attente:'suppression au prochain passage',trop_tard:'trop près de l’échéance pour être supprimé',reseau_different:'réseau différent dans Buffer',
  envoi_en_cours:'en cours d’envoi',post_partage:'post aussi tenu par un autre post',envoi_a_verifier:'envoi à vérifier',buffer_post_not_found:'Buffer dit ne plus le connaître',
  buffer_delete_mutation_error:'suppression refusée par Buffer',buffer_delete_refused:'clé refusée par Buffer',buffer_delete_rate_limited:'quota Buffer atteint'};
// A post of a withdrawn batch still in Buffer is normally deleted by the panel at its next engine pass. It is an
// alert only when that will not happen by itself (a deletion failed or is impossible), or when its slot is near.
const RETIRED_PENDING='suppression_en_attente',RETIRED_NEAR_HOURS=24;
// The panel alerts below this share of a Buffer API quota window (QUOTA_ALERT_RATIO of the panel).
export const QUOTA_ALERT_RATIO=0.1;
// A batch withdrawn from the reviewed stock is held on purpose: listed in the report, never an alert.
const WITHDRAWN='retired';

const PARIS=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Paris',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
const moment=value=>PARIS.format(new Date(value)).replace(' ',' à ')+', heure de Paris';
const plural=(count,[one,many])=>`${count} ${count>1?many:one}`;
const channelText=(channel,state)=>`${NETWORK[channel]} ${CHANNEL_STATE[state]}`;
const reasonText=reason=>REASON[reason]??'code `'+reason+'`';
const troubleText=post=>`\`${post.id}\` (${NETWORK[post.channel]}, ${JOB_STATE[post.state][0]}, ${reasonText(post.reason)}`;
const riskText=post=>`\`${post.id}\` (${channelText(post.channel,post.channelState)}, échéance le ${moment(post.dueAt)})`;
const retiredText=post=>`\`${post.id}\` (${NETWORK[post.channel]}, échéance le ${moment(post.dueAt)}, ${reasonText(post.reason)}${post.replacementWaiting?', son remplaçant attend':''})`;
const retiredPublishedText=post=>`\`${post.id}\` (${NETWORK[post.channel]}, publié vers le ${moment(post.at)})`;
const windowText=w=>`\`${w.name}\` ${w.remaining??'?'}${w.limit?` sur ${w.limit}`:''}`;
const quotaLow=quota=>quota!==null&&quota!==undefined&&quota.lowestRatio<QUOTA_ALERT_RATIO;
const named=(texts,total)=>{
  const shown=texts.slice(0,NAMED_IN_ALERT),rest=total-shown.length;
  if(!shown.length)return 'non détaillés ici, au-delà de la liste courte envoyée par le panneau';
  return shown.join(' ; ')+(rest>0?` et ${plural(rest,['autre','autres'])}`:'');
};

/** Lines of the « Publication » section; null when the panel could not be read or does not send the block yet. */
export function publicationLines(publication){
  if(!publication)return ['- État du moteur de publication indisponible (panneau privé injoignable ou pas encore à jour).'];
  const {channels,counts,problems,atRisk}=publication;
  const checked=publication.channelsCheckedAt?`relus par le panneau le ${moment(publication.channelsCheckedAt)}`:'date de leur dernière relecture non donnée par le panneau';
  const register=Object.entries(JOB_STATE).filter(([state])=>counts[state]>0).map(([state,words])=>plural(counts[state],words));
  const lines=[
    `- Moteur du panneau : ${publication.enabled?'actif':'désactivé'}, ${publication.lastPassAt?'dernier passage le '+moment(publication.lastPassAt):'aucun passage enregistré'}.`,
    `- Canaux Buffer : ${channels?Object.entries(channels).map(([channel,state])=>channelText(channel,state)).join(', ')+' ; '+checked:'aucun accès Buffer enregistré dans le panneau'}.`,
    `- Registre : ${register.length?register.join(', '):'vide'}.`];
  if(problems.length)lines.push(`- Retenus ou en échec depuis ${POST_TROUBLE_DAYS} jours (${publication.problemsCount}) : `+problems.map(post=>`${troubleText(post)}, ${post.at.slice(0,10)})`).join(' ; ')+'.');
  if(atRisk.length)lines.push(`- Prêts à moins de 24 h sur un canal qui ne reçoit rien (${publication.atRiskCount}) : `+atRisk.map(riskText).join(' ; ')+'.');
  const retired=publication.retiredInBuffer??[],retiredPublished=publication.retiredPublished??[];
  if(publication.retiredInBufferCount)lines.push(`- Lots retirés dont le post est encore dans Buffer (${publication.retiredInBufferCount}) : `+(retired.length?retired.map(retiredText).join(' ; '):'non détaillés')+'.');
  if(publication.retiredPublishedCount)lines.push(`- Lots retirés publiés malgré tout depuis ${POST_TROUBLE_DAYS} jours (${publication.retiredPublishedCount}) : `+(retiredPublished.length?retiredPublished.map(retiredPublishedText).join(' ; '):'non détaillés')+'.');
  if(publication.bufferQuota)lines.push(`- Quota de l’API Buffer relevé le ${moment(publication.bufferQuota.observedAt)} : `+publication.bufferQuota.windows.map(windowText).join(', ')+`${quotaLow(publication.bufferQuota)?' (moins de 10 % sur une fenêtre)':''}.`);
  return lines;
}

function channelAlerts(channels){
  if(!channels)return [{code:'publication_buffer_access',message:'Aucun accès Buffer enregistré dans le panneau : aucun post ne peut partir. Enregistrer la clé Buffer sur la page Connexions du panneau.'}];
  return Object.entries(channels)
    .filter(([channel,state])=>CHANNEL_FIX[state]&&(state!=='absent'||REQUIRED_CHANNELS.includes(channel)))
    .map(([channel,state])=>({code:`publication_channel:${channel}`,message:`${channelText(channel,state)} : ses posts ne partent plus. ${CHANNEL_FIX[state]}`}));
}

function engineAlerts({enabled,lastPassAt},now){
  if(!enabled)return [{code:'publication_engine_disabled',message:'Moteur de publication désactivé dans le panneau : plus aucun post n’est programmé. Le réactiver (réglage PUBLICATION_ENABLED du panneau, puis un déploiement).'}];
  if(lastPassAt&&now-Date.parse(lastPassAt)<=ENGINE_SILENCE_HOURS*HOUR)return [];
  const since=lastPassAt?`n’a fait aucun passage depuis le ${moment(lastPassAt)} (plus de ${ENGINE_SILENCE_HOURS} heures)`:'n’a encore enregistré aucun passage';
  return [{code:'publication_engine_silent',message:`Le moteur de publication ${since} : les posts ne sont plus programmés dans Buffer. Ouvrir la page Publication du panneau ; causes habituelles : clé Buffer refusée, Buffer injoignable ou tâche planifiée du panneau arrêtée.`}];
}

/** The channel states the other alerts rely on are those of the last re-reading: too old, they prove nothing. */
function channelCheckAlerts({channels,channelsCheckedAt},now){
  // No date (a key just saved, a panel older than this field): unknown is not late.
  if(!channels||!channelsCheckedAt||now-Date.parse(channelsCheckedAt)<=CHANNELS_CHECK_MAX_HOURS*HOUR)return [];
  return [{code:'publication_channels_stale',message:`Le panneau n’a pas relu les canaux Buffer depuis le ${moment(channelsCheckedAt)} (plus de ${CHANNELS_CHECK_MAX_HOURS} heures) : l’état des canaux donné ici date de ce moment, une coupure ou une reconnexion plus récente n’est pas vue. Vérifier la clé Buffer sur la page Connexions du panneau ; causes habituelles : clé Buffer refusée ou Buffer injoignable.`}];
}

function postAlerts({channels,problems,problemsCount,atRisk,atRiskCount},now){
  const alerts=[];
  // An optional network left out of Buffer is a choice: its posts are listed in the report, never alerted on.
  const leftOut=channel=>!REQUIRED_CHANNELS.includes(channel)&&channels?.[channel]==='absent';
  // Posts beyond the short list sent by the panel are unknown here: they are counted, never assumed harmless,
  // so a list filled with posts of a left-out network cannot hide a blocked Instagram or Facebook post.
  const recent=problems.filter(post=>post.reason!==WITHDRAWN&&!leftOut(post.channel)&&now-Date.parse(post.at)<POST_TROUBLE_DAYS*DAY);
  const blocked=recent.length+Math.max(0,problemsCount-problems.length);
  if(blocked){
    alerts.push({code:'publication_posts_blocked',count:blocked,message:`${blocked} ${blocked>1?'posts retenus':'post retenu'} ou en échec depuis moins de ${POST_TROUBLE_DAYS} jours : ${named(recent.map(post=>troubleText(post)+')'),blocked)}. Détail sur la page Publication du panneau ; l’alerte tombe d’elle-même ${POST_TROUBLE_DAYS} jours après le blocage.`});
  }
  const threatened=atRisk.filter(post=>!leftOut(post.channel));
  const total=threatened.length+Math.max(0,atRiskCount-atRisk.length);
  if(total){
    alerts.push({code:'publication_posts_at_risk',count:total,message:`${plural(total,['post prêt','posts prêts'])} à moins de 24 h de l’échéance sur un canal qui ne reçoit rien : ${named(threatened.map(riskText),total)}. Sans canal connecté avant l’échéance, le post sera retenu.`});
  }
  return alerts;
}

/** Withdrawn batches: a post that went out anyway, one still in Buffer that will not be deleted by itself or is near. */
function retiredAlerts({retiredInBuffer=[],retiredInBufferCount=0,retiredPublished=[],retiredPublishedCount=0},now){
  const alerts=[];
  const published=Math.max(retiredPublished.length,retiredPublishedCount);
  if(published){
    alerts.push({code:'publication_retired_published',count:published,message:`${plural(published,['post d’un lot retiré a','posts de lots retirés ont'])} été ${published>1?'publiés':'publié'} malgré le retrait : ${named(retiredPublished.map(retiredPublishedText),published)}. Le retirer à la main du réseau s’il ne doit pas rester en ligne ; l’alerte tombe d’elle-même ${POST_TROUBLE_DAYS} jours après.`});
  }
  // Entries beyond the short list are unknown here: counted, never assumed harmless.
  const stuck=retiredInBuffer.filter(post=>post.reason!==RETIRED_PENDING||Date.parse(post.dueAt)-now<RETIRED_NEAR_HOURS*HOUR);
  const total=stuck.length+Math.max(0,retiredInBufferCount-retiredInBuffer.length);
  if(total){
    alerts.push({code:'publication_retired_in_buffer',count:total,message:`${plural(total,['post d’un lot retiré est','posts de lots retirés sont'])} encore ${total>1?'programmés':'programmé'} dans Buffer sans suppression assurée avant l’échéance : ${named(stuck.map(retiredText),total)}. Le supprimer à la main dans Buffer (publish.buffer.com) avant l’échéance ; détail sur la page Publication du panneau.`});
  }
  return alerts;
}

/** Below a tenth of any Buffer API quota window, reading and scheduling are about to stop for every key of the account. */
function quotaAlerts({bufferQuota}){
  if(!quotaLow(bufferQuota))return [];
  return [{code:'publication_buffer_quota',message:`Quota de l’API Buffer presque épuisé (relevé le ${moment(bufferQuota.observedAt)}) : ${bufferQuota.windows.map(windowText).join(', ')}. Une fois une fenêtre épuisée, le panneau ne lit ni ne programme plus rien jusqu’à sa remise à zéro. Vérifier l’usage sur publish.buffer.com/settings/api ; toutes les clés du compte partagent ce quota.`}];
}

/**
 * What the report remembers from one run to the next: since when the panel has stopped giving the engine
 * state. The panel has been deployed for long, so its silence is a fault, but one missed reading is not.
 * `run` is the number GitHub gives each run of the workflow. A missed reading only continues the previous
 * one when the memory comes from the run just before, or from this same run started again. The time between
 * two runs says nothing: GitHub starts the scheduled runs hours late and skips some. A lost memory, a run
 * that left none, or no run number can therefore delay the alert, never raise it.
 * An earlier run started again after a later one reads the panel after it: it follows the later memory, and
 * the memory keeps the later number, so that the next run still finds the run before it.
 */
export function readingState(previous,seo,now,run=null){
  const number=Number.isInteger(run)&&run>0?run:null;
  const later=number!==null&&Number.isInteger(previous?.run)&&previous.run>number;
  const stamp=later?previous.run:number;
  if(seo?.publication)return {missingSince:null,run:stamp};
  const since=typeof previous?.missingSince==='string'?Date.parse(previous.missingSince):NaN;
  const follows=since<=now&&number!==null&&(later||previous.run===number||previous.run===number-1);
  return {missingSince:new Date(follows?since:now).toISOString(),reason:seo?'block_absent':'panel_unreadable',run:stamp};
}

function readingAlerts(reading,now){
  if(!reading?.missingSince||now-Date.parse(reading.missingSince)<=READING_GRACE_HOURS*HOUR)return [];
  const what=reading.reason==='block_absent'?'répond sans l’état du moteur de publication (version en ligne trop ancienne, ou registre illisible)':'ne répond plus au rapport';
  return [{code:READING_KIND,message:`Le panneau ${what} depuis le ${moment(reading.missingSince)} : les alertes sur les canaux Buffer, le moteur et les posts sont aveugles. Vérifier que le panneau est en ligne et déployé à jour.`}];
}

/**
 * Every alert is recomputed from the current state: it disappears with its cause. Without the engine
 * state, the only alert is the one saying the state has been missing for too long (`reading`).
 */
export function publicationAlerts(publication,now,reading=null){
  if(!publication)return readingAlerts(reading,now);
  return [...channelAlerts(publication.channels),...engineAlerts(publication,now),...channelCheckAlerts(publication,now),...postAlerts(publication,now),
    ...retiredAlerts(publication,now),...quotaAlerts(publication)];
}
