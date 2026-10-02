export function todayKey(now = new Date()) { return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`; }
export function cutoffKey(now = new Date(), days=30) { const d=new Date(now); d.setDate(d.getDate()-days); return todayKey(d); }
export function splitCurrentActions(items=[], now = new Date()) {
  const today=todayKey(now), cutoff=cutoffKey(now);
  const current=[], history=[];
  for(const item of items) {
    const deadline=String(item.deadline || item.review_at || '').slice(0,10);
    const valid=/^\d{4}-\d{2}-\d{2}$/.test(deadline);
    const future=valid && deadline>=today;
    const stale=valid && deadline<cutoff;
    const needsReview=item.message_delivery?.needs_review===true;
    (!future && (stale || needsReview) ? history : current).push(item);
  }
  return {current,history};
}
