import {ProjectResources} from './ProjectResources.jsx';
import {ProgressComposer} from './ProgressComposer.jsx';
import {blockerKind,isExecutionReceipt} from './projectPresentation.js';
import { reusedUnderstanding } from './reusedUnderstanding.js';
import { contextForProject, signalVerificationNote } from './signalProjectContext.js';
import { publicUrl } from './discovery-model.js';
import React, { useState, useEffect, useRef } from 'react';
import gsap from 'gsap';
import { ArrowDown, ArrowRight, ArrowUpRight, Check, ChevronRight, Circle, Clock3, FileText, Flag, GitBranch, Layers3, ListFilter, Mail, MessageSquare, Network, ShieldCheck, Target, Users, Wallet, Workflow, X } from 'lucide-react';
import { STAGES } from './projectOverview.js';
import './project-detail-redesign.css';
import { api } from './api.js';
import { CustomerUnderstanding, UnderstandingCoverage } from './CustomerUnderstanding.jsx';
import { ProjectStory } from './ProjectStory.jsx';
import { ProjectRecentChanges } from './ProjectRecentChanges.jsx';
import { analysisDraftIsCurrent } from './analysisDraft.js';

export function ProjectAnalysis({ identitySurface, commitmentSurface, crmSurface, historySurface, filesSurface,signalsSurface,project, markDirty, markSaving, onAdopted, refreshKey, otherEdits, autoStart=true, onStateChange, onOpenSource, relatedSurface, connectionsSurface, incomingSignal, onPrepareTopic }) {
  const [fileSelection,setFileSelection]=useState(null);
  const [composerRequest,setComposerRequest]=useState(0);
  function openComposer(){setComposerRequest(v=>v+1);}
  const signal=contextForProject(incomingSignal,project.id);
  const [signalChoice,setSignalChoice]=useState('');
  useEffect(()=>setSignalChoice(''),[signal?.signalId]);
  const [state,setState]=useState(null);
  useEffect(()=>{if(signal&&state?.correction?.includes(signalVerificationNote(signal)))setSignalChoice('submitted');},[signal?.signalId,state?.correction]);
  const [correction,setCorrection]=useState('');
  const [dirty,setDirty]=useState(false);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [error,setError]=useState('');
  const mounted=useRef(true);
  const surface=useRef(null);
  const [evidenceIndex,setEvidenceIndex]=useState(0);
  const [focusNode,setFocusNode]=useState('');
  const [view,setView]=useState('decision');
  const [historyTarget,setHistoryTarget]=useState(null);
  function changeView(next){setView(next);setFocusNode('');requestAnimationFrame(()=>surface.current?.scrollIntoView({block:'start',behavior:'auto'}));}
  useEffect(()=>{setView('decision');setFocusNode('');},[project.id]);
  const reader=useRef(null);
  function openNode(node){setFocusNode(node);requestAnimationFrame(()=>reader.current?.scrollIntoView({block:'start',behavior:'auto'}));}
  const inputDirty=useRef(false);
  const inputVersion=useRef(0);
  const stateIdentity=useRef('');
  const readVersion=useRef(0);
  const feedbackRequest=useRef(null);
  const analysisRequest=useRef(null);
  const statusRead=useRef(null);
  const key=`analysis:${project.id}`;
  const path=`/api/project-workspace/analysis?project_id=${project.id}`;
  function acceptStatus(value) {
    if(!mounted.current)return;
    setState(value);setError('');
    const identity=`${value.state}:${value.result?.analysis_id||''}:${value.stale}`;
    if(identity!==stateIdentity.current){stateIdentity.current=identity;onStateChange?.();}

  }
  function readStatus({fresh=false}={}) {
    if(statusRead.current&&!fresh)return statusRead.current;
    const version=++readVersion.current;
    const request=api.get(path).then(value=>{
      if(mounted.current&&version===readVersion.current){acceptStatus(value);return value;}
    }).catch(e=>{if(mounted.current&&version===readVersion.current)setError(e.message);});
    statusRead.current=request;
    request.finally(()=>{if(statusRead.current===request)statusRead.current=null;});
    return request;
  }
  async function requestAnalysis(force=false, initial=false) {
    const submittedVersion=inputVersion.current;
    const basis=JSON.stringify([project.id,initial?null:correction,force,submittedVersion]);
    if(analysisRequest.current?.basis!==basis)analysisRequest.current={basis,id:crypto.randomUUID()};
    readVersion.current++;
    setBusy(true);markSaving(key,true);setError('');setMessage('');
    try {
      const value=await api.post('/api/project-workspace/analysis',{project_id:project.id,archive_revision:project.archive?.revision||0,...(!initial?{correction}:{}),force,request_id:analysisRequest.current.id});
      if(!mounted.current)return;
      readVersion.current++;acceptStatus(value);
      if(value.busy&&!value.accepted){setMessage(value.message);return;}
      if(!value.accepted&&!value.started){setMessage('尚未收到保存回执，补充内容保留，请稍后重试。');return;}
      analysisRequest.current=null;
      setMessage(value.queued?'补充已保存并排队，后台会结合这次内容更新；可以离开此页。':'补充已保存，后台正在更新项目理解。');
      if(inputVersion.current===submittedVersion){inputDirty.current=false;setDirty(false);markDirty(key,false);setCorrection(value.correction || '');if(signalChoice==='verification')setSignalChoice('submitted');}
      else setMessage('已提交上一段补充；新输入的内容已保留，可以继续提交。');
    }catch(e){if(mounted.current)setError(e.message);}
    finally{markSaving(key,false);if(mounted.current)setBusy(false);}
  }
  useEffect(()=>{
    mounted.current=true;
    readStatus().then(value=>{
      if(!mounted.current || !value)return;
      // Read-only cached state first. A single initial request only when no analysis exists.
      // Background reconciliation owns automatic analysis, including failures.
    }).catch(e=>{if(mounted.current)setError(e.message);});
    return()=>{mounted.current=false;readVersion.current++;markDirty(key,false);};
  },[project.id]);
  useEffect(()=>{
    if(!refreshKey)return;
    readStatus();
  },[refreshKey]);
  useEffect(()=>{
    if(state?.state==='ready' && !state?.stale)return;
    let stopped=false;
    let timer;
    // A slow response must finish before starting the next poll; otherwise
    // readVersion keeps invalidating it and the view can load forever.
    const poll=async()=>{
      await readStatus();
      if(!stopped)timer=setTimeout(poll,8000);
    };
    timer=setTimeout(poll,8000);
    return()=>{stopped=true;clearTimeout(timer);};
  },[state?.state,state?.stale,project.id]);
  async function checkAction(outcome) {
    if(busy)return;
    const analysisId=outcome==='undo'?state.execution?.analysis_id:state.result?.analysis_id;
    const basis=`${analysisId}:${state.round_revision}:${outcome}`;
    if(feedbackRequest.current?.basis!==basis)feedbackRequest.current={basis,id:crypto.randomUUID()};
    setBusy(true);markSaving(key,true);setError('');setMessage('');readVersion.current++;
    try {
      const saved=await api.post('/api/project-workspace/analysis/feedback',{project_id:project.id,archive_revision:project.archive?.revision||0,analysis_id:analysisId,revision:state.round_revision,outcome,request_id:feedbackRequest.current.id});
      feedbackRequest.current=null;
      const verified=await readStatus({fresh:true});
      setMessage(verified?.round_revision===saved.revision ? outcome==='done'?'已记下你做过这件事，后续沟通会继续补充结果。':outcome==='pending'?'已保留这件事，不需要补填表单。':'已撤销标记，之前的记录已恢复。' : '已保存，正在读取最新状态。');
      onAdopted?.();
    } catch(e) { setError(e.message); await readStatus(); }
    finally {setBusy(false);markSaving(key,false);}
  }
  const result=state?.result;
  const analysis=state?.state==='ready' && !state?.stale ? result?.analysis : null;
  const viewAnalysis=analysis||result?.analysis;
  const reused = reusedUnderstanding(result);
  const historicalUnderstanding=!viewAnalysis?.understanding&&!reused?result?.historical_understanding:null;
  const understanding=viewAnalysis?.understanding||reused?.value||historicalUnderstanding?.value;
  const updateNotice=state?.state==='running'
    ? '正在更新项目理解。已有内容仍可阅读，执行建议需结合新材料核对。'
    : state?.state==='queued'
      ? '更新请求已排队，尚未开始处理。已有内容仍可阅读。'
      : state?.state==='error'
        ? '最近一次更新未完成，已保留上次理解。可继续查看需求、历程和依据。'
        : viewAnalysis
          ? '已有材料或记录发生变化，以下保留上次理解及日期；新增内容尚待综合核对。'
          : '尚无综合理解，可先查看已有沟通和项目材料。';
  const brief=viewAnalysis?.brief;
  const execution=state?.execution;
  const actionText=viewAnalysis?.next_action||brief?.next_action||'尚未形成具体建议';
  const actionIsReceipt=isExecutionReceipt(actionText,execution);
  const checked=(['done_waiting','new_evidence_review'].includes(state?.execution_state)&&Boolean(viewAnalysis?.guard))||(execution?.quick_outcome==='pending'&&execution.quick_action===brief?.next_action);
  const blocked=Boolean(project.archive?.archived)||execution?.relationship==='no_contact'||execution?.status==='暂停跟进'||analysis?.contact_boundary==='no_contact';
  async function copyDraft() {
    const expected=result, version=++readVersion.current, input=inputVersion.current;
    setBusy(true);markSaving(key,true);setError('');setMessage('');
    try {
      const current=await api.get(path);
      if(!mounted.current)return;
      if(version!==readVersion.current || input!==inputVersion.current || inputDirty.current) {
        setMessage('判断或输入正在更新，请查看最新材料后再复制。');return;
      }
      acceptStatus(current);
      if(!analysisDraftIsCurrent(expected,current)) {
        setMessage('依据或草稿已变化，本次未复制。请查看最新判断；旧分析需先更新。');return;
      }
      await navigator.clipboard.writeText(expected.analysis.draft);
      if(mounted.current)setMessage('已核对最新依据并复制，未发送。');
    } catch(e) {if(mounted.current)setError(`未能完成核验或复制，请重试：${e.message}`);}
    finally {markSaving(key,false);if(mounted.current)setBusy(false);}
  }
  useEffect(()=>{
    if(!analysis || !surface.current)return;
    const context=gsap.context(()=>{
      const mm=gsap.matchMedia();
      mm.add('(prefers-reduced-motion: no-preference)',()=>{
        gsap.fromTo('.decision-board',{y:5,opacity:.7},{y:0,opacity:1,duration:.22,ease:'power2.out',clearProps:'transform,opacity'});
      });
      return ()=>mm.revert();
    },surface);
    return ()=>context.revert();
  },[result?.analysis_id,Boolean(analysis)]);
  const progressionStages=STAGES.filter(stage=>stage!=='待核实');
  const stageUnconfirmed=!progressionStages.includes(brief?.stage);
  const evidence=viewAnalysis?.evidence||[];
  const selectedEvidence=evidence[Math.min(evidenceIndex,Math.max(0,evidence.length-1))];
  const readableEvidence=project.sources?.find(source=>source.path===selectedEvidence?.path&&source.readable&&source.exists);
  return <section ref={surface} className="analysis-surface analysis-compact project-detail-redesign" aria-label="AI项目分析">
      {signal&&<section className="project-signal-context" aria-label="此次进入项目的公开信号"><header><strong>刚才查看的公开变化</strong><span>{signal.publishedAt||'日期待核实'} · {signal.source||'来源待核实'}</span></header><p>{signal.title}</p>{signal.judgment&&<p><b>影响待核实：</b>{signal.judgment}</p>}<p><b>建议核实：</b>{signal.verification||'是否影响本项目，尚待验证。'}</p><div className="workspace-shortcuts">{publicUrl(signal.sourceUrl)&&<a href={publicUrl(signal.sourceUrl)} target="_blank" rel="noreferrer">查看公开原文 ↗</a>}<button type="button" aria-pressed={signalChoice==='reference'} disabled={['verification','submitted'].includes(signalChoice)} onClick={()=>setSignalChoice('reference')}>本次仅作参考</button><button type="button" disabled={busy||!state||['verification','submitted'].includes(signalChoice)} onClick={()=>{const text=signalVerificationNote(signal);const next=[correction,text].filter(Boolean).join('\n\n');if(next.length>6000){setError('现有补充加上信号超过输入容量，请先整理补充内容；未覆盖原输入。');return;}setCorrection(next);inputVersion.current++;inputDirty.current=true;setDirty(true);markDirty(key,true);setSignalChoice('verification');openComposer();const fold=surface.current?.querySelector('.progress-composer');if(fold){fold.scrollIntoView({block:'center'});fold.querySelector('textarea')?.focus();}}}>带入待核实补充</button></div>{signalChoice&&<small role="status">{signalChoice==='reference'?'本次作为参考阅读，未改变项目安排。':signalChoice==='submitted'?'此公开信号来由已保存，项目影响仍待综合；后续新输入须另行提交。':'已放入下方补充草稿，尚未提交；提交更新后再由AI综合判断。'}</small>}</section>}
      {view==='history'&&relatedSurface&&<details className="concept-related"><summary>客户与关联项目</summary>{relatedSurface}</details>}
    {(!state || state.state==='running') && <p className="detail-update-status" role="status"><Clock3 size={16} aria-hidden="true" />{state?.state==='running'?`正在更新项目判断 · ${state.sync?.phase||'模型处理中'}${state.sync?.segments_total?` · 已整理 ${state.sync.segments_done||0}/${state.sync.segments_total} 段材料`:''}${state.sync?.elapsed_seconds?` · 本次处理已用 ${Math.floor(state.sync.elapsed_seconds/60)} 分 ${state.sync.elapsed_seconds%60} 秒`:''}`:'正在读取已有判断…'}</p>}
    {state && !analysis && <p className="analysis-input-note" role="status">{updateNotice}</p>}
    {state?.pending_request&&<p className="project-feedback-notice" role="status">补充已保存 · {state.pending_request.submitted_at?.slice(5,16).replace('T',' ')} · 已排队，将在当前处理后优先更新。</p>}
    {state?.sync?.status==='retrying' && <p role="status">新材料已收到，分析将自动重试，不需要重新归档。</p>}
    {state&&<nav className="project-understanding-views" aria-label="项目阅读视角">{[['decision','概览',Target],['history','沟通与进程',GitBranch],['files','文件',FileText],['signals','客户动态',Network]].map(([id,label,Icon])=><button data-project-files-tab={id==='files'?'true':undefined} key={id} aria-pressed={view===id} aria-controls={`project-view-${project.id}`} onClick={()=>changeView(id)}><Icon size={16}/>{label}{id==='scope'&&understanding&&<small>{understanding.requirements.length}</small>}</button>)}</nav>}
    
    <div className="focus-project-content"><div id={`project-view-${project.id}`} className="project-reading-view">
    <div hidden={view!=='files'} className="project-files-entry">{filesSurface&&React.cloneElement(filesSurface,{initialAssetRequest:fileSelection})}</div>
    {view==='signals'&&signalsSurface}
    {view==='decision'&&identitySurface}
    {viewAnalysis && view==='decision' ? <>

      <section className="concept-current" aria-label="当前进展"><div><span className="project-state-chip">{analysis?(brief?.stage||'阶段待核实'):'上次判断'}</span><time>判断更新 {result.created_at?.slice(0,16).replace('T',' ')}</time></div><h3>{brief?.situation||viewAnalysis.judgement}</h3>{brief?.blocker&&<p className="concept-blocker">{blockerKind(brief.blocker)} · {brief.blocker}</p>}</section>
      <section className="concept-action" aria-label="当前最重要的行动"><span className="concept-action-label"><Target size={15}/>{!analysis?'判断待更新':blocked||brief?.attention==='暂缓'?'按已有约定推进':actionIsReceipt?'等待反馈':'当前行动'}</span><details className="component-action-text"><summary>{!analysis?'最新情况尚未核对，保留上次进展':actionIsReceipt?'这件事已做，等待对应结果':actionText}</summary><p>{!analysis?'最新情况尚未核对，保留上次进展':actionIsReceipt?'这件事已做，等待对应结果':actionText}</p></details>
       <div className="concept-action-buttons">{Boolean(analysis)&&!actionIsReceipt&&!blocked&&brief?.attention!=='暂缓'&&!(checked&&execution?.quick_outcome==='done')&&<button className="primary-button" disabled={busy||dirty||otherEdits} onClick={()=>checkAction('done')}><Check size={15}/>标记已做</button>}<button className="concept-text-button" onClick={()=>openNode('preparation')}>{analysis?'查看已准备的沟通内容':'查看上次准备'} ↗</button></div>
       {execution?.quick_outcome&&execution.quick_outcome!=='undo'&&<div className="project-execution-receipt" role="status"><span>{execution.quick_outcome==='done'?'已记录执行':'尚未执行'} · {execution.quick_action}</span><button disabled={project.archive?.archived||busy||dirty||otherEdits} onClick={()=>checkAction('undo')}>撤销标记</button></div>}
       <div className="concept-evidence-chips">{evidence.length>0&&<button onClick={()=>openNode('evidence')}><FileText size={14}/>查看 {evidence.length} 处判断依据 <ChevronRight size={13}/></button>}</div>
       {readableEvidence&&onOpenSource&&<button className="focus-prepared-source" onClick={()=>onOpenSource(readableEvidence)}><FileText size={23}/><span><strong>{readableEvidence.title||sourceLabel(readableEvidence.path)}</strong><small>本次判断引用 · 查看已有原文</small></span><ArrowUpRight size={16}/></button>}
      </section>
        <aside ref={reader} hidden={!focusNode} className="decision-reading canvas-inline-reader" aria-label="所选画布节点内容"><button className="canvas-reader-close" aria-label="收起展开内容" onClick={()=>setFocusNode('')}><X size={15}/></button>
        <section hidden={focusNode!=='judgement'} id={`canvas-panel-judgement-${project.id}`} className="decision-reading-panel" role="region" aria-labelledby={`canvas-judgement-${project.id}`}>
          <header className="detail-panel-heading"><span><Layers3 size={17} aria-hidden="true" />当前判断</span><small>AI 综合 · 可追溯原文</small></header>
          {brief?.stage_reason&&<section className="detail-stage-reason"><span>阶段依据</span><p>{brief.stage_reason}</p></section>}
          {viewAnalysis.story?.turning_point&&<section className="detail-stage-reason"><span>关键变化</span><p>{viewAnalysis.story.turning_point}</p></section>}
          <details className="decision-reason"><summary>完整判断</summary><p>{viewAnalysis.judgement}</p>{viewAnalysis.blocker!==brief?.blocker&&<p>阻点：{viewAnalysis.blocker}</p>}</details>
        </section>
        <section hidden={focusNode!=='evidence'} id={`canvas-panel-evidence-${project.id}`} className="decision-reading-panel decision-evidence" role="region" aria-labelledby={`canvas-evidence-${project.id}`}>
          <div className="detail-panel-heading"><span><FileText size={17} aria-hidden="true" />判断依据</span><small>{evidence.length} 处引用</small></div>
          {selectedEvidence ? <>
            <div className="evidence-selector" role="group" aria-label="选择引用依据">{evidence.map((entry,i)=><button key={`${entry.path}:${i}`} aria-pressed={Math.min(evidenceIndex,evidence.length-1)===i} aria-label={`引用 ${i+1}：${sourceLabel(entry.path)}`} aria-controls={`decision-evidence-${project.id}`} onClick={()=>setEvidenceIndex(i)}><span className="evidence-source-icon"><FileText size={15} aria-hidden="true" /></span><span className="evidence-source-label"><strong>{sourceLabel(entry.path)}</strong><time>{result.evidence_dates?.[entry.path]||'日期待核实'}</time></span><ChevronRight size={13} aria-hidden="true" /></button>)}</div>
            <div id={`decision-evidence-${project.id}`} className="decision-quote-panel" aria-live="polite">
              <span className="decision-quote-label">原文摘录</span>
              <blockquote className="decision-quote">{selectedEvidence.quote}</blockquote>
              {readableEvidence&&onOpenSource&&<button className="detail-source-open" onClick={()=>onOpenSource(readableEvidence)}>完整材料<ArrowUpRight size={13} aria-hidden="true" /></button>}
            </div>
          </> : <p className="decision-source-date">该版本未单列引用，请核对原始材料。</p>}
        </section>
        <section hidden={focusNode!=='preparation'} id={`canvas-panel-preparation-${project.id}`} className="decision-reading-panel" role="region" aria-labelledby={`canvas-preparation-${project.id}`}>
          <section className="canvas-full-action"><h3>本轮完整安排</h3><p>{viewAnalysis.next_action||brief?.next_action}</p></section>
          {viewAnalysis.story?<ProjectStory key={`preparation:${result.analysis_id}`} view="preparation" story={viewAnalysis.story} project={project} role={viewAnalysis.role} blocker={brief?.blocker} acceptance={viewAnalysis.acceptance} reentry={execution?.status==='暂停跟进'?execution.next_step:''} restricted={Boolean(viewAnalysis.guard)||blocked||brief?.attention==='暂缓'} onOpenSource={onOpenSource}/>:<><h3 className="detail-section-title"><Target size={17} aria-hidden="true" />行动准备</h3><p>{viewAnalysis.acceptance}</p><p>建议协作角色：{viewAnalysis.role||'待核实'}（未指派）</p></>}
          {viewAnalysis?.draft&&<section className="analysis-material" aria-label="本轮沟通草稿"><h3><FileText size={17} aria-hidden="true" />{analysis?'本轮沟通草稿 · 未发送':'上次沟通草稿 · 等待更新'}</h3><pre className="round-draft">{viewAnalysis.draft}</pre><button disabled={!analysis || busy || state.stale || state.state!=='ready' || dirty || otherEdits || blocked || Boolean(viewAnalysis.guard)} onClick={copyDraft}>核对最新依据并复制</button></section>}
        </section>
        <section hidden={focusNode!=='history'} id={`canvas-panel-history-${project.id}`} className="decision-reading-panel" role="region" aria-labelledby={`canvas-history-${project.id}`}>
          {viewAnalysis.story?<ProjectStory key={`history:${result.analysis_id}`} view="history" active={focusNode==='history'} story={viewAnalysis.story} project={project} onOpenSource={onOpenSource}/>:<p className="evidence-empty">本版未整理关键节点，请查看下方已有材料变化。</p>}
        </section>
        <section hidden={focusNode!=='questions'} id={`canvas-panel-questions-${project.id}`} className="decision-reading-panel" role="region" aria-labelledby={`canvas-questions-${project.id}`}><BuyingEvidence uncertainties={viewAnalysis.uncertainties||[]} /></section>
        </aside>

    </> : !viewAnalysis&&view==='decision'&&state&&state.state!=='running'&&<p>最新材料已归档，综合分析尚未完成。</p>}

    {view==='history'&&<ProjectRecentChanges projectId={project.id} refreshKey={refreshKey} pendingSynthesis={!analysis} journey={viewAnalysis?.story?.journey||[]} onHistory={()=>changeView('history')}/>}
    <div hidden={view!=='decision'}>{commitmentSurface}<ProgressComposer openRequest={composerRequest} project={project} markDirty={markDirty} markSaving={markSaving} initialText={correction} onSaved={()=>{inputDirty.current=false;setDirty(false);markDirty(key,false);setCorrection('');readStatus({fresh:true});onAdopted?.();}}/></div>
    {historicalUnderstanding&&view!=='decision'&&<p className="project-analysis-update" role="status">以下需求与画像沿用 {historicalUnderstanding.created_at?.slice(0,16).replace('T',' ')} 的历史整理，供追溯核对；不代表最新需求已确认。当前推进判断保留其独立更新时间。</p>}
    {state&&['scope','history','profile','responsibilities'].includes(view)&&<CustomerUnderstanding onPrepareTopic={!historicalUnderstanding&&onPrepareTopic?topic=>onPrepareTopic(project.id,{...topic,analysisId:result?.analysis_id,createdAt:result?.created_at,stale:!analysis}):undefined} key={`understanding:${project.id}:${result?.analysis_id||result?.created_at||"pending"}`} value={historicalUnderstanding&&view==='decision'?null:understanding} story={viewAnalysis?.story} project={project} onOpenSource={onOpenSource} createdAt={historicalUnderstanding&&view!=='decision'?historicalUnderstanding.created_at:result?.created_at} view={view==='responsibilities'?'decision':view==='decision'?'summary':view} historyTarget={historyTarget} onHistory={target=>{setHistoryTarget(target);changeView('history');}} stale={!analysis||!!historicalUnderstanding} running={state.state==='running'} failed={state.state==='error'}/>}

    {view==='decision'&&understanding?.interventions?.some(x=>x.action!==actionText&&!isExecutionReceipt(x.action,execution))&&<section className="focus-other-work"><header><strong>其他推进事项</strong><button onClick={()=>changeView('responsibilities')}>查看责任与安排 →</button></header>{understanding.interventions.filter(x=>x.action!==actionText&&!isExecutionReceipt(x.action,execution)).map((x,i)=><button key={i} onClick={()=>changeView('responsibilities')}><span>{x.title}</span><small>{analysis?'查看具体安排':'上次安排 · 待更新'} →</small></button>)}</section>}
    <div hidden={view!=='history'}>{historySurface}</div>
    </div></div>
    <div hidden={!['history','scope','profile','responsibilities'].includes(view)}>
    {crmSurface}
    <details className="concept-background"><summary>项目背景、范围与详细判断</summary><div className="concept-background-tabs">{[['scope','需求全貌'],['profile','客户画像'],['responsibilities','范围与责任']].map(([id,label])=><button key={id} onClick={()=>changeView(id)}>{label}</button>)}<button onClick={()=>{changeView('decision');openNode('judgement');}}>完整判断</button><button onClick={()=>{changeView('decision');openNode('questions');}}>待核实事项</button></div>
    {historicalUnderstanding&&view!=='decision'&&<UnderstandingCoverage coverage={historicalUnderstanding.source_coverage} createdAt={historicalUnderstanding.created_at}/>}
    <UnderstandingCoverage coverage={result?.source_coverage} createdAt={result?.created_at}/>
      {connectionsSurface&&<div className="canvas-system-connections">{React.cloneElement(connectionsSurface,{analysisState:state,onPrepare:()=>{setView('decision');openNode('preparation');}})}</div>}
    </details>
    </div>
    {(error || state?.error) && <p role="alert">{error || state.error}</p>}
    {message&&<p className="project-feedback-notice" role="status">{message}</p>}

    <details hidden={view!=='history'} className="project-support-details"><summary>分析信息与历史补充</summary>
      {result&&<p className="analysis-meta">分析时间 {result.created_at?.slice(0,19).replace('T',' ')} · {result.model}</p>}
      {state?.correction_history?.map(h=><p key={h.revision}>{h.date} · {h.text}</p>)}
      {(!analysis||state?.stale)&&<button disabled={busy||['running','queued'].includes(state?.state)} onClick={()=>requestAnalysis(true,true)}>重试更新判断</button>}
    </details>

  </section>;
}

function sourceLabel(path='') {
  if(path.startsWith('user://correction'))return '用户补充';
  if(path==='local://round')return '本地执行记录';
  if(path.startsWith('local://'))return '本地资料 · '+path.slice(8);
  if(/^[a-f0-9]{12,}_沟通整理\.md$/.test(path.split('/').pop()))return '本项目沟通整理';
  return path.split('/').pop();
}
const EVIDENCE_LENSES=[
  {id:'value',label:'客户价值',Icon:Target,match:/价值|目标|指标|痛点|基线|需求|业务问题/},
  {id:'people',label:'决策与协作',Icon:Users,match:/负责人|决策|签认人|授权|经办|谁|角色|权限|拍板/},
  {id:'budget',label:'预算与采购',Icon:Wallet,match:/预算|金额|报价|价格|成本|采购|付款|款项|审批/},
  {id:'timing',label:'时间与承诺',Icon:Clock3,match:/日期|时间|期限|排期|计划|承诺|何时|窗口|哪一步/},
  {id:'alternatives',label:'竞争与替代',Icon:Layers3,match:/竞品|竞争|供应商|替代|不做|自建|自研|旧流程|现有系统/},
  {id:'delivery',label:'交付与验收',Icon:ShieldCheck,match:/交付|验收|合同|签署|签章|范围|复验|复测|测试|到账|上线/},
];
function BuyingEvidence({uncertainties}) {
  const [lens,setLens]=useState('all');
  const selected=EVIDENCE_LENSES.find(item=>item.id===lens);
  const visible=uncertainties.map((text,index)=>({text,index})).filter(item=>!selected||selected.match.test(item.text));
  return <section className="buying-evidence-map" aria-label="项目运转依据">
    <header className="detail-section-heading"><h3 className="detail-section-title"><Workflow size={17} aria-hidden="true" />待核实事项 <span className="detail-count">{uncertainties.length}</span></h3><button className="evidence-all" aria-pressed={lens==='all'} onClick={()=>setLens('all')}><ListFilter size={14} aria-hidden="true" />查看全部</button></header>
    <div className="evidence-lenses" role="group" aria-label="按主题查看已有待核问题">{EVIDENCE_LENSES.map(({id,label,Icon,match})=><button key={id} aria-pressed={lens===id} onClick={()=>setLens(lens===id?'all':id)}><Icon size={14} aria-hidden="true" /><span>{label}</span><small>{uncertainties.filter(text=>match.test(text)).length}</small></button>)}</div>
    <div className="evidence-question-list" aria-live="polite">{visible.length?<ol>{visible.map(({text,index})=><li key={index}><span aria-hidden="true">{String(index+1).padStart(2,'0')}</span><p>{text}</p></li>)}</ol>:<p className="evidence-empty">{selected?'该主题未单列待核问题；不代表相关事项已确认。':'本版未单列待核问题，仍需结合引用原文判断。'}</p>}</div>
    <small className="evidence-boundary">按已有问题原文检索主题；复合问题可出现在多个主题。报价、批准、合同、验收与回款分别核验。</small>
  </section>;
}
