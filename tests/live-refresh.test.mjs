import test from 'node:test';
import assert from 'node:assert/strict';
import { installLiveRefresh } from '../src/liveRefresh.js';

test('visible reads coalesce, resume on focus, recover from failure and stop after cleanup', async () => {
  const doc = new EventTarget(), win = new EventTarget(); doc.visibilityState = 'visible';
  let tick, calls = 0, finish, cancelled = false;
  const stop = installLiveRefresh(() => { calls++; return new Promise(resolve => { finish = resolve; }); }, {
    doc, win, schedule: callback => { tick = callback; return 42; }, cancel: id => { assert.equal(id, 42); cancelled = true; }
  });
  const first = tick(); win.dispatchEvent(new Event('focus')); await tick(); assert.equal(calls, 1);
  finish(); await first;
  doc.visibilityState = 'hidden'; await tick(); win.dispatchEvent(new Event('focus')); assert.equal(calls, 1);
  doc.visibilityState = 'visible'; doc.dispatchEvent(new Event('visibilitychange')); assert.equal(calls, 2);
  finish(); await Promise.resolve(); stop(); await tick(); win.dispatchEvent(new Event('focus')); assert.equal(calls, 2); assert.ok(cancelled);
  let retry; let failures = 0;
  const off = installLiveRefresh(async () => { failures++; throw Error('offline'); }, { doc, win, schedule: f => { retry=f; }, cancel: () => {} });
  await retry(); await retry(); assert.equal(failures, 2); off();
});
