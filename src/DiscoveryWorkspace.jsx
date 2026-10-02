import {isFormalCustomer} from './k100DirectoryModel.js';
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { ArrowRight, ArrowUpRight, Building2, ChevronDown, FileSearch, Search, GitBranch } from 'lucide-react';
import { useDiscardChanges } from './DiscardDialog.jsx';
import { api } from './api.js';
import { installLiveRefresh } from './liveRefresh.js';
import { usePublicSignals, SignalRows, ResearchOverview, OperationsStrip } from './PublicSignals.jsx';
import { discoveryLane, revenueRecord, outreachRoute, publicUrl, mergeQualification } from './discovery-model.js';
const initial = { owner_scope: 'unknown', protection: 'unknown', owner_name: '', checked_at: '', ownership_evidence: '', demand: 'unknown', contact_result: '', next_date: '' };
const KEY = 'discovery-context-v3';
function remembered() { try { return JSON.parse(sessionStorage.getItem(KEY)) || {}; } catch { return {}; } }
export default function DiscoveryWorkspace({ data:initialData, registerNavigationGuard, navigate, accountId='', onClose, relatedProjects=[] }) {
  const [data,setData]=useState(initialData||{}),[sourceError,setSourceError]=useState(''),[sourceLoading,setSourceLoading]=useState(true);
  const [crmRoster,setCrmRoster]=useState(null),[crmError,setCrmError]=useState('');
  useEffect(()=>{let live=true;api.get('/api/k100/customers').then(x=>{if(live)setCrmRoster(x.items);}).catch(()=>{if(live)setCrmError('CRM客户去重暂未完成，列表保留原记录。');});return()=>{live=false;};},[]);
  const sourceVersion=useRef(0);
  const selectedSnapshot=useRef(null);
  const refresh=useCallback(async()=>{
    const version=++sourceVersion.current;
    const keys=accountId?['accounts']:['prospecting','accounts'];
    const result=await Promise.allSettled(keys.map(key=>api.get(key==='accounts'?'/api/account-advancement':'/api/prospecting')));
    if(version!==sourceVersion.current)return;
    setData(previous=>({...previous,...Object.fromEntries(result.flatMap((r,i)=>r.status==='fulfilled'?[[keys[i],r.value]]:[]))}));
    setSourceError(result.map((r,i)=>r.status==='rejected'?`${keys[i]==='accounts'?'工作台准入记录':'机会列表'}暂未更新：${r.reason.message}`:'').filter(Boolean).join('；'));
    setSourceLoading(false);
  },[]);
  useEffect(()=>{refresh();const cleanup=installLiveRefresh(refresh);return()=>{sourceVersion.current++;cleanup();};},[refresh]);
  const [saved] = useState(remembered), askDiscard = useDiscardChanges();
  const {data:signalData,error:signalError}=usePublicSignals();
  const [lane, setLane] = useState(saved.lane || 'current'), [query, setQuery] = useState(saved.query || '');
  const [selection, setSelection] = useState(accountId?{kind:'account',id:accountId}:saved.selection || null);
  const [record, setRecord] = useState(initial), [prepared, setPrepared] = useState(null), [projectId, setProjectId] = useState('');
  const [dirty, setDirty] = useState(false), [busy, setBusy] = useState(false), [loading, setLoading] = useState(false);
  const [mergeBackup, setMergeBackup] = useState(null);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [conflict, setConflict] = useState(null);
  const request = useRef(0), mounted = useRef(true), dirtyRef = useRef(false), listScroll = useRef(saved.scroll || 0);
  dirtyRef.current = dirty;
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const leads = (data.prospecting?.leads || []).filter(item=>!isFormalCustomer(item,crmRoster||[])).map(item => ({ ...item, kind: 'lead', name: item.company, lane: item.decision === "accepted" ? "admitted" : item.user_surface === "candidate" ? "current" : item.user_surface === "watch" ? "history" : item.decision === "ignored" ? "ignored" : "potential", revenue: revenueRecord(item) }));
  const accounts = (data.accounts?.accounts || []).map(item => ({ ...item, kind: 'account', revenue: revenueRecord(item) }));
  const liveSelected = [...leads, ...accounts].find(item => item.kind === selection?.kind && item.id === selection?.id);
  if(liveSelected) selectedSnapshot.current=liveSelected;
  const selected = liveSelected || (selectedSnapshot.current?.kind===selection?.kind && selectedSnapshot.current?.id===selection?.id ? selectedSnapshot.current : null);
  const sourceMissing=!!selected&&!liveSelected&&!sourceLoading;
  const admittedAccount = selected?.kind === 'lead' && selected.decision === 'accepted' && prepared?.account_id ? accounts.find(item => item.id === prepared.account_id) : null;
  const canLeave = async () => !busy && (!dirty || await askDiscard('本次补充尚未保存，离开会放弃修改。'));
  useEffect(() => registerNavigationGuard?.(canLeave), [dirty, busy, registerNavigationGuard]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; request.current++; }; }, []);
  useEffect(() => { const warn = e => { if (dirty || busy) { e.preventDefault(); e.returnValue = ''; } }; window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [dirty, busy]);
  useEffect(() => { if(accountId)return; try { sessionStorage.setItem(KEY, JSON.stringify({ lane, query, selection, scroll: listScroll.current })); } catch {} }, [lane, query, selection]);
  async function loadContext(item, preserve = false) {
    const id = ++request.current; setLoading(true); setError('');
    try {
      const value = await api.get(`/api/discovery/prepare?kind=${encodeURIComponent(item.kind)}&source_id=${encodeURIComponent(item.id)}`);
      if (!mounted.current || request.current !== id) return;
      setPrepared(value); setProjectId(value.existing?.project_id || (value.projects.length === 1 ? value.projects[0].id : ''));
      if (!preserve && !dirtyRef.current) setRecord({ ...initial, ...value.note });
    } catch(e) { if (mounted.current && request.current === id) setError(e.message); }
    finally { if (mounted.current && request.current === id) setLoading(false); }
  }
  useEffect(() => { setPrepared(null); setConflict(null); setMergeBackup(null); setNotice(''); if (selected) loadContext(selected); }, [selected?.kind, selected?.id]);
  async function choose(item) {
    if(item.kind===selection?.kind&&item.id===selection?.id)return;
    if (!await canLeave()) return;
    if (!selected) listScroll.current = document.querySelector('.app-main')?.scrollTop || 0;
    setDirty(false); dirtyRef.current = false; setRecord(initial); setSelection({ kind: item.kind, id: item.id });
  }
  async function back() {
    if (!await canLeave()) return;
    if(accountId){onClose?.();return;}
    setSelection(null); setDirty(false); setPrepared(null); request.current++;
    requestAnimationFrame(() => document.querySelector('.app-main')?.scrollTo({ top: listScroll.current }));
  }
  const edit = key => e => { setRecord(value => ({ ...value, [key]: e.target.value })); setDirty(true); setNotice(''); };
  async function save(e) {
    e.preventDefault(); if (!prepared) return; setBusy(true); setError('');
    try {
      await api.post('/api/discovery/notes', { ...record, kind: selected.kind, source_id: selected.id, revision: prepared.revision, entity_version: prepared.entity_version });
      setDirty(false); dirtyRef.current = false; setConflict(null); setNotice('实际补充已保存，下一步已重新准备。'); await loadContext(selected);
    } catch(e) {
      setError(e.message);
      try { const latest = await api.get(`/api/discovery/prepare?kind=${selected.kind}&source_id=${encodeURIComponent(selected.id)}`); if (latest.entity_version !== prepared.entity_version) setError('来源主体或内容已变化，当前输入保留；请复制需要的内容后返回列表重新核对。'); else if (latest.revision !== prepared.revision) setConflict(latest); } catch {}
    } finally { setBusy(false); }
  }
  async function admit() {
    setBusy(true); setError('');
    try { await api.post('/api/prospecting/lead', { id: selected.id, target: 'accept' }); await refresh({ quiet: true }); await loadContext(selected); setNotice('已进入工作台工作台准入记录；CRM归属仍按实际查询记录。'); }
    catch(e) { setError(e.message); } finally { setBusy(false); }
  }
  async function handoff() {
    setBusy(true); setError('');
    try {
      const result = await api.post('/api/discovery/handoff', { kind: selected.kind, source_id: selected.id, revision: prepared.revision, source_version: prepared.source_version, project_id: projectId });
      setNotice(result.message); await refresh({ quiet: true }); await loadContext(selected);
    } catch(e) { setError(e.message); } finally { setBusy(false); }
  }
  async function openAction() {
    const item = prepared?.existing;
    if (!item) return;
    if (item.project_id) await navigate('projects', { projectId: item.project_id, projectTitle: item.project_title, customer: item.customer });
    else await navigate('reminders', { projectId: '', focusAction: item });
  }
  const large = [...new Map([...leads, ...accounts].filter(item => item.revenue.checked && item.revenue.amount >= 50 && !item.name?.includes(' / ')).map(item => [item.name, item])).values()];
  const rows = (lane === 'accounts' ? accounts : lane === 'large' ? large : leads.filter(item => item.lane === lane).slice(0, lane === "current" ? 3 : lane === "history" ? 20 : 100)).filter(item => `${item.name} ${item.title || ''}`.includes(query));
  const PreparationSurface=accountId&&relatedProjects.length>0&&!prepared?.existing?'details':'section';
  const selectedPanel = selected ? <div className={accountId?"page-stack customer-account-editor":"page-stack discovery-inline-editor"}>
    <div className="workspace-shortcuts"><button className="plain-action" onClick={back}>{accountId?'返回客户目录':'收起补充与承接'}</button><button className="plain-action" onClick={() => navigate('projects', { projectId: '', resetProjectFilter: true })}>回首页</button></div>
    <header><p className="eyebrow">{selected.kind==='account'||prepared?.account_id ? '工作台准入记录 · 沿用同一跟进' : '公开信号 · 尚待准入'}</p><h2>{selected.name}{accountId?'':' · 核实与承接'}</h2></header>
    {accountId&&relatedProjects.length>0&&<section aria-label="该客户的项目"><h3>项目各自保留范围与判断</h3><div className="customer-account-projects">{relatedProjects.map(project=><button className="plain-action" key={project.id} onClick={()=>navigate('projects',{projectId:project.id,customer:selected.name})}>{project.title}<ArrowUpRight size={13}/></button>)}</div></section>}
    {sourceMissing&&<p role="alert">来源列表已更新，本次输入仍保留。请复制需要的内容后收起补充，再选择最新记录核对。</p>}
    {admittedAccount && <button className="plain-action" onClick={() => choose(admittedAccount)} disabled={busy}>进入工作台准入记录跟进</button>}
    {loading && <p role="status">正在准备来源与下一步…</p>}
    {prepared && <PreparationSurface className="project-judgement">{PreparationSurface==='details'&&<summary>账户归属与内部核实</summary>}{accountId&&relatedProjects.length>0&&!prepared.existing&&<p>项目的本轮行动请从上方对应项目查看；下方仅维护账户归属，不代表需要重新建联或暂停已有项目。</p>}<h2>{prepared.existing ? '本轮已承接' : accountId&&relatedProjects.length ? '账户归属核实（与项目推进分开）' : '下一步已准备'}</h2>
      <p>{prepared.existing?.next_step || prepared.existing?.action || prepared.action}</p><div className="workspace-shortcuts"><span>{(prepared.existing?.internal_only || prepared.internal_only) ? '仅内部核实' : '可准备客户跟进'}</span><span>{(prepared.existing?.deadline || prepared.due) ? `约定复访 ${String(prepared.existing?.deadline || prepared.due).replace('T',' ').replace('+08:00','')}` : '尚无约定日期'}</span></div>
      {prepared.existing ? <><p>{prepared.existing.status} · 日期和反馈在同一跟进记录中维护</p><button className="plain-action" onClick={openAction} disabled={busy || dirty || sourceMissing}>打开现有跟进</button></> : prepared.handled ? <p>这轮事项已处理。取得新的沟通结果后，补充事实即可准备下一轮。</p> : <>
        {prepared.projects.length > 0 && <label className="native-field"><span>承接位置</span><select value={projectId} onChange={e => setProjectId(e.target.value)} disabled={busy}><option value="">先保留在该客户跟进</option>{prepared.projects.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label>}
        {prepared.ready ? <button className="plain-action" onClick={handoff} disabled={busy || dirty || sourceMissing}>{busy ? '承接中…' : prepared.internal_only ? '加入内部核实' : '承接为本轮跟进'}</button> : <><p>{prepared.blocked}</p>{selected.kind === 'lead' && selected.user_surface === 'candidate' && selected.decision !== 'accepted' && <button className="plain-action" onClick={admit} disabled={busy || dirty || sourceMissing}>准入工作台账户</button>}</>}
      </>}
      {dirty && <p>先保存本次补充，再沿用它准备下一步。</p>}
    </PreparationSurface>}
    <details className="project-judgement"><summary>信号与判断依据</summary><p>{selected.title || selected.recent_signal || '暂无新需求证据'}</p><p>{outreachRoute(record)}</p><p>{selected.revenue.label}</p>{publicUrl(selected.source_url) && <a href={publicUrl(selected.source_url)} target="_blank" rel="noreferrer">原始公开信号 ↗</a>}{selected.revenue.url && <p><a href={selected.revenue.url} target="_blank" rel="noreferrer">营收来源 ↗</a></p>}</details>
    <details open={dirty || undefined}><summary>补充或更正实际沟通、归属</summary>
      <form className="qualification-form" onSubmit={save}><fieldset disabled={busy || !prepared}><legend>归属与保护</legend><a href="https://crm.example.invalid/sales-workspace" target="_blank" rel="noreferrer">公司 CRM 主体查询 ↗</a><div className="project-action-form">
        <label className="native-field"><span>主体归属</span><select value={record.owner_scope} onChange={edit('owner_scope')}>{[['unknown','尚未核实'],['mine','本人名下'],['other_k100','其他 K100 同事'],['direct','直销团队'],['channel','渠道团队'],['standard','标品团队'],['unowned','已查询，待按规则认领']].map(([v,l]) => <option value={v} key={v}>{l}</option>)}</select></label>
        <label className="native-field"><span>保护状态</span><select value={record.protection} onChange={edit('protection')}>{[['unknown','尚未核实'],['mine','本人保护'],['other','他人保护'],['none','已核实无保护']].map(([v,l]) => <option value={v} key={v}>{l}</option>)}</select></label>
        <label className="native-field"><span>内部负责人</span><input value={record.owner_name} onChange={edit('owner_name')} /></label><label className="native-field"><span>归属核实日期</span><input type="date" max={today} value={record.checked_at} onChange={edit('checked_at')} /></label></div>
        <label className="native-field"><span>CRM 查询依据</span><textarea value={record.ownership_evidence} onChange={edit('ownership_evidence')} rows={2} /></label>
        <label className="native-field"><span>本轮需求</span><select value={record.demand} onChange={edit('demand')}>{[['unknown','尚未沟通验证'],['confirmed','沟通确认有需求'],['none','本轮暂无需求'],['later','已有服务商，保留后续窗口']].map(([v,l]) => <option value={v} key={v}>{l}</option>)}</select></label>
        <label className="native-field"><span>实际沟通结果</span><textarea value={record.contact_result} onChange={edit('contact_result')} rows={3} /></label><label className="native-field"><span>约定复访日期</span><input type="date" value={record.next_date} onChange={edit('next_date')} /></label>
      </fieldset><button className="plain-action" disabled={busy || !prepared || sourceMissing}>{busy ? '保存中…' : '保存补充'}</button></form>
    </details>
    {conflict && <section role="alert"><strong>另一页面已有新版，你的输入保留</strong><p>合并时保留新版归属和保护；同一字段均有修改时保留新版，请核对后再编辑。</p><p>{outreachRoute(conflict.note)}</p><p>新版沟通：{conflict.note.contact_result || '暂无'} · 复访：{conflict.note.next_date || '未约定'}</p><button className="plain-action" onClick={() => {
      const result = mergeQualification({ ...initial, ...prepared.note }, record, { ...initial, ...conflict.note });
      setMergeBackup(result.conflicts.map(key => ({key, value:record[key]}))); setRecord(result.merged); setPrepared(conflict); setConflict(null);
      setNotice(result.conflicts.length ? '存在同时修改的字段，已保留新版。原输入保存在下面，可复制后重新编辑。' : '已保留双方未冲突的修改，请核对后保存。');
    }}>保留新版边界，合并其他补充</button></section>}
    {mergeBackup?.length > 0 && <details><summary>保留的原输入（尚未重新保存）</summary>{mergeBackup.map(item => <p key={item.key}>{({owner_scope:'归属',protection:'保护',owner_name:'负责人',checked_at:'核实日期',ownership_evidence:'归属依据',demand:'需求',contact_result:'沟通',next_date:'复访'})[item.key]}：{item.value || '空'}</p>)}</details>}
    {error && <p role="alert">{error}</p>}<p role="status">{notice}</p>
  </div> : null;
  const signalRows=(signalData?.signals||[]).filter(item=>!isFormalCustomer(item,crmRoster||[])).filter(item=>`${item.customer} ${item.title} ${item.summary}`.includes(query));
  const counts={signals:signalRows.length,current:Math.min(3,leads.filter(x=>x.lane==='current').length),history:Math.min(20,leads.filter(x=>x.lane==='history').length),potential:leads.filter(x=>x.lane==='potential').length,accounts:accounts.length};
  const tabs=[['signals','已收录信号'],['current','待你准入'],['history','升级与替换'],['potential','后台待补证'],['accounts','工作台准入记录']];
  if(accountId)return <section className="customer-account-work" aria-label="客户跟进工作面">{selectedPanel||<><button className="plain-action" onClick={onClose}>返回客户目录</button><p role={sourceError?'alert':'status'}>{sourceLoading?'正在核对这位客户的正式记录…':sourceError||'未找到对应正式客户，未切换到其他客户。'}</p></>}</section>;
  return <div className="page-stack discovery-control-room">
    <header className="discovery-heading"><div><span className="eyebrow">客户情报</span><h1>战略客户雷达</h1><p>从外部变化，找到值得验证的下一步。</p></div></header>
    <ResearchOverview data={signalData} error={signalError} compact/>{sourceError&&<p role="alert">{sourceError}。公开信号仍可独立阅读。<button className="plain-action" onClick={refresh}>重试列表</button></p>}
    <div className="workspace-shortcuts signal-filter" aria-label="机会分类">{tabs.filter(([id])=>!['signals','potential'].includes(id)).map(([id,label])=><button key={id} aria-pressed={lane===id} onClick={async()=>{if(await canLeave()){setLane(id);setSelection(null);setDirty(false);}}}>{label} <span>{id==="signals"&&!signalData?"…":id!=="signals"&&sourceLoading?"…":counts[id]}</span></button>)}<details className="radar-research-menu" open={['signals','potential'].includes(lane)||undefined}><summary>研究记录{['signals','potential'].includes(lane)?' · '+tabs.find(([id])=>id===lane)?.[1]:''}</summary><div>{tabs.filter(([id])=>['signals','potential'].includes(id)).map(([id,label])=><button key={id} aria-pressed={lane===id} onClick={async()=>{if(await canLeave()){setLane(id);setSelection(null);setDirty(false);}}}>{label} <span>{id==="signals"&&!signalData?"…":id!=="signals"&&sourceLoading?"…":counts[id]}</span></button>)}</div></details><label className="native-field"><span>查找客户或信号</span><input aria-label="查找客户或信号" value={query} disabled={dirty||busy} title={dirty?"先保存或收起当前补充，再筛选":""} onChange={e=>setQuery(e.target.value)} placeholder="客户、标题或公开变化"/></label></div>
    {crmError&&<p role="status">{crmError}</p>}{lane==='signals'?<><SignalRows rows={signalRows} navigate={navigate}/>{signalData&&!signalRows.length&&<p className="signal-empty">没有匹配的已保存信号；搜索是否完成以上方回执为准。</p>}</>:<>
      <p className="discovery-boundary">{lane==='current'?'最多 3 个待判断对象；招采需核清最早截止并保留 14–30 天准备时间。':lane==='history'?'历史采购证明过往意图或供应商关系，不代表当前可投；等待新触发，不自动生成催办。':lane==='potential'?'来源、主体、营收或窗口尚有缺口；留在后台研究，不占用你的今日行动。':'已准入客户在工作台准入记录中跟进，不因旧标讯过期退回候选。'}</p>
      <div className="discovery-judgement-list">{rows.map(item=><React.Fragment key={`${item.kind}:${item.id}`}><article className="discovery-lead-card">
        <header><span className="discovery-lead-avatar"><Building2 size={18}/></span><div><h2>{item.name}</h2><span>{item.kind==='account'?'工作台准入记录':item.status||'待核实'}</span></div><span className="discovery-revenue">{item.revenue.label}</span><button className="plain-action" onClick={()=>choose(item)}>{item.kind==='account'?'查看同一客户跟进':'补充事实 / 准入判断'}<ArrowUpRight size={13}/></button></header>
        <div className="discovery-lead-summary"><h3>{item.title||item.recent_signal||'已准入账户'}</h3><span>最早截止 <strong>{item.time_window?.deadline||item.deadline||'未核实'}</strong></span></div>
        <details className="discovery-lead-chain"><summary><GitBranch size={14}/> 查看依据、进入逻辑与下一步<ChevronDown size={14}/></summary><div className="discovery-lead-chain-grid">
          <section><span className="discovery-node-label"><FileSearch size={16}/> 来源与匹配依据</span><p>{Array.isArray(item.why_matched)?item.why_matched.join('；'):item.why_matched||item.purchase_signal||'本轮尚无新需求证据'}</p><small>{item.time_window?.note||item.time_window?.reason||item.actionability_reason||item.execution_boundary||''}</small><div className="discovery-source-links">{publicUrl(item.source_url)&&<a href={publicUrl(item.source_url)} target="_blank" rel="noreferrer">原始信号 <ArrowUpRight size={12}/></a>}{item.revenue.url&&<a href={item.revenue.url} target="_blank" rel="noreferrer">营收依据 <ArrowUpRight size={12}/></a>}</div></section>
          <span className="discovery-chain-arrow" aria-hidden="true"><ArrowRight size={18}/></span><section><span className="discovery-node-label"><Building2 size={16}/> AI 进入判断</span><p>{item.entry_strategy||item.youzan_fit||'继续核实需求、进入理由和关键负责人。'}</p><small>{item.supplier_path||'供应商与竞争路径待核验'}</small></section>
          <span className="discovery-chain-arrow" aria-hidden="true"><ArrowRight size={18}/></span><section><span className="discovery-node-label"><Search size={16}/> {lane==='history'?'等待下一触发':'建议核实动作'}</span><p>{item.next_trigger||item.next_step||'尚未形成可信的下一步，不自动产生行动。'}</p><small>由你决定投入与承接</small></section>
        </div></details>
      </article>{selected?.id===item.id&&selected?.kind===item.kind&&selectedPanel}</React.Fragment>)}</div>
      {selected&&!rows.some(item=>item.kind===selected.kind&&item.id===selected.id)&&selectedPanel}{!rows.length&&<p className="signal-empty">{sourceLoading?'正在读取该类记录…':sourceError?'本轮列表读取未完成，不能据此判断没有记录。':null}{!sourceLoading&&!sourceError&&<>{lane==='current'?'本轮没有符合准入门槛的候选；后台观察记录仍在保留。':'这个分类暂时没有记录。'}</>}</p>}
    </>}
    <details className="research-operations"><summary>后台同步与人工分工</summary><OperationsStrip data={signalData}/></details>{error&&<p role="alert">{error}</p>}<p role="status">{notice}</p>
  </div>;
}
