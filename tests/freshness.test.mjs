import test from 'node:test';
import assert from 'node:assert/strict';
import { splitCurrentActions } from '../src/freshness.js';
test('expired July actions move to history without changing original records or future commitments',()=>{
  const old={id:'清源健康',deadline:'2026-07-13',priority:'P0',message_delivery:{needs_review:true}};
  const future={id:'future',deadline:'2026-09-08',priority:'P0',message_delivery:{needs_review:true}};
  const current={id:'recent',deadline:'2026-09-05',priority:'P1'};
  const before=JSON.stringify([old,future,current]);
  const result=splitCurrentActions([old,future,current],new Date(2026,8,6));
  assert.deepEqual(result.history,[old]);assert.deepEqual(result.current,[future,current]);assert.equal(JSON.stringify([old,future,current]),before);
});
