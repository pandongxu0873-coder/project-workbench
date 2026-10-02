import test from 'node:test';
import assert from 'node:assert/strict';
import { stageDistribution, scopeProjects, shouldClearProject, analysisAttemptKey, projectConnections, orderOverviewProjects } from '../src/projectOverview.js';
test('stage distribution includes only current fresh AI briefs and respects customer scope',()=>{
  const items=[{id:'a',customer:'甲',is_current:true,analysis_state:'ready',analysis_stale:false,brief:{stage:'需求澄清'}},{id:'b',customer:'乙',is_current:true,analysis_state:'ready',brief:{stage:'方案验证'}},{id:'c',customer:'甲',is_current:false,analysis_state:'ready',brief:{stage:'商务推进'}},{id:'d',customer:'甲',is_current:true,analysis_state:'stale',analysis_stale:true,brief:{stage:'交付实施'}}];
  const result=stageDistribution(scopeProjects(items,{customer:'甲'}));
  assert.equal(result.total,2);assert.equal(result.counts['需求澄清'],1);assert.equal(result.counts['方案验证'],0);assert.equal(result.counts['交付实施'],0);assert.equal(result.pending,1);
});
test('explicit empty project navigation clears selection, omitted project preserves context',()=>{assert.equal(shouldClearProject({projectId:''}),true);assert.equal(shouldClearProject({}),false);});
test('default overview puts only fresh actionable projects first, preserving order and filtered views',()=>{
  const rows=[
    {id:'running',analysis_state:'running',brief:{attention:'可推进'}},
    {id:'waiting',analysis_state:'ready',analysis_stale:false,brief:{attention:'等反馈'}},
    {id:'action-a',analysis_state:'ready',analysis_stale:false,brief:{attention:'可推进'}},
    {id:'stale',analysis_state:'ready',analysis_stale:true,brief:{attention:'可推进'}},
    {id:'action-b',analysis_state:'ready',analysis_stale:false,brief:{attention:'可推进'}},
    {id:'paused',analysis_state:'ready',analysis_stale:false,brief:{attention:'暂缓'}},
  ];
  const original=structuredClone(rows);
  assert.deepEqual(orderOverviewProjects(rows).map(p=>p.id),['action-a','action-b','running','waiting','stale','paused']);
  for(const filter of [{query:'项目'},{customer:'客户'},{stage:'商务推进'},{attention:'等反馈'}]) {
    assert.deepEqual(orderOverviewProjects(rows,filter),original);
  }
  assert.deepEqual(rows,original);
});
test('automatic analysis deduplication is keyed to actual input fingerprint',()=>{assert.notEqual(analysisAttemptKey({id:'a',analysis_fingerprint:'old'}),analysisAttemptKey({id:'a',analysis_fingerprint:'new'}));});
test('project connections follow explicit customers or source edges without merging business lines',()=>{
  const p={id:'a',title:'商城一期',customer:'商城',source_path:'projects/a.md',sources:[{path:'projects/finance.md',relation:'background_reference'}]};
  const rows=[p,{id:'b',title:'商城二期',customer:'商城'},{id:'c',title:'财经平台',customer:'汽车财经',source_path:'projects/finance.md'},{id:'d',title:'商城关键词相似',customer:'独立客户'},{id:'e',title:'引用商城场景',customer:'其他业务',sources:[{path:p.source_path,relation:'background_reference'}]}];
  assert.deepEqual(projectConnections(p,rows).map(x=>[x.id,x.relation]),[['b','同客户'],['c','原文关联'],['e','原文关联']]);
  assert.deepEqual(projectConnections({id:'x',customer:'客户关联待核实'},[{id:'y',customer:'客户关联待核实'}]),[]);
  assert.equal(rows[2].customer,'汽车财经');
});
