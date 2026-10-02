import React,{useState,useEffect,useRef} from 'react';
import {K100Receipt} from './K100Workspace.jsx';
import {K100RoundFields} from './K100Sync.jsx';
import {CheckCircle2,Clock3,FileText,Sparkles} from 'lucide-react';
import {api} from './api.js';
const labels={queued:'判断待更新',running:'判断更新中',complete:'已纳入判断更新',failed:'判断更新失败，原话保留',superseded:'已合并到后续更新，原话保留'};
export function ProgressComposer({project,markDirty=()=>{},markSaving=()=>{},onSaved,initialText='',openRequest=0}) {
 const [text,setText]=useState(initialText),[items,setItems]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[receipt,setReceipt]=useState(null);
 const [k100,setK100]=useState(null),[expanded,setExpanded]=useState(false);
 const field=useRef(null);
 useEffect(()=>{if(openRequest){setExpanded(true);requestAnimationFrame(()=>field.current?.focus());}},[openRequest]);
 const request=useRef(null),live=useRef(true),version=useRef(0),key=`progress:${project.id}`;
 async function read(){try{const value=await api.get(`/api/project-workspace/progress?project_id=${project.id}`);if(live.current){setItems(value.items||[]);return value;}}catch(e){if(live.current)setError(e.message);}}
 useEffect(()=>{live.current=true;read();return()=>{live.current=false;markDirty(key,false);};},[project.id]);
 useEffect(()=>{if(!items.some(x=>['queued','running','superseded'].includes(x.analysis_status)))return;const t=setTimeout(read,8000);return()=>clearTimeout(t);},[items]);
 useEffect(()=>{if(initialText){setExpanded(true);setText(current=>current.includes(initialText)?current:[current,initialText].filter(Boolean).join('\n\n'));version.current++;markDirty(key,true);}},[initialText]);
 async function save(e){e.preventDefault();const submitted=text.trim(),v=version.current;if(!submitted||busy)return;
  if(!request.current||request.current.text!==submitted)request.current={text:submitted,id:crypto.randomUUID(),k100};
  setBusy(true);markSaving(key,true);setError('');
  try{const result=await api.post('/api/project-workspace/progress',{project_id:project.id,archive_revision:project.archive?.revision||0,text:submitted,request_id:request.current.id,...(request.current.k100?{k100:request.current.k100}:{})});
   if(!live.current)return;setReceipt(result);setItems(rows=>[{...result},...rows.filter(x=>x.record_id!==result.record_id)]);request.current=null;
   if(version.current===v){setText('');markDirty(key,false);}await read();onSaved?.();
  }catch(e){if(live.current)setError(e.message);}finally{markSaving(key,false);if(live.current)setBusy(false);}}
 return <section className="progress-composer" aria-label="记录新进展与最近记录"><button type="button" className="progress-open" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>＋ 补充进展</button><form hidden={!expanded} onSubmit={save}><label className="native-field"><span>补充进展 <small> · {project.title}</small></span><textarea ref={field} rows={2} aria-label="进展正文" value={text} maxLength={6000} placeholder="只写尚未收录的新情况即可" onChange={e=>{setText(e.target.value);version.current++;markDirty(key,Boolean(e.target.value));}}/></label><K100RoundFields compact projectId={project.id} onChange={setK100} refreshKey={items.length}/><button className="plain-action" disabled={busy||!text.trim()||project.archive?.archived}>{busy?'正在保存原话…':'保存进展'}</button></form>
 {error&&<p role="alert">{error}；输入保留，可重试。</p>}
 {items.length>0&&<div className="component-receipts" aria-live="polite" aria-label="本次补充处理回执">{items.slice(0,1).map(x=><React.Fragment key={x.record_id}>
 <div className="component-receipt-row"><span><FileText size={17}/>原话</span><div><strong><CheckCircle2 size={16}/>已保存</strong><details><summary>查看原话 · {x.submitted_at?.slice(5,16).replace('T',' ')}</summary><p>{x.text}</p></details></div></div>
 <div className="component-receipt-row"><span><Sparkles size={17}/>AI 判断</span><div><strong>{x.analysis_status==='complete'?<CheckCircle2 size={16}/>:<Clock3 size={16}/>} {labels[x.analysis_status]}</strong>{x.action_change?<details><summary>查看建议变化</summary><p>之前：{x.action_change.before||'无'}</p><p>现在：{x.action_change.after||'无'}</p></details>:null}</div></div>
 <K100Receipt event={x.k100} projectId={project.id} recordId={x.record_id} onRefresh={read}/>
 </React.Fragment>)}</div>}
 {items.length>1&&<details className="component-older-progress"><summary>更早补充 · {items.length-1}</summary>{items.slice(1).map(x=><p key={x.record_id}>{x.submitted_at?.slice(0,10)} · {x.text}</p>)}</details>}

 </section>;
}
