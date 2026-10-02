export const resetType = event => ({ direct_reset: '全员重置', reset_credit: '发重置卡' }[event.type] || '其他记录');
const stamp = value => Date.parse(value) || 0;
export function resetStatus(event, now = Date.now()) {
  if (event.status === 'confirmed') return event.confirmationBasis === 'receipt_review' ? '回执核验确认' : '已确认';
  if (event.status !== 'announced') return '状态待核验';
  if (event.schedule?.through && stamp(event.schedule.through) < now) return '原预告已过 · 尚无确认';
  return '预告 · 待确认';
}
export function resetOverview(events = [], now = Date.now()) {
  const confirmed = events.filter(e => e.status === 'confirmed').sort((a, b) => stamp(b.occurredOn || b.confirmedAt || b.createdAt) - stamp(a.occurredOn || a.confirmedAt || a.createdAt));
  return {
    direct: confirmed.find(e => e.type === 'direct_reset'),
    credit: confirmed.find(e => e.type === 'reset_credit'),
    upcoming: events.filter(e => e.status === 'announced' && stamp(e.schedule?.through) >= now).sort((a, b) => stamp(a.schedule.from) - stamp(b.schedule.from)),
  };
}

export function beijingDay(value) {
  if (!value || !Number.isFinite(Date.parse(value))) return '';
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(value));
}
export function shiftDay(day, offset) {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}
export function shiftMonth(month, offset) {
  const date = new Date(`${month}-01T12:00:00Z`);
  date.setUTCMonth(date.getUTCMonth() + offset);
  return date.toISOString().slice(0, 7);
}
export function eventDay(event) {
  return event.occurredOn || beijingDay(event.confirmedAt || (event.status === 'announced' && event.schedule?.from) || event.createdAt);
}
export function monthDays(month) {
  const first = `${month}-01`;
  const preceding = (new Date(`${first}T12:00:00Z`).getUTCDay() + 6) % 7;
  const length = (Date.parse(`${shiftMonth(month, 1)}-01T12:00:00Z`) - Date.parse(`${first}T12:00:00Z`)) / 86400000;
  return Array.from({ length: Math.ceil((preceding + length) / 7) * 7 }, (_, i) => shiftDay(first, i - preceding));
}
export const percentage = value => value > 0 && value < .01 ? '<1' : String(Math.round(value * 100));

// Reimplementation of the historical-interval method inspected on AIHOT's public page.
// Estimates are conditional on no reset since the last confirmation; never a promise.
export function resetForecast(events, asOf) {
  const now = Date.parse(asOf);
  if (!Number.isFinite(now)) return null;
  const unique = new Map();
  for (const event of events) {
    const at = Date.parse(event.confirmedAt);
    if (event.type !== 'direct_reset' || event.status !== 'confirmed' || !event.posts?.length || !Number.isFinite(at) || at > now) continue;
    unique.set(event.id, Math.min(unique.get(event.id) ?? Infinity, at));
  }
  const times = [...unique.values()].sort((a, b) => a - b);
  const intervals = times.slice(1).map((at, i) => (at - times[i]) / 86400000).filter(days => days > 0);
  if (intervals.length < 8) return null;
  const logs = intervals.map(Math.log);
  const mean = logs.reduce((a, b) => a + b, 0) / logs.length;
  const variance = logs.reduce((sum, value) => sum + (value - mean) ** 2, 0) / logs.length;
  if (variance < 1e-8) return null;
  const sigma = Math.sqrt(variance);
  function survival(days) {
    if (days <= 0) return 1;
    const z = (Math.log(days) - mean) / sigma;
    const a = Math.abs(z), t = 1 / (1 + .2316419 * a);
    const tail = Math.exp(-a * a / 2) / Math.sqrt(2 * Math.PI) * t * (.31938153 + t * (-.356563782 + t * (1.781477937 + t * (-1.821255978 + 1.330274429 * t))));
    return z < 0 ? 1 - tail : tail;
  }
  const last = times.at(-1), denominator = survival((now - last) / 86400000);
  if (denominator < 1e-6) return null;
  const clamp = value => Math.max(0, Math.min(1, value));
  const day = beijingDay(asOf);
  const probabilities = Array.from({ length: 3 }, (_, i) => {
    const date = shiftDay(day, i);
    const from = Math.max(now, Date.parse(`${date}T00:00:00+08:00`));
    const through = Date.parse(`${shiftDay(date, 1)}T00:00:00+08:00`);
    return { day: date, probability: clamp((survival((from - last) / 86400000) - survival((through - last) / 86400000)) / denominator) };
  });
  const end = Date.parse(`${shiftDay(day, 3)}T00:00:00+08:00`);
  return { asOf, sampleCount: times.length, probabilities, laterProbability: clamp(survival((end - last) / 86400000) / denominator) };
}
