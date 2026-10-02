import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Flame, RefreshCw, Search, Sparkles } from 'lucide-react';
import { safeNewsLink, newsTime, mergeNews } from './aiHotData.js';
import './ai-hot.css';
import { ResetMonitor } from './ResetMonitor.jsx';

const KEY = 'workbench-aihot-filters';
const DATES_KEY = 'workbench-aihot-dates';
const initial = { view: 'selected', window: '24h', category: '', q: '', date: '' };
const categories = [['', '全部'], ['ai-products', '产品应用'], ['tip', '实用技巧'], ['ai-models', '模型'], ['industry', '行业'], ['paper', '论文']];
function restore() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY));
    return { ...initial, ...saved, view: ['selected', 'hot', 'daily', 'resets'].includes(saved?.view) ? saved.view : 'selected' };
  } catch { return initial; }
}
function restoreDates() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(DATES_KEY));
    return Array.isArray(saved) ? saved.filter(date => typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date)) : [];
  } catch { return []; }
}
function SourceLink({ href, children, className = '' }) {
  const url = safeNewsLink(href);
  return url ? <a href={url} className={className} target="_blank" rel="noopener noreferrer">{children}<ArrowUpRight size={14} /></a> : null;
}
function NewsCard({ item, daily = false }) {
  const [expanded, setExpanded] = useState(false);
  const long = (item.summary?.length || 0) > 140 || (item.reason?.length || 0) > 90;
  return <article className="aihot-card">
    <div className="aihot-meta"><span>{categories.find(([key]) => key === item.category)?.[1] || (daily ? '日报精选' : 'AI 资讯')}</span>{item.selected === false && <span>未进入精选</span>}<time>{newsTime(item)}</time></div>
    <h3><SourceLink href={item.links?.aihot || item.links?.original}>{item.title || '未命名资讯'}</SourceLink></h3>
    {item.summary && <p className={expanded ? '' : 'aihot-summary'}>{item.summary}</p>}
    {item.reason && <div className="aihot-reason"><Sparkles size={14} /><div><span>AIHOT 推荐理由</span><p className={expanded ? '' : 'aihot-reason-short'}>{item.reason}</p></div></div>}
    {long && <button className="aihot-text-button" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>{expanded ? '收起摘要' : '展开摘要'}</button>}
    <footer><span>{item.source?.name || '来源待补充'}</span><SourceLink href={item.links?.original}>原始出处</SourceLink></footer>
  </article>;
}

export function AIHot() {
  const [filters, setFilters] = useState(restore);
  const [draft, setDraft] = useState(filters.q);
  const [result, setResult] = useState(null);
  const [items, setItems] = useState([]);
  const [dates, setDates] = useState(restoreDates);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef(0);
  const abort = useRef(null);
  const identity = JSON.stringify(filters);
  const currentIdentity = useRef('');

  const load = useCallback(async ({ more = false, refresh = false, cursor = '', mode = 'selected' } = {}) => {
    const id = ++request.current;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setBusy(true); setError('');
    if (currentIdentity.current !== identity) { setItems([]); setResult(null); currentIdentity.current = identity; }
    const params = { view: filters.view };
    if (filters.view === 'selected') Object.assign(params, { window: filters.window, category: filters.category, q: filters.q, mode });
    if (filters.view === 'daily' && filters.date) params.date = filters.date;
    if (more && cursor) params.cursor = cursor;
    if (refresh) params.refresh = '1';
    const timeout = setTimeout(() => controller.abort(), 55000);
    try {
      const response = await fetch('/api/ai-hot?' + new URLSearchParams(params), { signal: controller.signal });
      const value = await response.json();
      if (!response.ok || !value.ok) throw new Error(value.error || 'AI Hot 暂时不可用');
      if (id !== request.current) return;
      setResult(value);
      if (value.dates) {
        setDates(value.dates);
        try { sessionStorage.setItem(DATES_KEY, JSON.stringify(value.dates)); } catch { /* Date selection still works in this visit. */ }
      }
      setItems(old => more ? mergeNews(old, value.data.items || []) : value.data.items || []);
    } catch (e) {
      if (id === request.current) setError(e.name === 'AbortError' ? '读取超时，请稍后刷新' : e.message);
    } finally {
      clearTimeout(timeout);
      if (id === request.current) setBusy(false);
    }
  }, [identity]);

  useEffect(() => {
    try { sessionStorage.setItem(KEY, identity); } catch { /* Reading remains available. */ }
    load();
    return () => { ++request.current; abort.current?.abort(); };
  }, [load]);

  useEffect(() => {
    if (filters.view !== 'resets') return;
    const timer = setInterval(() => { if (document.visibilityState === 'visible') load(); }, 300000);
    return () => clearInterval(timer);
  }, [filters.view, load]);

  useEffect(() => {
    const onRefresh = () => load({ refresh: true });
    window.addEventListener('workbench-refresh', onRefresh);
    return () => window.removeEventListener('workbench-refresh', onRefresh);
  }, [load]);

  function search(event) {
    event.preventDefault();
    const q = draft.trim();
    if (q && (q.length < 2 || q.length > 200)) { setError('关键词请填写 2—200 个字'); return; }
    setFilters(old => ({ ...old, q, view: 'selected' }));
  }
  const report = result?.data?.report;
  const hasMore = filters.view === 'selected' && result?.data?.page?.hasMore;
  return <section className="aihot-page" aria-labelledby="aihot-title">
    <header className="aihot-header">
      <div><div className="aihot-eyebrow"><Flame size={16} /> AI HOT</div><h1 id="aihot-title">{filters.view === 'resets' ? 'Tibo 重置监控' : 'AI 资讯'}</h1><p>{filters.view === 'resets' ? 'Codex 的额度重置、重置卡发放与原帖记录' : '看看新变化，找到值得试的新方法。'}</p></div>
      <button className="plain-action" onClick={() => load({ refresh: true })} disabled={busy}><RefreshCw size={16} className={busy ? 'aihot-spinning' : ''} />{busy ? '读取中' : '刷新资讯'}</button>
    </header>
    <div className="aihot-tabs" role="group" aria-label="资讯视图">
      {[['selected', '近期精选'], ['hot', '当前热点'], ['daily', 'AI 日报'], ['resets', 'Tibo 重置监控']].map(([key, label]) => <button key={key} aria-pressed={filters.view === key} onClick={() => setFilters(old => ({ ...old, view: key }))}>{label}</button>)}
    </div>
    {filters.view === 'selected' && <div className="aihot-tools">
      <div className="aihot-filter-row"><div className="aihot-categories" role="group" aria-label="资讯分类">{categories.map(([key, label]) => <button key={key} aria-pressed={filters.category === key} onClick={() => setFilters(old => ({ ...old, category: key }))}>{label}</button>)}</div>
        <select aria-label="资讯时间范围" value={filters.window} onChange={e => setFilters(old => ({ ...old, window: e.target.value }))}><option value="24h">过去 24 小时</option><option value="7d">最近 7 天</option></select></div>
      <form onSubmit={search}><Search size={17} /><input aria-label="搜索 AI 资讯" placeholder="搜索公司、产品或主题" value={draft} onChange={e => setDraft(e.target.value)} maxLength={200} /><button type="submit">搜索</button>{filters.q && <button type="button" onClick={() => { setDraft(''); setFilters(old => ({ ...old, q: '' })); }}>清除</button>}</form>
    </div>}
    {filters.view === 'daily' && <div className="aihot-daily-control"><label>日报日期 <select value={filters.date} onChange={e => setFilters(old => ({ ...old, date: e.target.value }))}><option value="">最新一期</option>{[...new Set([...dates, ...(filters.date ? [filters.date] : [])])].map(date => <option key={date} value={date}>{date}</option>)}</select></label><span>按实际发布日期展示</span></div>}
    <div className={`aihot-status ${filters.view === 'resets' ? 'reset-fetch-status' : ''}`} aria-live="polite"><span>{filters.view === 'resets' ? 'Tibo 重置与发卡 · 页面打开时每 5 分钟更新' : filters.view === 'hot' ? 'AIHOT 当前排名' : filters.view === 'daily' ? (report ? `${report.date} 日报` : 'AIHOT 日报') : `${filters.window === '24h' ? '过去 24 小时' : '最近 7 天'}${filters.q ? ` · “${filters.q}”` : ''}`}{result && ['selected', 'hot'].includes(filters.view) ? ` · 已显示 ${items.length} 条` : ''}</span><span>{result ? `${result.stale ? '保留上次内容' : '已获取'} · ${newsTime({ publishedAt: result.checked_at })}` : busy ? '正在读取 AIHOT…' : ''}</span></div>
    {(error || result?.stale) && <div className="aihot-error" role="status">{error || result.error}{result && '；以下保留已读取的内容。'}<button onClick={() => load({ refresh: true })} disabled={busy}>重新读取</button></div>}
    {result?.unselected_search && <p className="aihot-note">精选中未找到匹配，以下为全部公开动态的搜索结果。</p>}
    {busy && !result && <div className="aihot-loading" role="status"><RefreshCw size={22} className="aihot-spinning" /> 正在整理资讯列表…</div>}
    {result && filters.view === 'selected' && <div className="aihot-grid">{items.map(item => <NewsCard key={item.id} item={item} />)}</div>}
    {result && filters.view === 'hot' && <div className="aihot-ranking">{[...items].sort((a, b) => a.rank - b.rank).map(item => <article key={item.id}><span className="aihot-rank">{item.rank}</span><div><h3><SourceLink href={item.links?.story || item.links?.aihot}>{item.title}</SourceLink></h3><p>{item.sourceCount} 个报道来源 · 最近进展 {newsTime({ publishedAt: item.latestAt })}</p><div className="aihot-hot-links"><SourceLink href={item.links?.aihot}>中文资讯</SourceLink><SourceLink href={item.links?.original}>原始出处</SourceLink></div></div></article>)}</div>}
    {result && filters.view === 'resets' && <ResetMonitor data={result.data} stale={result.stale || Boolean(error)} />}
    {report && filters.view === 'daily' && <div className="aihot-report">
      {report.lead && <div className="aihot-lead">{typeof report.lead === 'string' ? <p>{report.lead}</p> : <><h2>{report.lead.title}</h2><p>{report.lead.summary || report.lead.paragraph}</p></>}</div>}
      {(report.sections || []).map((section, n) => <section key={n}><h2>{section.label}</h2><div className="aihot-grid">{(section.items || []).map((item, i) => <NewsCard key={i} item={item} daily />)}</div></section>)}
      {!!report.flashes?.length && <section><h2>快讯</h2><div className="aihot-grid">{report.flashes.map((item, i) => <NewsCard key={i} item={item} daily />)}</div></section>}
      <SourceLink href={report.links?.aihot}>在 AIHOT 阅读本期日报</SourceLink>
    </div>}
    {result && filters.view !== 'resets' && !busy && !items.length && !report && <div className="aihot-empty">{filters.view === 'daily' ? '目前没有已发布的日报。' : filters.q ? '这个范围内没有找到相关资讯，可换个关键词或查看最近 7 天。' : '这个范围暂时没有资讯，可切换分类或查看最近 7 天。'}</div>}
    {hasMore && <button className="plain-action aihot-more" disabled={busy} onClick={() => load({ more: true, cursor: result.data.page.nextCursor, mode: result.unselected_search ? 'all' : 'selected' })}>{busy ? '读取中…' : '加载更多'}</button>}
    <footer className="aihot-attribution"><span>数据来源：<SourceLink href="https://aihot.news">AIHOT</SourceLink> · 北京时间 · 资讯刷新不调用大模型</span><SourceLink href="https://aihot.news/terms">使用说明</SourceLink></footer>
  </section>;
}
