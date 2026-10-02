import {hasCurrentJudgement} from './salesPursuitModel.js';

export const meetingKey=id=>`customer-meeting:v1:${id}`;
export function restoreMeeting(raw,projects) {
  const value=raw&&typeof raw==='object'?raw:{};
  const allowed=new Set(projects.map(p=>p.id));
  return {contact:typeof value.contact==='string'?value.contact:'',goal:typeof value.goal==='string'?value.goal:'',ids:[...new Set(Array.isArray(value.ids)?value.ids:[])].filter(id=>allowed.has(id)),notes:Object.fromEntries(Object.entries(value.notes||{}).filter(([id,text])=>allowed.has(id)&&typeof text==='string')),topics:Object.fromEntries(Object.entries(value.topics||{}).filter(([id,rows])=>allowed.has(id)&&Array.isArray(rows)).map(([id,rows])=>[id,rows.filter(r=>r&&typeof r.title==='string'&&typeof r.detail==='string')]))};
}
export function addMeetingTopic(draft,projectId,topic) {
  const rows=draft.topics?.[projectId]||[];
  return {...draft,ids:draft.ids.includes(projectId)?draft.ids:[...draft.ids,projectId],topics:{...draft.topics,[projectId]:[...rows.filter(r=>r.key!==topic.key),topic]}};
}
export function meetingTopic(project,note='') {
  const ready=hasCurrentJudgement(project),execution=project.execution||{};
  const restricted=execution.relationship==='no_contact';
  return {id:project.id,title:project.title,ready,restricted,
    basis:project.latest_evidence_date||'日期待核',
    situation:project.brief?.situation||'尚未形成综合理解，请先核对项目事实。',
    recorded:execution.feedback||execution.quick_action||execution.next_step||'尚无已收录的本轮执行结果。',
    decision:note||(ready?project.pursuit?.conversation?.goal||project.pursuit?.conversation?.success_signal||project.brief?.next_action:'')||'待结合新材料确定，不沿用旧AI建议。',
    condition:ready?project.pursuit?.conversation?.success_signal||'继续条件待核实':'AI尚未综合本轮新材料；已有约定继续保留，是否调整投入需结合实际事实核对。'};
}
export function meetingText(customer,draft,projects) {
  const selected=draft.ids.map(id=>projects.find(p=>p.id===id)).filter(Boolean).map(p=>meetingTopic(p,draft.notes[p.id]));
  if(!selected.length||!draft.contact.trim()||!draft.goal.trim())return '';
  if(selected.some(p=>p.restricted))return '';
  return [`${customer}｜本次沟通准备（本机草稿，未发送）`,`沟通对象：${draft.contact}`,`本次目标：${draft.goal}`,'议题顺序由你选择；不代表对方同意参会、范围或投入。',...selected.map((p,i)=>`\n${i+1}. ${p.title}\n依据日期：${p.basis}${p.ready?'':'；上次理解，尚待更新'}\n${p.ready?'当前情况':'上次理解'}：${p.situation}\n已记录结果：${p.recorded}\n本次议题：${p.decision}\n继续条件：${p.condition}${(draft.topics?.[p.id]||[]).map(t=>`\n带入的具体问题：${t.title}\n选取时的理解（${t.createdAt||'日期待核'}${t.stale?'，当时已待更新':''}；须结合当前事实复核）：\n${t.detail}\n${(t.evidence||[]).map(e=>`依据：${e.path}\n原文：${e.quote}`).join('\n')}`).join('\n')}`),'\n沟通后将各项结果分别记回对应项目；未讨论的事项不视为确认或取消。'].join('\n');
}

export function decisionMeetingTopic(kind,item) {
  const fields=kind==='scope'?[['对应约定或报价','baseline'],['现在提出的变化','change'],['确认边界','confirmation'],['影响','impact'],['建议处理','recommendation']]:[['判断','judgement'],['触发事实','trigger'],['建议介入','action'],['继续条件','success_signal'],['不处理的影响','if_ignored'],['建议参与','owner']];
  const title=kind==='scope'?item.name:item.title;
  return {key:`${kind}:${title}`,title,detail:fields.filter(([,key])=>item[key]).map(([label,key])=>`${label}：${item[key]}`).join('\n'),evidence:(item.evidence||[]).map(e=>({...e}))};
}
