export function hasCurrentJudgement(project) {
  return project.analysis_state === 'ready' && !project.analysis_stale && !!project.brief;
}
export function pursuitBucket(project) {
  const execution = project.execution || {};
  if (execution.relationship === 'no_contact') return 'quiet';
  if (execution.status === '暂停跟进') return 'nurture';
  if (!project.is_current) return 'history';
  if (['done_waiting','new_evidence_review'].includes(project.execution_state) || (!project.execution_state && execution.quick_outcome === 'done')) return 'waiting';
  if (execution.status === '已发出等待反馈') return 'waiting';
  if (!project.brief) return 'updating';
  // The last known working category remains a navigation aid during refresh.
  // It does not authorize presenting or executing the previous AI advice.
  if (project.brief.attention === '等反馈') return 'waiting';
  if (project.brief.attention === '暂缓') return 'nurture';
  if (project.brief.stage === '交付实施') return 'delivery';
  return 'advance';
}
export function groupPursuits(projects) {
  const groups = Object.fromEntries(['advance','delivery','waiting','nurture','quiet','history','updating'].map(k=>[k,[]]));
  for (const project of projects) if(!project.archive?.archived) groups[pursuitBucket(project)].push(project);
  return groups;
}
export function todaysCommitments(items, today) {
  return items.filter(item => String(item.deadline || item.due || '').slice(0,10) === today && item.action && !['暂停跟进','本轮完成','已处理','已闭环'].includes(item.status));
}

export function mergeCommitments(rounds, calendar) {
  const claimed = rounds.claimed_actions || {};
  return [...new Map([...(rounds.items || []), ...(calendar.items || []).filter(item => !claimed[item.id] && (item.source_type !== 'feishu_calendar' || item.matched_customer || (item.customer && item.customer !== '待匹配日程')))].map(item => [item.id,item])).values()];
}
