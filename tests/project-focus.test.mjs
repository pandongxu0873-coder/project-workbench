import test from 'node:test';
import assert from 'node:assert/strict';
import { todayFocus } from '../src/projectFocus.js';

const now = new Date('2026-09-07T12:00:00+08:00');
const action = (id, deadline, extra = {}) => ({ id, deadline, status: '推进中', ...extra });

test('homepage focuses three real commitments by due date without dropping remaining work', () => {
  const rows = [action('evening','2026-09-07T18:00:00+08:00'),action('late','2026-09-06T10:00:00+08:00'),action('afternoon','2026-09-07T15:00:00+08:00'),action('morning','2026-09-07T09:00:00+08:00')];
  const before=JSON.stringify(rows);
  const result=todayFocus(rows,now);
  assert.equal(result.total,4);
  assert.deepEqual(result.items.map(x=>x.id),['late','morning','afternoon']);
  assert.equal(JSON.stringify(rows),before);
});

test('undated, future, historical and terminal items do not become today pressure', () => {
  const rows=[action('unknown',''),action('invalid','明天'),action('future','2026-09-08'),action('july','2026-07-13'),action('closed','2026-09-07',{status:'本轮完成'}),action('paused','2026-09-07',{status:'暂停跟进'})];
  assert.deepEqual(todayFocus(rows,now),{items:[],total:0});
});

test('reschedule, closure and a reached feedback date update the same queue', () => {
  const waiting=action('original','2026-09-07T16:00:00+08:00',{status:'待客户反馈'});
  assert.equal(todayFocus([waiting],now).items[0].id,'original');
  assert.equal(todayFocus([{...waiting,deadline:'2026-09-08T16:00:00+08:00'}],now).total,0);
  assert.equal(todayFocus([{...waiting,status:'已完成'}],now).total,0);
});

test('alternate due field obeys freshness and impossible calendar days are rejected', () => {
  assert.deepEqual(todayFocus([{id:'old',due:'2026-07-13'},action('invalid','2026-09-00')],now),{items:[],total:0});
  assert.equal(todayFocus([{id:'valid',due:'2026-09-07'}],now).items[0].id,'valid');
  assert.equal(todayFocus([action('rolled','2026-02-30')],new Date('2026-03-07T12:00:00+08:00')).total,0);
});

test('received feedback needs a real recent record and never overrides a future appointment',()=>{
 const feedback={status:'已收到反馈',feedback:'已收到客户范围答复',saved_at:'2026-09-07T10:00:00+08:00'};
 const rows=[action('received','',feedback),action('old-deadline-new-reply','2026-07-01',feedback),action('empty','',{...feedback,feedback:''}),action('ancient','',{...feedback,saved_at:'2026-07-01'}),action('scheduled','2026-09-08',feedback),action('no-contact','',{...feedback,relationship:'no_contact'})];
 assert.deepEqual(todayFocus(rows,now).items.map(x=>x.id),['old-deadline-new-reply','received']);
 assert.ok(todayFocus(rows,now).items.every(x=>x.focus_reason==='已收到反馈，待承接'));
 assert.equal(rows[1].deadline,'2026-07-01');
});
