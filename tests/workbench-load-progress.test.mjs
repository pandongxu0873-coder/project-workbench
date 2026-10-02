import test from 'node:test';
import assert from 'node:assert/strict';
import { loadWorkbenchData, WORKBENCH_READS } from '../src/api.js';
test('full refresh reports actual independent completion; failure does not become success', async () => {
 const controls = new Map(), events=[];
 const task=loadWorkbenchData({onProgress:e=>events.push(e),get:path=>new Promise((resolve,reject)=>controls.set(path,{resolve,reject}))});
 assert.equal(controls.size,4);
 assert.equal(events.filter(e=>e.state==='ready').length,0);
 controls.get('/api/prospecting').resolve({leads:[]});
 await Promise.resolve();
 assert.equal(events.find(e=>e.key==='prospecting'&&e.state==='ready')?.state,'ready');
 controls.get('/api/accounts')?.resolve({});
 controls.get('/api/account-advancement').reject(Error('offline'));
 controls.get('/api/risk-todos').resolve({items:[]});
 controls.get('/api/dashboard').resolve({generated_at:'actual'});
 await assert.rejects(task,/客户资料.*offline/);
 assert.equal(events.filter(e=>e.state==='error').length,1);
 assert.equal(events.filter(e=>e.state==='ready').length,3);
});
test('all successful reads retain their source payloads', async () => {
 const result = await loadWorkbenchData({get:async path=>({source:path})});
 for(const item of WORKBENCH_READS) assert.equal(result[item.key].source,item.path);
});
