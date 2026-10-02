// Business dates come only from the saved event, never filenames or archive time.
export function eventDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return '';
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value ? value : '';
}

export function requirementTimeline(value, includeMilestones = true) {
  const events = ['evolution', ...(includeMilestones ? ['lifecycle'] : [])].flatMap(kind =>
    (value?.[kind] || []).map((item, index) => ({item, kind, date: eventDate(item.date), key: `${kind}:${index}`})));
  const groups = new Map();
  for (const event of events) {
    if (!groups.has(event.date)) groups.set(event.date, []);
    groups.get(event.date).push(event);
  }
  return [...groups].sort(([a], [b]) => (a || '9999').localeCompare(b || '9999'))
    .map(([date, events]) => ({date, events}));
}
