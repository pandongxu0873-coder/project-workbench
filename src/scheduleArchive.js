// Archive is a reversible time-based view of original records, never completion.
const DAY = 86400000;
export const SCHEDULE_ARCHIVE_DAYS = 15;
export function scheduleTime(value) {
  if (typeof value !== 'string' || !value.trim()) return NaN;
  let text = value.trim().replace(' ', 'T');
  const day = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:T|$)/);
  if (!day) return NaN;
  const check = new Date(Date.UTC(Number(day[1]), Number(day[2]) - 1, Number(day[3])));
  if (check.toISOString().slice(0,10) !== day[0].slice(0,10)) return NaN;
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) text += 'T23:59:59.999+08:00';
  else if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(text)) text += '+08:00';
  return Date.parse(text);
}
export function isScheduleAutoArchived(item, now = new Date()) {
  // Pending dates/failed reads are not dates. Preserve ambiguous records for review.
  const start = scheduleTime(item.deadline || item.due || item.review_at || '');
  const end = scheduleTime(item.end_time || '');
  const deadline = Number.isFinite(start) && Number.isFinite(end) && end > start ? end : start;
  return Number.isFinite(deadline) && now.getTime() - deadline > SCHEDULE_ARCHIVE_DAYS * DAY;
}
export function splitScheduleArchive(items = [], now = new Date()) {
  const current = [], archived = [];
  for (const item of items) (isScheduleAutoArchived(item, now) ? archived : current).push(item);
  return { current, archived };
}
export function splitReceiptArchive(items = [], now = new Date()) {
  const current = [], archived = [];
  for (const item of items) {
    const at = scheduleTime(item.submitted_at || '');
    (Number.isFinite(at) && now.getTime() - at > SCHEDULE_ARCHIVE_DAYS * DAY ? archived : current).push(item);
  }
  return { current, archived };
}
