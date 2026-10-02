import test from 'node:test';
import assert from 'node:assert/strict';
import {customerDirectory} from '../src/customerDirectory.js';

test('admitted customer remains searchable without inventing a project',()=>{
  const account={id:'admitted',name:'正式客户甲',next_action:'核对实际购买场景'};
  const rows=customerDirectory([account],[],'客户甲');
  assert.equal(rows.length,1);assert.equal(rows[0].account,account);assert.deepEqual(rows[0].projects,[]);
  assert.equal(rows[0].id,'account:admitted');
});
test('explicitly matched projects share a customer entrance but retain separate states',()=>{
  const projects=[{id:'p1',customer:'客户甲',title:'交付项目',is_current:true},{id:'p2',customer:'客户甲',title:'历史扩容',is_current:false}];
  const rows=customerDirectory([{id:'a',name:'客户甲'}],projects);
  assert.equal(rows.length,1);assert.deepEqual(rows[0].projects,projects);
  assert.equal(customerDirectory([{id:'a',name:'客户甲'}],projects,'历史扩容').length,1);
});
test('similar names and unknown identities never silently merge',()=>{
  const rows=customerDirectory([{id:'a',name:'客户甲集团'}],[{id:'p1',customer:'客户甲',title:'项目'},{id:'p2',customer:'客户待核实'},{id:'p3',customer:'客户待核实'}]);
  assert.equal(rows.length,4);assert.equal(rows.find(x=>x.id==='account:a').projects.length,0);
});
test('duplicate formal names need an explicit ID before a project can join either record',()=>{
  const accounts=[{id:'a',name:'同名客户'},{id:'b',name:'同名客户'}];
  const rows=customerDirectory(accounts,[{id:'p',customer:'同名客户'}]);
  assert.equal(rows.length,3);assert.ok(rows.filter(r=>r.account).every(r=>r.projects.length===0));
  const explicit=customerDirectory(accounts,[{id:'p',customer:'同名客户',account_id:'b'}]);
  assert.equal(explicit.find(r=>r.id==='account:b').projects.length,1);
});

test('customer scope excludes unrelated accounts but retains explicit project identities',()=>{
  const accounts=[{id:'a',name:'客户甲集团'},{id:'b',name:'客户乙'}];
  const projects=[{id:'p',customer:'客户甲',title:'一期',account_id:'a'}];
  const rows=customerDirectory(accounts,projects,'','客户甲');
  assert.equal(rows.length,1);assert.equal(rows[0].account.id,'a');
  assert.equal(customerDirectory(accounts,projects,'客户乙','客户甲').length,0);
});
