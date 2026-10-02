const DAY = 86400000;
export const shanghaiDay = (date = new Date()) => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
export function parseBusinessDate(value, endOfDay = false) {
  if (!value || typeof value !== 'string') return NaN;
  const date = /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T${endOfDay?'23:59:59':'00:00:00'}+08:00` : /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$/.test(value) ? `${value.replace(' ','T')}+08:00` : value;
  return Date.parse(date);
}
const closed = new Set(['closed','done','cancelled','canceled','本轮完成','暂停跟进','已处理','已闭环','已完成','已取消','已回填','已忽略']);
export function timelineModel(items = [], days = 14, now = new Date()) {
  const start = parseBusinessDate(shanghaiDay(now)), end = start + days * DAY;
  const seen = new Set(), pending = [], overdue = [], undated = [];
  for (const item of items) {
    if (!item.customer || ['待匹配日程','客户关联待核实','待匹配事项'].includes(item.customer) || closed.has(item.status) || item.sales_suppressed || item.ignored || item.handled || item.project_archive?.archived || item.source_type === 'transcript_intake') continue;
    if (item.source_type === 'feishu_calendar' && !item.matched_customer && !item.project_id) continue;
    const key = item.workflow_key || item.id || JSON.stringify([item.project_id,item.customer,item.deadline,item.title]);
    if (seen.has(key)) continue;
    seen.add(key);
    const from = parseBusinessDate(item.deadline || item.due), until = parseBusinessDate(item.end_time);
    const isInterval = item.source_type === 'feishu_calendar' && until > from;
    const effectiveEnd = isInterval ? until : parseBusinessDate(item.deadline || item.due, true);
    const row = {...item, deadline:item.deadline || item.due, key, from, until, isInterval, label:(item.source_type==='feishu_calendar'?item.title:item.next_step) || item.title || item.action || '跟进安排'};
    if (!Number.isFinite(from)) undated.push(row);
    else if (effectiveEnd < now.getTime()) overdue.push(row);
    else if (from < end && effectiveEnd >= start) pending.push(row);
  }
  pending.sort((a,b)=>a.from-b.from); overdue.sort((a,b)=>b.from-a.from);
  return {start,end,days,pending,overdue,undated,ticks:Array.from({length:days},(_,i)=>({date:shanghaiDay(new Date(start+i*DAY)),at:start+i*DAY}))};
}
export function periodDate(period, year, part) {
  const month = period === 'YEAR' ? 1 : period === 'QUARTER' ? (Number(part)-1)*3+1 : Number(part);
  return `${year}-${String(month).padStart(2,'0')}-01`;
}
export function periodLabel(period, date) {
  const [year,month] = date.split('-').map(Number);
  return period === 'YEAR' ? `${year} 年` : period === 'QUARTER' ? `${year} 年 · 第 ${Math.ceil(month/3)} 季度` : `${year} 年 ${month} 月`;
}

// Calendar occupancy is display-only; it never enters the sales queues.
export function calendarBackgroundModel(items = [], days = 14, now = new Date()) {
 const start = parseBusinessDate(shanghaiDay(now)), end = start + days * DAY;
 const seen = new Set();
 return items.filter(n => {
  const from = parseBusinessDate(n.deadline), until = parseBusinessDate(n.end_time) || from;
  const key = n.calendar?.event_id || n.id;
  if (!key || seen.has(key) || !n.calendar_background || n.matched_customer || n.project_id || ['cancelled','canceled'].includes(n.status) || !(from < end && until >= now.getTime())) return false;
  seen.add(key); return true;
 }).sort((a,b)=>parseBusinessDate(a.deadline)-parseBusinessDate(b.deadline));
}

// A customer name alone never dates a project; only explicit project links do.
export function projectsWithoutDates(projects=[],items=[],now=new Date()) {
 const schedule=timelineModel(items,3650,now);
 const datedIds=new Set([...schedule.pending,...schedule.overdue].map(n=>n.project_id).filter(Boolean));
 return projects.filter(p=>!p.archive?.archived&&!datedIds.has(p.id));
}
