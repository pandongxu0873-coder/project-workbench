import test from 'node:test';import assert from 'node:assert/strict';
import {projectNeed} from '../src/projectPresentation.js';
import {k100Directory} from '../src/k100DirectoryModel.js';
const ready={analysis_state:'ready',analysis_stale:false,brief:{attention:'可推进',next_action:'办理现有手续'},execution_state:'actionable'};
test('active filter excludes stale, waiting and archived records',()=>{assert.equal(projectNeed(ready).actionable,true);for(const p of [{...ready,analysis_stale:true},{...ready,archive:{archived:true}},{...ready,execution:{relationship:'no_contact'}},{...ready,brief:{attention:'等反馈',next_action:'等待结果'},execution_state:'waiting_feedback'}])assert.equal(projectNeed(p).actionable,false);});
test('completed receipt is not recommended again; independent action stays actionable',()=>{const execution={quick_outcome:'done',quick_action:'发送方案'};assert.equal(projectNeed({...ready,execution,brief:{next_action:'「发送方案」已做，结果尚待现有资料核对'}}).kind,'waiting');assert.equal(projectNeed({...ready,execution,execution_state:'done_waiting'}).actionable,true);});
test('formal directory never merges brand names or other owners',()=>{const roster=[{id:'a',legalName:'示例集团有限公司',isMine:true},{id:'b',legalName:'示例集团分公司',isMine:true},{id:'c',legalName:'他人客户',isMine:false}];const p=[{id:'p1',customer:'示例集团'},{id:'p2',customer:'示例集团有限公司'}];const rows=k100Directory(roster,p,{},[{id:'s',customer:'示例集团'}]);assert.equal(rows.length,2);assert.deepEqual(rows[0].projects.map(x=>x.id),['p2']);assert.equal(rows[0].signals.length,0);assert.equal(rows[1].projects.length,0);});
test('explicit CRM identity takes precedence; foreign IDs never fall back by name',()=>{const roster=[{id:'a',legalName:'示例主体',isMine:true}];const rows=k100Directory(roster,[{id:'p',customer:'品牌'},{id:'q',customer:'示例主体'}],{p:{link:{customer_id:'a'}},q:{link:{customer_id:'other'}}},[{id:'s',customer:'示例主体',k100_customer_id:'other'}]);assert.deepEqual(rows[0].projects.map(x=>x.id),['p']);assert.equal(rows[0].signals.length,0);});

test('failed analysis does not hide an independently recorded commitment',()=>{const p={...ready,analysis_state:'error'};const task={project_id:'p',action:'按约核对已寄合同'};assert.equal(projectNeed(p,[task]).actionable,true);assert.equal(projectNeed({...p,execution:{relationship:'no_contact'}},[task]).actionable,false);});

test('customer news uses explicit project links and never spreads a shared brand',()=>{
 const roster=[{id:'a',legalName:'总公司',isMine:true},{id:'b',legalName:'分公司',isMine:true}];
 const projects=[{id:'p',customer:'同品牌'},{id:'q',customer:'同品牌'}];
 const summary={p:{link:{customer_id:'a'}},q:{link:{customer_id:'b'}}};
 const rows=k100Directory(roster,projects,summary,[{id:'ambiguous',customer:'同品牌'},{id:'direct',project_id:'q',customer:'同品牌'}]);
 assert.equal(rows[0].signals.length,0);assert.deepEqual(rows[1].signals.map(x=>x.id),['direct']);
});
