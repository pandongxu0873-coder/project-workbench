import { decisionMeetingTopic } from './customerMeeting.js';
import { historyEvidenceLinks, orderedHistory, resolveHistoryTarget } from './historyEvidenceLinks.js';
import { requirementTimeline } from './requirementTimeline.js';
import React, {useEffect,useState,useRef,useLayoutEffect} from 'react';
import gsap from 'gsap';
import {ArrowRight, Building2, CircleHelp, GitBranch, History, Layers3, Route, ShieldCheck, Target, Users, Wallet} from 'lucide-react';
import {ProjectStory} from './ProjectStory.jsx';
import './customer-understanding.css';

function Citations({items=[],project,onOpenSource}) {
  if(!items.length)return null;
  return <details className="understanding-citations"><summary>核对依据 · {items.length}</summary>{items.map((item,index)=>{
    const source=project.sources?.find(s=>s.path===item.path&&s.readable&&s.exists);
    return <div key={`${item.path}:${index}`}><blockquote>{item.quote}</blockquote><small>{item.path.split('/').pop()}</small>{source&&<button onClick={()=>onOpenSource?.(source)}>核对原件 ↗</button>}</div>;
  })}</details>;
}

export function UnderstandingCoverage({coverage,createdAt}) {
  if(!coverage)return null;
  const {truncated=[],unavailable=[],limitations=[]}=coverage;
  return <details className={`understanding-source-coverage${truncated.length||unavailable.length||limitations.length?' has-gaps':''}`}><summary>这份理解的依据 · {coverage.included}/{coverage.linked} 份正文 · {createdAt?.slice(0,16).replace('T',' ')||'日期待核'}{coverage.ai_extracted?` · ${coverage.ai_extracted} 份长材料已逐段整理`:''}{unavailable.length?` · ${unavailable.length} 份未读取`:''}{limitations.length?` · ${limitations.length} 份仅读文字层`:''}</summary><p>范围限工作台已关联资料；收录了来源不等于已获得客户完整历史。{truncated.length?'较长来源使用节选，省略内容可能包含未呈现的变化。':''}</p>{truncated.map(path=><p key={path}>节选：{path.split('/').pop()}</p>)}{unavailable.map(item=><p key={item.path}>{item.reason}：{item.path.split('/').pop()}</p>)}{limitations.map(item=><p key={item.path}>{item.reason}：{item.path.split('/').pop()}</p>)}</details>;
}

function HistoryReplay({value,story,project,onOpenSource,target}) {
  const destination=resolveHistoryTarget(value,target);
  const [view,setView]=useState(destination?.view||(story?.journey?.length?'turns':'evolution'));
  const [selected,setSelected]=useState({evolution:0,lifecycle:0,...(destination?{[destination.view]:destination.index}:{})});
  const reading=useRef(null), track=useRef(null);
  const rows=orderedHistory(value,view).map((item,index)=>({...item,index}));
  const index=Math.min(selected[view]||0,Math.max(0,rows.length-1));
  const item=rows[index];
  function chooseEvent(next){setSelected(old=>({...old,[view]:next}));requestAnimationFrame(()=>reading.current?.scrollIntoView({block:'start',behavior:'auto'}));}
  useLayoutEffect(()=>{
    if(!reading.current)return;
    const mm=gsap.matchMedia();
    mm.add('(prefers-reduced-motion: no-preference)',()=>gsap.fromTo(reading.current,{opacity:.65,y:4},{opacity:1,y:0,duration:.18,clearProps:'transform,opacity'}));
    return()=>mm.revert();
  },[view,index]);
  useEffect(()=>{
    const el=track.current?.querySelector('[aria-pressed="true"]');
    if(el&&track.current){const top=el.offsetTop;if(top<track.current.scrollTop||top+el.offsetHeight>track.current.scrollTop+track.current.clientHeight)track.current.scrollTop=Math.max(0,top-8);}
  },[view,index]);
  return <section className="understanding-section understanding-replay" aria-label="项目全生命周期追溯">
    <header><h3><History size={18}/>项目如何走到今天</h3><div className="understanding-history-switch" role="group" aria-label="选择项目历程视角">
      {story?.journey?.length>0&&<button aria-pressed={view==='turns'} onClick={()=>setView('turns')}>关键转折 · {story.journey.length}</button>}
      <button aria-pressed={view==='evolution'} onClick={()=>setView('evolution')}>需求增删 · {value.evolution.length}</button><button aria-pressed={view==='lifecycle'} onClick={()=>setView('lifecycle')}>{value.reuse_meta?'已收录历程':'全部历程'} · {value.lifecycle.length}</button>
    </div></header>
    <p className="understanding-history-note">回看当时的依据、变化和影响。后续报价或审批结果不代表当时已确认；未收录的决定保持未知。</p>
    {view==='turns'?<ProjectStory key={project.id} story={story} project={project} view="history" onOpenSource={onOpenSource}/>:rows.length?<div className="understanding-replay-workspace">
      <div className="understanding-event-list" ref={track} role="group" aria-label="选择历史事件">
        {[{label:'有明确发生日期',items:rows.filter(i=>i.date)},{label:'发生日期待核',items:rows.filter(i=>!i.date)}].map(group=>group.items.length>0&&<section key={group.label}><h4>{group.label}</h4>{group.items.map(row=><button key={row.index} aria-pressed={row.index===index} aria-controls={`history-reading-${project.id}`} onClick={()=>chooseEvent(row.index)}><span className="understanding-event-dot"/><span><time>{row.date||'日期待核'}</time><strong>{row.title}</strong><small>{row.change_type||row.category}</small></span><ArrowRight size={13}/></button>)}</section>)}
      </div>
      <article className="understanding-event-reading" id={`history-reading-${project.id}`} ref={reading} aria-live="polite">
        <div className="understanding-event-meta"><time>{item.date||'发生日期待核'}</time><span className="understanding-status">{item.change_type||item.category}</span></div><h4>{item.title}</h4>
        {view==='evolution'?<><div className="understanding-delta"><section><span>这次变化之前</span><p>{item.previous}</p></section><ArrowRight size={18}/><section><span>这次变化之后</span><p>{item.current}</p></section></div><div className="understanding-event-meaning"><section><span>为什么改变</span><p>{item.reason}</p></section><section><span>改变了什么</span><p>{item.impact}</p></section></div></>:<><p>{item.event}</p><div className="understanding-event-meaning"><section><span>如何影响项目</span><p>{item.consequence}</p></section></div></>}
        <div className="understanding-event-confirmation"><GitBranch size={16}/><div><span>当时确认到哪里</span><p>{item.confirmation}</p></div></div>
        <Citations items={item.evidence} project={project} onOpenSource={onOpenSource}/>
        <div className="understanding-event-step"><button disabled={index===0} onClick={()=>chooseEvent(index-1)}>上一个</button><span>{index+1} / {rows.length} · 未删减已整理事件</span><button disabled={index===rows.length-1} onClick={()=>chooseEvent(index+1)}>下一个</button></div>
      </article>
    </div>:<p className="understanding-empty">尚无可验证的此类事件，不推定已经完成。</p>}
  </section>;
}

function CommercialComparison({value,project,onOpenSource,stale,onHistory,initialSelected=0,showSelector=true}) {
  const [selected,setSelected]=useState(initialSelected);
  const rows=value.scope_comparisons||[];
  const index=Math.min(selected,Math.max(0,rows.length-1));
  const current=rows[index];
  const linked=historyEvidenceLinks(value,current?.evidence);
  return <section className="understanding-section understanding-commercial" aria-label="商业基线与范围变化对照">
    <header><h3><Wallet size={18}/>范围与商业承接</h3><span>{stale?'上次整理，需结合新材料核对':'AI 对照 · 不代替客户确认'}</span></header>
    <div className="understanding-baseline"><span>适用的范围与商务基线</span><p>{value.commercial_baseline?.summary||'这一版尚未整理合同、报价与范围的直接对照，后台更新后补充；不能由需求已明确推定已包含在合同内。'}</p><Citations items={value.commercial_baseline?.evidence} project={project} onOpenSource={onOpenSource}/></div>
    {rows.length>0&&<>{showSelector&&<div className="understanding-comparison-selector" role="group" aria-label="选择需要判断的范围变化">{rows.map((item,i)=><button key={i} aria-pressed={i===index} onClick={()=>setSelected(i)}>{item.name}</button>)}</div>}<article className="understanding-comparison-reading" aria-live="polite">
      <div className="understanding-delta"><section><span>对应的约定或报价</span><p>{current.baseline}</p></section><ArrowRight size={18}/><section><span>现在提出的变化</span><p>{current.change}</p></section></div>
      <p className="understanding-confirmation">{current.confirmation}</p><div className="understanding-comparison-outcome"><section><span>对投入、交付或验收的影响</span><p>{current.impact}</p></section><section><span>{stale?'当时建议如何处理':'建议现在如何处理'}</span><p>{current.recommendation}</p>{current.prior_advice&&<details><summary>查看原建议 · 须结合已做结果重新判断</summary><p>{current.prior_advice}</p></details>}</section></div><Citations items={current.evidence} project={project} onOpenSource={onOpenSource}/>{onHistory&&linked.length>0&&<div className="understanding-history-links" aria-label="与当前对照共用原文的历史"><strong>追溯这项判断的历史依据</strong><small>以下事件共用所引原文，不代表已确认因果关系。</small>{linked.map(row=><button key={row.key} onClick={()=>onHistory(row)}>{row.view==='evolution'?'需求变化':'项目历程'} · {row.date||'日期待核'} · {row.title}<ArrowRight size={13}/></button>)}</div>}
    </article></>}
  </section>;
}

function DecisionConsiderations({value,project,onOpenSource,stale,onHistory,onPrepareTopic}) {
  const [choice,setChoice]=useState(null);
  const [compareOpen,setCompareOpen]=useState(false),[compared,setCompared]=useState([]);
  const comparisons=value.scope_comparisons||[], interventions=value.interventions||[];
  const intervention=choice?.kind==='intervention'?interventions[choice.index]:null;
  const select=(kind,index)=>setChoice(previous=>previous?.kind===kind&&previous.index===index?null:{kind,index});
  return <section className="understanding-section understanding-considerations" aria-label="范围变化与并行责任">
    <header><h3><GitBranch size={18}/>范围变化与并行责任</h3><span>{stale?'上次整理 · 待结合新材料核对':'按本次议题查看 · 未替你选择优先级'}</span></header>
    {interventions.length>1&&<div className="understanding-responsibility-tools"><button aria-expanded={compareOpen} onClick={()=>setCompareOpen(v=>!v)}>对照两项责任的行动与条件</button><small>用于判断先后与能否等待；共同出现不代表相互依赖。</small></div>}
    {compareOpen&&<section className="understanding-responsibility-compare" aria-label="对照两项责任">
      <div role="group" aria-label="选择要对照的责任">{interventions.map((item,index)=><label key={index}><input type="checkbox" checked={compared.includes(index)} disabled={!compared.includes(index)&&compared.length>=2} onChange={()=>setCompared(rows=>rows.includes(index)?rows.filter(i=>i!==index):[...rows,index])}/>{item.title}</label>)}</div>
      {!compared.length&&<p>选择本次需要一起判断的责任，保留完整行动、触发事实和继续条件。</p>}
      <div className="understanding-responsibility-columns">{compared.filter(i=>interventions[i]).map(index=>{const item=interventions[index];return <article key={index}><h4>{item.title}</h4><span>{stale?'上次判断 · 待复核':'AI建议 · 须结合实际事实'}</span><dl><dt>触发事实</dt><dd>{item.trigger}</dd><dt>要做什么</dt><dd>{item.action}</dd><dt>继续条件</dt><dd>{item.success_signal}</dd><dt>不处理的影响</dt><dd>{item.if_ignored}</dd><dt>建议参与</dt><dd>{item.owner}</dd></dl><Citations items={item.evidence} project={project} onOpenSource={onOpenSource}/>{onPrepareTopic&&<button onClick={()=>onPrepareTopic(decisionMeetingTopic('intervention',item))}>带入沟通：{item.title}</button>}</article>;})}</div>
    </section>}
    <div className="understanding-decision-index">
      <button aria-pressed={choice?.kind==='baseline'} onClick={()=>select('baseline',0)}><Wallet size={16}/><strong>适用的范围与商务基线</strong><span>报价、约定与确认边界</span><ArrowRight size={15}/></button>
      {comparisons.map((item,index)=><button key={'scope'+index} aria-pressed={choice?.kind==='scope'&&choice.index===index} onClick={()=>select('scope',index)}><Layers3 size={16}/><strong>{item.name}</strong><span>范围取舍</span><ArrowRight size={15}/></button>)}
      {interventions.map((item,index)=><button key={'intervention'+index} aria-pressed={choice?.kind==='intervention'&&choice.index===index} onClick={()=>select('intervention',index)}><ShieldCheck size={16}/><strong>{item.title}</strong><span data-priority={item.priority}>{item.priority}</span><ArrowRight size={15}/></button>)}
    </div>
    {choice?.kind==='baseline'&&<CommercialComparison value={{...value,scope_comparisons:[]}} project={project} onOpenSource={onOpenSource} stale={stale}/>}
    {choice?.kind==='scope'&&comparisons[choice.index]&&<CommercialComparison key={'scope'+choice.index} value={value} initialSelected={choice.index} showSelector={false} project={project} onOpenSource={onOpenSource} stale={stale} onHistory={onHistory}/>}
    {onPrepareTopic&&(intervention||(choice?.kind==='scope'&&comparisons[choice.index]))&&<button className="meeting-carry-question" onClick={()=>onPrepareTopic(decisionMeetingTopic(choice.kind,intervention||comparisons[choice.index]))}>将这个问题带入本次沟通</button>}
    {intervention&&<article className="understanding-selected-intervention" aria-label="所选干预的判断与依据">
      <h4>{intervention.title}</h4><p>{intervention.judgement}</p>
      <div className="understanding-event-meaning"><section><span>什么事实触发了这项判断</span><p>{intervention.trigger}</p></section><section><span>{stale?'当时建议':'建议怎么介入'}</span><p>{intervention.action}</p></section><section><span>什么结果足够继续</span><p>{intervention.success_signal}</p></section><section><span>不处理可能影响什么</span><p>{intervention.if_ignored}</p></section></div>
      <p>建议参与：{intervention.owner}</p>
      {intervention.prior_advice&&<details><summary>查看原建议 · 不重复派发</summary><p>{intervention.prior_advice}</p></details>}
      <Citations items={intervention.evidence} project={project} onOpenSource={onOpenSource}/>
    </article>}
  </section>;
}

function RequirementTimeline({value,project,onOpenSource,stale,onShowList}) {
  const [includeMilestones,setIncludeMilestones]=useState(true);
  const groups=requirementTimeline(value,includeMilestones);
  const dated=groups.filter(group=>group.date);
  return <section className="requirement-timeline" aria-label="需求演变时间线">
    <div className="requirement-timeline-toolbar"><div><h4>需求如何一步步走到今天</h4><p>{dated.length?`${dated[0].date} — ${dated.at(-1).date} · `:''}{value.evolution.length} 条需求变化{includeMilestones?` · ${value.lifecycle.length} 个项目节点`:''}</p></div><label><input type="checkbox" checked={includeMilestones} onChange={event=>setIncludeMilestones(event.target.checked)}/>同时看商务与交付等项目节点</label></div>
    <p className="requirement-timeline-note">按已收录的发生日期从早到晚排列，同日归组，不推定同日事件的先后。右侧保留{stale?'上次整理的':'目前的'}需求理解。</p>
    {groups.length>1&&<nav className="requirement-date-jumps" aria-label="按日期定位需求"><span>直达某一轮</span>{groups.map(group=><button key={group.date||'undated'} aria-label={`定位${group.date||'日期待核'}的${group.events.length}条记录`} onClick={()=>document.getElementById(`requirement-date-${project.id}-${group.date||'undated'}`)?.scrollIntoView({block:'start',behavior:'auto'})}>{group.date||'日期待核'}<small>{group.events.length}</small></button>)}</nav>}
    <div className="requirement-timeline-workspace">
      <div className="requirement-timeline-stream">
        {!groups.length&&<p className="understanding-empty">已有需求尚无可核实的变化记录，不能按材料归档日期补造时间线。可切换“当前需求清单”查看已整理范围。</p>}
        {groups.map(group=><section className={`requirement-date-group${group.date?'':' is-undated'}`} key={group.date||'undated'} id={`requirement-date-${project.id}-${group.date||'undated'}`} aria-label={group.date||'发生日期待核'}>
          <header className="requirement-date-heading"><span className="requirement-date-dot"/><time>{group.date||'日期待核'}</time><small>{group.events.length} 条记录</small></header>
          {!group.date&&<p className="requirement-undated-note">以下内容不能确定发生时间，单独保留，不视为最新变化。</p>}
          <div className="requirement-date-events">{group.events.map(({item,kind,key})=><article className={`requirement-timeline-card is-${kind}`} key={key}>
            <div className="requirement-timeline-card-heading"><span className="requirement-event-kind">{kind==='evolution'?item.change_type||'需求变化':item.category||'项目节点'}</span><h5>{item.title}</h5></div>
            {kind==='evolution'?<><div className="requirement-timeline-delta"><section><span>此前</span><p>{item.previous}</p></section><ArrowRight size={16} aria-hidden="true"/><section><span>这一轮变为</span><p>{item.current}</p></section></div><dl className="requirement-timeline-meaning"><div><dt>为什么变</dt><dd>{item.reason}</dd></div><div><dt>范围与项目影响</dt><dd>{item.impact}</dd></div></dl></>:<><p className="requirement-milestone-fact">{item.event}</p><p className="requirement-milestone-impact"><strong>对项目的影响</strong>{item.consequence}</p></>}
            <p className="requirement-timeline-confirmation"><ShieldCheck size={14} aria-hidden="true"/><span><strong>当时确认到哪里</strong>{item.confirmation}</span></p>
            <Citations items={item.evidence} project={project} onOpenSource={onOpenSource}/>
          </article>)}</div>
        </section>)}
      </div>
      <aside className="requirement-timeline-current" aria-label="时间线旁的需求理解">
        <span className="understanding-kicker"><Target size={16}/>最终要解决什么</span><p>{value.objective?.summary||'业务目标待核实。'}</p>
        <h4>{stale?'上次整理的需求范围':'现在如何理解需求'}</h4><span className="understanding-status">{value.scope_status}</span><p>{value.scope_summary}</p>
        <button onClick={onShowList}>查看{value.requirements.length}项需求及确认状态 <ArrowRight size={14}/></button>
        {value.open_decisions?.length>0&&<div className="requirement-timeline-open"><h4>仍需收口</h4><ul>{value.open_decisions.map((item,index)=><li key={index}>{item}</li>)}</ul></div>}
      </aside>
    </div>
  </section>;
}

export function CustomerUnderstanding({value,story,project,onOpenSource,createdAt,view='decision',stale=false,running=false,failed=false,onHistory,historyTarget,onPrepareTopic}) {
  const [scopeView,setScopeView]=useState('timeline');
  const [scopeFilter,setScopeFilter]=useState('全部');
  const [selectedRequirement,setSelectedRequirement]=useState('');
  const [allDetails,setAllDetails]=useState(false);
  const [profileFocus,setProfileFocus]=useState('business');
  const [legacyFocus,setLegacyFocus]=useState(0);
  const legacyPoints=story?.value_points||[];
  const legacyPoint=legacyPoints[Math.min(legacyFocus,Math.max(0,legacyPoints.length-1))];
  useEffect(()=>{if(value&&scopeFilter!=='全部'&&!value.requirements.some(item=>item.status===scopeFilter))setScopeFilter('全部');},[value,scopeFilter]);
  if(!value)return <section className="customer-understanding understanding-legacy" aria-label="已有客户理解">
    {view!=='decision'&&<div className="legacy-understanding-map" aria-label="已有整理范围"><span><Target size={15}/>业务目标</span><ArrowRight size={14}/><span><Layers3 size={15}/>{story?.value_points?.length||0} 个业务重点</span><ArrowRight size={14}/><span><History size={15}/>{story?.journey?.length||0} 个历史节点</span><small>沿用已有整理 · 不代表需求全量</small></div>}
    {view!=='decision'&&<><header><Target size={18}/><h3>客户要解决什么</h3><span>沿用已有分析 · {createdAt?.slice(0,10)||'日期待核'}</span></header>
    <p>{story?.customer_goal||'已有分析尚未单列业务目标。'}</p>{story?.turning_point&&<p><strong>最近变化：</strong>{story.turning_point}</p>}</>}
    {(view==='scope'||view==='profile')&&legacyPoint&&<section className="understanding-section" aria-label="已有业务重点"><header><h3><Layers3 size={18}/>已有业务重点</h3><span>沿用现有判断，不代表范围已冻结</span></header><div className="requirement-explorer"><div className="requirement-map" role="group" aria-label="选择已有业务重点">{legacyPoints.map((item,index)=><button key={index} aria-pressed={legacyPoint===item} onClick={()=>setLegacyFocus(index)}><span className="requirement-map-index">{String(index+1).padStart(2,'0')}</span><strong>{item.title}</strong><small>查看业务价值与依据</small></button>)}</div><section className="requirement-focus" aria-label="已有业务重点说明" aria-live="polite"><div className="requirement-focus-top">AI 已有整理 · {createdAt?.slice(0,10)||'日期待核'}</div><h4>{legacyPoint.title}</h4><p>{legacyPoint.meaning}</p><Citations items={legacyPoint.evidence?[legacyPoint.evidence]:[]} project={project} onOpenSource={onOpenSource}/></section></div></section>}
    {(view==='profile'||view==='scope'||view==='decision')&&story?.internal_track&&<section className="understanding-section" aria-label="已有协作与边界"><h3><Users size={18}/>已有协作与边界</h3><p>{story.internal_track}</p></section>}
    {view==='scope'&&story?.conversation?.questions?.length>0&&<section className="understanding-section legacy-scope-questions" aria-label="已有范围核对问题"><header><h3><CircleHelp size={18}/>需要核对的范围与确认条件</h3><span>已有建议 · 未代替客户确认</span></header><div className="understanding-profile-grid">{story.conversation.questions.map((question,index)=><article key={index}><span className="requirement-map-index">{String(index+1).padStart(2,'0')}</span><p>{question}</p></article>)}</div>{story.conversation.success_signal&&<div className="profile-scope-boundary"><ShieldCheck size={18}/><div><h4>什么结果足够继续</h4><p>{story.conversation.success_signal}</p></div></div>}</section>}
    {view==='history'&&story?.journey?.length>0&&<ProjectStory story={story} project={project} view="history" onOpenSource={onOpenSource}/>}
    <small>{failed?'最近一次更新未完成，已有内容保留。':running?'正在处理新增依据，已有内容可继续阅读。':'当前展示已有分析；未单列的画像或范围细项保持待核实，不以此认定完整范围。'}</small>
  </section>;
  const profileLabels=[['business','客户业务',Building2],['users','谁在什么场景使用',Users],['systems','系统与业务分工',Layers3],['stakeholders','参与者与决策角色',Route]];
  const scopeCounts=Object.entries(value.requirements.reduce((counts,item)=>({...counts,[item.status]:(counts[item.status]||0)+1}),{}));
  const scopeRows=scopeFilter==='全部'?value.requirements:value.requirements.filter(item=>item.status===scopeFilter);
  const focusedRequirement=scopeRows.find(item=>item.name===selectedRequirement)||scopeRows[0];
  const detailRows=allDetails?scopeRows:focusedRequirement?[focusedRequirement]:[];
  return <section className={`customer-understanding${stale?' is-historical':''}`}  aria-label="客户画像、需求全貌与项目生命周期">
    {value.reuse_meta&&<p className="understanding-coverage" role="note">覆盖边界：{value.coverage_note}</p>}
    {view==='decision'&&<DecisionConsiderations onPrepareTopic={onPrepareTopic} key={project.id} value={value} project={project} onOpenSource={onOpenSource} stale={stale} onHistory={onHistory}/>}
    {view==='profile'&&<div className="customer-profile-canvas">
      <section className="profile-objective-hub" aria-label="客户业务目标与画像"><div className="understanding-kicker"><Target size={17}/>客户最终要解决什么</div><h3>{value.objective.summary}</h3><Citations items={value.objective.evidence} project={project} onOpenSource={onOpenSource}/></section>
      <div className="profile-relationship-label"><span>围绕同一业务目标理解客户</span></div>
      <div className="profile-node-map" role="group" aria-label="选择客户画像维度">{profileLabels.map(([key,label,Icon])=><button key={key} aria-pressed={profileFocus===key} onClick={()=>setProfileFocus(key)}><span className="profile-node-heading"><Icon size={17}/>{label}</span><span className="profile-node-summary">{value.profile[key].summary}</span><span className="profile-node-more">完整说明{value.profile[key].evidence?.length>0?'与依据':''} <ArrowRight size={12}/></span></button>)}</div>
      <section className="profile-focus-reading" aria-label="画像完整说明与依据"><header><h4>{profileLabels.find(([key])=>key===profileFocus)?.[1]}</h4><small>已有关联资料整理</small></header><p>{value.profile[profileFocus].summary}</p><Citations items={value.profile[profileFocus].evidence} project={project} onOpenSource={onOpenSource}/></section>
      <section className="profile-scope-boundary"><span className="understanding-status">{value.scope_status}</span><div><h4>这些背景如何界定当前需求</h4><p>{value.scope_summary}</p></div></section>
    </div>}
    {view==='scope'&&<section className="understanding-section" aria-label="当前需求全貌">
      <header><h3><Layers3 size={18}/>需求全貌</h3><div className="understanding-history-switch" role="group" aria-label="需求阅读方式"><button aria-pressed={scopeView==='timeline'} onClick={()=>setScopeView('timeline')}>按时间看演变</button><button aria-pressed={scopeView==='list'} onClick={()=>setScopeView('list')}>当前需求清单 · {value.requirements.length}</button></div></header>
      {scopeView==='timeline'?<RequirementTimeline key={project.id} value={value} project={project} onOpenSource={onOpenSource} stale={stale} onShowList={()=>setScopeView('list')}/>:<><p className="understanding-scope-summary">{value.scope_summary}</p>
      {!value.requirements.length&&<p className="understanding-empty">已收录材料尚不足以整理具体范围，待补充有效需求依据。</p>}
      {value.requirements.length>0&&<div className="requirement-state-meter" role="group" aria-label="按确认状态筛选需求">{scopeCounts.map(([status,count])=><button key={status} data-state={status} aria-label={`${status}，${count}项，共${value.requirements.length}项`} aria-pressed={scopeFilter===status} onClick={()=>setScopeFilter(scopeFilter===status?'全部':status)} style={{flex:count}}><span>{count}</span></button>)}</div>}
      <div className="understanding-scope-distribution" aria-label="需求确认程度分布"><button onClick={()=>setScopeFilter('全部')} aria-pressed={scopeFilter==='全部'}>全部 <strong>{value.requirements.length}</strong></button>{scopeCounts.map(([status,count])=><button key={status} data-state={status} aria-pressed={scopeFilter===status} onClick={()=>setScopeFilter(scopeFilter===status?'全部':status)}><i style={{width:`${Math.max(10,count/value.requirements.length*110)}px`}}/>{status}<strong>{count}</strong></button>)}</div>
      <div className="requirement-explorer">
      <div className="requirement-map" role="group" aria-label="选择需求查看业务问题与范围">{scopeRows.map((item,index)=><button key={item.name} data-state={item.status} aria-pressed={focusedRequirement?.name===item.name&&!allDetails} onClick={()=>{setSelectedRequirement(item.name);setAllDetails(false);}}><span className="requirement-map-index">{String(index+1).padStart(2,'0')}</span><strong>{item.name}</strong><small>{item.status}</small></button>)}</div>
      {focusedRequirement&&<section className="requirement-focus" aria-label="选中需求说明" aria-live="polite"><div className="requirement-focus-top"><span>选中需求</span><span className="understanding-status" data-state={focusedRequirement.status}>{focusedRequirement.status}</span></div><h4>{focusedRequirement.name}</h4><div className="requirement-focus-section"><h5>要解决的问题</h5><p>{focusedRequirement.problem}</p></div><div className="requirement-focus-section"><h5>当前范围</h5><p>{focusedRequirement.scope}</p></div><div className="requirement-focus-section"><h5>由谁承接</h5><p>{focusedRequirement.owner}</p></div><Citations items={focusedRequirement.evidence} project={project} onOpenSource={onOpenSource}/></section>}
      </div>
      {scopeRows.length>0&&<div className="requirement-detail-heading"><span>{allDetails?`全部 ${scopeRows.length} 项明细`:'需要横向比较时，可展开完整明细'}</span><button onClick={()=>setAllDetails(!allDetails)}>{allDetails?'收起全部明细':'展开全部明细'}</button></div>}
      {allDetails&&<table className="understanding-scope-table"><thead><tr><th>业务问题</th><th>当前范围</th><th>分工与确认程度</th></tr></thead><tbody>{detailRows.map(item=><tr key={item.name} data-state={item.status}><th scope="row"><strong>{item.name}</strong><p>{item.problem}</p></th><td><p>{item.scope}</p><Citations items={item.evidence} project={project} onOpenSource={onOpenSource}/></td><td><span className="understanding-status" data-state={item.status}>{item.status}</span><p>{item.owner}</p></td></tr>)}</tbody></table>}
      {value.open_decisions.length>0&&<div className="understanding-open-decisions"><h4><CircleHelp size={16}/>仍需收口的边界</h4><ul>{value.open_decisions.map((item,i)=><li key={i}>{item}</li>)}</ul></div>}
      </>}
    </section>}
    {view==='history'&&<HistoryReplay key={`${project.id}:${historyTarget?.key||'default'}`} target={historyTarget} value={value} story={story} project={project} onOpenSource={onOpenSource}/>}
    {!value.reuse_meta&&<p className="understanding-coverage">理解范围：{value.coverage_note}</p>}
  </section>;
}
