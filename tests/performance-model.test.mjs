import test from 'node:test';
import assert from 'node:assert/strict';
import {performanceModel,periodOrders,projectPayments,finiteAmount} from '../src/performanceModel.js';
test('performance remains a CRM aggregate; missing target and received are not fabricated',()=>{
 const result=performanceModel({totalPerformance:{amount:200},pendingReceivable:{amount:50},personalTargetAchievement:{totalPerformance:{configured:false,target:0,actual:200}},signingTrend:[{label:'9月',totalAmount:200}]});
 assert.equal(result.amount,200);assert.equal(result.received,null);assert.equal(result.goal,null);assert.equal(result.rate,null);assert.equal(result.trend[0].amount,200);
 assert.equal(performanceModel().amount,null);assert.equal(finiteAmount(''),null);assert.equal(finiteAmount(0),0);
});
test('targets use authoritative actual and trend buckets are not presented as cumulative',()=>{
 const result=performanceModel({totalPerformance:{amount:200},personalTargetAchievement:{totalPerformance:{configured:true,target:100,actual:120}},signingTrends:{WEEK:[{label:'1',totalAmount:20},{label:'2',totalAmount:80}]}});
 assert.equal(result.rate,120);assert.equal(result.gap,0);assert.deepEqual(result.trend.map(x=>x.amount),[20,80]);
});
test('period order date includes the full final local day and excludes unknown dates',()=>{
 const start='2026-08-31T16:00:00Z',end='2026-09-16T16:00:00Z';
 const rows=[{id:1,orderDate:start},{id:2,orderDate:'2026-09-17T15:59:59Z'},{id:3,orderDate:'2026-09-17T16:00:00Z'},{id:4,orderDate:null}];
 assert.deepEqual(periodOrders({resources:{orders:{data:{list:rows}}}},{rangeStart:start,rangeEnd:end}).map(x=>x.id),[2,1]);
});
test('project receipts join by explicit opportunity ID, deduplicate orders, and preserve missing values',()=>{
 const one={id:1,opportunityId:20,customerName:'same',orderAmount:1,receivedAmount:.1,pendingReceivableAmount:.9};
 const two={id:2,opportunityId:20,customerName:'same',orderAmount:2,receivedAmount:.2,pendingReceivableAmount:1.8};
 const three={id:3,opportunityId:21,customerName:'same',orderAmount:5,receivedAmount:null,pendingReceivableAmount:5};
 const results=projectPayments([one,two,one,three,{id:4,customerName:'same',orderAmount:0,receivedAmount:0,pendingReceivableAmount:0}]);
 assert.equal(results.groups.length,3);assert.equal(results.count,4);assert.equal(results.groups[0].received,.3);assert.equal(results.groups[0].pending,2.7);assert.equal(results.received,null);assert.equal(results.pending,7.7);
 assert.equal(projectPayments([]).received,null);
});
