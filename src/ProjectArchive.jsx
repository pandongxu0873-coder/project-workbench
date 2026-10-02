import React,{useEffect,useRef,useState} from 'react';
import {api} from './api.js';
import './styles/project-archive.css';
export function ArchiveStatus({archive,onOpenSource,onRestore}){
 if(!archive?.history?.length)return null;
 return <section className="project-archive-status" aria-label="项目归档记录"><strong>{archive.archived?'已主动归档 · 停止销售推进':'已恢复跟进'}</strong><p>{archive.updated_at?.replace('T',' ').slice(0,19)} {archive.reason} {archive.note}</p>{archive.archived&&<p>已归档项目·待收尾：交付、验收、回款责任和真实会议仍需核对；历史、材料、报价及发票报销保留。</p>}{archive.archived&&archive.review?.has_new_material&&<section className="project-archive-new" aria-label="归档后新增资料"><strong>已归档 · 有新资料待查看</strong><p>仅表示材料发生变化，不代表已确认新机会。查看依据后，由你决定是否恢复跟进。</p><ul>{archive.review.items.map(item=><li key={item.path}><span>{item.change} · 材料日期 {item.date||'待核实'} · </span>{item.readable&&onOpenSource?<button onClick={()=>onOpenSource(item)}>{item.title}</button>:<span>{item.title}（原件保留）</span>}</li>)}</ul>{onRestore&&<button onClick={onRestore}>核对后恢复跟进</button>}</section>}{archive.archived&&archive.review?.baseline_missing&&<p>本次归档未记录材料基线；请核对原材料，系统不会推断有新机会或自动恢复。</p>}<details><summary>归档与恢复历史 · {archive.history.length}</summary><ol>{archive.history.map(e=><li key={e.revision}>{e.at.replace('T',' ').slice(0,19)} · {e.action==='archive'?'归档':'恢复'} · {e.reason} {e.note}</li>)}</ol></details></section>;
}
export function ProjectArchiveDialog({projects,action,onClose,onSaved}){
 const dialog=useRef(null),request=useRef(null);const [rows,setRows]=useState(null),[reason,setReason]=useState(''),[note,setNote]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const ids=projects.map(p=>p.id);const read=async()=>{try{const value=await api.get('/api/project-archive?ids='+ids.join(','));if(value.items.length!==ids.length)throw Error('项目已变化，请重新选择');setRows(value.items);request.current=null;setError('');}catch(e){setError(e.message);}};
 useEffect(()=>{dialog.current.showModal();read();},[]);
 async function save(){
  setBusy(true);setError('');
  try{
   const body={action,project_ids:ids,expected_revisions:Object.fromEntries(rows.map(r=>[r.project_id,r.archive.revision])),reason,note};
   const signature=JSON.stringify(body);if(request.current?.signature!==signature)request.current={signature,id:crypto.randomUUID()};
   const result=await api.post('/api/project-archive',{...body,request_id:request.current.id},{headers:{'X-Workbench-Request':'local-v1'}});
   const verified=await api.get('/api/project-archive?ids='+ids.join(','));
   if(!result.items.every(x=>verified.items.some(r=>r.project_id===x.project_id&&r.archive.revision>=x.revision&&r.archive.archived===x.archived)))throw Error('写入已返回，但状态又有变化；请重新核对');
   await onSaved(result.message);onClose();
  }catch(e){setError(e.message);}finally{setBusy(false);}
 }
 return <dialog ref={dialog} className="project-archive-dialog" aria-labelledby="archive-confirm-title" onCancel={e=>{e.preventDefault();if(!busy)onClose();}}><h2 id="archive-confirm-title">{action==='archive'?'归档项目':'恢复跟进'} · {ids.length} 项</h2><ul>{projects.map(p=><li key={p.id}>{p.title}</li>)}</ul><p>仅影响以上明确项目，不影响同客户其他项目和客户身份。</p>{action==='archive'?<><label>归档原因（必填）<select value={reason} onChange={e=>setReason(e.target.value)}><option value="">请选择原因</option>{['本轮无机会','客户取消','预算未通过','已丢单','我方不再投入','其他'].map(r=><option key={r}>{r}</option>)}</select></label><p>退出默认销售推进、活动项目计数和自动销售催办；不会认定履约完成、已收款或费用作废。</p></>:<p>恢复原项目和历史。禁联与暂停限制仍有效；旧提醒不自动重发，不修改截止日期，不启动同步或模型分析。</p>}<label>补充备注<textarea maxLength={2000} value={note} onChange={e=>setNote(e.target.value)}/></label>{rows?.map(r=><section key={r.project_id}><strong>{r.title}</strong><p>{r.impact.preserved}</p><p>{r.impact.calendar_notice}</p><p>{r.impact.calendar_state}</p>{r.impact.existing_meetings?.length>0&&<><b>已保存日程中的关联会议（继续保留）：</b><ul>{r.impact.existing_meetings.map(x=><li key={x.id}>{x.title} {x.due}</li>)}</ul></>}{r.impact.existing_items.length>0&&<><b>已有待核对事项：</b><ul>{r.impact.existing_items.map(x=><li key={x.id}>{x.title} {x.due}</li>)}</ul></>}</section>)}{!rows&&!error&&<p role="status">正在核对项目和影响范围…</p>}{error&&<p role="alert">{error} <button disabled={busy} onClick={read}>重新核对</button></p>}<footer><button disabled={busy} onClick={onClose}>取消</button><button disabled={busy||!rows||(action==='archive'&&!reason)} onClick={save}>{busy?'正在保存…':action==='archive'?'确认归档':'确认恢复跟进'}</button></footer></dialog>;
}
