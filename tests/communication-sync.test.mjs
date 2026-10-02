import test from 'node:test';
import assert from 'node:assert/strict';
import { syncSummary, syncStep } from '../src/communicationSync.js';
test('an active run never displays the last completed receipt as completion',()=>{
 assert.equal(syncSummary({job:{running:true,phase_label:'读取邮件'},receipt:{status:'completed',run_id:'previous'}}).title,'读取邮件');
});
test('unavailable sources differ from unprocessed collected materials',()=>{
 const receipt={run_id:'r',status:'partial',gaps:[{source:'微信'}],unresolved:{needs_review:0},refresh_pending:[]};
 assert.equal(syncSummary({receipt}).title,'可读取内容已整理，仍有来源缺口');
 receipt.refresh_pending=['project'];assert.equal(syncSummary({receipt}).tone,'warning');assert.equal(syncSummary({receipt}).pending,1);
});
test('filed reference uncertainty stays visible without becoming a failed processing task',()=>{
 const receipt={run_id:'r',status:'completed',unresolved:{needs_review:0},archived_reference:5};
 assert.equal(syncSummary({receipt}).pending,0);
 assert.equal(syncSummary({receipt}).title,'本轮整理完成');
});
test('interrupted jobs remain resumable and phases do not imply percentages',()=>{
 assert.equal(syncSummary({job:{state:'interrupted'}}).tone,'warning');assert.equal(syncStep('email'),0);assert.equal(syncStep('refreshing'),3);
});
test('unfinished materials explain the actual stage instead of requesting manual classification',()=>{
 const result=syncSummary({receipt:{run_id:'r',unresolved:{extraction_pending:3,ready_for_review:2}}});
 assert.equal(result.pending,5);assert.match(result.detail,/3 份材料提取未完成/);assert.match(result.detail,/2 份材料分析未完成/);
});

test('automatic analysis is not presented as a failed import or manual retry',()=>{
 const receipt={run_id:'phone',status:'partial',refresh_pending:['p'],unresolved:{}};
 const result=syncSummary({receipt,analysis_refresh:{active:true,pending:1}});
 assert.equal(result.analysisOnly,true);assert.equal(result.tone,'running');
 assert.equal(syncSummary({receipt,analysis_refresh:{active:false,pending:1,failed:1}}).tone,'warning');
});
