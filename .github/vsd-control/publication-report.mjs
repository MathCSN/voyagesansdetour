// Publication section and alerts of the report, from the engine state relayed by the private panel.
// seo-status.mjs has already reduced that state to booleans, counts, dates and closed lists of codes;
// post identifiers and unknown codes are only ever written inside a code span.
const HOUR=36e5,DAY=24*HOUR;
export const ENGINE_SILENCE_HOURS=6,POST_TROUBLE_DAYS=7;
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
  buffer_mutation_error:'refusé par Buffer',refused:'accès refusé par Buffer',rate_limited:'quota Buffer atteint',inconnu:'motif inconnu',autre:'motif non reconnu'};
// A batch withdrawn from the reviewed stock is held on purpose: listed in the report, never an alert.
const WITHDRAWN='retired';

const PARIS=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Paris',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
const moment=value=>PARIS.format(new Date(value)).replace(' ',' à ')+', heure de Paris';
const plural=(count,[one,many])=>`${count} ${count>1?many:one}`;
const channelText=(channel,state)=>`${NETWORK[channel]} ${CHANNEL_STATE[state]}`;
const reasonText=reason=>REASON[reason]??'code `'+reason+'`';
const troubleText=post=>`\`${post.id}\` (${NETWORK[post.channel]}, ${JOB_STATE[post.state][0]}, ${reasonText(post.reason)}`;
const riskText=post=>`\`${post.id}\` (${channelText(post.channel,post.channelState)}, échéance le ${moment(post.dueAt)})`;
const named=(texts,total)=>texts.slice(0,NAMED_IN_ALERT).join(' ; ')+(total>NAMED_IN_ALERT?` et ${plural(total-NAMED_IN_ALERT,['autre','autres'])}`:'');

/** Lines of the « Publication » section; null when the panel could not be read or does not send the block yet. */
export function publicationLines(publication){
  if(!publication)return ['- État du moteur de publication indisponible (panneau privé injoignable ou pas encore à jour).'];
  const {channels,counts,problems,atRisk}=publication;
  const register=Object.entries(JOB_STATE).filter(([state])=>counts[state]>0).map(([state,words])=>plural(counts[state],words));
  const lines=[
    `- Moteur du panneau : ${publication.enabled?'actif':'désactivé'}, ${publication.lastPassAt?'dernier passage le '+moment(publication.lastPassAt):'aucun passage enregistré'}.`,
    `- Canaux Buffer : ${channels?Object.entries(channels).map(([channel,state])=>channelText(channel,state)).join(', '):'aucun accès Buffer enregistré dans le panneau'}.`,
    `- Registre : ${register.length?register.join(', '):'vide'}.`];
  if(problems.length)lines.push(`- Retenus ou en échec depuis ${POST_TROUBLE_DAYS} jours (${publication.problemsCount}) : `+problems.map(post=>`${troubleText(post)}, ${post.at.slice(0,10)})`).join(' ; ')+'.');
  if(atRisk.length)lines.push(`- Prêts à moins de 24 h sur un canal qui ne reçoit rien (${publication.atRiskCount}) : `+atRisk.map(riskText).join(' ; ')+'.');
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

function postAlerts({channels,problems,problemsCount,atRisk,atRiskCount},now){
  const alerts=[];
  // An optional network left out of Buffer is a choice: its posts are listed in the report, never alerted on.
  const leftOut=channel=>!REQUIRED_CHANNELS.includes(channel)&&channels?.[channel]==='absent';
  const recent=problems.filter(post=>post.reason!==WITHDRAWN&&!leftOut(post.channel)&&now-Date.parse(post.at)<POST_TROUBLE_DAYS*DAY);
  if(recent.length){
    // Posts beyond the short list sent by the panel are counted, not named.
    const total=recent.length+Math.max(0,problemsCount-problems.length);
    alerts.push({code:'publication_posts_blocked',message:`${total} ${total>1?'posts retenus':'post retenu'} ou en échec depuis moins de ${POST_TROUBLE_DAYS} jours : ${named(recent.map(post=>troubleText(post)+')'),total)}. Détail sur la page Publication du panneau ; l’alerte tombe d’elle-même ${POST_TROUBLE_DAYS} jours après le blocage.`});
  }
  const threatened=atRisk.filter(post=>!leftOut(post.channel));
  if(threatened.length){
    const total=threatened.length+Math.max(0,atRiskCount-atRisk.length);
    alerts.push({code:'publication_posts_at_risk',message:`${plural(total,['post prêt','posts prêts'])} à moins de 24 h de l’échéance sur un canal qui ne reçoit rien : ${named(threatened.map(riskText),total)}. Sans canal connecté avant l’échéance, le post sera retenu.`});
  }
  return alerts;
}

/** Every alert is recomputed from the current state: it disappears with its cause. No reading, no alert. */
export function publicationAlerts(publication,now){
  if(!publication)return [];
  return [...channelAlerts(publication.channels),...engineAlerts(publication,now),...postAlerts(publication,now)];
}
