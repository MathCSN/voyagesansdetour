import {test} from 'node:test';
import assert from 'node:assert/strict';
import {alertTitle,planAlertIssue,previousCodes,reportDue} from './issue-plan.mjs';

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
  assert.equal(body.split('-->').length,2);
  assert.equal(previousCodes('<!-- vsd-alert-codes: %E0%A4%A -->'),null);
  assert.equal(previousCodes('<!-- vsd-alert-codes: <script> -->'),null);
  assert.deepEqual(previousCodes('texte\n<!-- vsd-alert-codes:  -->'),[]);
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
