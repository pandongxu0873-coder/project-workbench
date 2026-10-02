import React,{useState} from 'react';
import {splitScheduleArchive} from './scheduleArchive.js';
import {CalendarBlank,ArrowUpRight} from '@phosphor-icons/react';
import {timelineModel,calendarBackgroundModel,parseBusinessDate,shanghaiDay} from './dashboardModel.js';
export default function HomeWeek({overview,error,navigate}){
 const today=shanghaiDay(), midnight=parseBusinessDate(today), weekday=new Date(midnight+8*3600000).getUTCDay(), monday=midnight-((weekday+6)%7)*86400000;
 const schedules=splitScheduleArchive(overview?.risk_todos||[]).current;
 const week=timelineModel(schedules,7,new Date(monday)),current=timelineModel(schedules),calendar=overview?.calendar_status;
 const background=calendarBackgroundModel(calendar?.background_items,7,new Date(monday));
 const [selected,setSelected]=useState(null);
 const warning=error||(!overview?'正在读取日程…':!calendar||calendar.read_state==='unread'?'飞书日程尚未读取':calendar.ok===false||calendar.refresh_error?'飞书未能更新，保留已读记录':calendar.stale?'飞书日程待更新':calendar.refreshing?'飞书日程更新中':'');
 const matches=(n,day)=>{const from=n.from??parseBusinessDate(n.deadline),until=n.isInterval?n.until:parseBusinessDate(n.end_time)||from;const at=parseBusinessDate(day);return from<at+86400000&&until>=at};
 const overdueKeys=new Set(current.overdue.map(n=>n.key));
 const rows=selected?week.pending.filter(n=>matches(n,selected)):week.pending;
 const back=selected?background.filter(n=>matches(n,selected)):background;
 return <section className="home-week"><header><h2>本周日程 <small>{week.ticks[0].date.slice(5).replace('-','.')} — {week.ticks[6].date.slice(5).replace('-','.')}</small></h2><button onClick={()=>navigate('reminders')}>查看日程<ArrowUpRight size={14}/></button></header><div className="home-week-days">{week.ticks.map((t,i)=><button key={t.date} aria-label={`${t.date} 日程`} aria-pressed={selected===t.date} className={t.date===today?'is-today':''} onClick={()=>setSelected(selected===t.date?null:t.date)}><span>{'一二三四五六日'[i]}</span><b>{Number(t.date.slice(-2))}</b><small>{week.pending.filter(n=>matches(n,t.date)).length?`${week.pending.filter(n=>matches(n,t.date)).length} 节点`:background.some(n=>matches(n,t.date))?'日历占用':' '}</small></button>)}</div>{warning&&<p className="home-warning" role="status">{warning}</p>}
 <div className="home-week-items">{rows.length?rows.slice(0,3).map(n=><button key={n.key} onClick={()=>n.project_id?navigate('projects',{projectId:n.project_id,projectTitle:n.project_title,customer:n.customer}):navigate('reminders',{focusAction:n})}><time>{n.deadline.slice(5,10)}</time><b>{n.customer}</b><span>{n.label}</span>{overdueKeys.has(n.key)&&<em>过去节点 · 待核对</em>}<ArrowUpRight size={13}/></button>):<p className="home-empty"><CalendarBlank size={22}/>{warning?'安排尚待核对':selected?'当日暂无已关联客户节点':'本周暂无已关联客户节点'}</p>}</div>{back.length>0&&<details className="home-calendar-background"><summary>日历占用 {back.length}<small>不计入客户待办</small></summary>{back.map(n=><button key={n.id} onClick={()=>navigate('reminders')}><time>{n.deadline?.slice(5,16).replace('T',' ')}</time>{n.title}</button>)}</details>}
 {current.overdue.length>0&&<button className="home-past" onClick={()=>navigate('reminders')}>{current.overdue.length} 个过去节点待核对<ArrowUpRight size={13}/></button>}
 <details className="home-calendar-source"><summary>同步状态</summary><p>{calendar?.fetched_at?`飞书读取于 ${calendar.fetched_at.slice(0,16).replace('T',' ')}`:'飞书暂无成功读取记录'}{calendar?.window?.end?` · 覆盖至 ${calendar.window.end.slice(0,10)}`:''}</p></details></section>
}
