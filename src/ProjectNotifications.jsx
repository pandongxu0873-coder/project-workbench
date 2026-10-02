import React,{useCallback,useEffect,useId,useRef,useState} from 'react';
import {Bell,X} from 'lucide-react';
import {api} from './api.js';
import './project-notifications.css';
const dateLabel=value=>value?new Date(value).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'';
export function NotificationChanges({item,onSource}){
  return <section className="notification-context" aria-label="本次项目变化"><strong>本次变化 · {dateLabel(item.at)}</strong><ul>{item.changes.map((c,i)=><li key={`${c.kind}:${c.path||i}`}><span>{c.label}{c.title?`：${c.title}`:''}</span>{c.path&&c.readable!==false&&onSource&&<button className="plain-action" onClick={()=>onSource(c)}>查看原文</button>}{c.path&&c.readable===false&&<small> · 附件路径：{c.path}（请在资料中心查看原件）</small>}</li>)}</ul><small>提醒来自本机已读取的变化；资料内容与项目判断请核对原始依据。</small></section>;
}
export default function ProjectNotifications({onOpen,refreshKey}){
  const panelId=useId();
  const [feed,setFeed]=useState(null),[error,setError]=useState(''),[open,setOpen]=useState(false),[busy,setBusy]=useState(false);
  const root=useRef(null),trigger=useRef(null),generation=useRef(0),mounted=useRef(true);
  const refresh=useCallback(async()=>{
    const token=++generation.current;
    try{const result=await api.get('/api/project-notifications');if(mounted.current&&token===generation.current){setFeed(result);setError('');}}
    catch(e){if(mounted.current&&token===generation.current)setError(e.message);}
  },[]);
  useEffect(()=>{mounted.current=true;refresh();const update=()=>{if(!document.hidden)refresh();};
    const timer=setInterval(update,60000);document.addEventListener('visibilitychange',update);window.addEventListener('workbench-refresh',update);window.addEventListener('project-data-refreshed',update);window.addEventListener('project-notifications-read',update);
    return()=>{mounted.current=false;clearInterval(timer);document.removeEventListener('visibilitychange',update);window.removeEventListener('workbench-refresh',update);window.removeEventListener('project-data-refreshed',update);window.removeEventListener('project-notifications-read',update);};
  },[refresh]);
  useEffect(()=>{refresh();},[refreshKey,refresh]);
  useEffect(()=>{if(!open)return;const dismiss=e=>{if(!root.current?.contains(e.target))setOpen(false);};const escape=e=>{if(e.key==='Escape'){setOpen(false);trigger.current?.focus();}};document.addEventListener('pointerdown',dismiss);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',dismiss);document.removeEventListener('keydown',escape);};},[open]);
  async function mark(items){
    ++generation.current; // invalidate older GETs before a write/readback
    const result=await api.post('/api/project-notifications',{items:items.map(({project_id,revision})=>({project_id,revision}))},{headers:{'X-Workbench-Request':'local-v1'}});
    ++generation.current;setFeed(result);setError('');window.dispatchEvent(new Event('project-notifications-read'));
  }
  async function act(items,visit=false){if(busy)return;setBusy(true);try{if(visit){const allowed=await onOpen(items[0]);if(!allowed)return;}await mark(items);if(visit)setOpen(false);}catch(e){setError(e.message);}finally{setBusy(false);}}
  const count=feed?.unread_count||0;
  return <div className="project-notifications" ref={root}>
    <button ref={trigger} className="notification-bell" aria-label={`消息提醒${error?'，读取失败':count?`，${count} 个项目未读`:''}`} aria-expanded={open} aria-controls={panelId} onClick={()=>{setOpen(!open);if(!open)refresh();}}><Bell size={19}/>{count>0&&<span className="notification-count">{count>99?'99+':count}</span>}{error&&<span className="notification-fault">!</span>}</button>
    {open&&<section className="notification-panel" id={panelId} aria-label="项目消息提醒">
      <header><div><strong>消息提醒</strong><small>{count} 个项目未读 · 按项目合并</small></div><button aria-label="关闭消息提醒" onClick={()=>{setOpen(false);trigger.current?.focus();}}><X size={18}/></button></header>
      <div className="notification-toolbar"><span>新资料 · 项目调整</span><button disabled={busy||!count} onClick={()=>act(feed.items.filter(i=>i.unread))}>全部标为已读</button></div>
      {error&&<p role="alert">{error} <button onClick={refresh}>重新读取</button></p>}
      {feed?.observation_error&&<p role="alert">{feed.observation_error}</p>}
      {!feed&&!error&&<p>正在读取消息…</p>}
      {feed&&!feed.items.length&&<p className="notification-empty">{feed.initialized?'暂时没有新变化。后续读取到新资料或项目调整时，会在这里提醒。':'正在等待项目数据建立基线，已有历史不会批量提醒。'}</p>}
      <div className="notification-list">{feed?.items.map(item=><article key={item.project_id} className={item.unread?'is-unread':''}>
        <div className="notification-item-heading"><strong>{item.title}</strong><small>{dateLabel(item.at)}</small></div><small>{item.customer}{item.archived?' · 已归档，未自动恢复':''}{item.unread?' · 未读':' · 已读'}</small>
        <ul>{item.changes.slice(0,3).map((c,i)=><li key={i}>{c.label}{c.title?`：${c.title}`:''}</li>)}</ul>{item.changes.length>3&&<small>另有 {item.changes.length-3} 项变化，进入项目可查看</small>}
        <div className="notification-item-actions"><button disabled={busy} onClick={()=>act([item],true)}>查看项目与变化</button>{item.unread&&<button disabled={busy} onClick={()=>act([item])}>标为已读</button>}</div>
      </article>)}</div><footer>仅记录本机已读到的变化 · 不额外发起同步或分析</footer>
    </section>}
  </div>;
}
