import React, { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, CheckCircle2, CircleHelp, Database, FilePenLine, FileText, Mail, X } from 'lucide-react';
import { api } from './api.js';
import { ProjectContractAudit } from './ProjectContractAudit.jsx';
import { CommunicationRunStatus, CommunicationReceiptScope, communicationCustomerKey, knownCommunicationCustomer, mergedCommunicationGroups } from './CommunicationSync.jsx';
import './project-connections.css';

const stamp=value=>value?new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'时间待核实';
const KIND={email:'邮件与附件',message:'聊天沟通',recording:'录音',document:'文档依据'};
const ACTOR={customer:'客户沟通',internal:'内部沟通',partner:'合作方沟通',document:'文档依据',unknown:'身份待核实'};
export function projectCommunicationRows(communications,project={}) {
  const customer=communicationCustomerKey(project.customer),rows=new Map();
  for(const group of mergedCommunicationGroups(communications||{})){
    const exact=Boolean(project.id)&&group.project_id===project.id;
    if(!exact&&(!knownCommunicationCustomer(customer)||communicationCustomerKey(group.customer)!==customer))continue;
    for(const item of group.items||[]){
      const row={...item,group_project_id:group.project_id||'',group_project_title:group.project_title||'',group_customer:group.customer,match_scope:exact?'project':'customer',match_label:`${item.historical?'历史归档关联':'归档关联'} · ${exact?'本项目':group.project_id?'同客户其他项目':'同客户背景'}`};
      const key=item.id||`${group.id}:${item.title}:${item.business_date}`;
      if(!rows.has(key)||exact&&rows.get(key).match_scope!=='project')rows.set(key,row);
    }
  }
  const rank=item=>(item.historical?2:0)+(['customer','internal','partner','document'].includes(item.communication?.type)?0:1);
  return [...rows.values()].sort((a,b)=>rank(a)-rank(b)||Number(b.match_scope==='project')-Number(a.match_scope==='project')||(b.business_date||'').localeCompare(a.business_date||'')||a.title.localeCompare(b.title));
}
export function connectionStates({crm,links,communications,analysisState,project={},errors={}}) {
  const email=communications?.connections?.find(x=>x.name==='企业邮箱');
  const rows=projectCommunicationRows(communications,project),projectRows=rows.filter(row=>row.match_scope==='project'),emailRows=rows.filter(row=>row.kind==='email');
  const firstCommunication=rows[0],quote=firstCommunication?.evidence?.[0]?.quote;
  const mediaPlaceholder=typeof quote==='string'&&quote.trim().match(/^[\[【](图片|语音|视频|文件)[\]】]$/);
  const excerpt=mediaPlaceholder?`${mediaPlaceholder[1]}消息 · 内容尚未提取`:quote?'原文摘录：'+quote:'归档摘要（待核）：'+((firstCommunication?.summaries||[])[0]||firstCommunication?.title);
  const communicationPreview=firstCommunication?`${firstCommunication.match_scope==='customer'?'同客户背景 · ':''}${firstCommunication.historical?'历史归档 · ':''}${ACTOR[firstCommunication.communication?.type]||'身份待核'} · ${excerpt}`:'最近归档成果与微信历史';
  const linkErrors=Object.values(links?.sync_errors||{}).filter(Boolean),wrongProject=Boolean(links&&project.id&&links.project_id!==project.id),issues=links?.issues?.length||0;
  const crmStatus=crm?.retired?'旧CRM历史快照 · 已停止更新':errors.crm||errors.links?'读取未完成':!crm?'正在读取':!crm.configured?'需要连接':!links?'项目对应待读取':wrongProject?'项目对应不一致，暂不采用':linkErrors.length?'订单 / 合同同步未完成':crm.snapshot?.sync_status!=='success'?'同步待核实':issues?'部分对应依据需复核':links.matches?.length?`${links.matches.length} 条有依据的对应`:'项目对应待核实';
  return [
    {id:'crm',title:'历史订单与合同',icon:Database,mode:'历史只读 · 不再同步',status:crmStatus,detail:errors.crm||errors.links?'上次记录待重新读取':links?.matches?.length&&linkErrors.length?`${links.matches.length} 条旧对应保留供核对`:crm?.snapshot?.fetched_at?`读取 ${stamp(crm.snapshot.fetched_at)}`:'订单 · 合同 · 回款',preview:errors.crm||errors.links?'读取失败，稍后重试':links?.matches?.[0]?.order?.bizCode||'按原始编号关联本项目',known:!errors.crm&&!errors.links&&!linkErrors.length&&!wrongProject&&!issues&&Boolean(links?.matches?.length)&&crm?.snapshot?.sync_status==='success'},
    {id:'mail',title:'邮件与沟通',icon:Mail,mode:errors.communications?'读取未完成':!communications?'正在读取':email?.available?'邮箱可读取 · 只读':'邮箱连接待核实',status:errors.communications?'关联记录读取未完成':!communications?'正在读取关联记录':rows.length?`归档关联本项目 ${projectRows.length} 条 · 同客户 ${rows.length-projectRows.length} 条`:'已整理范围暂无关联沟通',detail:errors.communications?'上次内容不作为最新结果':!communications?'等待关联结果':emailRows.length?`${email?.available?'邮箱可读':'连接待核'} · ${emailRows.length} 条匹配邮件`:`${email?.available?'邮箱可读':'连接待核'} · 已整理范围未匹配邮件`,preview:errors.communications?'读取失败，稍后重试':communicationPreview,known:!errors.communications&&Boolean(rows.length)},
    {id:'draft',title:'本轮沟通准备',icon:FilePenLine,mode:'AI 草稿 · 未发送',
      status:!analysisState?'正在读取':!analysisState.result?'尚未形成本轮准备':analysisState.stale||analysisState.state!=='ready'?'上次准备 · 等待更新':analysisState.result?.analysis?.guard?'仅内部准备':analysisState.result?.analysis?.draft?'本轮草稿可核对':'本轮提纲与成功条件',
      detail:analysisState?.result?.created_at?`依据更新 ${stamp(analysisState.result.created_at)}`:'依据当前项目判断准备',
      preview:analysisState?.result?.analysis?.guard||analysisState?.result?.analysis?.story?.conversation?.goal||'结合当前任务准备沟通，不自动发送',
      known:Boolean(analysisState?.result)&&analysisState?.state==='ready'&&!analysisState?.stale}
  ];
}
function CommunicationRecord({item}) {
  const [open,setOpen]=useState(false),[body,setBody]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
  const request=useRef(0);
  useEffect(()=>()=>{request.current++;},[]);
  const source=(item.sources||[]).find(value=>value.readable&&/正文|原文|转写/.test(value.label||''))||(item.sources||[]).find(value=>value.readable);
  async function read(){
    if(!source||loading)return;
    const ticket=++request.current;setLoading(true);setError('');
    try{
      const url=source.path?`/api/project-workspace/source?project_id=${encodeURIComponent(source.project_id||item.group_project_id)}&path=${encodeURIComponent(source.path)}`:`/api/material-library/source?asset_id=${encodeURIComponent(source.id)}`;
      const value=await api.get(url);
      if(ticket===request.current){if(typeof value.content!=='string')throw new Error('原文暂不可读取');setBody(value);}
    }catch(e){if(ticket===request.current)setError(e.message);}
    finally{if(ticket===request.current)setLoading(false);}
  }
  return <article className="connection-communication-record">
    <button className="connection-record-heading" aria-expanded={open} onClick={()=>setOpen(value=>!value)}><FileText size={15}/><span><strong>{item.title}</strong><small><span>{item.match_label}</span><span>{KIND[item.kind]||'资料'} · {ACTOR[item.communication?.type]||'身份待核实'}</span></small></span><time>{item.business_date||'原文未标日期'}</time></button>
    {open&&<div className="connection-record-body"><p className="connection-match-scope">{item.match_label}：{item.group_project_title||item.group_customer}。归档关联属于系统整理，不代表客户确认。{item.match_scope==='customer'?'仅作客户背景，不代替本项目证据。':''}</p>{item.communication?.reason&&<p className="connection-match-scope">沟通对象判断：{item.communication.reason}</p>}{Boolean(item.summaries?.length)&&<small>归档时的 AI 摘要 · 以原文及当前项目判断核对</small>}{(item.summaries||[]).map((summary,i)=><p key={i}>{summary}</p>)}{(item.evidence||[]).slice(0,3).map((e,i)=><blockquote key={i}><small>{e.display_label||({customer_statement:'客户原话',internal_statement:'我方表述',document_text:'文件原文'})[e.level]||'来源待核事实'}</small>{e.quote}</blockquote>)}{source?<button className="connection-open" disabled={loading} onClick={read}>{loading?'正在读取原文…':'查看完整原文'}<ArrowUpRight size={13}/></button>:<small>该条未提供可读取原文入口，已有摘录保留。</small>}{error&&<p role="alert">{error}</p>}{body&&<div className="connection-source-reader"><strong>{body.title||'原始内容'}</strong><pre>{body.content}</pre>{body.truncated&&<small>原文较长，此处为截取内容。</small>}</div>}</div>}
  </article>;
}
export function ProjectConnections({project,navigate,refreshKey,compact=true,analysisState,onPrepare,showPreparation=true}) {
  const [data,setData]=useState({}),[selected,setSelected]=useState(''),[showAll,setShowAll]=useState(false);
  useEffect(()=>{
    let live=true;setData({});setSelected('');setShowAll(false);
    const requests={communications:'/api/communication-sync'};
    Promise.all(Object.entries(requests).map(async([key,url])=>{try{return [key,await api.get(url)];}catch(e){return [key,null,e.message];}})).then(rows=>{if(live){const next={errors:{}};rows.forEach(([key,value,error])=>{next[key]=value;if(error)next.errors[key]=error;});setData(next);}});
    return()=>{live=false;};
  },[project.id,refreshKey]);
  const context={projectId:project.id,projectTitle:project.title,customer:project.customer};
  const cards=connectionStates({...data,project,analysisState}),current=cards.find(x=>x.id===selected),rows=projectCommunicationRows(data.communications,project);
  return <section className={`project-connections-canvas ${compact?'is-compact':''}`} aria-label="客户画布连接的系统">
    <header><div><strong>关联业务记录</strong><span>本项目与同客户背景分别核对</span></div></header>
    <div className="connection-endpoints">{cards.filter(card=>card.id!=='crm'&&(showPreparation||card.id!=='draft')).map(({icon:Icon,...card})=><button key={card.id} aria-expanded={card.id==='draft'?undefined:selected===card.id} aria-controls={card.id==='draft'?`canvas-panel-preparation-${project.id}`:`connection-detail-${project.id}`} disabled={card.id==='draft'&&!analysisState?.result} onClick={()=>card.id==='draft'?onPrepare?.():setSelected(value=>value===card.id?'':card.id)}><span className="connection-card-title"><Icon size={16}/>{card.title}<ArrowUpRight size={12}/></span><strong className={card.known?'connection-known':''}>{card.known?<CheckCircle2 size={12}/>:<CircleHelp size={12}/>} {card.status}</strong><span className="connection-card-detail">{card.detail}</span><span className="connection-card-preview" title={card.preview}>{card.preview}</span><small>{card.mode}</small></button>)}</div>
    {selected&&<div className="connection-detail" id={`connection-detail-${project.id}`}><header><strong>{current.title}</strong><button aria-label="收起系统连接详情" onClick={()=>setSelected('')}><X size={16}/></button></header>
      {selected==='crm'&&<><p>旧CRM已停用。以下仅核对历史订单与合同；新跟进使用项目顶部 K100 关联。</p>{data.errors?.crm&&<p role="alert">连接状态未读回：{data.errors.crm}</p>}{data.errors?.links&&<p role="alert">本项目对应未读回：{data.errors.links}</p>}{Object.entries(data.links?.sync_errors||{}).map(([resource,error])=><p role="alert" key={resource}>{resource==='orders'?'订单':resource==='contracts'?'合同':resource}同步未完成：{String(error)}</p>)}<ProjectContractAudit projectId={project.id} refreshKey={refreshKey} navigate={navigate}/></>}
      {selected==='mail'&&<><div className="connection-communication-scope"><strong>{data.communications?.connections?.find(x=>x.name==='企业邮箱')?.available?'企业邮箱可读取':'企业邮箱连接待核实'}</strong><span>匹配范围：最近归档成果 {data.communications?.digest?.date||'日期待核'} ＋ 已收录微信历史。不是完整邮箱检索。</span></div>{data.errors?.communications&&<p role="alert">{data.errors.communications}</p>}{!rows.some(item=>item.kind==='email')&&<p className="connection-no-mail">当前已整理范围内未匹配该客户的邮件；不代表邮箱未连接，也不代表没有历史邮件。</p>}{rows.length?<div className="connection-communication-list">{(showAll?rows:rows.slice(0,6)).map(item=><CommunicationRecord key={item.id} item={item}/>)}</div>:<p>当前已整理范围内没有与本项目或该客户匹配的沟通记录。</p>}{rows.length>6&&<button className="connection-open" onClick={()=>setShowAll(value=>!value)}>{showAll?'收起':'展开其余 '+(rows.length-6)+' 条关联沟通'}</button>}<section className="connection-global-receipt" aria-label="全局沟通整理回执"><strong>本轮后台整理 · 全部来源</strong><small>以下是全局处理进度，与上方本客户归档匹配条数分别核对。</small>{data.errors?.communications?<p role="alert">最新处理回执未读回，不能判断本轮是否完成。</p>:<><CommunicationRunStatus data={data.communications}/><CommunicationReceiptScope receipt={data.communications?.receipt||{}} job={data.communications?.job||{}}/>{data.communications?.receipt?.gaps?.length>0&&<details><summary>来源缺口 · {data.communications.receipt.gaps.length}</summary>{data.communications.receipt.gaps.map((gap,i)=><p key={i}>{gap.source}：{gap.reason}</p>)}</details>}</>}</section><button className="connection-open" onClick={()=>navigate('communications',context)}>查看该客户的沟通记录 <ArrowUpRight size={14}/></button></>}

    </div>}
  </section>;
}
