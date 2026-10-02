import test from 'node:test';
import assert from 'node:assert/strict';
import {eventDate, requirementTimeline} from '../src/requirementTimeline.js';

test('business history is chronological, same-day changes and milestones coexist without changing saved order',()=>{
  const value={evolution:[{date:'2026-09-20',title:'新增范围'},{date:'2026-07-27',title:'首次需求'},{date:'2026-07-27',title:'收缩一期'}],lifecycle:[{date:'2026-07-27',title:'沟通完成'},{date:'2026-08-01',title:'报价待定'}]};
  const original=JSON.stringify(value);
  const groups=requirementTimeline(value);
  assert.deepEqual(groups.map(g=>g.date),['2026-07-27','2026-08-01','2026-09-20']);
  assert.deepEqual(groups[0].events.map(e=>e.item.title),['首次需求','收缩一期','沟通完成']);
  assert.equal(groups.flatMap(g=>g.events).length,5);
  assert.equal(JSON.stringify(value),original);
  assert.equal(requirementTimeline(value,false).flatMap(g=>g.events).length,3);
});

test('unknown and invalid dates cannot be inferred from filenames, quotes or result creation time',()=>{
  const value={created_at:'2026-09-23',evolution:[{date:'',title:'范围待核',evidence:[{path:'20260923_archive.md',quote:'2026-09-20整理'}]},{date:'2026-02-30',title:'无效日期'},{date:'2026-08',title:'仅月份'},{date:'2026-07-27',title:'发生日明确'}]};
  const groups=requirementTimeline(value);
  assert.deepEqual(groups.map(g=>g.date),['2026-07-27','']);
  assert.equal(groups[1].events.length,3);
  assert.equal(eventDate('2024-02-29'),'2024-02-29');
  assert.equal(eventDate('2026-02-29'),'');
});

test('requirements without history are retained by the caller, never assigned an invented history',()=>{
  assert.deepEqual(requirementTimeline({requirements:[{name:'物流',date:'2026-09-23'}]}),[]);
  assert.deepEqual(requirementTimeline(null),[]);
});
