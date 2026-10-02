export const STAGES = ['需求澄清','方案验证','商务推进','交付实施','待核实'];
export const ATTENTIONS = ['可推进','等反馈','需核实','暂缓'];
export const OVERVIEW_KEY='workbench-project-overview';
export function readOverviewPreference(storage) { try { const value=JSON.parse(storage.getItem(OVERVIEW_KEY));return value&&typeof value==='object'&&!Array.isArray(value)?value:{}; } catch { return {}; } }
export function recognizedCustomer(value) { return Boolean(value) && !/待核实|未关联|未知/.test(value); }
export function hasCurrentBrief(project) { return project.analysis_state==='ready' && !project.analysis_stale && Boolean(project.brief); }
export function stageDistribution(projects) {
  const current=projects.filter(p=>p.is_current);
  return {counts:Object.fromEntries(STAGES.map(stage=>[stage,current.filter(p=>hasCurrentBrief(p)&&p.brief.stage===stage).length])),pending:current.filter(p=>!hasCurrentBrief(p)).length,total:current.length};
}
export function shouldClearProject(options) { return Object.prototype.hasOwnProperty.call(options,'projectId'); }

export function scopeProjects(projects,{query='',customer=''}={}) { return projects.filter(p=>(!query.trim()||`${p.title} ${p.customer}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))&&(!customer||p.customer===customer)); }
export function orderOverviewProjects(projects,{query='',customer='',stage='全部',attention='全部'}={}) {
  if(query||customer||stage!=='全部'||attention!=='全部')return projects;
  const actionable=p=>hasCurrentBrief(p)&&p.brief.attention==='可推进';
  return [...projects.filter(actionable),...projects.filter(p=>!actionable(p))];
}
export function analysisAttemptKey(project) { return project.analysis_fingerprint ? `${project.id}:${project.analysis_fingerprint}` : ''; }

export function projectConnections(project,projects) {
  if(!project)return [];
  const references=p=>new Set((p.sources||[]).filter(s=>s.relation==='background_reference').map(s=>s.path));
  const linked=references(project);
  return projects.filter(p=>p.id!==project.id).flatMap(p=>{
    const same=recognizedCustomer(project.customer)&&p.customer===project.customer;
    const cited=Boolean(p.source_path&&linked.has(p.source_path))||Boolean(project.source_path&&references(p).has(project.source_path));
    return same||cited?[{id:p.id,title:p.title,relation:same?'同客户':'原文关联',is_current:p.is_current}]:[];
  });
}
