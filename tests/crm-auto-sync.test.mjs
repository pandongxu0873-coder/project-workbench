import test from 'node:test';
import assert from 'node:assert/strict';
import {CRM_REFRESH_MS, installCrmAutoSync, needsCrmRefresh} from '../src/crmAutoSync.js';
test('CRM auto sync runs on entry, every five minutes and return to visible; cleans up on exit', () => {
  let calls = 0, callback, interval, listener, cancelled;
  const doc = {visibilityState: 'visible', addEventListener: (name, fn) => listener = fn, removeEventListener: (name, fn) => {assert.equal(fn, listener); listener = null;}};
  const stop = installCrmAutoSync(() => calls++, doc, (fn, ms) => {callback = fn; interval = ms; return 42;}, id => cancelled = id);
  assert.equal(calls, 1); assert.equal(interval, 300000);
  callback(); assert.equal(calls, 2);
  doc.visibilityState = 'hidden'; callback(); assert.equal(calls, 2);
  doc.visibilityState = 'visible'; listener(); assert.equal(calls, 3);
  stop(); assert.equal(cancelled, 42); assert.equal(listener, null);
});
test('all three CRM periods must be fresh and unconfigured never starts sync', () => {
  const now = Date.now();
  const result = {configured:true,snapshot:{dashboards:Object.fromEntries(['QUARTER','MONTH','YEAR'].map(p=>[p,{fetched_at:new Date(now).toISOString()}]))}};
  assert.equal(needsCrmRefresh(result, now), false);
  assert.equal(needsCrmRefresh(result, now + CRM_REFRESH_MS), true);
  delete result.snapshot.dashboards.MONTH;
  assert.equal(needsCrmRefresh(result, now), true);
  result.configured = false; assert.equal(needsCrmRefresh(result, now), false);
});
