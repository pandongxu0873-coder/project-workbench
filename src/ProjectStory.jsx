import React,{useLayoutEffect,useRef,useState} from 'react';
import gsap from 'gsap';
import { ArrowUpRight, ChevronRight, FileText, Flag, GitBranch, MessageSquare, ShieldCheck, Target, Users } from 'lucide-react';
import './project-detail-redesign.css';

function Evidence({value}) {
  if(!value)return null;
  return <details className="story-evidence"><summary><FileText size={13} aria-hidden="true" />引用原句</summary><blockquote>{value.quote}</blockquote><small title={value.path}>{value.path?.split('/').pop()}</small></details>;
}
export function ProjectStory({story,project,role,blocker,acceptance,reentry,restricted=false,onOpenSource,view='all',active=true}) {
  const journey=story.journey||[];
  const [selected,setSelected]=useState(Math.max(0,journey.length-1));
  const current=Math.min(selected,Math.max(0,journey.length-1));
  const step=journey[current];
  const communication=step?.summary?.match(/^(客户沟通|内部沟通|合作方沟通|综合材料)[：:]\s*/);
  const readableSource=project.sources?.find(source=>source.path===step?.evidence?.path&&source.readable&&source.exists);
  const detail=useRef(null);
  const timeline=useRef(null);
  useLayoutEffect(()=>{
    const track=timeline.current,selectedNode=track?.querySelector('[aria-pressed="true"]');
    if(!active||!track||!selectedNode)return;
    const top=selectedNode.offsetTop;
    if(top<track.scrollTop||top+selectedNode.offsetHeight>track.scrollTop+track.clientHeight)track.scrollTop=Math.max(0,top-8);
  },[active,current]);
  useLayoutEffect(()=>{
    if(!detail.current)return;
    const mm=gsap.matchMedia();
    mm.add('(prefers-reduced-motion: no-preference)',()=>gsap.fromTo(detail.current,{opacity:.6,y:3},{opacity:1,y:0,duration:.18,ease:'power1.out',clearProps:'transform,opacity'}));
    return()=>mm.revert();
  },[current]);
  return <section className="project-story detail-story" aria-label={view==='history'?'客户沟通脉络':view==='preparation'?'客户价值与行动准备':'客户全貌与沟通路线'}>
    {view!=='preparation'&&<section id={'story-context-'+project.id} className="detail-journey" aria-label="已收录的关键节点">
      <header className="detail-section-heading"><h3 className="detail-section-title"><GitBranch size={18} aria-hidden="true" />项目脉络 <span className="detail-count">{journey.length}</span></h3><small>材料日期 · 不表示阶段完成</small></header>
      {journey.length ? <>
        <div className="detail-timeline-workspace">
          <div ref={timeline} className="detail-timeline" role="group" aria-label="选择沟通关键节点">{journey.map((item,i)=>{const NodeIcon=/^内部沟通[：:]/.test(item.summary||'')?Users:/^(客户沟通|合作方沟通)[：:]/.test(item.summary||'')?MessageSquare:FileText;return <button key={i} aria-pressed={current===i} aria-controls={'story-node-'+project.id} onClick={()=>setSelected(i)} title={item.title}><span className="timeline-node" aria-hidden="true"><NodeIcon size={15}/></span><span className="timeline-card-label"><time dateTime={item.date||undefined}>{item.date||'日期待核'}</time><span className="timeline-title">{item.title}</span></span><ChevronRight size={13} aria-hidden="true" /></button>;})}</div>
          <section id={'story-node-'+project.id} ref={detail} className="detail-timeline-reading" aria-label="所选节点与原文" aria-live="polite">
            <div className="timeline-reading-summary"><div className="timeline-reading-meta"><span className="detail-node-type">{communication?.[1] || 'AI综合提炼'}</span><time>{step.date||'日期待核'}</time></div><h4>{step.title}</h4><p>{communication ? step.summary.slice(communication[0].length) : step.summary}</p></div>
            {step.evidence&&<div className="timeline-reading-evidence"><div><span><FileText size={13} aria-hidden="true" />引用原句</span>{readableSource&&onOpenSource&&<button className="detail-source-open" onClick={()=>onOpenSource(readableSource)}>完整材料<ArrowUpRight size={13} aria-hidden="true" /></button>}</div><blockquote>{step.evidence.quote}</blockquote><small title={step.evidence.path}>{step.evidence.path?.split('/').pop()}</small></div>}
          </section>
        </div>
      </> : <p className="evidence-empty">本版未整理关键节点，请查看已有原始材料。</p>}
    </section>}
    {view!=='history'&&<><div className="detail-context-grid">
      <section className="detail-value-context"><h3 className="detail-section-title"><Target size={16} aria-hidden="true" />客户价值</h3><p className="detail-customer-goal">{story.customer_goal||'客户目标尚未单列，结合原文继续核实。'}</p>{Boolean(story.value_points?.length)&&<details className="detail-value-explanation"><summary>价值依据 · {story.value_points.length} 个表达切口</summary><div className="detail-value-list">{story.value_points.map((item,i)=><section key={i}><h4>{item.title}</h4><p>{item.meaning}</p><Evidence value={item.evidence}/></section>)}</div></details>}</section>
      <section className="detail-success-context"><h3 className="detail-section-title"><ShieldCheck size={16} aria-hidden="true" />{reentry?'重新投入条件':'本轮成功条件'}</h3><p>{reentry||story.conversation?.success_signal||acceptance||'本轮成功条件尚待核实。'}</p>{reentry&&story.conversation?.success_signal&&story.conversation.success_signal!==reentry&&<p>{story.conversation.success_signal}</p>}{acceptance&&acceptance!==(reentry||story.conversation?.success_signal)&&<details className="detail-acceptance"><summary><Flag size={13} aria-hidden="true" />推进与验收边界</summary><p>{acceptance}</p></details>}</section>
    </div>
    <details className="detail-fold detail-internal-context"><summary><Users size={18} aria-hidden="true" />内部准备<span>建议安排 · 尚未指派</span></summary><p>{story.internal_track||blocker}</p><small>建议协作角色：{role||'待核实'} · 尚未指派</small></details>
    {story.conversation&&<details open={view==='preparation'} id={'story-conversation-'+project.id} className="detail-fold detail-conversation"><summary><MessageSquare size={18} aria-hidden="true" />{restricted?'保留沟通准备':'沟通提纲'}<span>{restricted?'等待新依据':'未发送'}</span></summary><div className="detail-conversation-body"><div><span>沟通目标</span><p>{story.conversation.goal}</p><span>建议开场 · 未发送</span><p>{story.conversation.opening}</p></div><div><span>重点核对</span><ol>{(story.conversation.questions||[]).map((q,i)=><li key={i}>{q}</li>)}</ol></div></div></details>}</>}
  </section>;
}
