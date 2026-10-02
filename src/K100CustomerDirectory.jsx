import React,{useEffect,useState} from 'react';
import {api} from './api.js';
import {k100Directory} from './k100DirectoryModel.js';
import {CustomerFiles} from './CustomerFiles.jsx';
import {publicUrl} from './discovery-model.js';
import './k100-directory.css';
export function K100CustomerDirectory({query='',projects=[],summary={},signals=[],onProject,markDirty,markSaving,canLeave}){
 const [roster,setRoster]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[active,setActive]=useState(''),[tab,setTab]=useState('projects'),[checkedAt,setCheckedAt]=useState(''),[audit,setAudit]=useState(null),[auditing,setAuditing]=useState(false);
 async function auditLinks(){setAuditing(true);try{setAudit(await api.get('/api/k100/identity-audit'));}catch(e){setError(e.message);}finally{setAuditing(false);}}
 async function connect(p){setAuditing(true);try{await api.post('/api/k100/link-verified',{project_id:p.project_id});window.dispatchEvent(new Event('workbench-refresh'));await auditLinks();}catch(e){setError(e.message);}finally{setAuditing(false);}}
 async function read(){setBusy(true);try{const x=await api.get('/api/k100/customers');if(!x.ok)throw Error('K100 客户未完整读回');setRoster(x.items);setCheckedAt(new Date().toLocaleString('zh-CN'));setError('');}catch(e){setError(e.message);}finally{setBusy(false);}}
 useEffect(()=>{read();},[]);
 const allRows=k100Directory(roster||[],projects,summary,signals);
 const rows=allRows.filter(x=>x.legalName?.toLowerCase().includes(query.trim().toLowerCase()));
 const row=allRows.find(x=>x.id===active);
 async function select(id){if(await canLeave()){setActive(id);setTab('projects');}}
 return <section className="k100-directory" aria-label="K100客户目录"><header><div><h2>我的 K100 客户</h2><small>{checkedAt?`读取于 ${checkedAt}`:'正在读取正式客户主体'}</small></div><button disabled={busy} onClick={read}>{busy?'读取中…':'刷新目录'}</button></header>
 {error&&<p role="alert">{error}。{roster?'保留上次读取的客户，当前归属尚未核对。':'未使用本地候选名单代替。'}</p>}
 {!row&&<details><summary>项目关联核对</summary><button disabled={auditing} onClick={auditLinks}>{auditing?'正在核对原有依据…':'核对已有项目依据'}</button>{audit?.items?.map(p=><article key={p.project_id}><strong>{p.project_title}</strong>{p.state==='verified'?<><p>{p.proofs[0].customer_name} · {p.proofs[0].basis}</p><button disabled={auditing} onClick={()=>connect(p)}>按已核实依据关联</button></>:<><p>{p.reason}。仅影响客户归属与同步，不阻止本地推进。</p><button onClick={()=>onProject(p.project_id)}>进入项目确认主体</button></>}</article>)}</details>}
 {row?<><button className="plain-action" onClick={()=>select('')}>← 返回客户目录</button><h2>{row.legalName}</h2><nav className="focus-work-tabs"><div>{[['projects','项目'],['signals','客户动态'],['files','文件']].map(([id,label])=><button key={id} aria-pressed={tab===id} onClick={async()=>{if(await canLeave())setTab(id);}}>{label}</button>)}</div><a target="_blank" rel="noreferrer" href={'https://crm.example.invalid/sales/customers/'+encodeURIComponent(row.id)}>查看 CRM 主体 ↗</a></nav>
 {tab==='projects'&&(row.projects.length?row.projects.map(p=><button className="k100-project-link" key={p.id} onClick={()=>onProject(p.id)}>{p.title} →</button>):<p>尚无已核对的项目关联。已有项目仍保留在项目工作台。</p>)}
 {tab==='signals'&&(row.signals.length?row.signals.map(x=><article key={x.id}><small>{x.published_at||'日期待核实'}</small><h3>{x.title}</h3><p>{x.impact_judgment||x.relevance}</p>{publicUrl(x.source_url)&&<a href={publicUrl(x.source_url)} target="_blank" rel="noreferrer">查看原文 ↗</a>}</article>):<p>已收录资讯中，尚无明确关联到这个主体的内容。</p>)}
 <div hidden={tab!=='files'}>{tab==='files'&&<CustomerFiles customer={row.legalName} scopeProjectIds={row.projects.map(p=>p.id)} markDirty={markDirty} markSaving={markSaving}/>}</div>
 </>:<div className="k100-subject-list">{rows.map(x=><button key={x.id} onClick={()=>select(x.id)}><span className="k100-subject-initial">{x.legalName.slice(0,1)}</span><span><strong>{x.legalName}</strong><small>{x.projects.length?'关联项目 '+x.projects.length:'项目关联待核对'}</small></span><span>→</span></button>)}</div>}
 {!active&&!busy&&!error&&!rows.length&&<p>这个搜索条件下没有匹配的 K100 客户。</p>}
 </section>;
}
