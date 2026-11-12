import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {alertTitle,main,planAlertIssue,previousCodes,reportDue} from './issue-plan.mjs';

const RUN='https://github.com/MathCSN/voyagesansdetour/actions/runs/1';
const channel={code:'publication_channel:instagram',message:'Instagram déconnecté de Buffer : ses posts ne partent plus. Le reconnecter dans Buffer (publish.buffer.com > Channels).'};
const queue={code:'social_queue_low:facebook',message:'File facebook presque vide : dernier post programmé le 2026-11-20.'};
const failures={code:'workflow_failures:Voyage Sans Detour cloud control',message:'Voyage Sans Detour cloud control : 2 échecs sur 300 exécutions cette semaine (https://github.com/x/y/actions/runs/2).'};
const plan=(alerts,previousBody=null)=>planAlertIssue({alerts,previousBody,today:'2026-11-12',runUrl:RUN,owner:'MathCSN'});

test('the title says what is wrong, the most urgent alert first',()=>{
  assert.equal(plan([channel]).title,'⚠️ Instagram coupé de Buffer');
  assert.equal(plan([channel,queue]).title,'⚠️ Instagram coupé de Buffer et 1 autre alerte');
  assert.equal(plan([queue,failures,channel]).title,'⚠️ File Facebook presque vide et 2 autres alertes');
  assert.equal(alertTitle('workflow_failures:Voyage Sans Detour cloud control'),'échecs répétés d’un workflow');
  assert.equal(alertTitle('un_code_inconnu'),'alerte');
  assert.equal(plan([{code:'publication_channels_stale',message:'x'},queue]).title,'⚠️ Canaux Buffer plus relus par le panneau et 1 autre alerte');
});

test('a first issue carries the alerts and their codes, and needs no comment: opening it notifies',()=>{
  const first=plan([channel,queue]);
  assert.equal(first.comment,null);
  assert.ok(first.body.startsWith('Alertes au 2026-11-12 :\n\n- '+channel.message+'\n- '+queue.message),first.body);
  assert.ok(first.body.includes(RUN));
  assert.deepEqual(previousCodes(first.body),[channel.code,queue.code]);
});

test('an alert that was not there at the previous run is announced by a comment naming it',()=>{
  const before=plan([queue]).body;
  const after=plan([channel,queue],before);
  assert.ok(after.comment.startsWith('Nouvelle alerte :\n\n- '+channel.message),after.comment);
  assert.ok(!after.comment.includes(queue.message));
  assert.ok(after.comment.trimEnd().endsWith('@MathCSN'),after.comment);
  assert.equal(after.title,'⚠️ Instagram coupé de Buffer et 1 autre alerte');
  // Nothing new: the body and the title are refreshed in silence.
  assert.equal(plan([channel,queue],after.body).comment,null);
  assert.equal(plan([queue],after.body).comment,null);
  const two=plan([channel,queue,failures],before);
  assert.ok(two.comment.startsWith('Nouvelles alertes :\n\n- '+channel.message+'\n- '+failures.message),two.comment);
});

test('the comment also says which alerts have gone since the previous run',()=>{
  const after=plan([channel],plan([queue,failures]).body);
  assert.ok(after.comment.includes('Levées depuis le passage précédent : file Facebook presque vide ; échecs répétés d’un workflow.'),after.comment);
});

test('an issue written before the codes were recorded gets one comment listing every alert',()=>{
  const legacy='Alertes au 2026-11-11 :\n\n- '+failures.message+'\n\nCette issue se ferme seule quand plus aucune alerte ne tient.';
  assert.equal(previousCodes(legacy),null);
  const after=plan([queue,failures],legacy);
  assert.ok(after.comment.includes(queue.message)&&after.comment.includes(failures.message));
});

test('a code with spaces, colons or accents survives the round trip, and a tampered marker is ignored',()=>{
  const odd={code:'workflow_failures:Rédaction : guide, étape 2 -->',message:'x'};
  const body=plan([odd,channel]).body;
  assert.deepEqual(previousCodes(body),[odd.code,channel.code]);
  // Two records, the codes and the wordings: nothing in a code or a message closes either of them early.
  assert.equal(body.split('-->').length,3);
  assert.equal(previousCodes('<!-- vsd-alert-codes: %E0%A4%A -->'),null);
  assert.equal(previousCodes('<!-- vsd-alert-codes: <script> -->'),null);
  assert.deepEqual(previousCodes('texte\n<!-- vsd-alert-codes:  -->'),[]);
});

const blocked=count=>({code:'publication_posts_blocked',count,message:`${count} post(s) retenu(s) ou en échec depuis moins de 7 jours.`});
const expired=count=>({code:'guide_sources_expired',count,message:`${count} guide(s) aux sources vérifiées il y a plus de 45 jours.`});
const reading={code:'publication_reading_missing',message:'Le panneau ne répond plus au rapport depuis le 2026-11-12 à 02:07, heure de Paris.'};
// What the report could not re-read when the private panel gives no publication state.
const UNREAD=['publication_channel','publication_posts_blocked','publication_reading_missing'];
const planWith=(alerts,previousBody,unread)=>planAlertIssue({alerts,unread,previousBody,today:'2026-11-12',runUrl:RUN,owner:'MathCSN'});

test('an open alert that gets worse is announced by a comment; one that eases is not',()=>{
  const one=plan([blocked(1),queue]);
  assert.equal(one.comment,null);
  const two=plan([blocked(2),queue],one.body);
  assert.ok(two.comment.startsWith('Alerte aggravée :\n\n- '+blocked(2).message),two.comment);
  assert.ok(!two.comment.includes(queue.message));
  assert.ok(two.comment.trimEnd().endsWith('@MathCSN'),two.comment);
  // Same number, then fewer: the body is refreshed in silence.
  assert.equal(plan([blocked(2),queue],two.body).comment,null);
  const eased=plan([blocked(1),queue],two.body);
  assert.equal(eased.comment,null);
  // It grows again from what the previous run recorded.
  assert.ok(plan([blocked(2),queue],eased.body).comment.startsWith('Alerte aggravée :'));
  // New and worse alerts in the same run: each under its own heading.
  const both=plan([channel,blocked(3),expired(19),queue],plan([blocked(2),expired(1),queue]).body);
  assert.ok(both.comment.startsWith('Nouvelle alerte :\n\n- '+channel.message+'\n\nAlertes aggravées :\n\n- '+blocked(3).message+'\n- '+expired(19).message),both.comment);
});

test('the numbers survive the round trip, and a record without numbers never makes an alert look worse',()=>{
  const body=plan([blocked(2),queue]).body;
  assert.deepEqual(previousCodes(body),[blocked(2).code,queue.code]);
  assert.ok(body.includes('<!-- vsd-alert-codes: publication_posts_blocked=2,social_queue_low%3Afacebook -->'),body);
  const older='Alertes au 2026-11-11 :\n\n- x\n\n<!-- vsd-alert-codes: publication_posts_blocked -->';
  assert.deepEqual(previousCodes(older),['publication_posts_blocked']);
  assert.equal(plan([blocked(5)],older).comment,null);
  assert.equal(previousCodes('<!-- vsd-alert-codes: publication_posts_blocked=deux -->'),null);
});

test('an alert whose source could not be read at this run stays as it was known: neither lifted nor announced again',()=>{
  const before=plan([channel,blocked(2),queue]).body;
  const missed=planWith([queue],before,UNREAD);
  assert.equal(missed.comment,null);
  // The title keeps saying what is wrong, and the body says these alerts were not re-read.
  assert.equal(missed.title,'⚠️ Instagram coupé de Buffer et 2 autres alertes');
  assert.deepEqual(previousCodes(missed.body),[queue.code,channel.code,blocked(2).code]);
  assert.ok(missed.body.includes('Non relues à ce passage'),missed.body);
  assert.ok(missed.body.indexOf('- '+queue.message)<missed.body.indexOf('Non relues')&&missed.body.indexOf('Non relues')<missed.body.indexOf('- '+channel.message),missed.body);
  // A second miss in a row keeps them, word for word.
  const again=planWith([queue],missed.body,UNREAD);
  assert.equal(again.comment,null);
  assert.ok(again.body.includes('- '+channel.message)&&again.body.includes('- '+blocked(2).message),again.body);
  // The reading is back and nothing has changed: no « Nouvelle alerte ».
  const back=plan([channel,blocked(2),queue],again.body);
  assert.equal(back.comment,null);
  assert.ok(!back.body.includes('Non relues'),back.body);
  // Back and worse: the number kept through the misses still counts.
  assert.ok(plan([channel,blocked(3),queue],again.body).comment.startsWith('Alerte aggravée :\n\n- '+blocked(3).message));
  // Back and gone: lifted, said with the next comment.
  assert.ok(plan([failures,queue],again.body).comment.includes('Levées depuis le passage précédent : Instagram coupé de Buffer ; posts retenus ou en échec.'));
});

test('a missed reading does not close the issue when the alert it hides was the only one',()=>{
  const missed=planWith([],plan([channel]).body,UNREAD);
  assert.equal(missed.title,'⚠️ Instagram coupé de Buffer');
  assert.equal(missed.comment,null);
  assert.ok(missed.body.startsWith('Alertes au 2026-11-12 :\n\nNon relues à ce passage'),missed.body);
  assert.deepEqual(previousCodes(missed.body),[channel.code]);
  // Read again and all clear: nothing left, the workflow closes the issue.
  assert.equal(planWith([],missed.body,[]),null);
  // Nothing of that kind was open, or no issue at all: nothing to keep.
  assert.equal(planWith([],plan([queue]).body,UNREAD),null);
  assert.equal(planWith([],null,UNREAD),null);
});

test('the alert saying the panel is unreadable is new; the alerts it blinds are not lifted',()=>{
  const first=planWith([queue],plan([channel,queue]).body,UNREAD);
  const second=planWith([reading,queue],first.body,UNREAD);
  assert.ok(second.comment.startsWith('Nouvelle alerte :\n\n- '+reading.message),second.comment);
  assert.ok(!second.comment.includes('Levées'),second.comment);
  assert.deepEqual(previousCodes(second.body),[reading.code,queue.code,channel.code]);
  // The memory of the missed readings was lost: the alert is not raised again yet, and stays as known.
  const lost=planWith([queue],second.body,UNREAD);
  assert.equal(lost.comment,null);
  assert.deepEqual(previousCodes(lost.body),[queue.code,reading.code,channel.code]);
  assert.equal(planWith([reading,queue],lost.body,UNREAD).comment,null);
});

const withoutTexts=body=>body.replace(/\n<!-- vsd-alert-texts: [^\n]* -->/,'');

test('a body someone edited by hand still carries its alerts over a missed reading, in their recorded wording',()=>{
  const before=plan([channel,blocked(2),queue]).body;
  assert.notEqual(withoutTexts(before),before);
  const edits=[
    body=>body.replace('- '+channel.message+'\n','- '+channel.message+'\n- vu, je regarde ce soir\n'),
    body=>body.replace('- '+channel.message+'\n',''),
    body=>body.replace(channel.message,'Instagram : à reconnecter'),
    body=>body.replace('Alertes au','- [x] lu\n\nAlertes au').replaceAll('\n','\r\n'),
  ];
  for(const edit of edits){
    const missed=planWith([queue],edit(before),UNREAD);
    assert.equal(missed.comment,null);
    assert.equal(missed.title,'⚠️ Instagram coupé de Buffer et 2 autres alertes');
    assert.deepEqual(previousCodes(missed.body),[queue.code,channel.code,blocked(2).code]);
    // The body is written again from the record: the hand-made lines are gone, the wording is the recorded one.
    assert.ok(missed.body.includes('- '+channel.message+'\n- '+blocked(2).message),missed.body);
    assert.ok(!missed.body.includes('je regarde')&&!missed.body.includes('à reconnecter'),missed.body);
    // The reading is back, nothing has changed: still no « Nouvelle alerte ».
    assert.equal(plan([channel,blocked(2),queue],missed.body).comment,null);
  }
});

test('a wording with anything Markdown or a comment can read survives the record',()=>{
  const odd={code:'publication_posts_blocked',count:1,message:'1 post retenu : `ig:a` (Instagram, « motif », 50 %) --> <!-- x --> [lien](https://example.org), fin.'};
  const before=plan([odd,queue]).body;
  assert.equal(before.split('<!--').length,4);
  const missed=planWith([queue],before.replace('- '+queue.message+'\n',''),UNREAD);
  assert.ok(missed.body.includes('\n\n- '+odd.message+'\n\n'),missed.body);
});

test('an issue written before the wordings were recorded, or whose record is damaged, falls back on its lines',()=>{
  const before=plan([channel,queue]).body;
  const older=withoutTexts(before);
  assert.deepEqual(previousCodes(planWith([queue],older,UNREAD).body),[queue.code,channel.code]);
  // The same older body saved from the web page, with Windows line ends: the wording is kept clean, and recorded.
  const windows=planWith([queue],older.replaceAll('\n','\r\n'),UNREAD);
  assert.ok(windows.body.includes('- '+channel.message+'\n')&&!windows.body.includes('\r'),JSON.stringify(windows.body));
  assert.deepEqual(previousCodes(planWith([queue],windows.body.replace('- '+channel.message+'\n',''),UNREAD).body),[queue.code,channel.code]);
  // Lines that no longer match the record, and no recorded wording: nothing can be carried over.
  assert.deepEqual(previousCodes(planWith([queue],older.replace('- '+channel.message+'\n',''),UNREAD).body),[queue.code]);
  // A record with a wording missing, undecodable or holding a line break is not trusted.
  const damaged=[text=>text.replace(/(<!-- vsd-alert-texts: )[^,]*,/,'$1'),text=>text.replace('<!-- vsd-alert-texts: ','<!-- vsd-alert-texts: %E0%A4%A'),text=>text.replace('<!-- vsd-alert-texts: ','<!-- vsd-alert-texts: %0A')];
  for(const damage of damaged){
    assert.notEqual(damage(before),before);
    const missed=planWith([queue],damage(before),UNREAD);
    assert.deepEqual(previousCodes(missed.body),[queue.code,channel.code]);
    assert.ok(missed.body.includes('- '+channel.message),missed.body);
  }
});

test('the wordings are left out of the record rather than push the body past what GitHub accepts',()=>{
  const many=Array.from({length:40},(_,index)=>({code:'workflow_failures:w'+index,message:'é'.repeat(700)+index}));
  const body=plan(many).body;
  assert.ok(body.length<65536,String(body.length));
  assert.equal(withoutTexts(body),body);
  assert.equal(previousCodes(body).length,40);
  assert.notEqual(withoutTexts(plan(many.slice(0,3)).body),plan(many.slice(0,3)).body);
});

test('the command keeps the alert issue open on a missed reading and leaves no body once all is clear',async()=>{
  const out=await mkdtemp(join(tmpdir(),'vsd-issue-plan-'));
  const env={VSD_REPORT_OUT:out,VSD_ALERT_PREVIOUS:join(out,'alert-previous.md'),GITHUB_SERVER_URL:'https://github.com',GITHUB_REPOSITORY:'MathCSN/voyagesansdetour',GITHUB_RUN_ID:'1',GITHUB_REPOSITORY_OWNER:'MathCSN'};
  const write=(name,value)=>writeFile(join(out,name),typeof value==='string'?value:JSON.stringify(value));
  try{
    await write('alert-previous.md',plan([channel]).body);
    await write('vsd-alerts.json',[]);
    await write('vsd-alerts-unread.json',UNREAD);
    assert.deepEqual(await main({env,now:Date.parse('2026-11-12T13:07:00Z')}),{alerts:1,comment:false});
    assert.equal((await readFile(join(out,'alert-title.txt'),'utf8')).trim(),'⚠️ Instagram coupé de Buffer');
    assert.deepEqual(previousCodes(await readFile(join(out,'alert-body.md'),'utf8')),[channel.code]);
    // Next run: the panel is read again and nothing is wrong.
    const clear=await mkdtemp(join(tmpdir(),'vsd-issue-plan-'));
    await writeFile(join(clear,'vsd-alerts.json'),'[]');
    await writeFile(join(clear,'vsd-alerts-unread.json'),'[]');
    assert.deepEqual(await main({env:{...env,VSD_REPORT_OUT:clear},now:Date.parse('2026-11-12T19:07:00Z')}),{alerts:0,comment:false});
    await assert.rejects(readFile(join(clear,'alert-body.md'),'utf8'),{code:'ENOENT'});
    await rm(clear,{recursive:true,force:true});
  }finally{await rm(out,{recursive:true,force:true});}
});

test('the owner is only mentioned when its login is a plain GitHub login',()=>{
  const before=plan([queue]).body;
  const mention=owner=>planAlertIssue({alerts:[channel,queue],previousBody:before,today:'2026-11-12',runUrl:RUN,owner}).comment;
  assert.ok(mention('MathCSN').includes('@MathCSN'));
  for(const owner of ['','a b','x](y)','@team/all'])assert.ok(!mention(owner).includes('@'),owner);
});

test('the weekly report is due from Sunday noon UTC, once, and catches up after a missed run',()=>{
  const at=value=>Date.parse(value);
  // Sunday 15 November 2026, 12:00 UTC opens the week.
  assert.equal(reportDue({now:at('2026-11-15T11:59:00Z'),lastReportAt:'2026-11-11T12:09:58Z'}),false);
  assert.equal(reportDue({now:at('2026-11-15T13:07:00Z'),lastReportAt:'2026-11-11T12:09:58Z'}),true);
  assert.equal(reportDue({now:at('2026-11-15T19:07:00Z'),lastReportAt:'2026-11-15T13:09:00Z'}),false);
  assert.equal(reportDue({now:at('2026-11-21T19:07:00Z'),lastReportAt:'2026-11-15T13:09:00Z'}),false);
  // Every Sunday run was skipped: Monday or Wednesday still opens the report of the week.
  assert.equal(reportDue({now:at('2026-11-16T01:07:00Z'),lastReportAt:'2026-11-08T13:09:00Z'}),true);
  assert.equal(reportDue({now:at('2026-11-18T07:07:00Z'),lastReportAt:'2026-11-08T13:09:00Z'}),true);
  assert.equal(reportDue({now:at('2026-11-12T09:00:00Z'),lastReportAt:''}),true);
  assert.equal(reportDue({now:at('2026-11-12T09:00:00Z'),lastReportAt:'pas une date'}),true);
});
