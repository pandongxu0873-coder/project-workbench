export function signalProjectContext(item,project) {
  if(!project?.id||!item?.id||!(item.related_projects||[]).some(p=>p.id===project.id))return null;
  return {projectId:project.id,signalId:item.id,customer:item.customer||'',title:item.title||'',
    publishedAt:item.published_at||'',source:item.source||'',sourceUrl:item.source_url||'',
    judgment:item.impact_judgment||'',verification:item.recommended_action||''};
}
export function contextForProject(context,id){return context?.projectId===id&&context?.signalId?context:null;}
export function signalVerificationNote(context){
  return ['公开信号待核实（不是客户确认，也不自动改变原范围）：',context.title,
    `来源：${context.source||'待核实'}；发布日期：${context.publishedAt||'待核实'}`,
    context.sourceUrl?`来源链接：${context.sourceUrl}`:'',
    context.judgment?`AI影响判断：${context.judgment}`:'',
    `本次希望核实：${context.verification||'该变化是否影响本项目，尚待客户或项目事实验证'}`].filter(Boolean).join('\n');
}
