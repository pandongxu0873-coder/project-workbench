import React, { useEffect, useState, useRef } from 'react';
import { api } from './api.js';
const money=v=>v==null?'未提供':`¥${Number(v).toLocaleString('zh-CN',{maximumFractionDigits:2})}`;
const date=v=>v?new Date(v).toLocaleString('zh-CN'):'尚未读取';

export function ProjectContractAudit({projectId,refreshKey,navigate}) {
  const [data,setData]=useState(null),[error,setError]=useState(''),[source,setSource]=useState(null);
  const sourceReader=useRef(null),sourceTrigger=useRef(null);
  useEffect(()=>{if(source)sourceReader.current?.scrollIntoView({block:'start'});},[source]);
  useEffect(()=>{let live=true;setError('');
    if(projectId)api.get(`/api/crm/project-links?project_id=${encodeURIComponent(projectId)}`).then(x=>{if(live)setData(x);}).catch(e=>{if(live)setError(e.message);});
    return()=>{live=false;};
  },[projectId,refreshKey]);
  async function openSource(e){sourceTrigger.current=document.activeElement;try{const x=await api.get(`/api/project-workspace/source?project_id=${encodeURIComponent(projectId)}&path=${encodeURIComponent(e.path)}`);setSource(x);}catch(e){setError(e.message);}}
  function closeSource(){setSource(null);requestAnimationFrame(()=>{sourceTrigger.current?.focus();sourceTrigger.current?.scrollIntoView({block:'center'});});}
  if(!projectId)return null;
  return <section className="project-judgement" aria-label="本项目订单与合同核对">
    <h2>{data?.project_title||'本项目'} · 订单与合同</h2>
    {error&&<p role="alert">{error}</p>}
    {!data&&!error&&<p role="status">正在核对对应记录…</p>}
    {data&&<>
      {!data.matches.length&&<p>尚未建立有编号依据的对应关系，不代表没有合同或订单。</p>}
      {data.matches.map(({order:o,contract:c,evidence,materials,contract_note,payment_comparison:payment})=><article key={o.id}>
        <h3>{o.bizCode} · {o.approvalStatus||'审批状态未提供'}</h3><p>{o.customerName}</p>
        <div className="metric-strip"><div><span>订单金额</span><strong>{money(o.orderAmount)}</strong></div><div><span>CRM订单业绩明细</span><strong>{money(o.performanceAmount)}</strong></div><div><span>CRM已收款</span><strong>{money(o.receivedAmount)}</strong></div></div>
        <p>待回款 {money(o.pendingReceivableAmount)} · 合同 {c?.bizCode||o.contractBizCode||'编号未提供'} · 双方签署{Number(o.k100ContractSignedByBothParties)===1?'：CRM标记已签':'：CRM未确认'}</p>
        {payment&&<p role={payment.different?'status':undefined}>{payment.different?'回款日期不同 · ':''}客户邮件 {payment.customer_due||'待核'} / CRM计划 {payment.crm_due||'未填写'}{payment.different?'；需核对，保留客户原确认日期。':''}<button className="plain-action" onClick={()=>openSource(payment.evidence)}>查看客户原回复</button></p>}
        <small>旧CRM已停用 · 此处保留历史订单编号</small>
        {contract_note&&<p>{contract_note}</p>}
        <details><summary>报价、内部审批与正式记录的依据</summary>
          <p>商机：{o.opportunityName||'未提供'} · 编号 {o.opportunityId??'未提供'}</p>
          {c&&<p>合同金额 {money(c.contractAmount)} · 合同审批 {c.approvalStatus||'未提供'} · 签署日期字段 {c.signedDateDisplay||'未记录'}。日期字段与双方签署标记分别核对。</p>}
          <button className="source-link" onClick={()=>openSource(evidence)}>订单对应依据</button>
          {materials.map(e=><button className="source-link" key={e.path} onClick={()=>openSource(e)}>{e.label}</button>)}
        </details>
      </article>)}
      {data.issues.map((x,i)=><p role="status" key={i}>{x}</p>)}
      {Object.entries(data.sync_errors).map(([k,v])=><p role="alert" key={k}>{k==='orders'?'订单':'合同'}更新失败：{v}，保留上次读取时间。</p>)}
      <details><summary>读取范围与时间</summary><p>订单读取：{date(data.orders_read_at)}；合同读取：{date(data.contracts_read_at)}。</p><p>{Object.values(data.coverage).every(v=>v==='all_available_pages')?'已读取当前账号可见的全部分页。':'部分列表只读到首屏或尚未读取，不据此判断记录不存在。'}{data.note}</p></details>
    </>}
    {source&&<section className="source-reader" ref={sourceReader}><header><h3>对应材料</h3><button onClick={closeSource}>收起材料，继续核对</button></header><pre>{source.content}</pre></section>}
  </section>;
}
