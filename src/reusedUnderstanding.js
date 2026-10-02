import savedCanvases from './reusedFour.json' with { type: 'json' };
// Reuse only the exact saved analysis this supplement was prepared against.
// Fresh model output takes precedence; an older supplement cannot cross versions.
export function reusedUnderstanding(result) {
  const saved = result?.reused_understanding || savedCanvases[result?.analysis_id];
  if (result?.analysis?.understanding || !saved?.value) return null;
  return saved.analysis_id === result.analysis_id && saved.created_at === result.created_at
    ? saved : null;
}
