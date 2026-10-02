import React, { useEffect, useRef, useState } from 'react';
import { ArrowRight, CheckCircle2, CircleAlert, FileText, LoaderCircle, Mail, MessageSquare, Mic, RefreshCw, Sparkles } from 'lucide-react';
import { api } from './api.js';
import { syncSummary } from './communicationSync.js';
import './communication-sync.css';

const dateTime = value => value ? value.replace('T', ' ').slice(0, 16) : '';
const COMMUNICATION_TYPES = { customer: '客户沟通', internal: '内部沟通', partner: '合作方沟通', unknown: '身份依据不足', document: '文档依据' };
const rememberedCustomer = () => { try { return sessionStorage.getItem('communication-digest-customer') || '全部'; } catch { return '全部'; } };
export const communicationCustomerKey=value=>['星海汽车商城','示例汽车集团汽车','星海汽车'].includes(value)?'星海汽车／示例汽车集团':String(value||'').trim();
export const knownCommunicationCustomer=value=>Boolean(value)&&!/(待核|待确认|未知|未归属|其他沟通与知识|全部)/.test(value);
export function initialCommunicationCustomer(context={},remembered='全部') {
  return knownCommunicationCustomer(context.customer)?communicationCustomerKey(context.customer):context.projectId?'本项目':remembered==='本项目'?'全部':remembered;
}
export function mergedCommunicationGroups(data={}) {
  const groups=new Map();
  for(const digest of [data.digest,data.history_digest])for(const group of digest?.groups||[]){
    const key=group.id||`${group.project_id||''}:${group.customer}:${group.kind||''}`;
    const prior=groups.get(key);
    if(!prior){groups.set(key,{...group,items:[...(group.items||[])]});continue;}
    const ids=new Set(prior.items.map(item=>item.id));
    for(const item of group.items||[])if(!ids.has(item.id)){prior.items.push(item);ids.add(item.id);}
  }
  return [...groups.values()];
}
export function communicationGroupsForCustomer(groups,customer,projectId='') {
  if(customer==='本项目')return groups.filter(group=>Boolean(projectId)&&group.project_id===projectId);
  if(customer==='全部')return groups;
  const key=communicationCustomerKey(customer);
  if(!knownCommunicationCustomer(key))return [];
  return groups.filter(group=>communicationCustomerKey(group.customer)===key);
}
const SOURCE = {
  recording: { icon: Mic, label: '录音' },
  document: { icon: FileText, label: '文档' },
  email: { icon: Mail, label: '邮件与附件' },
  message: { icon: MessageSquare, label: '聊天沟通' },
};
const sourceTitle = item => {
  if (item.historical && item.title.startsWith('微信历史｜')) {
    const parts = item.title.split('｜');
    return parts.length >= 4 ? '微信 · ' + parts.slice(2, -1).join('｜') : '微信历史';
  }
  const phone=item.kind==='recording' && item.title.match(/^通话 (.+)_(\d{6})_(\d{2})(\d{2})\d{2}$/);
  if(phone)return (/^\d+$/.test(phone[1])?'客户电话':phone[1]+' · 电话')+' '+phone[3]+':'+phone[4];
  const time = item.title.match(/^\d{8}\s+(\d{2})(\d{2})\d{2}/);
  if (item.kind === 'recording' && time) return time[1] + ':' + time[2] + ' 录音';
  return item.title.replace(/ · 20\d\d-\d\d-\d\d$/, '');
};

function DigestItem({ item }) {
  const [body, setBody] = useState(null), [error, setError] = useState(''), [loading, setLoading] = useState(false);
  const descriptor = SOURCE[item.kind] || SOURCE.message, Icon = descriptor.icon;
  const audio = item.sources.find(s => s.kind === 'audio');
  const text = item.sources.find(s => s.readable && /正文|原文|转写/.test(s.label)) || item.sources.find(s => s.readable);
  const original = item.sources.find(s => s.downloadable && !s.readable);
  const read = async () => {
    if (!text || loading) return;
    setLoading(true); setError('');
    try { setBody(await api.get(text.path ? '/api/project-workspace/source?project_id='+encodeURIComponent(text.project_id)+'&path='+encodeURIComponent(text.path) : '/api/material-library/source?asset_id=' + encodeURIComponent(text.id))); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };
  return <article className="digest-item">
    <div className="digest-source"><Icon size={15} /><span>{sourceTitle(item)}</span><time>{item.historical ? '历史 · ' : ''}{item.business_date || '原文未标日期'}</time></div>
    {item.communication && <div className="digest-communication"><span className={'communication-kind ' + item.communication.type} title={item.communication.reason}>{COMMUNICATION_TYPES[item.communication.type] || '身份依据不足'}</span>{item.communication.customer_relay && <span>转述客户意见</span>}{item.communication.type === 'customer' && item.communication.our_message && <span>我方发出</span>}</div>}
    {item.summaries.map((summary, i) => <p className="digest-item-summary" key={i}>{summary}</p>)}
    <details className="digest-evidence">
      <summary>核对原文{audio ? ' / 听录音' : ''}</summary>
      {item.communication?.reason && <p className="digest-role-reason">沟通对象判断：{item.communication.reason}</p>}
      {item.evidence.slice(0, 3).map((e, i) => <blockquote key={i}><small>{e.display_label || ({ customer_statement: '客户原话', internal_statement: '我方表述', document_text: '文件原文', unverified: '来源待核事实' })[e.level] || '原文依据'}</small>{e.quote}</blockquote>)}
      {audio && <audio controls preload="none" aria-label={item.title} src={'/api/material-library/file?asset_id=' + encodeURIComponent(audio.id)} />}
      <div className="digest-original-actions">
        {text && <button onClick={read} disabled={loading}>{loading ? '读取中…' : '查看完整正文'}</button>}
        {original && <a href={'/api/material-library/file?asset_id=' + encodeURIComponent(original.id)}>下载原件</a>}
      </div>
      {error && <p role="alert">{error}</p>}
      {body && <pre className="digest-full-text">{body.content}</pre>}
    </details>
  </article>;
}

function ResultGroup({ group, navigate, historical = false }) {
  const [expanded, setExpanded] = useState(false);
  const chronological = [...group.items].reverse();
  const historyPreview = [...new Map([chronological[0], ...chronological.slice(-2)].filter(Boolean).map(i => [i.id, i])).values()];
  const visible = historical ? expanded ? chronological : historyPreview : expanded ? group.items : group.items.slice(0, 3);
  const kinds = Object.keys(SOURCE).map(kind => [kind, group.items.filter(i => i.kind === kind).length]).filter(([, n]) => n);
  return <section className={'digest-card digest-' + group.kind} aria-label={group.customer + ' · ' + group.project_title}>
    <header>
      <div className="digest-customer">{group.customer}</div>
      <h3>{group.project_title}</h3>
      <div className="digest-source-counts">{kinds.map(([kind, n]) => <span key={kind}>{n} {SOURCE[kind].label === '录音' ? '段录音' : SOURCE[kind].label === '飞书沟通' ? '条沟通' : SOURCE[kind].label}</span>)}</div>
    </header>
    <div>{visible.map(item => <DigestItem item={item} key={item.id} />)}</div>
    <footer>
      {group.items.length > 3 && <button className="digest-more" onClick={() => setExpanded(!expanded)}>{expanded ? '收起' : historical ? '展开完整历程 · ' + group.items.length + ' 个记录' : '展开其余 ' + (group.items.length - 3) + ' 条沟通'}</button>}
      {group.project_id && <button className="digest-project-link" onClick={() => navigate('projects', { projectId: group.project_id, projectTitle: group.project_title, customer: group.customer })}>项目全貌<ArrowRight size={14} /></button>}
    </footer>
  </section>;
}

const storedMaterialRetrySummary = receipt => {
  if (!receipt.source_scope?.includes('stored_material_retry')) return '';
  if (!Array.isArray(receipt.material_ids) || !Array.isArray(receipt.completed_material_ids)) return '已保存材料补跑，回执未提供份数';
  const selected = new Set(receipt.material_ids);
  const completed = new Set(receipt.completed_material_ids.filter(id => selected.has(id)));
  return `已保存材料补跑${selected.size}份，完成${completed.size}份`;
};

export function CommunicationReceiptScope({ receipt = {}, job = {} }) {
  const retry = storedMaterialRetrySummary(receipt);
  return retry ? <p className="sync-checked">{retry}。本轮只处理指定的已保存材料；来源缺口仍按全队列显示。</p> : <>
    <p className="sync-checked">读取范围：{receipt.from || job.from || '—'} — {receipt.to || job.to || '—'}；本日多次同步去重展示，材料日期不等于归档日期。</p>
    <p className="sync-checked">本轮读取 {receipt.observed ?? job.observed ?? 0} 项，重复跳过 {receipt.duplicates ?? job.duplicates ?? 0} 项。闲聊、表情与无业务增量内容自动略过。</p>
  </>;
}

export function CommunicationRunStatus({ data, summary = syncSummary(data || {}) }) {
  const job=data?.job||{}, receipt=data?.receipt||{};
  const retry=storedMaterialRetrySummary(receipt);
  const partial=job.state==='partial'||receipt.status==='partial';
  const tone=!data?'running':partial&&summary.tone==='done'?'warning':summary.tone;
  const title=!data?'正在读取整理结果…':partial&&summary.tone==='done'?'本轮仅部分完成，已有整理结果保留':summary.title;
  const progress=job.phase==='analyzing'&&job.analysis_total?`已分析 ${job.analysis_done||0} / ${job.analysis_total} 批`
    :job.phase==='refreshing'&&job.refresh_total?`已更新 ${job.refresh_done||0} / ${job.refresh_total} 个项目`:'';
  const detail=[!job.running&&retry, summary.detail||(job.running?progress:'')||(tone==='warning'&&receipt.gaps?.length?`${receipt.gaps.length} 项来源缺口，已有整理结果仍可阅读`:'')].filter(Boolean).join(' · ');
  return <div className={'sync-run-strip '+tone} role="status" aria-live="polite">
    {tone==='running'?<LoaderCircle className="sync-spin" size={16}/>:tone==='warning'?<CircleAlert size={16} style={{color:'var(--app-warning)'}}/>:tone==='done'?<CheckCircle2 size={16}/>:<RefreshCw size={16} style={{color:'var(--app-text-muted)'}}/>}
    <span>{title}{detail&&` · ${detail}`}</span>
    <small>{tone==='running'&&data?'可以离开本页，后台继续':receipt.checked_at?(retry?'上次补跑回执 ':'上次采集回执 ')+dateTime(receipt.checked_at):'同步后自动生成'}</small>
  </div>;
}

export function CommunicationSync({ navigate, onChanged, context={} }) {
  const contextual=Boolean(context.projectId||knownCommunicationCustomer(context.customer));
  const [data, setData] = useState(null), [error, setError] = useState(''), [sending, setSending] = useState(false), [customer, setCustomer] = useState(()=>initialCommunicationCustomer(context,rememberedCustomer()));
  const [scope, setScope] = useState(() => { if(contextual)return 'customer';try { return sessionStorage.getItem('communication-digest-scope') || 'latest'; } catch { return 'latest'; } });
  const [historyLimit, setHistoryLimit] = useState(12);
  const [communicationType, setCommunicationType] = useState(() => { if(contextual)return 'all';try { return sessionStorage.getItem('communication-digest-type') || 'all'; } catch { return 'all'; } });
  useEffect(()=>{if(contextual){setCustomer(initialCommunicationCustomer(context));setScope('customer');setCommunicationType('all');}},[context.projectId,context.customer]);
  useEffect(() => { try { sessionStorage.setItem('communication-digest-type', communicationType); } catch {} }, [communicationType]);
  useEffect(() => setHistoryLimit(12), [scope, customer, communicationType]);
  useEffect(() => { try { sessionStorage.setItem('communication-digest-scope', scope); } catch {} }, [scope]);
  useEffect(() => { try { sessionStorage.setItem('communication-digest-customer', customer); } catch {} }, [customer]);
  const sequence = useRef(0), mounted = useRef(true), onChangedRef = useRef(onChanged), notified = useRef('');
  onChangedRef.current = onChanged;
  const accept = result => {
    setData(result); setError('');
    const id = result.job?.request_id;
    if (id && !result.job.running && result.receipt?.run_id && id !== notified.current) {
      notified.current = id; onChangedRef.current?.();
    }
  };
  const reload = async () => {
    const ticket = ++sequence.current;
    try { const result = await api.get('/api/communication-sync'); if (mounted.current && ticket === sequence.current) accept(result); return result; }
    catch (e) { if (mounted.current && ticket === sequence.current) setError(e.message); }
  };
  useEffect(() => {
    mounted.current = true; let timer;
    const poll = async () => { const result = await reload(); if (mounted.current) timer = setTimeout(poll, !result || result.job?.running || result.wechat_history?.state === 'processing' ? 3000 : 30000); };
    poll();
    const manual = () => reload();
    window.addEventListener('workbench-refresh', manual);
    return () => { mounted.current = false; ++sequence.current; clearTimeout(timer); window.removeEventListener('workbench-refresh', manual); };
  }, []);
  const start = async action => {
    if (sending || data?.job.running) return;
    setSending(true); const ticket = ++sequence.current;
    try { const result = await api.post('/api/communication-sync', { action }); if (mounted.current && ticket === sequence.current) accept(result); }
    catch (e) { if (mounted.current) { setError(e.message); await reload(); } }
    finally { if (mounted.current) setSending(false); }
  };
  const job = data?.job || {}, receipt = data?.receipt || {}, summary = syncSummary(data || {}), digest = (scope === 'history' ? data?.history_digest : scope==='customer'?{groups:mergedCommunicationGroups(data||{}),date:'最近归档与微信历史'}:data?.digest) || {};
  const history = data?.wechat_history || {};
  const disabled = sending || job.running || !data || Boolean(error), groups = digest.groups || [];
  const projectCustomers = [...new Set(groups.filter(g => g.project_id).map(g => communicationCustomerKey(g.customer)))];
  const referenceCustomers = [...new Set(groups.map(g => communicationCustomerKey(g.customer)))].filter(name => !projectCustomers.includes(name));
  const customers = [...new Set(['全部',...(customer!=='全部'?[customer]:[]), ...projectCustomers, ...referenceCustomers])];
  const selected = customer;
  const customerGroups = communicationGroupsForCustomer(groups,selected,context.projectId);
  const scopedItems=customerGroups.flatMap(group=>group.items),counts={recordings:scopedItems.filter(item=>item.kind==='recording').length,documents:scopedItems.filter(item=>item.kind==='document').length,emails:scopedItems.filter(item=>item.kind==='email').length,messages:scopedItems.filter(item=>item.kind==='message').length};
  const typeCounts = customerGroups.flatMap(g => g.items).reduce((counts, item) => { const type = item.communication?.type || 'unknown'; counts[type] = (counts[type] || 0) + 1; return counts; }, {});
  const matchingGroups = customerGroups.map(g => ({ ...g, items: g.items.filter(item => communicationType === 'all' || (item.communication?.type || 'unknown') === communicationType) })).filter(g => g.items.length);
  if (scope === 'history') matchingGroups.sort((a, b) => Number(Boolean(b.project_id)) - Number(Boolean(a.project_id)) || (b.items[0]?.business_date || '').localeCompare(a.items[0]?.business_date || ''));
  const visibleGroups = scope === 'history' && selected === '全部' ? matchingGroups.slice(0, historyLimit) : matchingGroups;
  const conversationRows = new Map();
  for (const group of matchingGroups) for (const item of group.items) {
    const communication = item.communication || { type: 'unknown' }, name = communication.conversation || sourceTitle(item), key = communication.type + '|' + name;
    if (!conversationRows.has(key)) conversationRows.set(key, { key, name, type: communication.type, reason: communication.reason, customers: new Set() });
    conversationRows.get(key).customers.add(group.customer);
  }
  const gaps = [...new Map((receipt.gaps || []).map(g => [g.source + g.reason, g])).values()];
  return <div className="communication-sync sync-result-page">
    <header className="sync-heading"><div><p className="eyebrow">沟通自动整理 · 结果直接看</p><h1>{scope==='customer'?`${selected==='全部'?'全部客户':selected} · 沟通记录`:scope === 'history' ? '微信历史脉络' : digest.is_today === false ? digest.date + ' 整理成果' : '今日沟通成果'}</h1><p>{scope==='customer'?'最近归档成果与已收录微信历史；同客户其他项目分别标示，不等于本项目证据。':scope === 'history' ? '从最早的本机记录到最近沟通，只保留关键变化。' : '录音、邮件、飞书、微信与腾讯会议，按客户和项目整理。'}</p>{contextual&&<p className="sync-context-scope">来自客户画布：{context.customer||'客户待核实'}{context.projectTitle&&` · ${context.projectTitle}`}</p>}</div>
      {scope === 'history' ? <button className="sync-primary" onClick={() => setScope('latest')}>查看近期沟通<ArrowRight size={17} /></button> : <button className="sync-primary" disabled={disabled} onClick={() => start('run')}>{job.running ? <LoaderCircle className="sync-spin" size={17} /> : <RefreshCw size={17} />}{job.running ? '正在同步' : sending ? '正在启动…' : '同步最新资料'}</button>}</header>
    {error && <div className="sync-error" role="alert"><CircleAlert size={18} /><span>暂时无法获取最新进度：{error}</span><button onClick={reload}>重新连接</button></div>}
    {scope === 'latest' && <CommunicationRunStatus data={data} summary={summary}/>}
    {scope==='latest'&&receipt.source_scope?.includes('phone_recording')&&<p className="sync-checked">手机录音核对 {receipt.from}—{receipt.to}：{receipt.observed} 段原件 · {receipt.new} 段业务补齐 · {receipt.duplicates} 段已有整理 · {receipt.excluded||0} 段非业务略过。</p>}
    {scope === 'history' && history.conversations > 0 && <div className="sync-run-strip" aria-label="微信历史整理">
      {history.state === 'completed' ? <CheckCircle2 size={16} /> : history.state === 'failed' ? <CircleAlert size={16} /> : <LoaderCircle className="sync-spin" size={16} />}
      <span>{history.state === 'completed' ? `微信历史已归档 · 本次回补 ${history.events || 0} 条业务线索` : history.state === 'failed' ? '微信历史整理暂未完成，进度已保留' : `微信历史正在${({ triage: '识别业务会话', extracting: '提炼关键变化', consolidating: '梳理客户历程', archiving: '归档', refreshing: '更新项目判断' })[history.phase] || '整理'}`}</span>
      <small>{history.state === 'processing' && history.phase === 'refreshing' && history.total > 0 ? `已更新 ${history.done || 0} / ${history.total} 个项目判断 · ` : ''}{history.from} — {history.to} · 本机 {history.conversations} 个会话 · 文字与卡片，未解读语音及附件正文</small>
    </div>}
    {(contextual||history.conversations > 0) && <nav className="digest-filters" aria-label="整理范围">
      {contextual&&<button aria-pressed={scope==='customer'} onClick={()=>{setScope('customer');setCustomer(initialCommunicationCustomer(context));setCommunicationType('all');}}>当前客户沟通</button>}
      <button aria-pressed={scope === 'latest'} onClick={() => setScope('latest')}>近期沟通</button>
      <button aria-pressed={scope === 'history'} onClick={() => setScope('history')}>微信历史{scope !== 'history' && history.state === 'processing' ? ' · 整理中' : ''}</button>
    </nav>}
    {groups.length > 0 ? <>
      <section className="digest-stats" aria-label={scope === 'history' ? '历史整理成果统计' : '今日整理成果统计'}>
        {scope === 'history' ? <div><MessageSquare size={19} /><strong>{new Set(customerGroups.filter(group=>group.project_id).map(group=>communicationCustomerKey(group.customer))).size}</strong><span>个已有项目客户</span></div> : <>
          {counts.recordings > 0 && <div><Mic size={19} /><strong>{counts.recordings}</strong><span>段录音</span></div>}
          {(counts.documents || 0) + (counts.emails || 0) > 0 && <div><Mail size={19} /><strong>{(counts.documents || 0) + (counts.emails || 0)}</strong><span>{counts.emails ? '份文档与邮件' : '份文档与纪要'}</span></div>}
        </>}
        <div><MessageSquare size={19} /><strong>{counts.messages || 0}</strong><span>{scope === 'history' ? '条关键变化' : '条沟通'}</span></div>
        <div><Sparkles size={19} /><strong>{customerGroups.filter(group=>group.project_id).length}</strong><span>个项目已整理</span></div>
      </section>
      <div className="digest-section-heading"><h2>{scope === 'history' ? '按客户看历史脉络' : '按客户看沟通进展'}</h2><span>{digest.date} 整理 · 每条保留实际沟通日期</span></div>
      {scope === 'history'||scope==='customer' ? <label className="digest-customer-select">查看客户或业务对象<select aria-label="历史客户筛选" value={selected} onChange={e => setCustomer(e.target.value)}><option value="全部">全部客户与业务参考</option>{!projectCustomers.includes(selected)&&!referenceCustomers.includes(selected)&&selected!=='全部'&&<option value={selected}>{selected} · 当前范围无匹配</option>}<optgroup label="已有项目客户">{projectCustomers.map(name => <option key={name} value={name}>{name}</option>)}</optgroup>{referenceCustomers.length > 0 && <optgroup label="其他业务往来 · 尚未关联具体项目">{referenceCustomers.map(name => <option key={name} value={name}>{name}</option>)}</optgroup>}</select><span>{projectCustomers.length} 个已有项目客户</span></label> : <nav className="digest-filters" aria-label="客户筛选">{customers.map(name => <button key={name} aria-pressed={selected === name} onClick={() => setCustomer(name)}>{name}</button>)}</nav>}
      <nav className="digest-filters" aria-label="沟通类型筛选"><button aria-pressed={communicationType === 'all'} onClick={() => setCommunicationType('all')}>全部沟通</button>{Object.entries(COMMUNICATION_TYPES).filter(([type]) => typeCounts[type] || communicationType === type).map(([type, label]) => <button key={type} aria-pressed={communicationType === type} onClick={() => setCommunicationType(type)}>{label} {typeCounts[type] || 0}</button>)}</nav>
      {conversationRows.size > 0 && <details className="digest-conversations"><summary>沟通来源分类 · {conversationRows.size} 个会话或来源</summary><div><table><thead><tr><th>会话或来源</th><th>沟通对象</th><th>涉及客户</th></tr></thead><tbody>{[...conversationRows.values()].map(row => <tr key={row.key}><td>{row.name}</td><td title={row.reason}>{COMMUNICATION_TYPES[row.type]}</td><td>{[...row.customers].join('、')}</td></tr>)}</tbody></table></div></details>}
      <div className="digest-grid">{visibleGroups.map(group => <ResultGroup group={group} navigate={navigate} historical={scope === 'history'} key={scope + group.id} />)}</div>
      {matchingGroups.length === 0 && <p className="digest-role-reason">当前已整理范围内，没有匹配{selected==='全部'?'当前筛选':selected}的{communicationType==='all'?'沟通记录':'这类沟通'}。这不代表邮箱未连接或客户没有历史往来。</p>}
      {visibleGroups.length < matchingGroups.length && <div className="digest-load-more"><span>已展示 {visibleGroups.length} / {matchingGroups.length} 组，或直接按客户查找</span><button onClick={() => setHistoryLimit(limit => limit + 12)}>展开更多客户与项目</button></div>}
    </> : data && <section className="digest-empty"><Sparkles size={28} /><h2>{scope==='customer'?'当前范围暂无关联沟通':scope === 'history' ? history.state === 'failed' ? '历史整理进度已保留' : history.state === 'completed' ? '本次未发现新增业务线索' : '正在梳理微信历史脉络' : job.running ? '正在为你整理沟通成果' : '同步一次，直接看各项目发生了什么'}</h2><p>{scope==='customer'?'当前客户在最近归档成果与微信历史中未匹配到记录；不代表邮箱未连接或没有历史往来。':scope === 'history' ? history.state === 'failed' ? '已保存的记录不会丢失，恢复处理后会继续核对。' : history.state === 'completed' ? '已核对本次读取范围，没有可新增到客户或项目的内容。' : '自动核对客户、项目与原话，完成后会按客户直接展示。' : job.running ? '有结果就自动显示，不需要重复点击。' : '自动读取最近两天的材料、提炼进展并归档到客户与项目。'}</p></section>}
    {summary.analysisOnly && <div className="sync-progress" role="status"><LoaderCircle className="sync-spin" size={17} /><span>{summary.title} · {summary.detail}</span></div>}
    {summary.pending > 0 && !summary.analysisOnly && !job.running && <div className="sync-error"><CircleAlert size={17} /><span>部分内容尚未同步成功：{summary.detail || summary.title}。已归档结果保留。</span><button disabled={disabled} onClick={() => start('run')}>自动补齐</button></div>}
    <details className="sync-diagnostics"><summary>同步记录与来源情况{gaps.length ? ' · ' + gaps.length + ' 项读取范围说明' : ''}</summary>
      <div className="sync-connections">{(data?.connections || []).map((item, i) => <span key={item.name + i} className={item.available ? 'available' : 'unavailable'}>{item.available ? <CheckCircle2 size={15} /> : <CircleAlert size={15} />}{item.name}<small>{item.available ? '可读取' : '待连接'}</small></span>)}</div>
      <CommunicationReceiptScope receipt={receipt} job={job}/>
      {gaps.length > 0 && <ul>{gaps.map((g, i) => <li key={i}><strong>{g.source}</strong>：{g.reason}</li>)}</ul>}
      <button disabled={disabled} onClick={() => start('doctor')}>检查来源</button>
      <button className="sync-link" onClick={() => navigate('knowledge', { projectId: '' })}>查看全部历史资料<ArrowRight size={14} /></button>
    </details>
  </div>;
}
