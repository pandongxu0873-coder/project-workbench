import test from 'node:test';
import assert from 'node:assert/strict';
import { scenarios, emptyRound, guidance, roundDraft } from '../src/roundPlaybook.js';
const project = {title:'隔离项目',sources:[{path:'projects/explicit.md'}]};
test('all seven scenarios provide a complete actionable plan', () => {
  assert.equal(Object.keys(scenarios).length, 7);
  for (const scenario of Object.keys(scenarios)) for (const key of ['goal','questions','materials','roles','acceptance','branches','draft']) assert.ok(guidance({...emptyRound(),scenario})[key]);
});
test('saved no-contact cannot be bypassed by switching scenario or unsaved relationship', () => {
  for (const scenario of Object.keys(scenarios)) {
    const record = {...emptyRound(), scenario, relationship:'no_contact'};
    assert.equal(roundDraft(project,record), '');
    assert.equal(roundDraft(project,{...record,relationship:'unknown',recontact_basis:'new fact'},record), '');
  }
});
test('waiting for feedback produces no repeat contact draft', () => {
  for (const scenario of Object.keys(scenarios)) assert.equal(roundDraft(project,{...emptyRound(),scenario,status:'已发出等待反馈'}), '');
});
test('internal packet includes explicit sources and separates facts and judgment', () => {
  const draft = roundDraft(project,{...emptyRound(),scenario:'collaboration',facts:'客户原话',judgement:'个人推测'});
  assert.match(draft,/projects\/explicit.md/); assert.match(draft,/沟通事实：客户原话/); assert.match(draft,/个人判断.*个人推测/); assert.match(draft,/未发送/);
});
test('pause reasons each provide distinct preparation and conditional customer words', () => {
  const reasons=['budget','blocked','concern','no_need'];
  const results=reasons.map(relationship=>guidance({...emptyRound(),scenario:'relationship',relationship}));
  for (const key of ['goal','materials','questions','branches','draft']) assert.equal(new Set(results.map(r=>r[key])).size,4);
});
test('external draft uses explicit public topic without leaking internal feedback or judgment', () => {
  const draft=roundDraft(project,{...emptyRound(),topic:'会员演示范围',judgement:'内部毛利低',action:'成本45000',feedback:'内部评价'});
  assert.match(draft,/会员演示范围/); assert.doesNotMatch(draft,/内部毛利|45000|内部评价/);
});
