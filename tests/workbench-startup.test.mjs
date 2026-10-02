import test from 'node:test';
import assert from 'node:assert/strict';
import {needsWorkbenchData,readProjectSnapshot,writeProjectSnapshot,PROJECT_SNAPSHOT_KEY} from '../src/workbenchStartup.js';
function storage() { const values = new Map(); return {getItem:key=>values.get(key),setItem:(key,value)=>values.set(key,value)}; }
test('independent pages do not require legacy sales aggregate; action pages do', () => {
 for (const view of ['projects','agent','communications','knowledge','today','discover']) assert.equal(needsWorkbenchData(view),false);
 for (const view of ['accounts','reminders']) assert.equal(needsWorkbenchData(view),true);
});
test('project snapshot is a bounded display copy without write revisions or source content', () => {
 const store=storage(); const now=100000;
 writeProjectSnapshot(store,[{id:'real-id',title:'project',customer:'customer',brief:{next_action:'review'},pursuit:{conversation:{success_signal:'客户确认一期范围',opening:'full draft'},internal_track:'internal detail'},plan_revision:42,actions:[{id:'action'}],sources:[{content:'original'}]}],now);
 const value=readProjectSnapshot(store,now+1);
 assert.equal(value.projects[0].id,'real-id');
 assert.equal(value.projects[0].plan_revision,undefined);
 assert.equal(value.projects[0].actions,undefined);
 assert.equal(value.projects[0].sources,undefined);
 assert.deepEqual(value.projects[0].pursuit,{conversation:{success_signal:'客户确认一期范围'}});
 assert.equal(readProjectSnapshot(store,now+24*60*60*1000+1),null);
 assert.equal(readProjectSnapshot(store,now-1),null);
});
test('corrupt, wrong-version and unavailable storage fall back to live reads', () => {
 const store=storage();store.setItem(PROJECT_SNAPSHOT_KEY,'{broken');assert.equal(readProjectSnapshot(store),null);
 store.setItem(PROJECT_SNAPSHOT_KEY,JSON.stringify({version:0,savedAt:Date.now(),projects:[]}));assert.equal(readProjectSnapshot(store),null);
 const denied={getItem(){throw Error('disabled')},setItem(){throw Error('full')}};
 assert.equal(readProjectSnapshot(denied),null);
 assert.doesNotThrow(()=>writeProjectSnapshot(denied,[]));
});
