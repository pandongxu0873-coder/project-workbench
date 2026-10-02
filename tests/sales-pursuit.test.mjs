import test from 'node:test';
import assert from 'node:assert/strict';
import {pursuitBucket,groupPursuits,todaysCommitments,mergeCommitments,hasCurrentJudgement} from '../src/salesPursuitModel.js';
const base={id:'p',is_current:true,analysis_state:'ready',analysis_stale:false,brief:{stage:'方案验证',attention:'可推进',next_action:'共定验证目标'}};
test('a nurturing relationship never reenters active sales because evidence is recent',()=>{
 const project={...base,execution:{status:'暂停跟进',relationship:'no_need'}};
 assert.equal(pursuitBucket(project),'nurture');assert.equal(groupPursuits([project]).advance.length,0);
 assert.equal(pursuitBucket({...project,execution:{relationship:'no_contact'}}),'quiet');
});
test('execution is distinct from customer acceptance and investment mode',()=>{
 assert.equal(pursuitBucket({...base,execution:{quick_outcome:'done',quick_action:'共定验证目标'}}),'waiting');
 assert.equal(pursuitBucket({...base,execution:{quick_outcome:'done',quick_action:'上一件事'}}),'waiting');
 assert.equal(pursuitBucket({...base,analysis_stale:true}),'advance');
 assert.equal(pursuitBucket({...base,is_current:false}),'history');
 assert.equal(pursuitBucket({...base,brief:{...base.brief,stage:'交付实施'}}),'delivery');
});
test('refresh preserves known work and actual execution without making old advice current',()=>{
 const refreshing={...base,analysis_state:'running',analysis_stale:true,brief:{...base.brief,stage:'交付实施'}};
 assert.equal(pursuitBucket(refreshing),'delivery');
 assert.equal(hasCurrentJudgement(refreshing),false);
 assert.equal(pursuitBucket({...refreshing,execution:{status:'已发出等待反馈'}}),'waiting');
 assert.equal(pursuitBucket({...refreshing,brief:null,execution_state:'done_waiting'}),'waiting');
 assert.equal(pursuitBucket({...refreshing,brief:null}),'updating');
 assert.equal(pursuitBucket({...refreshing,execution:{relationship:'no_contact'}}),'quiet');
 assert.equal(pursuitBucket({...refreshing,execution:{status:'暂停跟进'}}),'nurture');
 assert.equal(hasCurrentJudgement(base),true);
});
test('old deadlines and undated suggestions are not todays promises',()=>{
 const items=[{id:'old',deadline:'2026-07-13',action:'追客户'},{id:'today',deadline:'2026-09-17T14:00',action:'约定沟通'},{id:'future',deadline:'2026-09-18',action:'未来沟通'},{id:'paused',deadline:'2026-09-17',action:'旧承诺',status:'暂停跟进'},{id:'unknown',action:'建议'}];
 assert.deepEqual(todaysCommitments(items,'2026-09-17').map(i=>i.id),['today']);
});

test('today keeps customer appointments but excludes claimed tasks and routine unmatched calendar',()=>{
 const rounds={items:[{id:'round:p',action:'确认范围',due:'2026-09-18'}],claimed_actions:{old:'p'}};
 const calendar={items:[{id:'old',action:'旧动作',deadline:'2026-09-18'},{id:'meeting',source_type:'feishu_calendar',matched_customer:true,customer:'客户甲',action:'沟通',deadline:'2026-09-18'},{id:'routine',source_type:'feishu_calendar',customer:'待匹配日程',action:'培训',deadline:'2026-09-18'}]};
 assert.deepEqual(todaysCommitments(mergeCommitments(rounds,calendar),'2026-09-18').map(i=>i.id),['round:p','meeting']);
});
