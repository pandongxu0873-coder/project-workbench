import test from 'node:test';
import assert from 'node:assert/strict';
import {calendarBackgroundModel,timelineModel,periodDate,periodLabel} from '../src/dashboardModel.js';
const now=new Date('2026-10-02T12:00:00+08:00');
const item={id:'1',customer:'测试客户',deadline:'2026-10-02',status:'待反馈',source_type:'project_round'};
test('date-only today remains current; formal project followups retained',()=>{const m=timelineModel([item],14,now);assert.equal(m.pending.length,1);assert.equal(m.overdue.length,0)});
test('closed, suppressed, transcript candidates, unmatched internal meetings do not enter the timeline',()=>{const a=[{...item,status:'暂停跟进'},{...item,id:'2',sales_suppressed:true},{...item,id:'3',source_type:'transcript_intake'},{...item,id:'4',source_type:'feishu_calendar',matched_customer:false}];assert.equal(timelineModel(a,14,now).pending.length,0)});
test('ongoing meeting stays current; only real meetings get duration bars',()=>{const m=timelineModel([{...item,source_type:'feishu_calendar',matched_customer:true,deadline:'2026-10-02T11:00+08:00',end_time:'2026-10-02T13:00+08:00'},{...item,id:'2',deadline:'2026-10-03',end_time:'2026-10-05'}],14,now);assert.equal(m.pending.length,2);assert.equal(m.pending[0].isInterval,true);assert.equal(m.pending[1].isInterval,false)});
test('old nodes and unknown dates stay out of future timeline',()=>{const m=timelineModel([{...item,deadline:'2026-07-01'},{...item,id:'2',deadline:'bad'}],14,now);assert.equal(m.pending.length,0);assert.equal(m.overdue.length,1);assert.equal(m.undated.length,1)});
test('period selection maps quarter and month separately',()=>{assert.equal(periodDate('QUARTER',2026,3),'2026-07-01');assert.equal(periodDate('MONTH',2026,9),'2026-09-01');assert.equal(periodLabel('QUARTER','2026-07-01'),'2026 年 · 第 3 季度')});

test('due fallback remains displayable and timezone-free business time uses Shanghai',()=>{
 const m=timelineModel([{id:'due',customer:'测试客户',due:'2026-10-02 10:00',status:'推进中'}],14,new Date('2026-10-02T01:00:00Z'));
 assert.equal(m.pending[0].deadline,'2026-10-02 10:00');
 assert.equal(m.pending[0].from,Date.parse('2026-10-02T02:00:00Z'));
});

test('calendar occupancy is bounded, deduplicated and never a customer task',()=>{
 const n={id:'meeting',calendar_background:true,title:'周会',deadline:'2026-10-03T10:00+08:00',end_time:'2026-10-03T11:00+08:00'};
 assert.equal(calendarBackgroundModel([n,n,{...n,id:'linked',project_id:'p'},{...n,id:'cancel',status:'cancelled'},{...n,id:'old',end_time:'2026-10-01'}],14,now).length,1);
 assert.equal(timelineModel([n],14,now).pending.length,0);
});

test('project dates need explicit IDs and ignore closed/internal calendar records',async()=>{
 const {projectsWithoutDates}=await import('../src/dashboardModel.js');
 const ps=[{id:'a',customer:'同客户'},{id:'b',customer:'同客户'},{id:'c'},{id:'archived',archive:{archived:true}}];
 const records=[{...item,project_id:'a'},{...item,id:'closed',project_id:'b',status:'已完成'},{...item,id:'internal',project_id:'c',sales_suppressed:true}];
 assert.deepEqual(projectsWithoutDates(ps,records,now).map(p=>p.id),['b','c']);
 assert.deepEqual(projectsWithoutDates(ps,[{...item,customer:'同客户'}],now).map(p=>p.id),['a','b','c']);
});
