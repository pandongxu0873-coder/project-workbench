import {projectNext,projectNeed} from '../../projectPresentation.js';
import React from 'react';
import {ArrowRight} from 'lucide-react';
import {CustomerLogo} from '../customer/CustomerIdentity.jsx';
import '../../styles/workbench.css';
export function ProjectTable({projects,onOpen,onArchive,commitments=[],selectedIds=[],onSelect}){
 return <div className="workbench-table concept-table" role="table" aria-label="项目对照">
 <div className="workbench-table-head" role="row">{['客户 / 项目','当前情况','当前需要',''].map(x=><span role="columnheader" key={x}>{x}</span>)}</div>
 {projects.map(p=>{const need=projectNeed(p,commitments.filter(x=>x.project_id===p.id));return <div className="workbench-table-row" key={p.id} role="row">
 <div role="cell" className="workbench-project-name"><span className="project-archive-select">{onSelect&&<input type="checkbox" aria-label={`选择项目${p.title}`} checked={selectedIds.includes(p.id)} onChange={e=>onSelect(p.id,e.target.checked)}/>}<CustomerLogo name={p.customer} entityId={p.account_id?`account:${p.account_id}`:`customer:${p.customer}`} projectId={p.id}/></span><div><button className="project-name-link" data-project-trigger={p.id} aria-label={`进入${p.title}`} onClick={()=>onOpen(p)}><strong>{p.title}</strong><span>{p.customer||'客户待核实'} · {p.brief?.stage||'阶段待核实'}</span></button></div></div>
 <div role="cell" className="project-change-cell"><button onClick={()=>onOpen(p)}><span>{p.brief?.situation||p.judgement||'尚待综合已有材料'}</span></button><small>{need.kind==='updating'?'上次判断 · ':''}依据 {p.latest_evidence_date||'日期待核实'}</small></div>
 <div role="cell" className="project-next-cell"><span className="need-chip" data-kind={need.kind}>{need.label}</span><button title={projectNext(p)} onClick={()=>onOpen(p)}><span>{need.commitment?(need.commitment.action||need.commitment.next_step||'查看已有约定'):need.actionable?projectNext(p):need.kind==='waiting'?'查看已做记录与反馈':need.kind==='updating'?'查看已有进展':need.kind==='quiet'?'查看项目与约定':'查看项目'}</span><ArrowRight size={14}/></button>{p.execution?.due&&<small>已记录安排 · {p.execution.due}</small>}</div>
 <div role="cell">{onArchive&&<details className="project-archive-more"><summary aria-label={`${p.title}更多`}>···</summary><button onClick={()=>onArchive([p],p.archive?.archived?'restore':'archive')}>{p.archive?.archived?'恢复跟进':'归档项目'}</button></details>}</div></div>;})}</div>;
}
