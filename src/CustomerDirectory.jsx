import {CustomerFiles} from './CustomerFiles.jsx';
import {CustomerIdentity} from './components/customer/CustomerIdentity.jsx';
import React,{useState,useEffect} from 'react';
import {CustomerMeeting} from './CustomerMeeting.jsx';
import { ArrowUpRight, Building2 } from 'lucide-react';
import { customerDirectory } from './customerDirectory.js';
import './customer-directory.css';

export function CustomerDirectory({accounts,projects,query,customerFilter,loading,error,onAccount,onProject,meetingRequest,markDirty,markSaving,canLeave=async()=>true}) {
  const [preparing,setPreparing]=useState('');
  const [files,setFiles]=useState('');
  useEffect(()=>{if(meetingRequest?.rowId)setPreparing(meetingRequest.rowId);},[meetingRequest]);
  const rows=customerDirectory(accounts,projects,query,customerFilter);
  return <section className="customer-directory" aria-label="客户经营目录">
    <header><h2>客户经营</h2><span>客户是固定入口 · 项目独立推进</span></header>
    {loading&&<p role="status">正在核对正式客户记录，已有项目仍可阅读。</p>}
    {error&&<p role="alert">正式客户尚未更新：{error}。已显示的项目不代表全部客户。</p>}
    <div role="list">{rows.map(row=><article role="listitem" key={row.id} className="customer-directory-row">
      <div className="customer-directory-name"><div><CustomerIdentity row={row}/><small>{row.account?'正式客户记录':'已有项目客户'} · {row.projects.length?`${row.projects.length} 个关联项目`:'尚无明确关联项目'}</small></div></div>
      <div className="customer-directory-work">{row.projects.length?row.projects.map(project=><div key={project.id} className="customer-directory-project"><button onClick={()=>onProject(project.id)}>{project.title}<ArrowUpRight size={13}/></button><span>{project.is_current?'当前项目':'历史项目'} · {project.analysis_state==='ready'&&!project.analysis_stale?project.brief?.situation||'已整理项目判断':'项目理解待更新'}</span></div>):<><p>{row.account?.next_action||row.account?.opportunity||'尚无已记录的下一步，先核对现有客户事实。'}</p><small>账户记录 · {row.account?.updated_at?.slice(0,10)||'记录日期未明确'} · 待结合当前情况核对</small></>}</div>
      <div className="customer-directory-actions"><button onClick={async()=>{if(await canLeave())setFiles(files===row.id?'':row.id);}}>文件</button>{row.projects.length>1&&<button className="plain-action" onClick={()=>setPreparing(preparing===row.id?'':row.id)}>准备这次沟通<ArrowUpRight size={13}/></button>}{row.account&&<button className="plain-action" onClick={()=>onAccount(row.account)}>客户跟进<ArrowUpRight size={13}/></button>}</div>
      {files===row.id&&<CustomerFiles markDirty={markDirty} markSaving={markSaving} customer={row.name} onClose={()=>setFiles('')}/>}
      {preparing===row.id&&<CustomerMeeting key={`${row.id}:${meetingRequest?.token||''}`} row={row} onProject={onProject} onClose={()=>setPreparing('')}/>}
    </article>)}</div>
    {!loading&&!error&&!rows.length&&<p>没有匹配的客户或项目。</p>}
  </section>;
}
