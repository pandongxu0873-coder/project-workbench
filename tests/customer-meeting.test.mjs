import test from 'node:test';
import assert from 'node:assert/strict';
import {restoreMeeting,meetingText} from '../src/customerMeeting.js';
const projects=[{id:'delivery',title:'一期交付',analysis_state:'ready',analysis_stale:false,brief:{situation:'复验待确认',next_action:'确认范围'},pursuit:{conversation:{goal:'确认阶段验收范围',success_signal:'取得范围反馈'}}},{id:'growth',title:'二期新增',analysis_state:'running',analysis_stale:true,brief:{situation:'有新增需求',next_action:'旧建议：马上投入开发'}}];
test('a customer preparation preserves chosen order but rejects foreign projects',()=>{
 const draft=restoreMeeting({contact:'项目负责人',goal:'分别收口范围',ids:['growth','other-customer','delivery','growth'],notes:{delivery:'本次确认复验人','other-customer':'不能混入'}},projects);
 assert.deepEqual(draft.ids,['growth','delivery']);
 assert.deepEqual(draft.notes,{delivery:'本次确认复验人'});
 const text=meetingText('客户甲',draft,projects);
 assert.ok(text.indexOf('1. 二期新增')<text.indexOf('2. 一期交付'));
 assert.ok(text.includes('上次理解，尚待更新'));
 assert.ok(!text.includes('马上投入开发'));
 assert.ok(text.includes('本次确认复验人'));
});
test('no-contact changes block an existing prepared agenda without deleting it',()=>{
 const draft=restoreMeeting({contact:'联系人',goal:'范围讨论',ids:['delivery']},projects);
 assert.ok(meetingText('客户甲',draft,projects));
 assert.equal(meetingText('客户甲',draft,[{...projects[0],execution:{relationship:'no_contact'}}]),'');
 assert.deepEqual(draft.ids,['delivery']);
 assert.equal(meetingText('客户甲',{...draft,contact:''},projects),'');
});

test('selected issue preserves preparation, provenance and confirmation boundary',async()=>{
 const {addMeetingTopic,decisionMeetingTopic}=await import('../src/customerMeeting.js');
 let draft=restoreMeeting({contact:'负责人',goal:'范围确认',ids:['growth'],notes:{growth:'人工保留'}},projects);
 const topic={...decisionMeetingTopic('scope',{name:'新增范围',baseline:'原合同A',change:'新增B',confirmation:'尚未确认',impact:'投入待评估',recommendation:'先澄清',evidence:[{path:'会议.md',quote:'客户提出B，尚未报价'}]}),createdAt:'2026-09-20',stale:true};
 draft=addMeetingTopic(draft,'delivery',topic);
 draft=addMeetingTopic(draft,'delivery',{...topic,detail:topic.detail+'\n须单独确认'});
 assert.deepEqual(draft.ids,['growth','delivery']);assert.equal(draft.notes.growth,'人工保留');assert.equal(draft.topics.delivery.length,1);
 const text=meetingText('客户甲',restoreMeeting(JSON.parse(JSON.stringify(draft)),projects),projects);
 for(const value of ['尚未确认','原合同A','客户提出B，尚未报价','当时已待更新','须单独确认'])assert.ok(text.includes(value));
 assert.deepEqual(restoreMeeting(draft,[projects[1]]).topics,{});
});
