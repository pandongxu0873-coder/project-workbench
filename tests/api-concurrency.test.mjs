import test from 'node:test';
import assert from 'node:assert/strict';
import {createApi} from '../src/api.js';
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};

test('slow concurrent reads share transport but not mutable payloads',async()=>{
  const gate=deferred();let calls=0;
  const api=createApi(()=>{calls++;return gate.promise;});
  const first=api.get('/overview'),second=api.get('/overview');
  await Promise.resolve();assert.equal(calls,1);
  gate.resolve({projects:[{title:'客户项目'}]});
  const [a,b]=await Promise.all([first,second]);a.projects[0].title='仅本视图修改';assert.equal(b.projects[0].title,'客户项目');
  await api.get('/overview');assert.equal(calls,2);
});
test('failed read releases its slot and unrelated endpoints run independently',async()=>{
  const fail=deferred();let calls=0;
  const api=createApi(path=>{calls++;return path==='/broken'&&calls<3?fail.promise:Promise.resolve({path});});
  const a=api.get('/broken'),b=api.get('/broken');
  assert.equal((await api.get('/other')).path,'/other');
  fail.reject(new Error('断线'));await assert.rejects(a,/断线/);await assert.rejects(b,/断线/);
  assert.equal((await api.get('/broken')).path,'/broken');assert.equal(calls,3);
});
test('post-write verification cannot reuse the pre-write request',async()=>{
  const old=deferred();let version=0,reads=0;
  const api=createApi((path,options)=>{if(options?.method==='POST'){version++;return Promise.resolve({saved:true});}reads++;return reads===1?old.promise:Promise.resolve({version});});
  const prior=api.get('/analysis');await Promise.resolve();await api.post('/analysis',{correction:'新范围'});
  const fresh=await api.get('/analysis');assert.equal(fresh.version,1);assert.equal(reads,2);
  old.resolve({version:0});assert.equal((await prior).version,0);
  assert.equal((await api.get('/analysis')).version,1);
});
