import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {transformWithOxc} from 'vite';
const root=fileURLToPath(new URL('..',import.meta.url)),require=createRequire(path.join(root,'package.json')),cache=new Map();
async function load(file){
 if(cache.has(file))return cache.get(file);
 let source=(await readFile(file,'utf8')).replace(/^import ['"][^'"]+\.css['"];?\s*$/gm,'');
 for(const match of [...source.matchAll(/from ['"]([^'"]+)['"]/g)]){
  const spec=match[1],target=spec.startsWith('.')?path.resolve(path.dirname(file),spec):require.resolve(spec);
  const url=target.endsWith('.jsx')?await load(target):pathToFileURL(target).href;
  source=source.replace(match[0],`from '${url}'`);
 }
 const {code}=await transformWithOxc(source,file,{jsx:{runtime:'classic'}});
 const url=`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`;cache.set(file,url);return url;
}
const {connectionStates,projectCommunicationRows}=await import(await load(path.join(root,'src/ProjectConnections.jsx')));
const {initialCommunicationCustomer,communicationGroupsForCustomer,mergedCommunicationGroups}=await import(await load(path.join(root,'src/CommunicationSync.jsx')));
const project={id:'project-A',customer:'星海汽车商城',title:'星海汽车一期'},other={id:'project-B',customer:'星海汽车／示例汽车集团',title:'星海汽车二期'};
const item=(id,kind='message',overrides={})=>({id,title:id,kind,business_date:'2026-09-20',summaries:['原文支持的内容'],sources:[{id:'source-'+id,readable:true}],communication:{type:'internal',our_message:true},...overrides});
const group=(project,items)=>({id:project.id,project_id:project.id,project_title:project.title,customer:project.customer,items});
const communications={connections:[{name:'企业邮箱',available:true}],digest:{date:'2026-09-20',groups:[group(other,[item('shared'),item('other-email','email')]),group(project,[item('shared'),item('direct')])]},history_digest:{groups:[group(project,[item('direct'),item('history')]),group({id:'unrelated',customer:'其他客户',title:'其他'},[item('unrelated-email','email')])]}};
const ready={project,crm:{configured:true,snapshot:{sync_status:'success'}},links:{project_id:project.id,matches:[{order:{bizCode:'ORDER-A'}}],sync_errors:{},issues:[]},communications,commercial:{draft:{revision:1},customer_email:{subject:'已保存主题'}}};
const card=(data,id)=>connectionStates(data).find(row=>row.id===id);

test('project ID is authoritative and customer-only records remain separately labelled',()=>{
 const rows=projectCommunicationRows(communications,project);
 assert.equal(rows.length,4);assert.equal(rows.filter(row=>row.match_scope==='project').length,3);
 assert.equal(rows.find(row=>row.id==='other-email').match_label,'归档关联 · 同客户其他项目');
 assert.ok(!rows.some(row=>row.id==='unrelated-email'));
 assert.equal(rows.find(row=>row.id==='shared').group_project_id,project.id);
});
test('source, actor and date survive scoped projection without customer-confirmation promotion',()=>{
 const row=projectCommunicationRows(communications,project).find(row=>row.id==='direct');
 assert.equal(row.communication.type,'internal');assert.equal(row.communication.our_message,true);assert.equal(row.sources[0].id,'source-direct');assert.equal(row.business_date,'2026-09-20');
});
test('unconfirmed customer labels never join different projects as a customer',()=>{
 const rows=projectCommunicationRows({digest:{groups:[group({id:'B',customer:'客户待核实'},[item('wrong')])] }},{id:'A',customer:'客户待核实'});
 assert.deepEqual(rows,[]);
});
test('matching never uses a near-equal project title or substring customer name',()=>{
 assert.deepEqual(projectCommunicationRows({digest:{groups:[group({id:'B',title:'星海汽车一期',customer:'星海汽车商城候选'},[item('wrong')])] }},project),[]);
});
test('deduplication combines recent and history without modifying API objects',()=>{
 const before=JSON.stringify(communications);const merged=mergedCommunicationGroups(communications);
 assert.equal(merged.find(g=>g.project_id===project.id).items.length,3);assert.equal(JSON.stringify(communications),before);
});
test('global mailbox availability is not a project email match or source-count receipt',()=>{
 const data={...ready,communications:{connections:[{name:'企业邮箱',available:true}],receipt:{status:'completed',new:100},digest:{groups:[]},history_digest:{groups:[]}}};
 const mail=card(data,'mail');assert.equal(mail.known,false);assert.match(mail.mode,/邮箱可读取/);assert.match(mail.status,/暂无关联沟通/);assert.match(mail.detail,/未匹配邮件/);assert.ok(!mail.status.includes('100'));
});
test('existing internal messages do not become email when mailbox is connected',()=>{
 const mail=card({...ready,communications:{connections:[{name:'企业邮箱',available:true}],digest:{groups:[group(project,[item('internal')])]}}},'mail');
 assert.match(mail.status,/本项目 1 条/);assert.match(mail.detail,/未匹配邮件/);assert.match(mail.preview,/内部沟通/);assert.match(mail.preview,/原文支持的内容/);
});
test('project CRM resource errors override a global successful snapshot',()=>{
 const crm=card({...ready,links:{...ready.links,sync_errors:{contracts:'failed'}}},'crm');
 assert.equal(crm.known,false);assert.match(crm.status,/同步未完成/);assert.match(crm.detail,/旧对应/);
});
test('a response for another project cannot claim the current project is linked',()=>{
 const crm=card({...ready,links:{...ready.links,project_id:'wrong'}},'crm');
 assert.equal(crm.known,false);assert.match(crm.status,/暂不采用/);
});
test('project preparation follows the actual task rather than a zero-value quote template',()=>{
 const draft=card({...ready,analysisState:{state:'ready',stale:false,result:{analysis:{draft:'请核对复验结果。',story:{conversation:{goal:'确认门店筛选的复验安排'}}}}},commercial:{draft:{revision:0},customer_email:{subject:'零元报价确认'}}},'draft');
 assert.equal(draft.known,true);assert.equal(draft.title,'本轮沟通准备');assert.equal(draft.preview,'确认门店筛选的复验安排');assert.match(draft.mode,/未发送/);assert.ok(!draft.preview.includes('报价'));
});
test('preparation preserves stale and no-contact boundaries independently of quote status',()=>{
 const analysis={guard:'客户明确暂勿联系，仅内部准备',draft:'',story:{conversation:{goal:'保留内部安排'}}};
 const current={...ready,analysisState:{state:'ready',stale:false,result:{analysis}}};
 assert.equal(card(current,'draft').status,'仅内部准备');assert.match(card(current,'draft').preview,/暂勿联系/);
 const stale=card({...current,analysisState:{...current.analysisState,stale:true}},'draft');
 assert.equal(stale.known,false);assert.match(stale.status,/等待更新/);
});
test('explicit customer context overrides a previously remembered different customer',()=>{
 assert.equal(initialCommunicationCustomer({projectId:project.id,customer:'星海汽车商城'},'麦田食品'),'星海汽车／示例汽车集团');
 assert.equal(initialCommunicationCustomer({projectId:'unknown',customer:'客户待核实'},'麦田食品'),'本项目');
});
test('an absent contextual customer remains an empty result and never falls back to all',()=>{
 const groups=mergedCommunicationGroups(communications);
 assert.deepEqual(communicationGroupsForCustomer(groups,'麦田食品'),[]);
 assert.deepEqual(communicationGroupsForCustomer(groups,'本项目','missing'),[]);
 assert.equal(communicationGroupsForCustomer(groups,'星海汽车商城').length,2);
});


test('historical association and internal claims remain labelled in the direct card preview',()=>{
 const mail=card({...ready,communications:{digest:{groups:[]},history_digest:{groups:[group(project,[item('ambiguous-group','message',{historical:true,summaries:['内部表示催办，并无客户验收结果']})])]}}},'mail');
 assert.match(mail.status,/归档关联本项目/);assert.match(mail.preview,/历史归档 · 内部沟通/);assert.match(mail.preview,/并无客户验收结果/);
});
test('recent classified communication precedes historical association without merging its project scope',()=>{
 const rows=projectCommunicationRows({digest:{groups:[group(other,[item('recent')])]},history_digest:{groups:[group(project,[item('historical','message',{historical:true,business_date:'2026-09-21'})])]}},project);
 assert.equal(rows[0].id,'recent');assert.equal(rows[0].match_scope,'customer');assert.equal(rows[1].match_scope,'project');
 const preview=card({...ready,communications:{digest:{groups:[group(other,[item('recent')])]},history_digest:{groups:[]}}},'mail').preview;assert.match(preview,/同客户背景/);
});
test('failed CRM and communication reads cannot display cached success as a current green result',()=>{
 const data={...ready,errors:{crm:'offline',communications:'offline'}};
 for(const id of ['crm','mail']){const value=card(data,id);assert.equal(value.known,false);assert.match(value.status,/读取未完成/);assert.match(value.preview,/读取失败/);}
});
