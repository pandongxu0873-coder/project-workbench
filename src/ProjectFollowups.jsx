import React, { useCallback, useEffect, useRef, useState } from 'react';
import { splitCurrentActions } from './freshness.js';
import { todayFocus,currentFocusItems } from './projectFocus.js';
import { mergeCommitments } from './salesPursuitModel.js';
import { api } from './api.js';
import { calendarRead } from './calendarRead.js';
import { installLiveRefresh } from './liveRefresh.js';
import './project-followups.css';

export function ProjectFollowups({ onFocusItems,navigate, refreshKey, all = false, projectId = "", legacyOnly = false }) {
  const [data, setData] = useState(null), [error, setError] = useState('');
  const version = useRef(0);
  const read = useCallback(async () => {
    const request = ++version.current;
    try { const [roundResult,calendarResult] = await Promise.allSettled([api.get('/api/project-workspace/followups'),api.get('/api/calendar/events')]); if(roundResult.status==='rejected')throw roundResult.reason; const rounds=roundResult.value,calendarState=calendarRead(calendarResult); const next={...rounds,items:mergeCommitments(rounds,calendarState.calendar),calendarError:calendarState.error,calendarPending:calendarState.pending}; if (request === version.current) { setData(next); setError(''); } }
    catch (e) { if (request === version.current) setError(e.message); }
  }, []);
  useEffect(() => { read(); return () => { version.current++; }; }, [read, refreshKey]);
  useEffect(() => installLiveRefresh(read), [read]);
  useEffect(()=>{if(!data?.calendarPending)return;const timer=setTimeout(read,10000);return()=>clearTimeout(timer);},[data,read]);
  const scoped = (data?.items || []).filter(item => (all || !item.sales_suppressed) && (!projectId || item.project_id === projectId) && (!legacyOnly || item.source_type !== 'project_round'));
  const focus = todayFocus(scoped);
  useEffect(()=>{if(onFocusItems&&data)onFocusItems(currentFocusItems((data.items||[]).filter(x=>!x.sales_suppressed)));},[data,onFocusItems]);
  const items = all ? splitCurrentActions(scoped).current : focus.items;
  if (all && !items.length && !error && !data?.errors?.length && !data?.calendarError && !data?.calendarPending) return null;
  if(!all&&data&&!items.length&&!error&&!data.errors?.length&&!data.calendarError&&!data.calendarPending)return <section className="project-followups" aria-label="已约事项与待承接反馈"><div className="project-followups-heading"><h2>已约事项</h2><span>今天暂无到期约定或待承接反馈</span><button className="plain-action" onClick={()=>navigate('reminders')}>查看日程 →</button></div></section>;
  return <section className="project-followups" aria-label={all ? '已安排的项目跟进' : '已约事项与待承接反馈' }>
    <div className="project-followups-heading"><h2>{all ? '项目跟进与日期' : '已约事项与待承接反馈' } <small>{all ? items.length : `按已有记录 · ${items.length} 项`}</small></h2>{!all && focus.total > 3 && <button className="plain-action" onClick={() => navigate('reminders')}>查看全部 {focus.total} 项跟进 →</button>}</div>
    {items.map(item => <button className="project-followup-row" key={item.id} onClick={() => item.project_id ? navigate('projects', { projectId: item.project_id, projectTitle: item.project_title || item.title, customer: item.customer }) : navigate('reminders', { focusAction: item })}>
      <strong>{item.customer&&<small>{item.customer} · </small>}{item.archive_label&&<small>{item.archive_label} · </small>}{item.title}</strong><span>{(item.due || item.deadline) ? `${item.due || item.deadline}${item.schedule_bucket === 'overdue' ? ' · 已到期' : ''}` : '尚无约定日期'} · {item.status}{!all&&<b className="followup-reason">{item.focus_reason}</b>}</span><span>{item.status === '已收到反馈' ? item.next_step || item.action : item.action || item.next_step}</span><span aria-hidden="true">→</span>
    </button>)}
    {!all&&!items.length&&!error&&<p role="status">{data?(data.calendarPending?'日程正在后台更新；已有跟进记录保留，完成后自动核对。':data.calendarError?'已读取的项目记录中暂无到期约定或待承接反馈；日程尚未完整核对。':'今天没有已记录的到期约定或待承接反馈。'):'正在核对约定和反馈…'}</p>}
    {all&&data?.calendarPending&&<p role="status">日程正在后台更新，完成后自动核对。</p>}
    {data?.calendarError&&<p role="alert">部分日程暂未读取，已有跟进记录保留。<button onClick={read}>重新读取日程</button><button onClick={()=>navigate('reminders')}>查看提醒与日程</button></p>}
    {error && <p role="alert">跟进列表暂未更新：{error}<button onClick={read}>重试</button></p>}
    {data?.errors?.map(item => <p role="alert" key={item.project_id}>{item.title}：{item.message}</p>)}
  </section>;
}
