import React,{useState,useEffect} from 'react';
import {ExternalLink,Database,CheckCircle2,AlertCircle} from 'lucide-react';
import {api} from './api.js';
export const K100_URL='https://crm.example.invalid/sales-workspace';
export function useK100Summary(refreshKey){
 const [value,setValue]=useState(null),[error,setError]=useState('');
 useEffect(()=>{let live=true;async function read(){try{const x=await api.get('/api/k100/summary');if(live){setValue(x);setError('');}}catch(e){if(live)setError('K100 回执暂未读到');}}read();window.addEventListener('workbench-refresh',read);const t=setInterval(read,30000);return()=>{live=false;clearInterval(t);window.removeEventListener('workbench-refresh',read);};},[refreshKey]);
 return {value,error};
}
export function K100ProjectContext({projectId,refreshKey}){
 const {value,error}=useK100Summary(refreshKey),x=value?.projects?.[projectId],link=x?.link,event=x?.event;
 return <section className="crm-context" aria-label="新版CRM关联"><span className="crm-source"><Database size={14}/>K100</span><span>{error||(!value?'正在读取关联':link?link.customer_name:'本项目尚未关联新版 CRM')}</span>{event&&<span className={event.state==='confirmed'?'crm-ok':'crm-warning'}>{event.state==='confirmed'?<CheckCircle2 size={14}/>:<AlertCircle size={14}/>} {event.state==='confirmed'?'最近跟进已同步':'最近同步待处理'}</span>}<a href={link?`https://crm.example.invalid/sales/customers/${encodeURIComponent(link.customer_id)}`:K100_URL} target="_blank" rel="noreferrer">{link?'在 K100 查看':'打开 K100'} <ExternalLink size={13}/></a></section>;
}
export function K100Receipt({event,projectId,recordId,onRefresh}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 async function recover(){setBusy(true);setError('');try{const route=event?.id?(['sending','written','uncertain'].includes(event.state)?'reconcile':'retry'):'recover-progress';await api.post('/api/k100/'+route,event?.id?{id:event.id}:{project_id:projectId,record_id:recordId});await onRefresh?.();window.dispatchEvent(new Event('workbench-refresh'));}catch(e){setError(e.message);}finally{setBusy(false);}}
 return <div className="progress-crm-receipt"><span className="crm-source">K100</span><div><strong>{event?.message||'同步状态待读取'}</strong>{event?.state==='confirmed'&&<small>有效跟进：{event.effective?'是':'否'} · 刷新保护计时：{event.protection_refreshed?'是':'否'}</small>}{error&&<p role="alert">{error}</p>}</div>{event&&event.state!=='confirmed'&&event.state!=='needs_link'&&<button type="button" disabled={busy} onClick={recover}>{busy?'核对中…':['sending','written','uncertain'].includes(event.state)?'核对回执':'恢复同步'}</button>}</div>;
}

export function K100IdentityQuestion({projectId}) {
 const [state,setState]=useState(null),[rows,setRows]=useState([]),[selected,setSelected]=useState(''),[open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{let live=true;const read=()=>api.get('/api/k100/status?project_id='+encodeURIComponent(projectId)).then(x=>{if(live)setState(x);}).catch(e=>{if(live)setError(e.message);});read();window.addEventListener('workbench-refresh',read);return()=>{live=false;window.removeEventListener('workbench-refresh',read);};},[projectId]);
 async function choose(){setOpen(true);setBusy(true);setError('');try{setRows((await api.get('/api/k100/customers')).items.filter(x=>x.isMine));}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function link(){setBusy(true);setError('');try{setState(await api.post('/api/k100/link',{project_id:projectId,customer_id:selected}));window.dispatchEvent(new Event('workbench-refresh'));}catch(e){setError(e.message);}finally{setBusy(false);}}
 if(state?.link)return null;
 if(!state)return error?<p role="alert">{error}</p>:null;
 return <section className="identity-question" aria-label="需要确认的客户主体"><strong>需要你确认：这个项目对应哪个 CRM 客户主体？</strong><p>影响进展同步和客户文件归属；本地推进仍可继续。尚未核到唯一主体；不确定可以暂不选择。</p>{!open?<button type="button" onClick={choose}>选择客户主体</button>:<><label className="native-field"><span>项目对应主体</span><select aria-label="项目对应主体" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">{busy?'正在读取…':'选择准确主体；不确定可暂不选择'}</option>{rows.map(x=><option key={x.id} value={x.id}>{x.legalName}</option>)}</select></label><button type="button" disabled={busy||!selected} onClick={link}>确认关联</button><button type="button" onClick={()=>setOpen(false)}>暂不确定</button></>}{error&&<p role="alert">{error}</p>}</section>;
}
