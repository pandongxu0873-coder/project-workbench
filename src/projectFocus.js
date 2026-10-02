import { splitCurrentActions, todayKey, cutoffKey } from './freshness.js';

const terminal = new Set(['已完成','本轮完成','暂停跟进','已取消','已关闭','已处理','已闭环']);
const validDay = value => {
 const text=String(value||''), day=text.slice(0,10), parsed=new Date(`${day}T00:00:00Z`);
 return /^\d{4}-\d{2}-\d{2}(?:T|$)/.test(text)&&Number.isFinite(Date.parse(text))&&Number.isFinite(parsed.getTime())&&parsed.toISOString().slice(0,10)===day ? day : '';
};
// Both entry points read the same existing records; no inferred task or deadline.
export function currentFocusItems(items, now=new Date()) {
 const today=todayKey(now), cutoff=cutoffKey(now);
 const normalized=items.map(item=>({...item,deadline:item.deadline||item.due||''}));
 const current=new Set(splitCurrentActions(normalized,now).current);
 return normalized
  .filter(item=>!terminal.has(item.status)&&item.relationship!=='no_contact')
  .flatMap(item=>{
   const day=validDay(item.deadline), received=validDay(item.saved_at);
   const hasFeedback=item.status==='已收到反馈'&&Boolean(item.feedback?.trim())&&received&&received>=cutoff&&received<=today;
   if(day&&day<=today&&current.has(item))return [{...item,focus_kind:'commitment',focus_reason:day<today?'约定日期已到，核对结果':'今天已有约定'}];
   // A future agreed follow-up remains future, even if feedback was received.
   if((!item.deadline||(day&&day<=today))&&hasFeedback)return [{...item,focus_kind:'feedback',focus_reason:'已收到反馈，待承接'}];
   return [];
  }).sort((a,b)=>(a.focus_kind==='commitment'?0:1)-(b.focus_kind==='commitment'?0:1)||Date.parse(a.focus_kind==='commitment'?a.deadline:a.saved_at)-Date.parse(b.focus_kind==='commitment'?b.deadline:b.saved_at)||String(a.id).localeCompare(String(b.id)));
}
export function todayFocus(items, now=new Date()) {
 const current=currentFocusItems(items,now);
 return {items:current.slice(0,3),total:current.length};
}
