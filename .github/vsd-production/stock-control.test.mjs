import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {runStockControl} from './stock-control.mjs';

// Offline integration of the shipped bundle and immutable catalogue. Provider
// states below are synthetic, never a claim about the production database.
const root=fileURLToPath(new URL('../../',import.meta.url));
const index=JSON.parse(await readFile(new URL('./reviewed-social/index.json',import.meta.url),'utf8'));
const stable=value=>Array.isArray(value)?value.map(stable):value&&typeof value==='object'?
  Object.fromEntries(Object.keys(value).sort().map(key=>[key,stable(value[key])])):value;
const retired=new Set((index.retirements??[]).map(row=>row.batchId));
const now=new Date(Math.max(Date.parse('2026-10-12T03:00:00Z'),...(index.retirements??[]).map(row=>Date.parse(row.retiredAt)+1000))).toISOString();
function transport(conflict=false){return async body=>{
  assert.equal(body.action,'stock_status','retired lots must never cause an import');
  return {kind:'publications',status:'stock_checked',schemaVersion:1,checkedAt:now,revision:1,
    requestSha256:createHash('sha256').update(JSON.stringify(stable(body.batches))).digest('hex'),
    batches:body.batches.map(row=>({...row,state:retired.has(row.batchId)?conflict?'conflict':'absent':'imported',
      importedAt:retired.has(row.batchId)?null:'2026-09-27T00:00:00Z'}))};
};}

test('shipped controller settles imported and retired lots without importing or claiming retired lots imported',async()=>{
  assert.ok(retired.size>0);
  const result=await runStockControl({repositoryRoot:root,transport:transport(),now:()=>now});
  assert.equal(result.status,'stock_settled');assert.equal(result.importAttempted,false);
  assert.deepEqual(new Set(result.retiredBatchIds),retired);
  assert.equal(result.importedBatchIds.some(id=>retired.has(id)),false);
});

test('shipped controller preserves a conflicting remote state even for a retired duplicate',async()=>{
  const result=await runStockControl({repositoryRoot:root,transport:transport(true),now:()=>now});
  assert.equal(result.status,'attention_required');assert.equal(result.importAttempted,false);
});
