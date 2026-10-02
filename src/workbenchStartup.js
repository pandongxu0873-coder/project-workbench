// These views own their reads; they must never wait for the legacy aggregate dashboard.
export const INDEPENDENT_VIEWS = new Set(['agent', 'projects', 'communications', 'knowledge', 'today', 'discover']);
export const needsWorkbenchData = view => !INDEPENDENT_VIEWS.has(view);
export const EMPTY_WORKBENCH_VALUE = Object.freeze({});
export const PROJECT_SNAPSHOT_KEY = 'workbench-project-list-snapshot-v1';
const MAX_AGE = 24 * 60 * 60 * 1000;
const DISPLAY_FIELDS = ['id','title','customer','latest_evidence_date','is_current','analysis_state','analysis_stale','brief','execution','execution_state'];
export function readProjectSnapshot(storage, now = Date.now()) {
  try {
    const raw = storage.getItem(PROJECT_SNAPSHOT_KEY);
    if (!raw || raw.length > 1500000) return null;
    const value = JSON.parse(raw);
    if (value.version !== 1 || !Number.isFinite(value.savedAt) || now < value.savedAt || now - value.savedAt > MAX_AGE || !Array.isArray(value.projects) || value.projects.length > 1000) return null;
    if (!value.projects.every(p => p && typeof p.id === 'string' && typeof p.title === 'string')) return null;
    return value;
  } catch { return null; }
}
export function writeProjectSnapshot(storage, projects, now = Date.now()) {
  try {
    // Only list presentation: no sources, drafts, revisions or executable action records.
    const value = {version:1,savedAt:now,projects:projects.map(p=>({
      ...Object.fromEntries(DISPLAY_FIELDS.filter(k=>k in p).map(k=>[k,p[k]])),
      ...(p.archive?{archive:{archived:p.archive.archived}}:{}),
      ...(p.pursuit?.conversation?.success_signal ? {pursuit:{conversation:{success_signal:p.pursuit.conversation.success_signal}}} : {}),
    }))};
    const raw=JSON.stringify(value);
    if(raw.length<=1500000) storage.setItem(PROJECT_SNAPSHOT_KEY,raw);
  } catch { /* A full or disabled browser cache must not block live data. */ }
}
