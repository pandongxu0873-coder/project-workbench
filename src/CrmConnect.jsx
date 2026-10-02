import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowUpRight, RefreshCw } from 'lucide-react';
import { api } from './api.js';
import { installCrmAutoSync } from './crmAutoSync.js';
import { AnimatedNumber, GoalBar } from './WorkbenchMotion.jsx';
import { PerformanceChart } from './PerformanceChart.jsx';
import { finiteAmount, performanceModel, periodOrders, projectPayments } from './performanceModel.js';
import './performance.css';
const periods = { QUARTER: '本季度', MONTH: '本月', YEAR: '本年度' };
const money = value => finiteAmount(value) == null ? '未提供' : `¥${Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const wan = value => (value / 10000).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
const stamp = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false }) : '未记录';
const day = value => value ? new Date(value).toLocaleDateString('zh-CN', { timeZone:'Asia/Shanghai' }) : '未提供';

export function CrmConnect({ onSynced, refreshKey }) {
  const [state,setState] = useState(null), [key,setKey] = useState(''), [busy,setBusy] = useState(false), [message,setMessage] = useState('');
  const [period,setPeriod] = useState(() => { try { return Object.hasOwn(periods,sessionStorage.getItem('workbench-performance-period')) ? sessionStorage.getItem('workbench-performance-period') : 'QUARTER'; } catch { return 'QUARTER'; } });
  const [expanded,setExpanded] = useState(null), [allRows,setAllRows] = useState(false);
  const inFlight = useRef(false), live = useRef(true);
  async function refresh() { const result = await api.get('/api/crm/status'); if(live.current)setState(result); return result; }
  useEffect(() => {
    live.current=true;
    const check=async()=>{if(document.visibilityState==='hidden'||inFlight.current)return;try{const result=await refresh();}catch(error){if(live.current)setMessage(error.message);}};
    const stop=installCrmAutoSync(check);
    const manual=()=>refresh().catch(error=>{if(live.current)setMessage(error.message);});window.addEventListener('workbench-refresh',manual);
    return()=>{live.current=false;stop();window.removeEventListener('workbench-refresh',manual);};
  },[]);
  const previousRefresh=useRef(refreshKey);
  useEffect(()=>{if(previousRefresh.current!==refreshKey){previousRefresh.current=refreshKey;refresh().catch(e=>setMessage(e.message));}},[refreshKey]);
  useEffect(()=>{try{sessionStorage.setItem('workbench-performance-period',period);}catch{}setExpanded(null);setAllRows(false);},[period]);
  const snapshot=state?.snapshot, record=snapshot?.dashboards?.[period], data=record?.data;
  const model=useMemo(()=>performanceModel(data),[data]);
  const rows=useMemo(()=>periodOrders(snapshot,data),[snapshot,data]);
  const payments=useMemo(()=>projectPayments(rows),[rows]);
  const visibleRows=allRows?payments.groups:payments.groups.slice(0,5);
  const error=snapshot?.errors?.[period];
  const crmUrl='https://crm.example.invalid/sales-workspace';
  const stale=record?.fetched_at && Date.now()-Date.parse(record.fetched_at)>5*60*1000;
  return <section className="graphite-performance" aria-label="历史业绩快照">
    <header className="performance-heading"><div><p className="performance-kicker">经营概览</p><h1>合同业绩</h1></div><div className="performance-controls"><label><span className="sr-only">业绩周期</span><select value={period} onChange={e=>setPeriod(e.target.value)}>{Object.entries(periods).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label></div></header>
    <div className="performance-source"><span>{data ? `${data.periodLabel} · ${data.scopeLabel} · 已审批订单业绩` : '历史经营快照'}</span><span>{record?`${stale?'上次读取':'读取于'} ${stamp(record.fetched_at)}`:'暂无历史快照'}</span></div>
    <p className="performance-read-message">业务平台旧CRM接口已停用。以下仅为最后保存的历史业绩，不再更新；当前业务请在新版 K100 核对。</p>
    {error&&<details className="performance-read-message"><summary>旧接口停用前的读取记录</summary><p>{record?'已保留最后快照。':'此周期未保存历史数据。'}{error}</p></details>}
    {!data ? <div className="crm-empty" role="status"><h2>{state?'此周期没有历史快照':'正在读取合同业绩'}</h2><p>{state?'旧CRM已停止读取；历史材料不删除。':'页面已打开，正在读取本机保存的旧 CRM 快照。'}</p><div className="skeleton-bar wide"/></div> : <>
      <section className="performance-chapter"><span className="chapter-index">01</span><div className="chapter-content"><h2>签约进度</h2><div className="performance-split"><div className="performance-hero"><strong title={money(model.amount)}><AnimatedNumber value={model.amount} format={wan}/><small>万</small></strong><span>合同业绩 · {data.totalPerformance?.count??'—'} 笔已审批订单</span><div className="performance-target">{model.goal==null?<><b>本期未设目标</b><span>历史快照中的目标</span></>:<><b>目标 {wan(model.goal)} 万 · 完成 {model.rate.toFixed(1)}%</b><GoalBar rate={model.rate} label={`目标完成率 ${model.rate.toFixed(1)}%`}/><span>距目标 {wan(model.gap)} 万</span></>}</div><div className="performance-customer-mix"><span>新客 <b>{money(data.newCustomerPerformance?.amount)}</b></span><span>老客 <b>{money(data.existingCustomerPerformance?.amount)}</b></span></div></div><PerformanceChart trend={model.trend} granularity={model.granularity}/></div></div></section>
      <section className="performance-chapter"><span className="chapter-index">02</span><div className="chapter-content"><h2>回款关注 <small className="chapter-subtitle">单独跟进，不影响合同业绩口径</small></h2><div className="performance-payment"><div className="payment-main"><strong title={money(payments.received)}><AnimatedNumber value={payments.received} format={wan}/><small>万</small></strong><span>明细已收款</span></div><div className="payment-overdue"><strong title={money(payments.pending)}><AnimatedNumber value={payments.pending} format={wan}/><small>万</small></strong><span>明细待回款</span></div><div className="payment-boundary"><strong>逐项目核对付款进展</strong><p>当前明细 {payments.groups.length} 个 CRM 项目 · {payments.count} 笔订单</p>{payments.received!=null&&payments.pending!=null&&payments.received>=0&&payments.pending>=0&&payments.received+payments.pending>0&&<GoalBar rate={payments.received/(payments.received+payments.pending)*100} label={`当前明细已收款 ${money(payments.received)}，待回款 ${money(payments.pending)}`}/>}<p>按订单日期筛选；{snapshot?.resources?.orders?.coverage==='all_available_pages'?'当前账号可见分页已读完':'已读部分，非全量'}。</p></div></div></div></section>
      <section className="performance-chapter"><span className="chapter-index">03</span><div className="chapter-content"><header className="performance-ledger-heading"><h2>项目回款明细</h2><span>按 CRM 商机编号关联</span></header><div className="performance-ledger-scroll"><table className="performance-ledger"><thead><tr><th>客户 / 项目</th><th>订单金额</th><th>已收款</th><th>待回款</th><th>付款记录</th></tr></thead><tbody>{visibleRows.map(group=><React.Fragment key={group.key}><tr><td><strong>{group.customer||'客户未提供'}</strong><span>{group.title}</span></td><td>{money(group.amount)}</td><td>{money(group.received)}</td><td>{money(group.pending)}</td><td><button className="ledger-open" aria-expanded={expanded===group.key} onClick={()=>setExpanded(expanded===group.key?null:group.key)}>{expanded===group.key?'收起':'查看记录'} <span aria-hidden="true">{expanded===group.key?'−':'→'}</span></button></td></tr>{expanded===group.key&&<tr className="ledger-expanded"><td colSpan="5"><div className="ledger-detail"><div>{group.orders.map(order=><article key={order.id}><strong>{order.bizCode} · {day(order.orderDate)}</strong><p>{order.approvalStatus||'审批状态未提供'} · {order.paymentStatus||'回款状态未提供'} · {Number(order.k100ContractSignedByBothParties)===1?'CRM 标记双方已签署':'双方签署待核对'}</p><p>已收 {money(order.receivedAmount)} · 待收 {money(order.pendingReceivableAmount)} · 合同 {order.contractBizCode||'未提供'}</p>{[1,2,3,4].filter(i=>Number(order[`planReceivableAmount${i}`])>0&&Date.parse(order[`planReceivableDate${i}`])>0).map(i=><p key={i}>CRM 计划：{day(order[`planReceivableDate${i}`])} · {money(order[`planReceivableAmount${i}`])}（计划日期，到账以收款记录为准）</p>)}<small>旧订单编号保留供历史核对</small></article>)}</div></div></td></tr>}</React.Fragment>)}</tbody></table></div>{!rows.length&&<p className="performance-empty-note">此日期范围没有已读取的订单明细，不据此判断没有合同。</p>}{payments.groups.length>5&&<button className="ledger-more" onClick={()=>setAllRows(!allRows)}>{allRows?'收起更多项目':`展开全部 ${payments.groups.length} 个项目`}</button>}<p className="performance-footnote">明细按订单日期展示，未合计为上方考核业绩。订单读取 {stamp(snapshot?.resources?.orders?.fetched_at)}。</p></div></section>
    </>}
    {message&&<p className="performance-read-message" role="status">{message}</p>}
    <details className="performance-source-details"><summary>数据来源与统计口径</summary><p>业绩取历史经营快照“本期已审批订单业绩”；订单金额、合同签署与回款分别核对。CRM 统计范围 {day(data?.rangeStart)} 至 {day(data?.rangeEnd)}，CRM 更新 {stamp(data?.updatedAt)}。</p><p>经营看板待回款 {money(model.pending)} · {data?.pendingReceivable?.secondaryLabel||"逾期金额"} {money(model.overdue)}，与按订单日期筛选的明细分别展示。</p><p>旧CRM远程接口、密钥配置及每日同步已停用。这里仅展示停用前保存的历史记录。</p><a href={crmUrl} target="_blank" rel="noreferrer">打开新版 K100 ↗</a>{snapshot&&<p>{snapshot.coverage} · 最近尝试 {stamp(snapshot.last_attempt_at)}</p>}{Object.entries(snapshot?.errors||{}).map(([name,reason])=><p key={name}>{periods[name]||name}：{reason}</p>)}</details>
  </section>;
}
