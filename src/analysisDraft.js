export function analysisDraftIsCurrent(expected, current) {
  const result = current?.result;
  return Boolean(expected?.project_id && expected.analysis_id && expected.fingerprint && expected.analysis?.draft
    && current?.state === 'ready' && current.stale === false
    && current.project_id === expected.project_id && result?.project_id === expected.project_id
    && result.analysis_id === expected.analysis_id
    && current.fingerprint === expected.fingerprint && result.fingerprint === expected.fingerprint
    && result.analysis?.draft === expected.analysis.draft);
}
