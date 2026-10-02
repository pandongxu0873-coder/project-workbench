import test from 'node:test';
import assert from 'node:assert/strict';
import {splitScheduleArchive, splitReceiptArchive, isScheduleAutoArchived} from '../src/scheduleArchive.js';
test('only strictly more than fifteen days overdue archives; local timestamps use Shanghai',()=>{
 const item={deadline:'2026-09-17 20:00'};
 assert.equal(isScheduleAutoArchived(item,new Date('2026-10-02T20:00:00+08:00')),false);
 assert.equal(isScheduleAutoArchived(item,new Date('2026-10-02T20:00:00.001+08:00')),true);
 assert.equal(isScheduleAutoArchived({deadline:'2026-09-17'},new Date('2026-10-02T20:00:00+08:00')),false);
});
test('future/rescheduled or missing dates stay visible; archived records remain intact',()=>{
 const old={id:'old',deadline:'2026-09-01',status:'待客户反馈',project_id:'keep'};
 const future={...old,id:'new',deadline:'2026-10-10'};
 const unread={id:'unread',deadline:'未知'};
 assert.equal(isScheduleAutoArchived({deadline:'2026-02-31'},new Date('2026-10-02T20:00:00+08:00')),false);
 const original=JSON.stringify(old);
 const result=splitScheduleArchive([old,future,unread],new Date('2026-10-02T20:00:00+08:00'));
 assert.deepEqual(result.current,[future,unread]);assert.deepEqual(result.archived,[old]);assert.equal(JSON.stringify(old),original);
});
test('old closed receipts leave recent section without changing status or dropping history',()=>{
 const receipt={submitted_at:'2026-07-11 11:28',status:'已闭环'};
 const result=splitReceiptArchive([receipt],new Date('2026-10-02T20:00:00+08:00'));
 assert.equal(result.current.length,0);assert.equal(result.archived[0],receipt);assert.equal(receipt.status,'已闭环');
});

test('ongoing multiday schedules archive from effective end rather than start',()=>{
 const meeting={deadline:'2026-09-01T09:00+08:00',end_time:'2026-10-05T18:00+08:00',source_type:'feishu_calendar'};
 assert.equal(isScheduleAutoArchived(meeting,new Date('2026-10-02T20:00+08:00')),false);
 assert.equal(isScheduleAutoArchived(meeting,new Date('2026-10-20T18:00+08:00')),false);
 assert.equal(isScheduleAutoArchived(meeting,new Date('2026-10-20T18:00:00.001+08:00')),true);
});
