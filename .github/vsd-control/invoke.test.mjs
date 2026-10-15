import {test} from 'node:test';
import assert from 'node:assert/strict';
import {invoke,safeDiagnostic} from './invoke.mjs';
const env={VSD_CLOUD_ORIGIN:'https://voyage-sans-detour-admin.cousinmathis31.chatgpt.site',VSD_SITE_ID:'appgprj_6ab8ae0785988191a26f73b4a4e6c687',VSD_CLOUD_KEY:'a'.repeat(43),VSD_SITES_DISPATCH_TOKEN:'SECRET',VSD_TICK_KIND:'publications'};
const clock=()=>Date.parse('2026-10-12T00:00:00Z');
const json=x=>new Response(JSON.stringify(x),{headers:{'content-type':'application/json'}});
test('annual stop before configuration or network',async()=>{assert.deepEqual(await invoke({env:{},clock:()=>Date.parse('2027-09-14T21:59:59Z'),fetcher:()=>assert.fail()}),{status:'period_ended',requests:0});});
test('publication sent only once and receipt logged safely',async()=>{let calls=0;const logs=[];const result=await invoke({env,clock,log:s=>logs.push(s),fetcher:async(url,options)=>{calls++;assert.equal(JSON.parse(options.body).kind,'publications');return json({kind:'publications',status:'idle',untrusted:'SECRET'});}});assert.equal(result.requests,1);assert.equal(calls,1);assert.deepEqual(logs,['Cloud receipt: publications / idle.']);});
test('401 is identifiable and never retried',async()=>{let calls=0;await assert.rejects(invoke({env,clock,fetcher:async()=>{calls++;return new Response('SECRET',{status:401});}}),e=>safeDiagnostic(e).includes('HTTP 401')&&!safeDiagnostic(e).includes('SECRET'));assert.equal(calls,1);});
test('unknown response status is held, not logged or retried',async()=>{let calls=0;await assert.rejects(invoke({env,clock,log:()=>assert.fail(),fetcher:async()=>{calls++;return json({kind:'publications',status:'SECRET'});}}),e=>safeDiagnostic(e).includes('task_attention_required'));assert.equal(calls,1);});
test('oversized response bounded',async()=>{await assert.rejects(invoke({env,clock,fetcher:async()=>json({content:'x'.repeat(2000)})}),e=>e.code==='response_too_large');});
test('metrics six bounded passes cover twelve report windows',async()=>{const timestamps=[];await invoke({env:{...env,VSD_TICK_KIND:'metrics'},clock,log:()=>{},fetcher:async(url,o)=>{timestamps.push(Number(o.headers['X-VSD-Sent-At']));return json({kind:'metrics',status:'finished'});}});assert.equal(timestamps.length,6);assert.ok(timestamps[0]<timestamps[1]&&timestamps[1]<timestamps[2]);});
test('metrics disabled ends after first pass',async()=>{const result=await invoke({env:{...env,VSD_TICK_KIND:'metrics'},clock,log:()=>{},fetcher:async()=>json({kind:'metrics',status:'disabled'})});assert.equal(result.requests,1);});
test('arbitrary network exception never disclosed',async()=>{await assert.rejects(invoke({env,clock,fetcher:async()=>{throw Error('SECRET');}}),e=>!safeDiagnostic(e).includes('SECRET'));assert.ok(!safeDiagnostic(Error('SECRET')).includes('SECRET'));});

test('archival maintenance uses exact action envelope once and never bare publications',async()=>{let calls=0;const result=await invoke({env:{...env,VSD_TICK_KIND:'reconcile_windsor'},clock,log:()=>{},fetcher:async(url,o)=>{calls++;assert.deepEqual(JSON.parse(o.body),{kind:'publications',action:'reconcile_windsor_refusal'});return json({kind:'publications',status:'archival_reconciled'});}});assert.equal(calls,1);assert.equal(result.requests,1);});

test('metrics reaches Stay22 after six Google windows without repeating completed reports',async()=>{
  const pending=['ga4:7d','ga4:30d','ga4:90d','search:7d','search:30d','search:90d','stay22:7d','stay22:30d','stay22:90d'];
  const seen=[];const result=await invoke({env:{...env,VSD_TICK_KIND:'metrics'},clock,log:()=>{},fetcher:async()=>{seen.push(...pending.splice(0,2));return json({kind:'metrics',status:'finished'});}});
  assert.equal(result.requests,6);assert.equal(pending.length,0);assert.equal(new Set(seen).size,9);assert.equal(seen.at(-1),'stay22:90d');
});
