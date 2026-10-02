import {K100CustomerDirectory} from './K100CustomerDirectory.jsx';
import {projectNeed} from './projectPresentation.js';
import {useK100Summary,K100ProjectContext,K100IdentityQuestion,K100_URL} from './K100Workspace.jsx';
import {usePublicSignals} from './PublicSignals.jsx';
import {CustomerFiles} from './CustomerFiles.jsx';
import ProjectNotifications,{NotificationChanges} from './ProjectNotifications.jsx';
import {ProjectArchiveDialog,ArchiveStatus} from './ProjectArchive.jsx';
import {selectProjectOverview} from './models/workbenchViewModel.js';
import {ProjectTable} from './components/workbench/ProjectTable.jsx';
import {CustomerMeeting} from './CustomerMeeting.jsx';
import { meetingKey, restoreMeeting, addMeetingTopic } from './customerMeeting.js';
import { CustomerDirectory } from './CustomerDirectory.jsx';
import { customerDirectory } from './customerDirectory.js';
import DiscoveryWorkspace from './DiscoveryWorkspace.jsx';
import { ProjectConnections } from './ProjectConnections.jsx';
import { PublicSignalBrief } from './PublicSignals.jsx';
import { ProjectListSkeleton } from './WorkbenchLoading.jsx';
import { readProjectSnapshot, writeProjectSnapshot } from './workbenchStartup.js';
import React, { useEffect, useLayoutEffect, useState, useRef, useCallback } from "react";
import './project-decision.css';
import './workspace-redesign.css';
import './concept-workspace.css';
import { ArrowUpRight, ArrowRight, Building2, CheckCircle2, ChevronDown, CircleHelp, Clock3, GitBranch, Layers3, PauseCircle, Search, X } from 'lucide-react';
import gsap from 'gsap';
import { useDiscardChanges } from "./DiscardDialog.jsx";
import { api } from "./api.js";
import { ProjectAnalysis } from "./ProjectAnalysis.jsx";
import { installLiveRefresh } from "./liveRefresh.js";
import { ProjectFollowups } from "./ProjectFollowups.jsx";
import { ProjectRound } from "./ProjectRound.jsx";
import { SourceText } from './SourceText.jsx';
import { STAGES, ATTENTIONS, OVERVIEW_KEY, readOverviewPreference, recognizedCustomer, hasCurrentBrief, stageDistribution, scopeProjects, projectConnections, orderOverviewProjects } from './projectOverview.js';

const sourceUrl = (path) => `obsidian://open?vault=${encodeURIComponent("工作台用户销售知识库")}&file=${encodeURIComponent(path)}`;
const statusLabels={empty:'待分析',queued:'已排队',running:'分析中',ready:'已分析',stale:'需更新',error:'分析未完成'};
const displayCustomer=value=>String(value||'客户待核实').split('/').pop();
const attentionIcons={'可推进':ArrowUpRight,'等反馈':Clock3,'需核实':CircleHelp,'暂缓':PauseCircle};

export function ProjectWorkspace({ directoryOnly=false, onOpenNotification, notificationContext, onBack, navigate, initialProjectId = "", initialAccountId, onAccountSelected, signalContext, refreshKey, onActionsChanged, registerNavigationGuard, onProjectSelected, overviewReset=0 }) {
  const {value:crmSummary,error:crmError}=useK100Summary(refreshKey);
  const {data:signalData}=usePublicSignals(refreshKey?.generated_at);
  const [snapshot] = useState(() => readProjectSnapshot(localStorage));
  const [projects,setProjects]=useState(snapshot?.projects || []);
  const [verified,setVerified]=useState(false);
  const [selected,setSelected]=useState(initialProjectId);
  const [verifiedSelection,setVerifiedSelection]=useState(null);
  const [preference]=useState(()=>readOverviewPreference(sessionStorage));
  const consumedReset=useRef(preference.resetToken||0);
  const [directoryMode,setDirectoryMode]=useState(directoryOnly?'customers':'projects');
  const [meetingRequest,setMeetingRequest]=useState(null);
  const [accountId,setAccountId]=useState(initialProjectId?'':initialAccountId??preference.accountId??'');
  const [accounts,setAccounts]=useState([]),[accountsLoading,setAccountsLoading]=useState(true),[accountsError,setAccountsError]=useState('');
  const accountGuard=useRef(null);
  const registerAccountGuard=useCallback(guard=>{accountGuard.current=guard;return()=>{if(accountGuard.current===guard)accountGuard.current=null;};},[]);
  useEffect(()=>{let live=true;const read=async()=>{try{const value=await api.get('/api/account-advancement');if(live){setAccounts(value.accounts||[]);setAccountsError('');}}catch(error){if(live)setAccountsError(error.message);}finally{if(live)setAccountsLoading(false);}};read();const stop=installLiveRefresh(read);return()=>{live=false;stop();};},[refreshKey]);

  const [commitments,setCommitments]=useState([]);
  const receiveCommitments=useCallback(items=>setCommitments(items),[]);
  const [batchMode,setBatchMode]=useState(false);
  const [workMode,setWorkMode]=useState(preference.workMode||'needs');
  const [filtersOpen,setFiltersOpen]=useState(false);
  const [archiveScope,setArchiveScope]=useState('active'),[archiveRequest,setArchiveRequest]=useState(null),[selectedIds,setSelectedIds]=useState([]);
  const onSelectArchive=(id,checked)=>setSelectedIds(ids=>checked?[...new Set([...ids,id])]:ids.filter(x=>x!==id));
  async function requestArchive(rows,action){if(!verified)return;if(!await canLeave())return;setArchiveRequest({projects:rows,action});}
  const [query,setQuery]=useState(preference.query||'');
  const [customerFilter,setCustomerFilter]=useState(preference.customerFilter||'');
  const [stageFilter,setStageFilter]=useState(preference.stageFilter||'全部');
  const [attentionFilter,setAttentionFilter]=useState(preference.attentionFilter||'全部');
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(true);
  const [source,setSource]=useState(null);
  const [sourceBusy,setSourceBusy]=useState(false);
  const [receipt,setReceipt]=useState('');
  const [roundRefresh,setRoundRefresh]=useState(0);
  const [roundReload,setRoundReload]=useState(0);
  const refreshRequest=useRef(0);
  const askDiscard = useDiscardChanges();
  const [dirtyKeys,setDirtyKeys]=useState([]);
  const [savingCount,setSavingCount]=useState(0);
  const dirtyActions=useRef(new Set()),savingActions=useRef(new Set()),leaveDecision=useRef(null);
  const sourceScroll=useRef(0);
  const sourceViewport=useRef('');
  const sourceTrigger=useRef(null);
  useLayoutEffect(()=>{
    if(!sourceViewport.current) return;
    const body=drawer.current?.querySelector('.drawer-body');
    const returning=sourceViewport.current==='return';
    sourceViewport.current='';
    if(body) body.scrollTop=returning?sourceScroll.current:0;
    const focus=returning?sourceTrigger.current:body?.querySelector('.source-reader header button');
    if(focus?.isConnected) focus.focus({preventScroll:true});
  },[source]);
  function closeSource(){sourceRequest.current++;sourceViewport.current='return';setSource(null);}
  const sourceRequest=useRef(0),drawer=useRef(null),overviewRoot=useRef(null),transitionPending=useRef(false);
  const live=useRef(true),restored=useRef(false);
  const lastTrigger=useRef(preference.lastTrigger||initialProjectId||'');
  const scrollPosition=useRef({scrollMain:preference.scrollMain||0,scrollWindow:preference.scrollWindow||0});
  const markDirty=useCallback((id,dirty)=>{if(dirty)dirtyActions.current.add(id);else dirtyActions.current.delete(id);setDirtyKeys([...dirtyActions.current]);},[]);
  const markSaving=useCallback((id,saving)=>{if(saving)savingActions.current.add(id);else savingActions.current.delete(id);setSavingCount(savingActions.current.size);},[]);
  const canLeave=useCallback(async()=>{
    if(savingActions.current.size || transitionPending.current)return false;
    if(accountGuard.current&&!await accountGuard.current())return false;
    if(!dirtyActions.current.size)return true;
    return await askDiscard('当前项目有未保存内容。继续编辑可保留输入。') && !savingActions.current.size;
  },[askDiscard]);
  useEffect(()=>registerNavigationGuard?.(canLeave),[registerNavigationGuard,canLeave]);
  useEffect(()=>{live.current=true;return()=>{live.current=false;leaveDecision.current?.(false);leaveDecision.current=null;};},[]);
  useEffect(()=>{const warn=e=>{if(dirtyActions.current.size||savingActions.current.size){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[]);
  useEffect(()=>{if(initialAccountId!==undefined)setAccountId(initialAccountId);},[initialAccountId]);
  useEffect(()=>{setSelected(initialProjectId);if(initialProjectId)setAccountId('');},[initialProjectId]);
  useEffect(()=>{if(overviewReset&&overviewReset!==consumedReset.current){consumedReset.current=overviewReset;scrollPosition.current={scrollMain:0,scrollWindow:0};lastTrigger.current='';requestAnimationFrame(()=>{document.querySelector('.app-main')?.scrollTo({top:0,behavior:'instant'});window.scrollTo({top:0,behavior:'instant'});});setSelected('');setAccountId('');setQuery('');setCustomerFilter('');setStageFilter('全部');setAttentionFilter('全部');try{sessionStorage.setItem(OVERVIEW_KEY,JSON.stringify({...readOverviewPreference(sessionStorage),query:'',customerFilter:'',accountId:'',stageFilter:'全部',attentionFilter:'全部',resetToken:overviewReset,scrollMain:0,scrollWindow:0,lastTrigger:''}));}catch{}}},[overviewReset]);
  useEffect(()=>{
    const persist=()=>{try{sessionStorage.setItem(OVERVIEW_KEY,JSON.stringify({query,customerFilter,stageFilter,attentionFilter,directoryMode,workMode,accountId,resetToken:consumedReset.current,lastTrigger:lastTrigger.current,...scrollPosition.current}));}catch{}};
    persist();
    const main=document.querySelector('.app-main');
    const remember=()=>{if(!drawer.current?.open){scrollPosition.current={scrollMain:main?.scrollTop||0,scrollWindow:window.scrollY};persist();}};
    main?.addEventListener('scroll',remember);window.addEventListener('scroll',remember);
    return()=>{persist();main?.removeEventListener('scroll',remember);window.removeEventListener('scroll',remember);};
  },[query,customerFilter,stageFilter,attentionFilter,directoryMode,workMode,accountId]);
  const refresh=useCallback(async()=>{
    const request=++refreshRequest.current;
    try{const result=await api.get('/api/project-workspace/overview');if(live.current&&request===refreshRequest.current){setProjects(result.projects);setVerified(true);window.dispatchEvent(new Event('project-data-refreshed'));writeProjectSnapshot(localStorage,result.projects);setError('');}return result.projects;}
    catch(e){if(live.current&&request===refreshRequest.current)setError(e.message);}
    finally{if(live.current&&request===refreshRequest.current)setLoading(false);}
  },[]);
  // A project drawer only needs fresh project identity/material links here.
  // ProjectAnalysis and write surfaces verify their own current state; do not
  // serialize them behind the expensive all-project analysis overview.
  useEffect(()=>{
    if(verified||!selected)return;
    let active=true;
    api.get('/api/project-workspace').then(result=>{
      if(active)setVerifiedSelection(result.projects.find(item=>item.id===selected)||null);
    }).catch(()=>{}); // The overview still owns the visible retry/error path.
    return()=>{active=false;};
  },[selected,verified,refreshKey]);
  useEffect(()=>{refresh();},[refreshKey,refresh]);
  useEffect(()=>installLiveRefresh(refresh),[refresh]);
  useEffect(()=>{
    let stopped=false,timer;const poll=async()=>{await refresh();if(!stopped)timer=setTimeout(poll,10000);};timer=setTimeout(poll,10000);return()=>{stopped=true;clearTimeout(timer);};
  },[refresh]);
  useLayoutEffect(()=>{
    if(loading||restored.current)return;restored.current=true;
    const frame=requestAnimationFrame(()=>{document.querySelector('.app-main')?.scrollTo({top:scrollPosition.current.scrollMain,behavior:'instant'});window.scrollTo({top:scrollPosition.current.scrollWindow,behavior:'instant'});if(!selected)document.querySelector(`[data-project-trigger="${lastTrigger.current}"]`)?.focus({preventScroll:true});});
    return()=>cancelAnimationFrame(frame);
  },[loading,selected]);
  const overview=selectProjectOverview(projects,{query,customer:customerFilter,stage:stageFilter,attention:attentionFilter,archive:archiveScope});
  const {scope:scopedProjects,distribution,current:scopedCurrent,history:scopedHistory,items:filteredProjects,attentionScope,attentionCounts}=overview;
  const neededProjects=filteredProjects.filter(p=>projectNeed(p,commitments.filter(x=>x.project_id===p.id)).actionable);
  const displayed=workMode==='needs'?neededProjects:filteredProjects;
  useLayoutEffect(()=>{
    const mm=gsap.matchMedia();
    const context=gsap.context(()=>{mm.add('(prefers-reduced-motion: no-preference)',()=>{const meters=overviewRoot.current?.querySelectorAll('.stage-meter-fill'),rows=overviewRoot.current?.querySelectorAll('.project-overview-row');if(meters?.length)gsap.fromTo(meters,{scaleX:0},{scaleX:(_,el)=>Number(el.dataset.share)||0,duration:.2,ease:'power2.out',transformOrigin:'left center'});if(rows?.length)gsap.fromTo(rows,{autoAlpha:.55,y:3},{autoAlpha:1,y:0,duration:.16,ease:'power1.out',clearProps:'opacity,visibility,transform'});});},overviewRoot);
    return()=>{mm.revert();context.revert();};
  },[JSON.stringify(distribution.counts),stageFilter,attentionFilter,query,customerFilter]);
  async function choose(id,{customer,reset=false}={}){
    if(!await canLeave())return false;
    transitionPending.current=true;
    if(id&&!drawer.current?.open){scrollPosition.current={scrollMain:document.querySelector('.app-main')?.scrollTop||0,scrollWindow:window.scrollY};try{sessionStorage.setItem(OVERVIEW_KEY,JSON.stringify({query,customerFilter,stageFilter,attentionFilter,directoryMode,accountId:'',resetToken:consumedReset.current,lastTrigger:id,...scrollPosition.current}));}catch{}}
    try{
      if(drawer.current&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches)await new Promise(resolve=>gsap.to(drawer.current,{y:10,autoAlpha:0,duration:.16,ease:'power1.in',onComplete:resolve}));
      sourceRequest.current++;setSource(null);setReceipt('');setAccountId('');
      if(reset){scrollPosition.current={scrollMain:0,scrollWindow:0};lastTrigger.current='';setQuery('');setCustomerFilter('');setStageFilter('全部');setAttentionFilter('全部');requestAnimationFrame(()=>{document.querySelector('.app-main')?.scrollTo({top:0,behavior:'instant'});window.scrollTo({top:0,behavior:'instant'});});}
      if(customer){setQuery('');setCustomerFilter(customer);setStageFilter('全部');setAttentionFilter('全部');}
      if(id)lastTrigger.current=id;
      setSelected(id);onProjectSelected?.(id,projects.find(p=>p.id===id)||{});dirtyActions.current.clear();setDirtyKeys([]);
      if(!id)requestAnimationFrame(()=>document.querySelector(`[data-project-trigger="${lastTrigger.current}"]`)?.focus({preventScroll:true}));
    }finally{transitionPending.current=false;}
    return true;
  }
  async function prepareTopic(projectId,topic){
    const row=customerDirectory(accounts,projects).find(item=>item.projects.some(p=>p.id===projectId));
    if(!row)return;
    if(!await canLeave())return;
    try{
      const key=meetingKey(row.id),raw=localStorage.getItem(key);
      const draft=restoreMeeting(raw?JSON.parse(raw):null,row.projects);
      localStorage.setItem(key,JSON.stringify(addMeetingTopic(draft,projectId,topic)));
      setMeetingRequest({rowId:row.id,row,projectId,token:Date.now()});
      requestAnimationFrame(()=>document.querySelector('.customer-meeting')?.scrollIntoView({block:'start'}));
    }catch(error){setError('沟通准备未保存：'+error.message);}
  }
  function commitAction(projectId,actionId,saved){setProjects(current=>current.map(p=>p.id!==projectId?p:{...p,plan_revision:saved.revision,actions:p.actions.map(a=>a.id===actionId?{...a,record:saved.record}:a)}));}
  async function openSource(item){sourceScroll.current=drawer.current?.querySelector('.drawer-body')?.scrollTop||0;sourceTrigger.current=document.activeElement;const request=++sourceRequest.current;setSourceBusy(true);setError('');try{const value=await api.get(`/api/project-workspace/source?project_id=${selected}&path=${encodeURIComponent(item.path)}`);if(request===sourceRequest.current){sourceViewport.current='open';setSource(value);}}catch(e){if(request===sourceRequest.current)setError(e.message);}finally{if(request===sourceRequest.current)setSourceBusy(false);}}
  const project=verified ? projects.find(p=>p.id===selected) : verifiedSelection?.id===selected ? verifiedSelection : null;
  const readingSnapshot=!project&&!verified?projects.find(p=>p.id===selected):null;
  useEffect(()=>{if(project){lastTrigger.current=project.id;onProjectSelected?.(project.id,project);}},[project?.id,onProjectSelected]);
  const current=projects.filter(p=>p.is_current),historical=projects.filter(p=>!p.is_current);
  const actionableFirst=!query&&!customerFilter&&stageFilter==='全部'&&attentionFilter==='全部';
  const running=projects.find(p=>p.analysis_state==='running');
  const countsKnown=verified||Boolean(snapshot);
  return <div className="page-stack project-workspace project-overview workspace-redesign" ref={overviewRoot}>
    <header className="overview-heading overview-heading-compact workspace-overview-heading">
      <div className="workspace-heading-title"><h1>{directoryOnly?'客户目录':accountId?'客户跟进':customerFilter?displayCustomer(customerFilter):'项目工作台'}</h1><span className="overview-counts" hidden={Boolean(accountId)||directoryOnly}>{!countsKnown ? (loading?"正在读取项目":"项目数量待读取") : `${scopedProjects.length} 个项目`}</span></div>
      <div className="workspace-heading-tools" hidden={Boolean(accountId)}><label className="native-field workspace-project-search"><Search size={16} aria-hidden="true"/><span className="sr-only">搜索客户或项目</span><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索客户或项目" /></label>{customerFilter&&<button className="plain-action" onClick={()=>{setCustomerFilter('');setQuery('');}}>全部客户 ×</button>}<details className="overview-more"><summary>更多</summary><div className="workspace-shortcuts">{[['reports','项目群日报'],['reminders','提醒与日程'],['knowledge','全部沟通材料']].map(([view,label])=><button key={view} onClick={()=>navigate(view)}>{label}</button>)}</div></details></div>
    </header>
    {accountId&&<DiscoveryWorkspace key={`account:${accountId}`} accountId={accountId} relatedProjects={customerDirectory(accounts,projects).find(row=>row.account?.id===accountId)?.projects||[]} registerNavigationGuard={registerAccountGuard} onClose={()=>{onAccountSelected?.('');setAccountId('');requestAnimationFrame(()=>document.querySelector('.app-main')?.scrollTo({top:scrollPosition.current.scrollMain}));}} navigate={(view,options)=>view==='projects'&&options?.projectId?choose(options.projectId):navigate(view,options)}/>}
    <div hidden={Boolean(accountId)}>
    
    <div className="workspace-overview-grid"><section className="workspace-project-main" aria-label="项目推进工作区">

    <div className="customer-directory-mode" role="group" aria-label="客户与项目显示方式"><button aria-pressed={directoryMode==='projects'} onClick={async()=>{if(await canLeave())setDirectoryMode('projects');}}>项目工作面</button><button aria-pressed={directoryMode==='customers'} onClick={async()=>{if(await canLeave())setDirectoryMode('customers');}}>客户目录</button></div>
    {directoryMode==='customers'&&<K100CustomerDirectory query={query} projects={projects} summary={crmSummary?.projects||{}} signals={signalData?.signals||[]} markDirty={markDirty} markSaving={markSaving} canLeave={canLeave} onProject={id=>navigate('projects',{projectId:id})}/>}
    <div hidden={directoryMode!=='projects'}>
    <div className="focus-work-tabs"><div role="group" aria-label="项目处理范围"><button aria-pressed={workMode==='needs'} onClick={()=>setWorkMode('needs')}>需要我处理 <small>{neededProjects.length}</small></button><button aria-pressed={workMode==='all'} onClick={()=>setWorkMode('all')}>全部项目 <small>{filteredProjects.length}</small></button></div><button aria-expanded={filtersOpen} onClick={()=>setFiltersOpen(!filtersOpen)}>筛选{stageFilter!=='全部'||attentionFilter!=='全部'||archiveScope!=='active'?' · 已设置':''}</button></div><div hidden={!filtersOpen} className="workbench-filterbar" aria-label="项目筛选">    <div className="project-archive-toolbar"><label><select aria-label="项目归档范围" value={archiveScope} onChange={e=>{setArchiveScope(e.target.value);setSelectedIds([]);}}><option value="active">未归档</option><option value="archived">已归档</option><option value="all">全部</option></select></label>{selectedIds.length>0&&<><strong>已选 {selectedIds.length} 项</strong><button onClick={()=>requestArchive(projects.filter(p=>selectedIds.includes(p.id)&&!p.archive?.archived),'archive')} disabled={!verified||!projects.some(p=>selectedIds.includes(p.id)&&!p.archive?.archived)}>归档所选未归档项目</button><button onClick={()=>setSelectedIds([])}>清除选择</button></>}{receipt&&<span role="status">{receipt}</span>}</div>
      <label>阶段 <select aria-label="项目阶段" value={stageFilter} onChange={e=>setStageFilter(e.target.value)}>{['全部',...STAGES,'待更新'].map(x=><option key={x}>{x}</option>)}</select></label>
      <label>状态 <select aria-label="项目状态" value={attentionFilter} onChange={e=>setAttentionFilter(e.target.value)}>{['全部',...ATTENTIONS].map(x=><option key={x}>{x}</option>)}</select></label>
      <button className="plain-action" onClick={()=>{setBatchMode(!batchMode);setSelectedIds([]);}}>{batchMode?'结束批量':'批量归档'}</button><span role="status">{!verified?(snapshot?'上次列表 · 正在核对':'正在读取项目'):`${displayed.length} 个项目`}</span>
    </div>
    {loading&&!snapshot&&<ProjectListSkeleton />}{!verified&&selected&&<p role="status">正在核对所选项目的最新进展，核对后打开。</p>}{error&&<p role="alert">{error}<button onClick={refresh}>重新读取</button></p>}
    <ProjectTable commitments={commitments} crm={crmSummary?.projects||{}} signals={signalData?.signals||[]} projects={displayed} onOpen={p=>choose(p.id)} onArchive={requestArchive} selectedIds={selectedIds} onSelect={batchMode?onSelectArchive:undefined}/>
    {verified&&!loading&&!displayed.length&&<p className="overview-empty">这个筛选下暂无项目。<button className="plain-action" onClick={()=>{setQuery('');setStageFilter('全部');setAttentionFilter('全部');setCustomerFilter('');setWorkMode('all');}}>查看全部当前项目</button></p>}
    <div className="concept-home-receipt">{crmError||(!crmSummary?'正在读取 K100 本地回执':`K100 已关联 ${Object.values(crmSummary.projects).filter(x=>x.link).length} 个项目`)}<span>关联后，新补充沿用同一同步链路</span></div>
    <details className="concept-operations"><summary>日程与公开研究回执</summary><ProjectFollowups onFocusItems={receiveCommitments} navigate={navigate} refreshKey={roundRefresh}/><PublicSignalBrief navigate={navigate} refreshKey={refreshKey?.generated_at} customer={customerFilter} layout="summary"/></details>

    </div></section></div></div>
    {readingSnapshot&&<ProjectDrawer key={`snapshot:${readingSnapshot.id}`} onBack={onBack} dialogRef={drawer} project={readingSnapshot} related={[]} onRelated={choose} onClose={()=>choose('')} onOverview={()=>choose('',{reset:true})} onCustomer={()=>choose('',{customer:readingSnapshot.customer})}>
      <section className="project-judgement" aria-label="项目已有内容预览"><p role="status">正在核对最新状态，先显示上次已保存内容。核对完成后自动载入完整画布。</p><h2>上次项目判断</h2><p>{readingSnapshot.brief?.situation||readingSnapshot.judgement||'该项目尚无已保存判断。'}</p>{readingSnapshot.brief?.blocker&&<><h3>上次记录的推进卡点</h3><p>{readingSnapshot.brief.blocker}</p></>}<small>依据日期 {readingSnapshot.latest_evidence_date||'待核实'} · 只读预览</small>{error&&<p role="alert">最新状态暂未读到。<button onClick={refresh}>重新读取</button></p>}</section>
    </ProjectDrawer>}
    {project&&<ProjectDrawer onOpenNotification={onOpenNotification} onArchive={requestArchive} key={project.id} onBack={onBack} dialogRef={drawer} project={project} related={verified?projectConnections(project,projects):[]} onRelated={choose} onClose={()=>choose('')} onOverview={()=>choose('',{reset:true})} onCustomer={()=>choose('',{customer:recognizedCustomer(project.customer)?project.customer:undefined})}>
      <div hidden={Boolean(source)}>{notificationContext?.project_id===project.id&&<NotificationChanges item={notificationContext} onSource={openSource}/>}<ArchiveStatus archive={project.archive} onOpenSource={openSource} onRestore={()=>requestArchive([project],'restore')}/><ProjectAnalysis identitySurface={<K100IdentityQuestion key={project.id} projectId={project.id}/>} crmSurface={<K100ProjectContext projectId={project.id} refreshKey={roundRefresh}/>} historySurface={<>      <details className="project-manual-history"><summary>约定、暂停与执行历史</summary><ProjectRound key={`${project.id}:${roundReload}`} project={project} externallyBusy={savingCount>0&&savingActions.current.has(`analysis:${project.id}`)} onSavedRound={()=>{setRoundRefresh(v=>v+1);refresh();onActionsChanged?.();}} markDirty={markDirty} markSaving={markSaving} navigate={(view,options)=>navigate(view,{...options,projectTitle:project.title,customer:project.customer})} /></details>

      <details className="drawer-tools"><summary>商务与项目工具</summary><div className="workspace-shortcuts">{[['pricing','报价／邮件／审批'],['reports','项目群日报'],['reminders','提醒与日程'],['performance','合同业绩'],['accounts','客户登记']].map(([view,label])=><button key={view} onClick={()=>navigate(view,{projectId:project.id,projectTitle:project.title,customer:project.customer})}>{label}</button>)}</div>
        
        <details><summary>其他材料建议与历史行动</summary>{project.actions.map(action=><ProjectAction key={action.id} action={action} project={project} refresh={refresh} commitAction={commitAction} markDirty={markDirty} markSaving={markSaving} onSaved={verified=>setReceipt(verified?'历史行动已保存并读回。':'已保存，读回暂未完成。')} />)}</details>
      </details>
      <details className="drawer-evidence"><summary>原始材料与历史归档判断 · {project.sources.length}</summary><p className="readonly-banner">以下保留归档当时的判断，不代表最新需求范围；当前全貌与变化见上方 AI 综合。</p><p>{project.judgement}</p>{project.risks.length>0&&<ul>{project.risks.map((risk,i)=><li key={i}>{risk}</li>)}</ul>}{project.sources.map(item=>item.readable&&item.exists?<button className="source-link" key={item.path} onClick={()=>openSource(item)}>{item.title || item.path.split('/').pop()}</button>:<a key={item.path} href={sourceUrl(item.path)}>{item.title || item.path.split('/').pop()}{!item.exists?'（文件待找回）':''}</a>)}<p>{project.formal_status}</p></details></>} filesSurface={<CustomerFiles projectId={project.id} customer={project.customer} markDirty={markDirty} markSaving={markSaving}/>} commitmentSurface={<ProjectFollowups navigate={navigate} refreshKey={roundRefresh} projectId={project.id} all/>} signalsSurface={<PublicSignalBrief navigate={navigate} projectId={project.id} customer={project.customer} compact/>} onPrepareTopic={prepareTopic} key={`analysis:${project.id}`} project={project} incomingSignal={signalContext} onOpenSource={openSource} relatedSurface={<ProjectRelationshipCards project={project} related={verified?projectConnections(project,projects):[]} onRelated={choose}/>} connectionsSurface={<ProjectConnections showPreparation={false} project={project} navigate={navigate} refreshKey={roundRefresh}/>} otherEdits={dirtyKeys.some(k=>k!==`analysis:${project.id}`)||[...savingActions.current].some(k=>k!==`analysis:${project.id}`)} markDirty={markDirty} markSaving={markSaving} refreshKey={`${roundRefresh}:${project.analysis_fingerprint}:${project.analysis_meta?.analysis_id}:${project.analysis_state}`} onAdopted={()=>{setRoundReload(v=>v+1);setRoundRefresh(v=>v+1);refresh();onActionsChanged?.();}} autoStart={false} onStateChange={refresh} />
      {meetingRequest?.projectId===project.id&&<CustomerMeeting key={`${meetingRequest.rowId}:${meetingRequest.token}`} row={customerDirectory(accounts,projects).find(r=>r.id===meetingRequest.rowId)||meetingRequest.row} onProject={id=>choose(id)} onClose={()=>setMeetingRequest(null)}/>}


      </div>{error&&<p role="alert">{error}</p>}{sourceBusy&&<p role="status">正在读取原文…</p>}{source&&<section className="source-reader"><header><h3>原文依据</h3><button onClick={closeSource}>← 返回项目</button></header><SourceText key={source.path} {...source} /><details key={`info:${source.path}`} className="source-file-info"><summary>文件信息</summary><p>{source.path}</p><a href={sourceUrl(source.path)}>在知识库中打开原文件</a></details></section>}{receipt&&<p role="status">{receipt}</p>}
    </ProjectDrawer>}
    {archiveRequest&&<ProjectArchiveDialog {...archiveRequest} onClose={()=>setArchiveRequest(null)} onSaved={async message=>{setReceipt(message);setSelectedIds([]);await refresh();setRoundRefresh(v=>v+1);onActionsChanged?.();window.dispatchEvent(new Event('workbench-refresh'));}}/>}
  </div>;
}

export function ProjectStageDistribution({distribution,known,stageFilter,onFilter}) {
  const pending=known&&distribution.pending>0;
  return <section className="stage-distribution workspace-stage-distribution" aria-label="当前项目AI阶段分布" aria-busy={!known}>
    <div className="stage-distribution-title"><span>当前项目分布 <small>{known?'按项目数':'正在读取…'}</small></span><button disabled={!known} aria-pressed={stageFilter==='全部'} onClick={()=>onFilter('全部')}>全部 {known?distribution.total:'—'}</button></div>
    <div className="stage-meter-grid" data-includes-pending={pending?'true':undefined}>{STAGES.map(stage=><button key={stage} disabled={!known} aria-pressed={stageFilter===stage} onClick={()=>onFilter(stageFilter===stage?'全部':stage)} aria-label={known?`${stage} ${distribution.counts[stage]} 个当前项目，点击筛选`:`${stage}，正在读取`}><span>{stage}<strong>{known?distribution.counts[stage]:'—'}</strong></span><i className="stage-meter-track" aria-hidden="true"><i className="stage-meter-fill" data-share={known&&distribution.total?distribution.counts[stage]/distribution.total:0} style={{transform:`scaleX(${known&&distribution.total?distribution.counts[stage]/distribution.total:0})`}} /></i></button>)}{pending&&<button className="workspace-stage-pending" aria-pressed={stageFilter==='待更新'} onClick={()=>onFilter(stageFilter==='待更新'?'全部':'待更新')} aria-label={`${distribution.pending} 个项目待分析或更新，未纳入阶段判断，点击筛选`}><span>待更新<strong>{distribution.pending}</strong></span><i className="stage-meter-track" aria-hidden="true"><i className="stage-meter-fill" data-share={distribution.total?distribution.pending/distribution.total:0} style={{transform:`scaleX(${distribution.total?distribution.pending/distribution.total:0})`}}/></i></button>}</div>
  </section>;
}

export function ProjectOverviewRow({project:p,onOpen,selected,related=[]}){
  const [expanded,setExpanded]=useState(false);
  const valid=hasCurrentBrief(p), brief=p.brief;
  const prior=Boolean(brief&&!valid);
  const actionDone=['done_waiting','new_evidence_review'].includes(p.execution_state);
  const situation=brief?.situation||p.judgement||'最新材料已收到，等待综合分析';
  const attention=valid?brief.attention:'需核实';
  const AttentionIcon=attentionIcons[attention]||CircleHelp;
  const next=actionDone?'已做 · 等待实际反馈':prior?'正在核对最新依据，原分析保留供参考':brief?.next_action||'打开分析与依据';
  return <div className={`project-overview-row workspace-project-row ${selected?'is-selected':''} ${expanded?'is-expanded':''}`} role="listitem">
    <div className="overview-project-cell"><span className="project-avatar" aria-hidden="true">{displayCustomer(p.customer).slice(0,1)}</span><div><small className="workspace-project-customer">{displayCustomer(p.customer)}</small><button className="project-row-trigger" data-project-trigger={p.id} onClick={onOpen} title={p.title}><span>{p.title}</span></button><span className="project-row-meta"><time>{p.latest_evidence_date||'日期待核实'}</time>{related.length>0&&<button onClick={onOpen} title="查看有依据的关联项目"><GitBranch size={12}/>{related.length} 关联</button>}</span></div></div>
    <div className="overview-stage-cell workspace-project-stage"><span className="workspace-stage-name"><Layers3 size={13}/>{valid?brief.stage:statusLabels[p.analysis_state]||'待分析'}</span><span className={`attention-tag attention-${ATTENTIONS.indexOf(attention)}`}><AttentionIcon size={12} aria-hidden="true"/>{actionDone?'已做 · 承接结果':attention}</span>{prior&&<small className="prior-analysis-label">上次判断待更新</small>}</div>
    <div className="overview-next-cell workspace-row-action"><p title={next} className={actionDone?'overview-action-done':''}>{next}</p></div>
    <div className="overview-blocker-cell workspace-row-blocker"><p title={brief?.blocker||'待分析'}>{brief?.blocker||'待分析'}</p></div>
    <div className="workspace-row-controls"><button aria-label={`展开${p.title}的完整判断`} aria-expanded={expanded} onClick={()=>setExpanded(v=>!v)}><ChevronDown size={15}/></button><button aria-label={`进入${p.title}`} onClick={onOpen}><ArrowUpRight size={16}/></button></div>
    {expanded&&<div className="workspace-row-expanded"><section><span>当前判断{prior?' · 上次分析':''}</span><p>{situation}</p></section><section><span>{actionDone?'后续反馈':'下一步与卡点'}</span><p>{next}</p><p className="row-expanded-blocker">{brief?.blocker||'待核实'}</p>{valid&&p.pursuit?.conversation?.success_signal&&<p><b>本轮目标：</b>{p.pursuit.conversation.success_signal}</p>}</section><button className="row-detail-link" onClick={onOpen}>打开客户工作面 <ArrowRight size={14}/></button></div>}
  </div>;
}

function ProjectDrawer({onOpenNotification,onArchive,onBack,dialogRef,project,related=[],onRelated,onClose,onOverview,onCustomer,children}){
  useLayoutEffect(()=>{
    const element=dialogRef.current;element.showModal();
    const body=element.querySelector('.drawer-body');const storageKey=`workbench-drawer-scroll-${project.id}`;let desired=0;try{desired=Number(sessionStorage.getItem(storageKey))||0;}catch{}
    let restored=false;const restore=()=>{if(!restored&&body.scrollHeight-body.clientHeight>=desired){body.scrollTop=desired;restored=true;observer.disconnect();}};
    const observer=new MutationObserver(restore);observer.observe(body,{childList:true,subtree:true});restore();
    const remember=()=>{if(restored){try{sessionStorage.setItem(storageKey,String(body.scrollTop));}catch{}}};body.addEventListener('scroll',remember);
    const previous=document.body.style.overflow;document.body.style.overflow='hidden';
    const mm=gsap.matchMedia();const context=gsap.context(()=>{mm.add('(prefers-reduced-motion: no-preference)',()=>gsap.fromTo(element,{y:12,autoAlpha:0},{y:0,autoAlpha:1,duration:.2,ease:'power2.out',clearProps:'transform,opacity,visibility'}));},element);
    return()=>{observer.disconnect();body.removeEventListener('scroll',remember);mm.revert();context.revert();document.body.style.overflow=previous;};
  },[project.id]);
  return <dialog ref={dialogRef} className="project-detail-drawer project-decision-drawer workspace-project-sheet" aria-labelledby="project-drawer-title" onCancel={event=>{event.preventDefault();onClose();}} onClick={event=>{if(event.target===event.currentTarget){const box=event.currentTarget.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)onClose();}}}>
    <header className="drawer-header"><div className="drawer-topline"><nav aria-label="项目位置">{onBack&&<button onClick={onBack}>← 返回上一步</button>}<button onClick={onOverview}>项目工作台</button><span>/</span>{recognizedCustomer(project.customer)?<button onClick={onCustomer}>{displayCustomer(project.customer)}</button>:<span>{displayCustomer(project.customer)}</span>}</nav><div className="drawer-header-actions"><button onClick={()=>{dialogRef.current?.querySelector('[data-project-files-tab]')?.click();}}>文件</button>{onArchive&&<details><summary>更多</summary><button onClick={()=>onArchive([project],project.archive?.archived?'restore':'archive')}>{project.archive?.archived?'恢复跟进':'归档项目'}</button></details>}{onOpenNotification&&<ProjectNotifications onOpen={onOpenNotification}/>}<button className="drawer-close" autoFocus aria-label="关闭项目详情，返回总览" onClick={onClose}><X size={18}/></button></div></div><div className="workspace-sheet-title"><span className="sheet-customer-icon"><Building2 size={23}/></span><div><h2 id="project-drawer-title">{project.title}</h2><small>{displayCustomer(project.customer)} · 业务依据 {project.latest_evidence_date||'日期待核实'}</small></div></div></header>

    <div className="drawer-body"><div className="workspace-project-content">{children}</div></div>
  </dialog>;
}

function ProjectRelationshipCards({project,related,onRelated}){
  const [all,setAll]=useState(false);
  if(!related.length)return null;
  const visible=all?related:related.slice(0,3);
  return <section className="customer-project-strip" aria-label="客户与关联项目"><small>关联项目</small><div className="customer-project-links">{visible.map(item=><button key={item.id} onClick={()=>onRelated(item.id)} title={item.title}><span>{item.relation}</span><strong>{item.title}</strong><ArrowUpRight size={12}/></button>)}</div>{related.length>3&&<button className="customer-project-all" onClick={()=>setAll(v=>!v)}>{all?'收起':`全部 ${related.length}`}</button>}</section>;
}

function ProjectAction({ action, project, refresh, commitAction, markDirty, markSaving, onSaved }) {
  const [open, setOpen] = useState(false);
  const [record, setRecord] = useState({ owner: "", due: "", status: "待安排", result: "", ...action.record });
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const baseline = useRef({ record: JSON.stringify(action.record), revision: project.plan_revision });
  useEffect(() => {
    const current = JSON.stringify(action.record);
    if (!dirty || current === baseline.current.record) baseline.current = { record: current, revision: project.plan_revision };
  }, [action.record, project.plan_revision, dirty]);
  useEffect(() => { if (!dirty) setRecord({ owner: "", due: "", status: "待安排", result: "", ...action.record }); }, [action.record, dirty]);
  useEffect(() => () => markDirty(action.id, false), [action.id, markDirty]);
  const set = key => e => { setRecord({ ...record, [key]: e.target.value }); setDirty(true); markDirty(action.id, true); };
  async function save(e) {
    e.preventDefault(); setBusy(true); markSaving(action.id, true); setMessage("");
    try { const saved = await api.post("/api/project-workspace/plan", { project_id: project.id, archive_revision:project.archive?.revision||0, action_id: action.id, revision: baseline.current.revision, ...record }); setRecord(saved.record); commitAction(project.id, action.id, saved); markDirty(action.id, false); const latest = await refresh(); setDirty(false); setOpen(false); onSaved(Boolean(latest)); }
    catch (e) { setMessage(e.message); }
    finally { setBusy(false); markSaving(action.id, false); }
  }
  async function reload() {
    if (dirty && !window.confirm("重新加载将放弃本条未保存修改，继续？")) return;
    const latest = (await refresh())?.find(p => p.id === project.id)?.actions.find(a => a.id === action.id);
    if (latest) { setRecord({ owner: "", due: "", status: "待安排", result: "", ...latest.record }); setDirty(false); markDirty(action.id, false); setMessage(""); }
  }
  return <article className="project-action"><div><small>{action.record.status || "材料建议 · 尚未复核"} · 建议协作：{[action.suggested_role, ...(action.support_roles || [])].join("、")}</small><h3>{action.task}</h3><p>{action.record.owner ? `已记录协作人：${action.record.owner}` : `期望产出：${action.deliverable}`}{action.record.due && ` · 跟进日期 ${action.record.due}`}</p>{action.record.result && <p>最近结果：{action.record.result}</p>}<button className="plain-action" onClick={() => setOpen(!open)}>{open ? "收起" : "安排 / 记录结果"}</button></div>
    {open && <form onSubmit={save}><fieldset disabled={busy} className="project-action-form"><label className="native-field"><span>具体协作人</span><input value={record.owner} onChange={set("owner")} placeholder="尚未确认时留空，不自动指派" /></label><label className="native-field"><span>计划跟进日期（不自动创建提醒）</span><input type="date" value={record.due} onChange={set("due")} /></label><label className="native-field"><span>实际推进状态</span><select value={record.status} onChange={set("status")}>{["待安排", "已联系待接受", "执行中", "等待反馈", "已完成"].map(s => <option key={s}>{s}</option>)}</select></label><label className="native-field"><span>实际结果 / 确认依据</span><textarea value={record.result} onChange={set("result")} rows={3} required={record.status === "已完成"} placeholder="已发送不等于已接受；已接受不等于已完成" /></label><button className="plain-action" type="submit">{busy ? "保存中…" : "保存本轮进展"}</button>{message && <button className="plain-action" type="button" onClick={reload}>放弃本条修改，重新加载最新记录</button>}<p role="status">{message}</p></fieldset></form>}
  </article>;
}

export function ReportSync({ refresh }) {
  const [status, setStatus] = useState(null);
  const [health, setHealth] = useState(null);
  const [auth, setAuth] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function inspect() { const [s, h] = await Promise.all([api.get("/api/messages/status"), api.get("/api/messages/health")]); setStatus(s); setHealth(h.health); setAuth(s.auth || null); }
  useEffect(() => { inspect().catch(e => setMessage(e.message)); }, []);
  async function run(kind) {
    setBusy(true); setMessage("");
    try {
      if (kind === "sync" && status?.action_required) {
        setMessage("正在接收授权并验证项目群读取…");
        const completed = await api.post("/api/messages/auth/complete");
        if (!completed.ready) { setMessage(completed.message); await inspect(); return; }
      }
      const result = await api.post(`/api/messages/${kind}`);
      if (kind === "auth/start") { setAuth(result); setMessage(result.reused ? "已保留当前授权请求，不会覆盖你正在确认的链接。" : "授权链接已生成，请打开飞书授权页面；完成后回来同步，工作台会先接回授权。"); }
      else { setMessage(kind === "sync" ? `读取结束：新增 ${result.new_messages || 0} 条，失败 ${result.failed_groups || 0} 个群。` : result.message); await inspect(); await refresh({ quiet: true }); }
    } catch (e) { setMessage(e.message); await inspect().catch(() => {}); }
    finally { setBusy(false); }
  }
  return <section className="project-judgement" aria-label="日报同步状态"><h2>{status ? (status.action_required ? (auth?.verification_url && !auth.expired ? "授权链接已生成，等待你在飞书确认" : "飞书读取需要恢复授权") : "飞书用户读取通道可用") : "正在检查飞书读取权限…"}</h2><p>最后完整成功：{health?.last_success_at || "未记录"} · 最近同步尝试：{health?.last_attempt_at || "未记录"}</p><p>{status?.action_required ? "历史日报不受影响。生成链接后，还需到飞书确认，再回来检查结果。" : "同步只读取项目群消息并更新本地日报，不往群里发送内容。"}</p>
    {health?.status === "partial" && <p>上次有 {health.failed_groups} 个群失败，日报不完整。</p>}
    <div className="workspace-shortcuts"><button disabled={busy || !status} onClick={() => run("sync")}>{busy ? "处理中…" : status?.action_required ? "接回授权并同步今天消息" : "同步今天消息"}</button>{status?.action_required && <button disabled={busy} onClick={() => run("auth/start")}>{auth?.verification_url && !auth.expired ? "查看当前授权链接" : "重新授权飞书"}</button>}</div>
    {auth?.verification_url && !auth.expired && <div><p><a href={auth.verification_url} target="_blank" rel="noreferrer">第 1 步：打开飞书授权页面 ↗</a></p><p>此次申请群消息读取、群信息读取及持续读取授权，不申请用户消息发送权限。请核对飞书页面后确认。过期时间：{auth.expires_at}</p><button className="plain-action" disabled={busy} onClick={() => run("auth/complete")}>第 2 步：我已授权，检查结果</button><p>检查通过后，再点“同步今天消息”。</p></div>}
    {auth?.expired && <p>旧授权链接已过期，请点击“重新授权飞书”生成新的链接。</p>}
    {message && <p role="status" className="break-text">{message}</p>}
    {health?.error && <details><summary>查看上次同步失败记录 · {health.last_attempt_at || "历史记录"}</summary><p>这是上次同步的结果，不代表刚生成的授权失败。</p><p className="break-text">{health.error}</p></details>}
  </section>;
}
