import React,{useState,useEffect} from 'react';
import {Building2,Activity,ArrowRight,Target,GitBranch,Clock3} from 'lucide-react';
import {ProjectTable} from './components/workbench/ProjectTable.jsx';
import {selectWorkbench,pursuitModes} from './models/workbenchViewModel.js';
import {api} from './api.js';
import {groupPursuits,mergeCommitments,hasCurrentJudgement} from './salesPursuitModel.js';
import {currentFocusItems} from './projectFocus.js';
import {readProjectSnapshot,writeProjectSnapshot} from './workbenchStartup.js';

const rememberedMode=()=>{try{const value=sessionStorage.getItem('sales-pursuit-mode');return ['advance','delivery','waiting','nurture'].includes(value)?value:'advance';}catch{return 'advance';}};

export function SalesPursuit({navigate,focusAction,onFocusConsumed,refreshKey}) {
 const [projects,setProjects]=useState(()=>readProjectSnapshot(localStorage)?.projects || []);
 const [verified,setVerified]=useState(false),[error,setError]=useState(''),[items,setItems]=useState([]),[commitmentsError,setCommitmentsError]=useState(''),[commitmentsLoaded,setCommitmentsLoaded]=useState(false);
 useEffect(()=>{let live=true; async function read(){try{const p=await api.get('/api/project-workspace/overview');if(live){setProjects(p.projects);writeProjectSnapshot(localStorage,p.projects);setVerified(true);setError('');}}catch(e){if(live){setVerified(false);setError(e.message);}}}
 const readCommitments=async()=>{const [roundResult,calendarResult]=await Promise.allSettled([api.get('/api/project-workspace/followups'),api.get('/api/calendar/events')]);if(!live)return;const rounds=roundResult.status==='fulfilled'?roundResult.value:{items:[]},calendar=calendarResult.status==='fulfilled'?calendarResult.value:{items:[],error:true};setItems(mergeCommitments(rounds,calendar));const missing=[];if(roundResult.status==='rejected')missing.push('项目跟进');if(calendar.error)missing.push('日程');setCommitmentsError(missing.length?`${missing.join('与')}暂未完整读取，当前只显示已取得的记录，请在提醒与日程核对。`:'');setCommitmentsLoaded(true);};
 let timer;const poll=async()=>{await read();if(live)timer=setTimeout(poll,10000);};const reload=()=>{read();readCommitments();};reload();timer=setTimeout(poll,10000);window.addEventListener('workbench-refresh',reload);
 return()=>{live=false;clearTimeout(timer);window.removeEventListener('workbench-refresh',reload);};},[refreshKey]);
 useEffect(()=>{if(!focusAction||!verified)return;const project=projects.find(p=>p.id===focusAction.project_id||(focusAction.project_source&&p.source_path===focusAction.project_source));onFocusConsumed?.();if(project)navigate('projects',{projectId:project.id,projectTitle:project.title,customer:project.customer});else navigate('reminders',{focusAction});},[focusAction,verified,projects]);
 const due=currentFocusItems(items);
 const open=p=>navigate('projects',{projectId:p.id,projectTitle:p.title,customer:p.customer});
 return <div className="page-stack sales-pursuit">
  <header className="pursuit-header"><div><p className="page-eyebrow">客户推进</p><h1>今天怎么推进</h1><p>先看客户下一步要作什么决定，再看你需要做什么。</p></div><button className="plain-action" onClick={()=>navigate('communications')}>查看近期沟通 →</button></header>
  <section className={'pursuit-commitments'+(!due.length?' is-empty':'')}><strong>已约事项与待承接反馈</strong>{due.length?due.map(item=><button key={item.id} onClick={()=>item.project_id?navigate('projects',{projectId:item.project_id}):navigate('reminders',{focusAction:item})}><time>{item.focus_reason}</time><span>{item.customer} · {item.source_type==='feishu_calendar'?item.title:item.next_step||item.action}</span><b>→</b></button>):<p>{!commitmentsLoaded?'正在读取今天的约定…':commitmentsError?'已取得的记录中暂无到期约定或待承接反馈。':'今天没有已记录的到期约定或待承接反馈。'}</p>}{commitmentsError&&<p role="alert">{commitmentsError}</p>}<button className="plain-action" onClick={()=>navigate('reminders')}>查看全部约定与历史 →</button></section>
  <PursuitBoard projects={projects} verified={verified} error={error} onOpen={open}/>
 </div>;
}

// Shared selector and row surface; preserved buckets and exclusions.
export function PursuitBoard({projects,verified,error,onOpen,onArchive,selectedIds,onSelect}) {
 const [mode,setMode]=useState(()=>{try{return sessionStorage.getItem('workbench-view-v2-mode')||'all';}catch{return 'all';}}),[sort,setSort]=useState('existing');
 const {items,groups,counts}=selectWorkbench(projects,{mode,sort});
 useEffect(()=>{try{sessionStorage.setItem('workbench-view-v2-mode',mode);}catch{}},[mode]);
 return <section className="workbench-project-list"><div className="workbench-filterbar">{Object.entries(pursuitModes).map(([id,label])=><button key={id} aria-pressed={mode===id} onClick={()=>setMode(id)}>{label} {counts[id]}</button>)}<label>排序 <select value={sort} onChange={e=>setSort(e.target.value)}><option value="existing">原有项目顺序</option><option value="name">客户名称</option></select></label></div>{error&&<p role="alert">最新判断未完整读取：{error}</p>}{!verified&&<p role="status">上次列表 · 正在核对最新状态</p>}<ProjectTable projects={items} onOpen={onOpen} onArchive={onArchive} selectedIds={selectedIds} onSelect={onSelect}/>{verified&&!items.length&&<p>当前分类暂无项目。</p>}{groups.updating.length>0&&<details className="workbench-history"><summary>尚未形成综合判断 · {groups.updating.length}</summary>{groups.updating.map(p=><button key={p.id} onClick={()=>onOpen(p)}>{p.title} →</button>)}</details>}<details className="workbench-history"><summary>历史与暂停接触 · {groups.history.length+groups.quiet.length}</summary>{[...groups.history,...groups.quiet].map(p=><button key={p.id} onClick={()=>onOpen(p)}>{p.title} →</button>)}</details></section>;
}
