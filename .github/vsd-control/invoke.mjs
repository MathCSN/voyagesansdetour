import { createHash, createHmac, randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';
const STOP = Date.parse('2027-09-14T21:59:59Z');
const ORIGIN = 'https://voyage-sans-detour-admin.cousinmathis31.chatgpt.site';
const ID = 'appgprj_6ab8ae0785988191a26f73b4a4e6c687';
const allowed = {health:['healthy'],metrics:['disabled','finished'],publications:['disabled','idle','busy_or_recent','dispatched','reconciled','recovered']};
export class ControlError extends Error {
  constructor(code, httpStatus) {super(code);this.code=code;this.httpStatus=httpStatus;}
}
async function boundedBody(response) {
  if(!response.body)throw new ControlError('response_empty');
  const reader=response.body.getReader();let length=0;const chunks=[];
  try {
    for(;;){const {done,value}=await reader.read();if(done)break;length+=value.byteLength;
      if(length>1024){await reader.cancel();throw new ControlError('response_too_large');}chunks.push(value);}
  }finally{reader.releaseLock();}
  try{return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks)));}
  catch {throw new ControlError('response_invalid_json');}
}
export async function invoke({env=process.env,fetcher=fetch,clock=Date.now,nonce=randomUUID,log=console.log}={}) {
  if(clock()>=STOP)return {status:'period_ended',requests:0};
  const origin=env.VSD_CLOUD_ORIGIN,id=env.VSD_SITE_ID,key=env.VSD_CLOUD_KEY,dispatcher=env.VSD_SITES_DISPATCH_TOKEN;
  const task=env.VSD_TICK_KIND||'health';
  const archival=task==='reconcile_windsor',kind=archival?'publications':task;
  const statuses=archival?['archival_reconciled','archival_existing','disabled','period_ended']:allowed[kind];
  if(origin!==ORIGIN||id!==ID||!/^[A-Za-z0-9_-]{43}$/.test(key??'')||!dispatcher||!Object.hasOwn(allowed,kind))throw new ControlError('configuration');
  const path='/internal/tick',body=JSON.stringify(archival?{kind,action:'reconcile_windsor_refusal'}:{kind}),digest=createHash('sha256').update(body).digest('hex');
  let lastSentAt=0,requests=0;
  for(let pass=0;pass<(kind==='metrics'?3:1);pass++){
    if(clock()>=STOP)return {status:'period_ended',requests};
    const sentAt=Math.max(clock(),lastSentAt+1);lastSentAt=sentAt;
    const sent=String(sentAt),requestNonce=nonce();
    const signature=createHmac('sha256',Buffer.from(key,'base64url')).update(['vsd-cloud-v1',id,origin,'POST',path,sent,requestNonce,digest].join('\n')).digest('hex');
    let response;requests++;
    try {response=await fetcher(origin+path,{method:'POST',redirect:'error',signal:AbortSignal.timeout(60000),
      headers:{'Content-Type':'application/json','OAI-Sites-Authorization':'Bearer '+dispatcher,'X-VSD-Sent-At':sent,'X-VSD-Nonce':requestNonce,'X-VSD-Signature':signature},body});}
    catch(error){throw new ControlError(error?.name==='TimeoutError'?'request_timeout':'request_unconfirmed');}
    if(response.status!==200){await response.body?.cancel();throw new ControlError('http_non_success',response.status);}
    if(!response.headers.get('content-type')?.includes('application/json')){await response.body?.cancel();throw new ControlError('response_content_type');}
    const data=await boundedBody(response);
    if(!data||data.kind!==kind||!statuses.includes(data.status))throw new ControlError('task_attention_required');
    log('Cloud receipt: '+kind+' / '+data.status+'.');
    if(kind==='metrics'&&data.status==='disabled')break;
  }
  return {status:'confirmed',requests};
}
export function safeDiagnostic(error){
  // Only codes created here. Never serialize provider bodies, error messages,
  // environment, URLs, headers or credentials from arbitrary thrown values.
  const codes=new Set(['configuration','request_timeout','request_unconfirmed','http_non_success','response_empty','response_too_large','response_invalid_json','response_content_type','task_attention_required']);
  const code=error instanceof ControlError&&codes.has(error.code)?error.code:'operation_unconfirmed';
  return 'Cloud task not confirmed: '+code+(code==='http_non_success'&&Number.isInteger(error.httpStatus)?' (HTTP '+error.httpStatus+')':'')+'. No automatic retry was made.';
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{const result=await invoke();if(result.status==='period_ended')console.log('Follow-up period ended; no further request sent.');}
  catch(error){console.error(safeDiagnostic(error));process.exitCode=1;}
}
