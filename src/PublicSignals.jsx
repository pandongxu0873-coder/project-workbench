import { signalProjectContext } from './signalProjectContext.js';
import React, { useEffect, useId, useRef, useState } from 'react';
import { api } from './api.js';
import { publicUrl } from './discovery-model.js';
import './signal-workspace.css';
import { Radio, ArrowUpRight, ArrowRight, ChevronDown, ChevronRight, GitBranch, Search, Building2, FileSearch, Clock3, Bot, UserRound, X } from 'lucide-react';
import './signal-redesign.css';

const stamp = v => v ? String(v).replace('T',' ').slice(0,16) : '尚无回执';
export function usePublicSignals(refreshKey) {
  const [data,setData]=useState(null),[error,setError]=useState('');
  useEffect(()=>{
    let live=true,sequence=0;
    async function read(){const ticket=++sequence;try{const value=await api.get('/api/public-signals');if(live&&ticket===sequence){setData(value);setError('');}}catch(e){if(live&&ticket===sequence)setError(e.message);}}
    read();const timer=setInterval(()=>{if(document.visibilityState!=='hidden')read();},60000);
    window.addEventListener('workbench-refresh',read);
    return()=>{live=false;clearInterval(timer);window.removeEventListener('workbench-refresh',read);};
  },[refreshKey]);
  return {data,error};
}

const signalKey = item => `${item.customer}:${item.id}`;
const currentState = (task, receipt) => ['running','error','failed','partial','no_import'].includes(task?.status) ? task.status : receipt?.status || task?.status;
const stateTone = (status, overdue = false) => overdue || ['error','failed','partial','no_import','search_unavailable'].includes(status) ? 'attention' : status === 'running' ? 'running' : ['ok','ready','no_change','no_result'].includes(status) ? 'complete' : 'waiting';

function SignalProjectLinks({item,navigate}) {
  const projects=item.related_projects||[];
  return <div className="signal-relation-map"><span><GitBranch size={14}/> 关联项目 · 影响仍待核实</span>{projects.length>0?<>
    <div className="signal-project-links">{projects.map(p=><button key={p.id} aria-label={`进入客户画布：${p.title}`} onClick={()=>navigate('projects',{projectId:p.id,projectTitle:p.title,customer:p.customer,signalContext:signalProjectContext(item,p)})}><span><small>客户画布</small>{p.title}</span><ArrowUpRight size={14}/></button>)}</div>
    <small>{projects.some(p=>p.relation_scope==='explicit_project_reference')?'资料明示关联，不代表业务关系或项目影响已确认。':'按已核对的客户身份关联，业务影响待核实。'}</small>
  </>:<small>尚无已核对的关联项目</small>}</div>;
}

export function SignalChain({item,navigate}) {
  const [selected,setSelected]=useState('source'), panelRef=useRef(null), id=useId();
  const projects=item.related_projects||[], source=publicUrl(item.source_url);
  useEffect(()=>{
    let active=true, context;
    if(window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
    import('gsap').then(({gsap})=>{
      if(!active||!panelRef.current||panelRef.current.offsetParent===null)return;
      context=gsap.context(()=>gsap.fromTo(panelRef.current,{opacity:.7,y:4},{opacity:1,y:0,duration:.18,ease:'power2.out',clearProps:'opacity,transform'}),panelRef.current);
    }).catch(()=>{});
    return()=>{active=false;context?.revert();};
  },[selected,item.id]);
  const nodes=[
    {key:'source',Icon:FileSearch,label:'公开事实',title:item.title||item.summary||'具体事实待核实',meta:item.source||'来源待核实'},
    {key:'relations',Icon:Building2,label:'关联到客户',title:item.customer||'主体待核实',meta:projects.length?`${projects[0].title}${projects.length>1?` · 共 ${projects.length} 个项目`:''}`:'关联项目待核对'},
    {key:'action',Icon:Search,label:'AI 判断与核实',title:item.impact_judgment||'影响待核实',meta:item.recommended_action||'核实动作待准备'}
  ];
  return <div className="signal-chain" aria-label={`${item.customer}的信号关联链`}>
    <div className="signal-chain-nodes" role="group" aria-label="点选卡片查看相关内容">{nodes.map(({key,Icon,label,title,meta},index)=><React.Fragment key={key}>{index>0&&<span className="signal-chain-connector" aria-hidden="true"><span>{index===1?'资料关联':'提供依据'}</span><ArrowRight size={18}/></span>}<button type="button" className={`signal-chain-node node-${key}`} aria-pressed={selected===key} aria-controls={`${id}-detail`} onClick={()=>setSelected(key)}><span className="signal-node-icon"><Icon size={18}/></span><span className="signal-node-copy"><small>{label}</small><strong title={title}>{title}</strong><span title={meta}>{meta}</span></span><ChevronDown size={15}/></button></React.Fragment>)}</div>
    <div className={`signal-chain-detail detail-${selected}`} id={`${id}-detail`} ref={panelRef}>
      <div hidden={selected!=='source'}><div className="signal-detail-heading"><strong>来源摘要</strong>{source&&<a href={source} target="_blank" rel="noreferrer">{item.source||'核对原文'} <ArrowUpRight size={13}/></a>}</div><p>{item.summary||'来源尚未收录摘要，请核对原文。'}</p><div className="signal-detail-meta"><time>来源日期 {item.published_at||'待核实'}</time><span>{item.freshness_label||'时效待核实'}</span></div></div>
      <div hidden={selected!=='relations'}><div className="signal-detail-heading"><strong>{item.customer||'客户主体待核实'}</strong><span>项目保持各自的判断和跟进记录</span></div><SignalProjectLinks item={item} navigate={navigate}/></div>
      <div hidden={selected!=='action'}><div className="signal-action-columns"><div><span className="signal-owner"><Bot size={14}/> AI 提供判断</span><p>{item.impact_judgment||'影响待核实'}</p></div><div><span className="signal-owner owner-human"><UserRound size={14}/> 你决定跟进</span><p>{item.recommended_action||'下一次沟通核实内容待准备'}</p>{projects.length>0&&<div className="signal-action-handoff"><small>进入客户画布，沿用同一跟进</small>{projects.map(project=><button type="button" key={project.id} aria-label={`进入客户画布：${project.title}`} onClick={()=>navigate('projects',{projectId:project.id,projectTitle:project.title,customer:project.customer,signalContext:signalProjectContext(item,project)})}>{project.title}<ArrowUpRight size={13}/></button>)}</div>}</div></div></div>
    </div>
  </div>;
}

export function SignalRows({rows=[],navigate}) {
  return <><p className="discovery-boundary">相对时间按原文日期理解；当前可投机会以待你准入的截止核验为准。</p><div className="signal-rows signal-event-feed">{rows.map(item=><details className="signal-event" key={signalKey(item)}>
    <summary className="signal-event-summary"><span className="signal-feed-icon"><Radio size={16}/></span><span className="signal-event-identity"><strong>{item.customer}</strong><time>来源日期 {item.published_at||'待核实'}</time></span><span className="signal-event-headline"><strong>{item.title}</strong><span>{item.signal_type||'公开信息'} · {item.freshness_label||'时效待核实'}</span></span><span className="signal-link-count"><GitBranch size={14}/>{item.related_projects?.length||'—'}<span> 关联</span></span><ChevronRight className="signal-open-chevron" size={16}/></summary>
    <SignalChain item={item} navigate={navigate}/>
  </details>)}</div></>;
}

export function ResearchOverview({data,error,compact=false}) {
  const receipt=data?.runs?.[0], task=data?.task, tender=data?.tender_receipt, opportunity=data?.opportunity_receipt;
  const tenderJob=data?.operations?.jobs?.tender;
  const tenderState=currentState(tenderJob,tender);
  const opportunityState=currentState(data?.opportunity_task,opportunity);
  const overview=<section className="research-overview" aria-label="每日研究运行概览">
    <div className="research-overview-heading"><div><Radio size={19}/><strong>每日研究</strong><span>06:00 自动运行</span></div><span className="research-state"><Clock3 size={14}/> 各项独立回执</span></div>
    <div className="research-channel-grid">
      <article data-state={stateTone(task?.status,task?.overdue||!!error)}><Building2 size={20}/><div><span>客户公开资料</span><strong>{receipt?.checked_customers?.length??'—'}<small>家已覆盖</small></strong><p>新增 {receipt?.new_count??'—'} 条 · 更新 {receipt?.updated_count??'—'} 条</p><small>{error?'读取未完成':task?.label||'等待回执'} · {stamp(receipt?.at||task?.last_attempt_at)}</small></div></article>
      <article data-state={stateTone(tenderState)}><FileSearch size={20}/><div><span>招采核查</span><strong>{tender?.detail_count??'—'}<small>条详情已核查</small></strong><p>{({ok:'本轮已完成',no_result:'已查，无新记录',search_unavailable:'本轮未完成',running:'核查中',error:'本轮未完成',failed:'本轮未完成',partial:'部分核查'})[tenderState]||'等待回执'}</p><small>{tenderState==='running'?'本轮开始 '+stamp(tenderJob?.current_started_at):'最近保存 '+stamp(tender?.at)}</small></div></article>
      <article data-state={stateTone(opportunityState,data?.opportunity_task?.overdue)}><Search size={20}/><div><span>新客户搜索</span><strong>{opportunity?.candidate_added_count??'—'}<small>个新增线索</small></strong><p>{data?.opportunity_task?.overdue?'本轮尚未收到搜索回执':({ok:'本轮已完成',no_change:'已查，无新增线索',failed:'本轮未完成',error:'本轮未完成',no_import:'覆盖待核实',running:'正在搜索'})[opportunityState]||'等待回执'}</p><small>最近保存 {stamp(opportunity?.at)}</small></div></article>
    </div><div className="research-overview-foot"><span>数量来自最近已保存回执，未完成项不代表本轮覆盖</span><span>搜索结果 ≠ 已确认商机</span></div>
    <details className="research-receipt-detail"><summary>查看本轮范围、来源和覆盖缺口</summary><ResearchStatus data={data} error={error}/></details>
  </section>;
  if(!compact)return overview;
  const gaps=[error||task?.overdue||['error','failed','partial'].includes(task?.status)||!receipt?'客户研究':null,['error','failed','partial','search_unavailable'].includes(tenderState)||!tender?'招采核查':null,data?.opportunity_task?.overdue||['error','failed','no_import'].includes(opportunityState)||!opportunity?'新客户搜索':null].filter(Boolean);
  return <details className="research-compact"><summary><span>研究回执</span><span className={gaps.length?'research-incomplete':''}>{gaps.length?gaps.join('、')+'尚未完整回传':'最近客户研究 '+stamp(receipt?.at)} · 展开核对</span></summary>{overview}</details>;

}

export function OpportunityResearchReceipt({task,receipt}) {
  const hasReceipt=!!receipt?.at, status=currentState(task,receipt);
  const completed=['ok','no_change'].includes(status);
  const completedAt=completed ? receipt?.checked_at||task?.last_success_at||receipt?.at : task?.last_success_at;
  const queries=Array.isArray(receipt?.checked_queries)?receipt.checked_queries:Array.isArray(task?.searched_queries)?task.searched_queries:null;
  const notes=Array.isArray(receipt?.coverage_notes)?receipt.coverage_notes:[];
  const exclusions=Array.isArray(receipt?.reviewed_exclusions)?receipt.reviewed_exclusions:null;
  const sources=Array.isArray(receipt?.source_links)?receipt.source_links:[];
  const label=task?.overdue?'本轮尚未收到搜索回执':({ok:'本轮已完成',no_change:'本轮已查，无新增线索',failed:'本轮搜索未完成',error:'本轮搜索未完成',no_import:'已回传，覆盖待核实',running:'正在搜索'})[status]||'尚未收到搜索回执';
  const scope=[...new Set((queries||[]).map(q=>typeof q==='object'?q?.group:'').filter(Boolean))].join('、')||receipt?.scope;
  return <>
    <p className="tender-receipt opportunity-receipt"><strong>新客户搜索</strong> · {label} · 上次实际完成 {completedAt?stamp(completedAt):'尚无完成回执'}
      {hasReceipt&&<> · {queries?`回执查询 ${queries.length} 式`:'查询数未提供'} · 新增客户线索 {receipt.candidate_added_count??'未提供'}{receipt.candidate_added_count!=null?' 个':''} · {exclusions?`核对与排除说明 ${exclusions.length} 条`:'核对与排除说明未提供'}</>}
      <small>{hasReceipt?(scope?`查询范围：${scope}`:'查询范围未提供。'):'查询范围、新增线索和核对排除说明尚待回传。'}{task?.error&&` ${task.error}`}</small>
    </p>
    {hasReceipt&&<details className="research-gaps"><summary>新客户搜索范围与覆盖缺口</summary>
      {queries?.map((query,i)=><p key={`query:${i}`}>搜索：{typeof query==='string'?query:[query?.group,query?.query].filter(Boolean).join(' · ')||'查询内容未提供'}</p>)}
      {notes.length?notes.map((note,i)=><p key={`note:${i}`}>{typeof note==='string'?note:[note?.group||note?.type,note?.result||note?.note,note?.gap&&`覆盖缺口：${note.gap}`].filter(Boolean).join(' · ')||'覆盖说明未提供'}</p>):<p>覆盖缺口未提供，不能据此认定已完整覆盖。</p>}
      {exclusions?.map((item,i)=><p key={`exclusion:${i}`}>核对与排除说明：{typeof item==='string'?item:[item?.company||item?.title,item?.reason||'原因未提供'].filter(Boolean).join(' · ')}{publicUrl(item?.source_url)&&<> · <a href={publicUrl(item.source_url)} target="_blank" rel="noreferrer">原文 ↗</a></>}</p>)}
      {sources.map((source,i)=>{const url=publicUrl(typeof source==='string'?source:source?.url);return <p key={`source:${i}`}>来源依据：{url?<a href={url} target="_blank" rel="noreferrer">{source?.title||new URL(url).hostname} ↗</a>:'链接未提供或格式无效'} · 核读状态：{source?.read_status||'未提供'}{source?.supports&&` · 支持依据：${source.supports}`}</p>;})}
    </details>}
  </>;
}

export function ResearchStatus({data,error,compact=false}) {
  const task=data?.task,receipt=data?.runs?.[0],tender=data?.tender_receipt;
  const tenderState=currentState(data?.operations?.jobs?.tender,tender);
  return <div className={'research-status '+(task?.overdue||error?'needs-attention':'')} role="status">
    <strong>{error?'公开信号读取未完成':task?.label||'正在读取公开研究成果…'}</strong>
    {task&&<span>最近回传 {stamp(task.last_attempt_at)} · 每天 06:00 后台搜索</span>}
    {receipt?.checked_customers?.length>0&&<span>本轮覆盖 {receipt.checked_customers.length} 家 · 新增 {receipt.new_count??'待核对'} 条 · 更新 {receipt.updated_count??'待核对'} 条</span>}
    {!compact&&receipt?.checked_customers?.length>0&&<p className="research-coverage">客户研究：{receipt.checked_customers.join('、')}。{receipt.checked_queries?.length>0&&`共 ${receipt.checked_queries.length} 个搜索式；`}未检出不等于没有变化。</p>}
    {!compact&&tender&&<p className="tender-receipt"><strong>标讯核查</strong> · {({ok:'已完成',no_result:'已查，无新记录',search_unavailable:'本轮未完成',running:'核查中',failed:'本轮未完成',error:'本轮未完成',partial:'部分核查'})[tenderState]||'等待回执'} · {stamp(tender.at)}{tender.search_total!=null&&` · 平台命中 ${tender.search_total} 条`}{tender.searched_item_count!=null&&` · 本轮读取 ${tender.searched_item_count} 条`}{tender.detail_count!=null&&` · 详情核查 ${tender.detail_count} 条`}{` · 当前待准入 ${tender.current_candidate_count??'待核实'} 个`}{tender.error&&` · ${tender.error}`}<small>平台命中数不代表逐条核实；招采按最早截止保留 14–30 天准备时间。</small></p>}
    {!compact&&data&&<OpportunityResearchReceipt task={data.opportunity_task} receipt={data.opportunity_receipt}/>}
    {!compact&&receipt?.coverage_notes?.length>0&&<details className="research-gaps"><summary>本轮覆盖说明与未核实来源</summary>{receipt.coverage_notes.map((note,i)=><p key={i}>{typeof note==='string'?note:JSON.stringify(note)}</p>)}</details>}
    {!compact&&task?.error&&<p>{task.error}</p>}{error&&<p>{error}。已有结果保留，不能据此判断没有新变化。</p>}
  </div>;
}

export function PublicSignalBrief({navigate,refreshKey,customer='',projectId='',compact=false,layout=''}) {
  const {data,error}=usePublicSignals(refreshKey),[selectedKey,setSelectedKey]=useState(null);
  const rows=(data?.signals||[]).filter(x=>projectId?x.related_projects?.some(p=>p.id===projectId):!customer||x.customer===customer||x.related_projects?.some(p=>p.customer===customer));
  const unique=[...new Map(rows.map(x=>[x.customer,rows.find(r=>r.customer===x.customer)])).values()];
  const visible=(customer||projectId?rows:unique).slice(0,3),selected=rows.find(item=>signalKey(item)===selectedKey);
  const receipt=data?.runs?.[0], task=data?.task;
  const tenderState=currentState(data?.operations?.jobs?.tender,data?.tender_receipt);
  const opportunityState=currentState(data?.opportunity_task,data?.opportunity_receipt);
  if(layout==='summary')return <section className="home-signal-summary" aria-label="每日公开信号"><header><h2>公开信号</h2><small>{error?'读取失败，保留历史':data?task?.label||'已有保存记录':'正在读取…'} · 回传 {stamp(task?.last_attempt_at)}</small><button onClick={()=>navigate('discover')}>查看全部 {data?rows.length:'—'} →</button></header>{visible.map(item=><button className="home-signal-row" key={signalKey(item)} onClick={()=>setSelectedKey(selectedKey===signalKey(item)?null:signalKey(item))}><span>{item.title}</span></button>)}{data&&!visible.length&&<p>尚无已保存信号；不代表研究已完整完成。</p>}{error&&<p role="alert">{error}</p>}{selected&&<SignalChain item={selected} navigate={navigate}/>}</section>;
  const ribbon=layout==='ribbon'||layout==='rail';
  return <section className={'public-signal-brief signal-intelligence '+(compact?'is-compact ':'')+(ribbon?'is-ribbon':'')} aria-label={projectId?'相关公开资料':'每日公开信号'}>
    <header><div className="signal-brief-heading"><span className="signal-section-icon"><Radio size={18}/></span><div><h2>{projectId?'相关公开资料':'每日公开信号'}</h2><span>{projectId?'公开变化与本项目的关系':'06:00 自动研究 · 点击信号查看关联与下一步'}</span></div></div><button className="signal-all-link" onClick={()=>navigate('discover')}>全部 {data?rows.length:'—'} 条 <ArrowUpRight size={14}/></button></header>
    <div className="signal-run-line" role="status"><span className={`signal-run-state is-${stateTone(task?.status,task?.overdue||!!error)}`}><i/>{error?'公开信号读取未完成':task?.label||'正在读取研究成果…'}</span><span>最近回传 {stamp(task?.last_attempt_at)}</span><span className="signal-run-counts"><b>{receipt?.checked_customers?.length??'—'}</b> 家覆盖<span>·</span><b>{receipt?.new_count??'—'}</b> 新增<span>·</span><b>{receipt?.updated_count??'—'}</b> 更新</span><span className="signal-run-secondary"><span className={`signal-channel-dot is-${stateTone(tenderState)}`}/>招采 · {({running:'核查中',ok:'已保存',no_result:'无新记录',failed:'未完成',error:'未完成',partial:'部分核查',search_unavailable:'未完成'})[tenderState]||'待回执'}</span><span className="signal-run-secondary"><span className={`signal-channel-dot is-${stateTone(opportunityState,data?.opportunity_task?.overdue)}`}/>新客户 · {data?.opportunity_task?.overdue?'待回执':({running:'搜索中',ok:'已保存',no_change:'无新增',failed:'未完成',error:'未完成',no_import:'待核实'})[opportunityState]||'待回执'}</span></div>
    {(error||task?.error)&&<p className="signal-read-error">{error||task.error}。已有资料保留，不能据此判断没有新变化。</p>}
    <div className="signal-preview-grid">{visible.map(item=><button type="button" className="signal-preview-card" key={signalKey(item)} aria-expanded={selectedKey===signalKey(item)} onClick={()=>setSelectedKey(previous=>previous===signalKey(item)?null:signalKey(item))}><span className="signal-preview-meta"><strong>{item.customer}</strong><time>{item.published_at||'日期待核实'}</time></span><span className="signal-preview-title">{item.title}</span><span className="signal-preview-bottom"><span>{item.signal_type||'公开信息'}</span><span><GitBranch size={13}/>{item.related_projects?.length?`${item.related_projects.length} 个项目`:'关联待核对'}<ChevronDown size={14}/></span></span></button>)}</div>
    {selected&&<div className="signal-ribbon-detail"><div className="signal-ribbon-detail-heading"><strong>{selected.title}</strong><button type="button" aria-label="收起信号关联" onClick={()=>setSelectedKey(null)}><X size={16}/></button></div><SignalChain key={signalKey(selected)} item={selected} navigate={navigate}/></div>}
    {ribbon&&!projectId&&<OperationsSummary data={data}/> }
    {data&&!rows.length&&<p className="signal-empty">{projectId?'尚未有已核对关联到本项目的公开资料。':'当前没有已保存的公开信号。搜索是否完成请以上方回执为准。'}</p>}
  </section>;
}

export function OperationsSummary({data}) {
  const jobs=data?.operations?.jobs||{};
  const labels={ready:'已完成',running:'处理中',waiting:'等待下一轮',error:'待重试',partial:'部分更新',failed:'未完成',needs_input:'需处理'};
  return <details className="homepage-operations"><summary><span className="homepage-operations-label"><Bot size={15}/>后台自动处理</span><span className="homepage-operation-jobs">{[['communications','沟通整理'],['tender','招采核查']].map(([key,label])=><span key={key} data-status={jobs[key]?.status||'unknown'}><i/>{label}<b>{labels[jobs[key]?.status]||'状态待读取'}</b></span>)}</span><span className="homepage-human-role"><UserRound size={14}/>你来确认范围与承诺<ChevronDown size={14}/></span></summary><OperationsStrip data={data}/></details>;
}

export function OperationsStrip({data}) {
  const jobs=data?.operations?.jobs||{};
  const labels={ready:'最近完成',running:'后台处理中',waiting:'等待下一轮',error:'待自动重试',partial:'部分更新',failed:'更新未完成',needs_input:'需要处理'};
  const timing=(key,job)=>job.status==='running'&&job.current_started_at?`本轮开始 ${stamp(job.current_started_at)}`:job.current_finished_at?`本轮结束 ${stamp(job.current_finished_at)}`:(key==='tender'?data?.tender_receipt?.last_success_at:job.last_success_at)?`上次完成 ${stamp(key==='tender'?data?.tender_receipt?.last_success_at:job.last_success_at)}`:`最近检查 ${stamp(job.last_attempt_at)}`;
  return <section className="operations-strip" aria-label="后台与人工分工"><h2>后台在做什么，你负责什么</h2>
    <div><strong><Bot size={17}/>自动运行</strong><p>公开研究每天 06:00；已连接沟通来源每小时整理；CRM 每天上午 10 点（北京时间）只读同步一次；新材料自动更新项目判断。</p>
      {Object.entries(jobs).map(([key,job])=><span className="operation-state" key={key}>{{crm:'CRM',communications:'沟通整理',tender:'招采核查',external_outbox:'本地待处理队列'}[key]||'后台检查'} · {labels[job.status]||'等待'} · {timing(key,job)}{job.error&&` · ${job.error}`}</span>)}</div>
    <div><strong><UserRound size={17}/>需要你补充或决定</strong><p>未记录的谈话、设备与来源连接、归属纠正；是否准入、联系客户、投入方案，以及报价合同等正式承诺。</p></div>
  </section>;
}
