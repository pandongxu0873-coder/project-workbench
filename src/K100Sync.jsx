import React, { useEffect, useState } from 'react';
import { api } from './api.js';

const localTime = () => {
  const date = new Date();
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
export function K100RoundFields({ projectId, onChange, refreshKey, compact=false }) {
  const [data, setData] = useState(null), [rows, setRows] = useState([]), [selected, setSelected] = useState('');
  const [type, setType] = useState('GENERAL_NOTE'), [occurredAt, setOccurredAt] = useState(localTime);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  async function load() { setData(await api.get('/api/k100/status?project_id=' + encodeURIComponent(projectId))); }
  useEffect(() => { let live = true; setData(null); setRows([]); setSelected(''); setType('GENERAL_NOTE'); setOccurredAt(localTime()); api.get('/api/k100/status?project_id=' + encodeURIComponent(projectId)).then(v => { if (live) setData(v); }).catch(e => { if (live) setError(e.message); }); return () => { live = false; }; }, [projectId, refreshKey]);
  useEffect(() => {
    const date = new Date(occurredAt);
    onChange(data?.link?.enabled ? { type, occurredAt: Number.isFinite(date.getTime()) ? date.toISOString() : '' } : null);
  }, [data?.link?.enabled, type, occurredAt, onChange]);
  async function run(task) { setBusy(true); setError(''); try { await task(); } catch (e) { setError(e.message); } finally { setBusy(false); } }
  if(compact&&data&&!data.link)return <p>原话可直接保存；确认上方客户主体后才能同步 K100。</p>;
  return <details className="k100-sync-fields"><summary>新 K100 同步 · {data?.link ? data.link.customer_name : '尚未关联'}</summary>
    {data?.link ? <>
      {!compact&&<button type="button" disabled={busy} onClick={() => run(async () => { const value = await api.post('/api/k100/recover-round', {project_id: projectId}); if (value.event?.message) setError(value.event.message); await load(); })}>恢复最新已存进展的同步</button>}<p>本项目新保存的实际反馈（无反馈时取已有事实）会自动同步到 {data.link.customer_name}。判断、话术和计划不自动发送。</p>
      <label className="native-field"><span>CRM 记录类型</span><select value={type} onChange={e => setType(e.target.value)}>{Object.entries(data.types || {}).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label className="native-field"><span>实际发生时间</span><input type="datetime-local" value={occurredAt} onChange={e => setOccurredAt(e.target.value)} required /></label>
      <p>{['GENERAL_NOTE', 'INTERNAL_COMMUNICATION'].includes(type) ? '普通备注／内部沟通不会刷新保护期。' : '请填写实际发生的客户沟通或推进；保护期是否更新以 CRM 回读为准。'}</p>
    </> : <>
      <p>一次核对本项目对应的客户主体；关联后保存新进展时自动同步。不会覆盖原项目、归档或附件。</p>
      <button type="button" disabled={busy} onClick={() => run(async () => setRows((await api.get('/api/k100/customers')).items.filter(r => r.isMine)))}>读取我的 K100 客户</button>
      {rows.length > 0 && <><label className="native-field"><span>新 K100 对应客户</span><select value={selected} onChange={e => setSelected(e.target.value)}><option value="">请选择准确的客户主体</option>{rows.map(r => <option key={r.id} value={r.id}>{r.legalName}</option>)}</select></label><button type="button" disabled={busy || !selected} onClick={() => run(async () => { await api.post('/api/k100/link', { project_id: projectId, customer_id: selected }); await load(); window.dispatchEvent(new Event('workbench-refresh')); })}>关联并自动同步新进展</button></>}
    </>}
    {<p><a href="/k100-connection.html" target="_blank" rel="noreferrer">新 K100 连接与验证</a></p>}
    {error && <p role="alert">{error}</p>}
    {!compact && data?.events?.length > 0 && <div aria-label="新 K100 同步回执">{data.events.slice(0, 5).map(event => <article key={event.id}><strong>{event.message}</strong><p>{event.created_at} · {data.types[event.type]}</p>{event.state === 'confirmed' && <p>有效跟进：{event.effective ? '是' : '否'} · 刷新保护计时：{event.protection_refreshed ? '是' : '否'}</p>}{event.state !== 'confirmed' && <button type="button" disabled={busy} onClick={() => run(async () => { await api.post(['written', 'uncertain', 'sending'].includes(event.state) ? '/api/k100/reconcile' : '/api/k100/retry', { id: event.id }); await load(); })}>{['written', 'uncertain', 'sending'].includes(event.state) ? '只回读核对，不重发' : '重试这条同步'}</button>}</article>)}</div>}
  </details>;
}
