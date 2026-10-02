export function safeNewsLink(value) {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : ''; }
  catch { return ''; }
}
export function newsTime(item) {
  const raw = item.publishedAt || item.discoveredAt;
  if (!raw || Number.isNaN(Date.parse(raw))) return '';
  const time = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(raw));
  return (item.publishedAt ? '' : '收录于 ') + time;
}
export function mergeNews(current, next) {
  const byId = new Map(current.map(item => [item.id, item]));
  for (const item of next) byId.set(item.id, item);
  return [...byId.values()];
}
