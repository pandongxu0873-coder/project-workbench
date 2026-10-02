export const SYNC_STEPS = ['读取来源', 'AI归类', '保存到本机', '更新工作台'];
export function syncStep(phase) {
  return ({ checking: 0, local: 0, feishu: 0, email: 0, analyzing: 1, archiving: 2, refreshing: 3, done: 4 })[phase] ?? 0;
}
export function syncSummary(data = {}) {
  const job = data.job || {}, receipt = data.receipt || {};
  const pending = Object.values(receipt.unresolved || {}).reduce((a, b) => a + Number(b || 0), 0) + (receipt.refresh_pending || []).length;
  if (job.running) return { title: job.phase_label || '正在整理', pending, tone: 'running' };
  if (job.state === 'interrupted') return { title: '上次整理中断，可继续', pending, tone: 'warning' };
  if (job.state === 'failed' || receipt.status === 'failed') return { title: '本轮未完成，已保留进度', pending, tone: 'warning' };
  if (receipt.status === 'checked') return { title: '来源检查完成', pending, tone: 'done' };
  if (!receipt.run_id) return { title: '准备好整理近期沟通', pending, tone: 'idle' };
  if (data.analysis_refresh?.active && !Object.values(receipt.unresolved || {}).some(Number) && !receipt.gaps?.length) return { title: '材料已归档，正在更新客户判断', detail: `${data.analysis_refresh.pending} 个项目正在自动更新，不需要重复同步。`, pending, tone: 'running', analysisOnly: true };
  if (pending) {
    const u = receipt.unresolved || {};
    const detail = [[u.extraction_pending, '份材料提取未完成'], [u.ready_for_review, '份材料分析未完成'], [u.needs_review, '份材料归属需核对'], [(receipt.refresh_pending || []).length, '个项目摘要未更新']].filter(([n]) => n > 0).map(([n, label]) => `${n} ${label}`).join(' · ');
    return { title: '同步未完成，原件已保留', detail, pending, tone: 'warning' };
  }
  return { title: receipt.gaps?.length ? '可读取内容已整理，仍有来源缺口' : '本轮整理完成', pending, tone: receipt.gaps?.length ? 'warning' : 'done' };
}
