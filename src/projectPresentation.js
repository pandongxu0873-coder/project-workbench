import {hasCurrentJudgement} from './salesPursuitModel.js';
export function blockerKind(text='') {
  return /资料|原文|原件|未收录|未读取|读取失败|证据不足|材料不足|来源缺失/.test(text)?'资料范围':'业务卡点';
}
export function isExecutionReceipt(text, record={}) {
  record=record||{};
  if(record.due&&typeof text==='string'&&text.endsWith(`；复盘 ${record.due}`))text=text.slice(0,-(`；复盘 ${record.due}`).length);
  const done=record.quick_action||record.action;
  return !!done && [done,`等待「${done}」的反馈`,`「${done}」已做，结果尚待现有资料核对`].includes(text) && (record.quick_outcome==='done'||record.status==='已发出等待反馈');
}
export function projectExecutionNote(project) {
  const record=project.execution||{};
  return record.quick_outcome==='done'||['done_waiting','new_evidence_review','waiting_feedback'].includes(project.execution_state)?'已做记录 · 结果待核对':'';
}
export function projectNext(project) {
  if(project.archive?.archived)return '已停止销售推进';
  const record=project.execution||{};
  if(record.relationship==='no_contact')return '遵守暂勿联系约定';
  if(record.status==='暂停跟进')return '按原安排暂停跟进';
  if(hasCurrentJudgement(project))return isExecutionReceipt(project.brief.next_action,record)?'暂无新的行动建议':project.brief.next_action||'尚无具体行动建议';
  if(record.next_step&&!isExecutionReceipt(record.next_step,record))return record.next_step;
  if(['done_waiting','new_evidence_review','waiting_feedback'].includes(project.execution_state))return '新建议待更新 · 查看项目责任';
  return '最新判断待更新；已有进展可在项目内查看';
}

// One display classification shared by the table and its filter. Unknown evidence
// is not a request for the user to audit the project.
export function projectNeed(project,commitments=[]) {
  const record=project.execution||{},brief=project.brief||{};
  if(project.archive?.archived)return {kind:'quiet',label:'已归档',actionable:false};
  if(record.relationship==='no_contact')return {kind:'quiet',label:'暂勿联系',actionable:false};
  if(record.status==='暂停跟进'||brief.attention==='暂缓')return {kind:'quiet',label:'暂停推进',actionable:false};
  if(commitments.length)return {kind:'commitment',label:'已有约定待承接',actionable:true,commitment:commitments[0]};
  if(!hasCurrentJudgement(project))return {kind:'updating',label:project.analysis_state==='error'?'判断更新未完成':'判断待更新',actionable:false};
  if(isExecutionReceipt(brief.next_action,record))return {kind:'waiting',label:'等待反馈',actionable:false};
  // The project may wait on one thread while another has an explicit action.
  if(brief.next_action&&project.execution_state==='actionable')return {kind:'action',label:'需要执行',actionable:true};
  if(brief.attention==='等反馈')return {kind:'waiting',label:'等待反馈',actionable:false};
  if(brief.next_action)return {kind:'action',label:'需要执行',actionable:true};
  return {kind:'unknown',label:'尚无具体建议',actionable:false};
}
