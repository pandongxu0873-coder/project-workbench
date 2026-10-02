import React,{useState,useEffect} from 'react';
import {meetingKey,restoreMeeting,meetingTopic,meetingText} from './customerMeeting.js';

export function CustomerMeeting({row,onProject,onClose}) {
  const [draft,setDraft]=useState(()=>{try{return restoreMeeting(JSON.parse(localStorage.getItem(meetingKey(row.id))),row.projects);}catch{return restoreMeeting(null,row.projects);}});
  const [notice,setNotice]=useState(''),[saveError,setSaveError]=useState('');
  const current=restoreMeeting(draft,row.projects);
  useEffect(()=>{try{localStorage.setItem(meetingKey(row.id),JSON.stringify(draft));setSaveError('');}catch{setSaveError('本机草稿暂未保存，请保留当前页面或复制准备内容。');}},[draft,row.id]);
  const change=values=>{setDraft(old=>({...old,...values}));setNotice('');};
  const toggle=id=>change({ids:current.ids.includes(id)?current.ids.filter(x=>x!==id):[...current.ids,id]});
  const move=(index,step)=>{const ids=[...current.ids];[ids[index],ids[index+step]]=[ids[index+step],ids[index]];change({ids});};
  const text=meetingText(row.name,current,row.projects);
  const selected=current.ids.map(id=>row.projects.find(p=>p.id===id)).filter(Boolean);
  return <section className="customer-meeting" aria-label={`${row.name}本次沟通准备`}>
    <header><div><h3>准备这次沟通 · {row.name}</h3><p>选择适合同一对象讨论的议题，排好先后；各项目范围与责任分别保留。</p></div><button className="plain-action" onClick={onClose}>收起</button></header>
    <div className="customer-meeting-intent"><label>这次和谁沟通<input value={current.contact} onChange={e=>change({contact:e.target.value})} placeholder="联系人或角色；不代表已约定参会"/></label><label>这次要促成什么<input value={current.goal} onChange={e=>change({goal:e.target.value})} placeholder="例如先收口本次验收范围，再明确新增项的评估安排"/></label></div>
    <div className="customer-meeting-layout"><section aria-label="选择本次议题"><h4>选择议题</h4>{row.projects.map(p=><label className="customer-meeting-option" key={p.id}><input type="checkbox" checked={current.ids.includes(p.id)} disabled={p.execution?.relationship==='no_contact'} onChange={()=>toggle(p.id)}/><span>{p.title}<small>{p.execution?.relationship==='no_contact'?'已明确暂勿联系，不加入沟通':p.is_current?'当前项目':'历史项目 · 仅在确与本次有关时加入'}</small></span></label>)}</section>
      <section aria-label="本次沟通议程"><h4>本次议程 · {selected.length} 项</h4>{!selected.length&&<p>先选择本次真正需要讨论的项目，不自动合并同客户的全部事项。</p>}{selected.map((project,index)=>{const topic=meetingTopic(project,current.notes[project.id]);return <article key={project.id} className="customer-meeting-topic"><header><h4>{index+1}. {project.title}</h4><div><button disabled={index===0} aria-label={`上移议题：${project.title}`} onClick={()=>move(index,-1)}>↑</button><button disabled={index===selected.length-1} aria-label={`下移议题：${project.title}`} onClick={()=>move(index,1)}>↓</button><button aria-label={`移除议题：${project.title}`} onClick={()=>toggle(project.id)}>移除</button></div></header>
        {topic.restricted&&<p role="alert">该项目已明确暂勿联系，请从本次沟通中移除；准备内容暂不可复制。</p>}
        <small>{topic.ready?'当前理解':'上次理解 · 待更新'} · 依据 {topic.basis}</small><p>{topic.situation}</p><p><strong>已记录：</strong>{topic.recorded}</p>
        <label>本次要讨论的决定<textarea value={current.notes[project.id]??''} placeholder={topic.decision} onChange={e=>change({notes:{...current.notes,[project.id]:e.target.value}})}/></label>
        <p><strong>继续条件：</strong>{topic.condition}</p><button className="plain-action" onClick={()=>onProject(project.id)}>核对项目全貌 / 记录本项结果 →</button>
        {(current.topics[project.id]||[]).map(item=><section className="meeting-selected-question" key={item.key}><h4>{item.title}</h4><small>选取时的理解 · {item.createdAt||'日期待核'}{item.stale?' · 当时已待更新':''} · 须结合当前事实复核</small><p style={{whiteSpace:'pre-wrap'}}>{item.detail}</p><details><summary>带入的原文依据 · {item.evidence?.length||0}</summary>{item.evidence?.map((e,i)=><blockquote key={i}><p>{e.quote}</p><small>{e.path}</small></blockquote>)}</details><button className="plain-action" onClick={()=>change({topics:{...current.topics,[project.id]:current.topics[project.id].filter(t=>t.key!==item.key)}})}>移除这个问题</button></section>)}
      </article>;})}</section></div>
    <footer><span>{saveError||'选择、顺序和补充自动保存在本机；不是客户确认或正式会议记录。'}</span><button disabled={!text} onClick={async()=>{try{await navigator.clipboard.writeText(text);setNotice('准备内容已复制，尚未发送；沟通结果仍需分别记回项目。');}catch{setNotice('未能复制，请稍后重试。');}}}>复制本次沟通准备</button></footer>
    {notice&&<p role="status">{notice}</p>}
  </section>;
}
