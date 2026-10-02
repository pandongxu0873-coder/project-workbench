import {useDiscardChanges} from './DiscardDialog.jsx';
import {CustomerFiles} from './CustomerFiles.jsx';
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import gsap from 'gsap';
import { api } from './api.js';
import { installLiveRefresh } from './liveRefresh.js';
import { customerFacet } from './materialCustomers.js';
import { SourceText } from './SourceText.jsx';
import './material-library.css';

const CATEGORIES = ['有业务增量', '已有内容已归档', '历史参考', '非业务或测试', '内容不足待核'];
const PROCESSING = new Set(['running', 'processing', 'pending', 'queued', 'transcribing', '处理中', '转写中', '待处理']);
const array = value => Array.isArray(value) ? value : [];
const text = value => typeof value === 'string' ? value : '';
const isProcessing = item => PROCESSING.has(text(item.processing));
const fileUrl = id => `/api/material-library/file?asset_id=${encodeURIComponent(id)}`;
const isAudio = source => /audio|音频|录音/i.test(text(source.kind));
const minutes = value => Number.isFinite(Number(value)) && Number(value) > 0 ? `${Math.floor(Number(value) / 60)}分${Math.floor(Number(value) % 60) ? `${Math.floor(Number(value) % 60)}秒` : ''}` : '';
const evidenceText = value => typeof value === 'string' ? value : text(value?.quote) || text(value?.text) || text(value?.summary) || text(value?.label);
const count = value => Number.isInteger(value) && value >= 0 ? value.toLocaleString('zh-CN') : '—';
function readPreference(key) {
  try { const value = JSON.parse(sessionStorage.getItem(key)); return value && typeof value === 'object' ? value : {}; } catch { return {}; }
}

export function MaterialLibrary({ projectId = '', navigate, refreshKey }) {
  const [surface,setSurface]=useState('files'),editState=useRef({});
  const askDiscard=useDiscardChanges(),onEditState=useCallback(value=>{editState.current=value;},[]);
  async function switchSurface(next){if(editState.current.busy)return;if(editState.current.editing&&!await askDiscard('文件标注未保存，是否离开？'))return;setSurface(next);}
  return <><header className="page-header material-page-heading"><div><h1>材料库</h1><p className="page-subtitle">按客户和项目查找原件，核对版本与来源。</p></div></header><div className="customer-directory-mode"><button aria-pressed={surface==='files'} onClick={()=>switchSurface('files')}>客户文件档案</button><button aria-pressed={surface==='communications'} onClick={()=>switchSurface('communications')}>沟通与来源记录</button></div>{surface==='files'?<CustomerFiles key={projectId||'all'} grouped onEditState={onEditState} projectId={projectId}/>:<LibraryContent key={projectId || 'all'} projectId={projectId} navigate={navigate} refreshKey={refreshKey}/>}</>;
}

function LibraryContent({ projectId, navigate, refreshKey }) {
  const key = `material-library-v1:${projectId || 'all'}`;
  const [initial] = useState(() => readPreference(key));
  const [tab, setTab] = useState(initial.tab === 'files' ? 'files' : 'recordings');
  const [query, setQuery] = useState(text(initial.query));
  const [customer, setCustomer] = useState(text(initial.customer));
  const [category, setCategory] = useState(text(initial.category) || '重点');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selection, setSelected] = useState(null);
  const selected = selection && [...array(data?.recordings), ...array(data?.files)].find(item => item.id === selection.id);
  const [source, setSource] = useState(null);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [sourceError, setSourceError] = useState('');
  const [audioId, setAudioId] = useState('');
  const [audioError, setAudioError] = useState('');
  const [navBusy, setNavBusy] = useState(false);
  const [checking, setChecking] = useState('');
  const [checkNotice, setCheckNotice] = useState('');
  const root = useRef(null), dialog = useRef(null), list = useRef(null), trigger = useRef(null);
  const live = useRef(true), requestId = useRef(0), sourceRequestId = useRef(0), restored = useRef(false);
  const scroll = useRef(Number.isFinite(initial.scroll) ? initial.scroll : 0);
  const preference = useRef({ tab, query, customer, category });
  preference.current = { tab, query, customer, category };
  const persist = useCallback(() => {
    try { sessionStorage.setItem(key, JSON.stringify({ ...preference.current, scroll: scroll.current })); } catch { /* Session storage may be unavailable. */ }
  }, [key]);
  const load = useCallback(async (quiet = false) => {
    const id = ++requestId.current;
    if (quiet !== true) setLoading(true); setError('');
    try {
      const value = await api.get('/api/material-library');
      if (!value || !Array.isArray(value.recordings) || !Array.isArray(value.files)) throw new Error('资料列表暂时无法读取');
      if (live.current && id === requestId.current) setData(value);
    } catch (e) { if (live.current && id === requestId.current) setError(e.message || '资料加载失败'); }
    finally { if (live.current && id === requestId.current) setLoading(false); }
  }, []);
  useEffect(() => {
    live.current = true; load();
    return () => { live.current = false; requestId.current++; sourceRequestId.current++; persist(); };
  }, [load, persist]);
  useEffect(() => installLiveRefresh(() => load(true)), [load]);
  useEffect(() => { if (refreshKey) load(true); }, [refreshKey, load]);
  // An open detail follows the current list, including removed/restricted assets.
  useEffect(() => {
    sourceRequestId.current++; setSource(null); setSourceBusy(false); setSourceError('');
    setAudioId(''); setAudioError('');
  }, [JSON.stringify(selected)]);
  useEffect(persist, [tab, query, customer, category, persist]);
  useLayoutEffect(() => {
    if (!data || restored.current || !list.current) return;
    list.current.scrollTop = scroll.current; restored.current = true;
  }, [data]);
  useLayoutEffect(() => {
    if (!data) return;
    const mm = gsap.matchMedia();
    mm.add('(prefers-reduced-motion: no-preference)', () => {
      const ctx = gsap.context(() => gsap.from('.ml-entry', { y: 7, opacity: 0, duration: .22, stagger: .025, clearProps: 'transform,opacity' }), root);
      return () => ctx.revert();
    });
    return () => mm.revert();
  }, [Boolean(data)]);
  useLayoutEffect(() => {
    if (!selected || !dialog.current) return;
    const el = dialog.current;
    if (!el.open) el.showModal();
    const mm = gsap.matchMedia();
    mm.add('(prefers-reduced-motion: no-preference)', () => {
      const tween = gsap.fromTo(el, { y: 12, opacity: 0 }, { y: 0, opacity: 1, duration: .2, clearProps: 'transform,opacity' });
      return () => tween.revert();
    });
    return () => { mm.revert(); if (el.open) el.close(); };
  }, [selected?.id]);

  const recordings = array(data?.recordings);
  // Project context narrows recordings only: the API does not provide project_id on desktop files.
  const scoped = useMemo(() => recordings.filter(item => !projectId || item.project_id === projectId), [data, projectId]);
  const base = tab === 'recordings' ? scoped : array(data?.files).filter(item=>!projectId||item.project_id===projectId);
  const customers = useMemo(() => [...new Set(base.map(item => customerFacet(item.customer)).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN')), [base]);
  const chosenCustomer = customerFacet(customer);
  const activeCustomer = customer && customers.includes(chosenCustomer) ? chosenCustomer : '';
  const counts = CATEGORIES.map(label => ({ label, value: scoped.filter(item => item.category === label).length }));
  const running = scoped.filter(isProcessing).length;
  const filtered = base.filter(item => {
    const matchCategory = (tab === 'files' && category !== '处理缺口') || category === '全部' || (category === '重点' ? item.category === '有业务增量' || isProcessing(item) : category === '处理缺口' ? item.pipeline?.stale || item.pipeline?.missing_asset_ids?.length : category === '处理中' ? isProcessing(item) : item.category === category);
    const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    const haystack = [item.title, item.original_title, item.customer, customerFacet(item.customer), item.project_title, item.summary, item.category].filter(Boolean).join(' ').toLocaleLowerCase();
    return matchCategory && (!activeCustomer || customerFacet(item.customer) === activeCustomer) && terms.every(term => haystack.includes(term));
  });
  const resetScroll = () => { scroll.current = 0; if (list.current) list.current.scrollTop = 0; };
  const changeFilter = (setter, value) => { setter(value); resetScroll(); };
  const open = (item, event) => {
    trigger.current = event.currentTarget;
    sourceRequestId.current++; setSource(null); setSourceError(''); setSourceBusy(false); setAudioId(''); setAudioError('');
    setSelected(item);
  };
  const close = () => {
    sourceRequestId.current++; setSourceBusy(false); setSource(null); setAudioId(''); setSelected(null);
    dialog.current?.close();
    const previous = trigger.current;
    requestAnimationFrame(() => { if (live.current && previous?.isConnected) previous.focus({ preventScroll: true }); });
  };
  const readSource = async item => {
    const id = ++sourceRequestId.current;
    setSourceBusy(true); setSourceError(''); setSource(null);
    try {
      const value = await api.get(`/api/material-library/source?asset_id=${encodeURIComponent(item.id)}`);
      if (typeof value?.content !== 'string') throw new Error('暂时无法读取这份原文');
      if (live.current && sourceRequestId.current === id) setSource(value);
    } catch (e) { if (live.current && sourceRequestId.current === id) setSourceError(e.message || '原文读取失败，请重试'); }
    finally { if (live.current && sourceRequestId.current === id) setSourceBusy(false); }
  };
  const go = async (view, options) => {
    if (navBusy) return;
    setNavBusy(true); persist();
    try { await navigate(view, options); }
    catch { if (live.current) setError('暂时无法切换，请重试'); }
    finally { if (live.current) setNavBusy(false); }
  };
  const sources = array(selected?.sources).filter(item => item?.id && item.available);
  const activeConflicts = array(data?.conflicts).filter(item => array(item.affected_ids).includes(selected?.id));

  return <section className="material-library" ref={root} aria-labelledby="ml-heading">
    <header className="ml-header ml-entry">
      <div><p className="ml-eyebrow">录音与文件 · 有据可查</p><h1 id="ml-heading">资料中心</h1></div>
      <button type="button" onClick={() => go('agent', {})} disabled={navBusy}>返回首页</button>
    </header>
    <div className="ml-metrics ml-entry" aria-label="资料汇总">
      <div><strong>{count(data?.summary?.recording_count)}</strong><span>录音</span></div>
      <div><strong>{count(data?.coverage?.summary?.text_count)}</strong><span>已有转写或摘录</span></div>
      <div><strong>{count(data?.summary?.file_count)}</strong><span>文件与附件</span></div>
      <div><strong>{count(data?.coverage?.summary?.exception_count)}</strong><span>来源变化或读取异常</span></div>
    </div>
    {projectId && <p className="ml-context">当前项目资料 · 按已关联项目筛选</p>}
    {error && <div role="alert" className="ml-notice">{error}<button type="button" onClick={load} disabled={loading}>重试</button></div>}
    {loading && <p role="status" className="ml-notice">{data ? '正在刷新资料…' : '正在读取录音和文件…'}</p>}
    {data && <>
      <CoverageStatus coverage={data.coverage && { ...data.coverage, exceptions: array(data.coverage.exceptions).filter(item => !projectId || item.kind === 'files' || item.project_id === projectId) }} onException={item => { setTab(item.kind); setCategory('处理缺口'); setQuery(''); setCustomer(''); resetScroll(); }} />
      <div className="ml-toolbar ml-entry">
        <div className="ml-tabs" aria-label="资料类型">
          <button type="button" aria-pressed={tab === 'recordings'} onClick={() => changeFilter(setTab, 'recordings')}>录音</button>
          <button type="button" aria-pressed={tab === 'files'} onClick={() => changeFilter(setTab, 'files')}>文件与附件</button>
        </div>
        <label className="ml-search"><span className="ml-sr-only">搜索资料</span><input type="search" value={query} onChange={e => changeFilter(setQuery, e.target.value)} placeholder="搜索客户、主题或原文件名" /></label>
        <label><span className="ml-sr-only">客户筛选</span><select value={activeCustomer} onChange={e => changeFilter(setCustomer, e.target.value)}><option value="">全部客户</option>{customers.map(name => <option key={name}>{name}</option>)}</select></label>
      </div>
      {tab === 'recordings' && <div className="ml-classification">
        <div className="ml-ratio" aria-label={counts.map(item => `${item.label}${item.value}条`).join('，')} role="img">{counts.filter(item => item.value).map(item => <span key={item.label} className={`ml-tone-${CATEGORIES.indexOf(item.label)}`} style={{ flex: item.value }} />)}</div>
        <div className="ml-filters">{['重点', '全部', '处理缺口', '处理中', ...CATEGORIES].map(label => <button type="button" key={label} aria-pressed={category === label} onClick={() => changeFilter(setCategory, label)}>{label}{label === '处理中' ? ` ${running}` : counts.find(item => item.label === label) ? ` ${counts.find(item => item.label === label).value}` : ''}</button>)}</div>
      </div>}
      {array(data.conflicts).length > 0 && <details className="ml-conflicts"><summary>已保留的资料差异 <span>{data.conflicts.length}</span></summary>{data.conflicts.map((item, i) => <div key={`${item.title}-${i}`}><strong>{item.title}</strong><p>{item.summary}</p></div>)}</details>}
      <div className="ml-list-heading"><span>{filtered.length} 份{query || activeCustomer ? '匹配资料' : '资料'}</span><button type="button" onClick={load} disabled={loading}>刷新</button></div>
      <div className="ml-list" ref={list} onScroll={e => { scroll.current = e.currentTarget.scrollTop; persist(); }} aria-label={tab === 'recordings' ? '录音列表' : '文件与附件列表'}>
        {filtered.map(item => <button type="button" className="ml-row" key={item.id} onClick={event => open(item, event)} aria-haspopup="dialog">
          <span className="ml-row-main"><strong>{item.title || item.original_title || '未命名资料'}</strong><span>{item.summary || (isProcessing(item) ? '正在整理内容' : '展开查看资料')}</span></span>
          <span className="ml-row-meta"><span>{customerFacet(item.customer)}</span>{tab === 'recordings' && <time>{text(item.recorded_at).slice(0, 10)} {minutes(item.duration_seconds)}</time>}{item.pipeline?.stale && <small>内容变化待复核</small>}<small className={isProcessing(item) ? 'ml-processing' : ''}>{isProcessing(item) ? '处理中' : item.category || '待整理'}</small></span>
        </button>)}
        {!filtered.length && <div className="ml-empty"><p>{tab === 'recordings' && category === '重点' ? '当前没有业务增量或处理中的录音' : '没有匹配的资料'}</p><button type="button" onClick={() => { setQuery(''); setCustomer(''); setCategory('全部'); resetScroll(); }}>查看全部</button></div>}
      </div>
    </>}
    {selected && <dialog className="ml-dialog" ref={dialog} aria-labelledby="ml-detail-title" onCancel={event => { event.preventDefault(); close(); }} onClick={event => { if (event.target === event.currentTarget) close(); }}>
      <div className="ml-detail">
        <header><div><p className="ml-eyebrow">{selected.customer || '归属待核'} · {isProcessing(selected) ? '处理中' : selected.category}</p><h2 id="ml-detail-title">{selected.title || selected.original_title || '资料详情'}</h2></div><button type="button" autoFocus onClick={close} aria-label="关闭资料详情">关闭</button></header>
        {selected.pipeline && <div className="ml-stages" aria-label="材料处理阶段">{[[selected.pipeline.original_available, tab === 'recordings' ? '原始录音可读' : '归档文件可读'], [tab === 'recordings' ? selected.pipeline.text_ready : sources.some(item => item.available && item.readable), tab === 'recordings' ? '转写/摘录' : '文字资料可读'], [selected.pipeline.classified, '内容分类'], [selected.pipeline.linked, '关联项目']].map(([done, label]) => <span key={label} data-done={done}>{done ? '✓' : '·'} {label}</span>)}<span>商务确认见具体事实</span></div>}
        {selected.pipeline?.stale && <p role="status" className="ml-notice">来源或关联内容变化，原分类需要复核。</p>}
        <p>{selected.summary || '这份资料暂时没有摘要。'}</p>
        {selected.recorded_at && <p className="ml-muted">录音时间 {text(selected.recorded_at).slice(0, 10)} · {minutes(selected.duration_seconds) || '时长未提供'}</p>}
        {selected.project_id && <button type="button" onClick={() => go('projects', { projectId: selected.project_id })} disabled={navBusy}>查看项目{selected.project_title ? ` · ${selected.project_title}` : ''}</button>}
        {activeConflicts.map((item, i) => <details key={i} className="ml-conflicts"><summary>{item.title}</summary><p>{item.summary}</p>{array(item.details).map((v, n) => <p key={n}>{evidenceText(v)}</p>)}</details>)}
        {array(selected.evidence).length > 0 && <details className="ml-evidence"><summary>查看判断依据</summary>{array(selected.evidence).map((item, i) => <p key={i}>{evidenceText(item) || '此项证据请查看原文'}</p>)}</details>}
        <section className="ml-sources" aria-label="来源文件"><h3>原始资料</h3>{!sources.length && <p className="ml-muted">暂未提供可读取的来源</p>}{sources.map(item => <div key={item.id}><span>{item.label || '来源文件'}</span><div>{item.readable && <button type="button" onClick={() => readSource(item)} disabled={sourceBusy}>读原文</button>}{isAudio(item) && item.downloadable && <button type="button" onClick={() => { setAudioId(item.id); setAudioError(''); }}>播放录音</button>}{item.downloadable && <a href={fileUrl(item.id)} download>下载</a>}</div></div>)}</section>
        {array(selected.pipeline?.missing_asset_ids).length > 0 && <section className="ml-notice" aria-label="来源读取异常"><strong>以下来源暂不可读</strong>{selected.pipeline.missing_asset_ids.map(id => <div key={id}><span>{array(selected.sources).find(s => s.id === id)?.label || '来源文件'}</span><button type="button" disabled={Boolean(checking)} onClick={async () => { setChecking(id); setCheckNotice(''); try { const result = await api.get(`/api/material-library/check?asset_id=${encodeURIComponent(id)}`); setCheckNotice(result.message); await load(true); } catch(e) { setCheckNotice(e.message); } finally { setChecking(''); } }}>{checking === id ? '检查中…' : '重新检查此来源'}</button></div>)}{checkNotice && <p role="status">{checkNotice}</p>}</section>}
        {audioId && <div className="ml-audio"><audio key={audioId} controls autoPlay preload="none" src={fileUrl(audioId)} onError={() => setAudioError('暂时无法播放这份录音，可以下载后收听。')} />{audioError && <p role="alert">{audioError}</p>}</div>}
        {sourceBusy && <p role="status">正在读取原文…</p>}
        {sourceError && <p role="alert">{sourceError}，可再次点击“读原文”。</p>}
        {source && <section className="ml-source-reader"><h3>{source.title || '原文'}</h3><SourceText key={source.path} {...source} /></section>}
        <details className="ml-original"><summary>文件信息</summary>{selected.original_title && <p>原名：{selected.original_title}</p>}{selected.current_path && <p>保存位置：{selected.current_path}</p>}{source?.path && <p>原文位置：{source.path}</p>}</details>
      </div>
    </dialog>}
  </section>;
}

function CoverageStatus({ coverage, onException }) {
  if (!coverage) return <p className="ml-muted">来源采集状态尚未取得</p>;
  const labels = { ok: '已查范围见详情', partial: '部分核验', unavailable: '暂不可访问', unknown: '未取得扫描回执', excluded: '不在同步范围' };
  return <section className="ml-coverage" aria-label="来源覆盖状态">
    <div className="ml-coverage-grid">{array(coverage.channels).map(source => <details key={source.id} data-state={source.status}>
      <summary><strong>{source.label}</strong><span>{source.status !== 'unavailable' && source.inventory?.status === 'ready' && source.inventory.unindexed_count > 0 ? `待核收录 ${count(source.inventory.unindexed_count)} 种` : labels[source.status] || '待核'}</span></summary>
      <p>{source.scope}</p><p>{source.note || '未取得新的采集回执，已有材料可继续使用。'}</p>
      <small>最近检查：{source.checked_at ? source.checked_at.replace('T', ' ').slice(0, 16) : '未记录'}</small>
      {source.last_complete_scan && <small>该范围上次完整扫描：{source.last_complete_scan.replace('T', ' ').slice(0, 16)}</small>}
      {array(source.pending_files).length > 0 && <details><summary>新增或变化 {source.pending_files.length}</summary>{source.pending_files.map(item => <p key={item.title}>{item.title} · {item.stage}</p>)}</details>}
      {array(source.failed_files).length > 0 && <details><summary>未读成功 {source.failed_files.length}</summary>{source.failed_files.map(item => <p key={item.title}>{item.title} · {item.stage}</p>)}</details>}
      {Number.isInteger(source.observed) && <small>本次检查范围 {source.observed} 项{source.new_count !== undefined ? ` · 新增 ${source.new_count}` : ''}{source.changed_count !== undefined ? ` · 内容变化 ${source.changed_count}` : ''}</small>}
      {source.id === 'desktop' && <DesktopInventory inventory={source.inventory} />}
    </details>)}</div>
    <small className="ml-muted">转写、分类、关联和商务确认分别记录；刷新列表不会扫描全部邮件与聊天。</small>
    {array(coverage.exceptions).length > 0 && <details className="ml-coverage-gaps"><summary>需要继续处理的来源 {coverage.exceptions.length}</summary>{coverage.exceptions.map(item => <button key={item.id} type="button" onClick={() => onException(item)}><strong>{item.title}</strong><span>{item.reason}</span></button>)}</details>}
  </section>;
}

function DesktopInventory({ inventory }) {
  const [limit, setLimit] = useState(20);
  if (inventory?.status !== 'ready') return <small>收录对账等待本轮扫描完成。</small>;
  return <div className="ml-inventory">
    {inventory.retained_scan && <small>以下为上次可读范围：{text(inventory.checked_at).replace('T', ' ').slice(0, 16)}；本轮未更新文件清单。</small>}
    <div className="ml-inventory-counts" aria-label="桌面扫描与资料库收录对账">
      <span><b>{count(inventory.unique_count)}</b>去重文件</span>
      <span><b>{count(inventory.indexed_count)}</b>索引已匹配</span>
      <span><b>{count(inventory.unindexed_count)}</b>待核收录</span>
    </div>
    <small>{inventory.partial_scan ? '仅本轮成功读取的文件；读取失败项另列。' : `已合并 ${count(inventory.duplicate_count)} 份相同内容的副本。`}索引匹配不代表内容已核验。</small>
    {inventory.unindexed_count > 0 && <details>
      <summary>查看待核收录文件</summary>
      <p>尚未匹配资料库中的文件版本，可能已在知识库其他位置留存。由后台核对；不生成销售待办。</p>
      <div className="ml-inventory-list">{array(inventory.unindexed_files).slice(0, limit).map(item => <details key={item.id}>
        <summary>{item.title}{item.copy_count > 1 ? ` · ${item.copy_count} 份同内容` : ''}</summary>
        {array(item.paths).map(path => <p key={path}>{path}</p>)}
      </details>)}</div>
      {limit < inventory.unindexed_count && <button type="button" onClick={() => setLimit(value => value + 20)}>再显示 20 项</button>}
    </details>}
  </div>;
}
