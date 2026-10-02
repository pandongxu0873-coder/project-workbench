// Keep a refreshing calendar separate from a failed read. A partial calendar
// receipt can still carry local deadlines and the last fetched calendar items.
export function calendarRead(result) {
  const payload=result.status==='fulfilled'?result.value:result.reason?.payload;
  if(!payload||!Array.isArray(payload.items)||!['ready','refreshing','stale','error','unread'].includes(payload.read_state)) {
    return {calendar:result.status==='fulfilled'?(payload||{items:[]}):{items:[]},pending:false,error:result.status==='rejected'||Boolean(payload?.error)};
  }
  const pending=payload.refreshing===true||['refreshing','unread'].includes(payload.read_state);
  const error=Boolean(payload.refresh_error)||payload.read_state==='error'||(!pending&&payload.ok===false);
  return {calendar:payload,pending,error};
}
