import React, { useState, useEffect } from 'react';
import { api } from './api.js';
import { scenarios, relationships, emptyRound, guidance, roundDraft } from './roundPlaybook.js';
import { K100RoundFields } from './K100Sync.jsx';

export function ProjectRound({ project, markDirty, markSaving, navigate, onSavedRound, externallyBusy=false }) {
  const [stored, setStored] = useState(null);
  const [record, setRecord] = useState(emptyRound);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [latest, setLatest] = useState(null);
  const [k100, setK100] = useState(null);
  const key = `round:${project.id}`;
  const savedOutcome = value => ['本轮完成','暂停跟进'].includes(value.status)||value.relationship==='no_contact' ? '已从待处理移除。' : value.due ? `下次跟进 ${value.due}，已在工作台安排。` : '已记下进展，尚未安排跟进日期。';
  useEffect(() => {
    let active = true;
    api.get(`/api/project-workspace/round?project_id=${project.id}`).then(value => { if(active) { setStored(value); setRecord({ ...emptyRound(), ...value.record }); } }).catch(e => { if(active) setError(e.message); });
    return () => { active = false; markDirty(key, false); };
  }, [project.id, markDirty]);
  const change = field => e => { const value=e.target.value; setRecord(r => ({ ...r, [field]: value })); setDirty(true); markDirty(key, true); setNotice(''); };
  const guide = guidance(record, stored?.record);
  const draft = roundDraft(project, record, stored?.record);
  async function inspectLatest() { try { setLatest(await api.get(`/api/project-workspace/round?project_id=${project.id}`)); } catch(e) { setError(e.message); } }
  async function save(e) {
    e.preventDefault(); setBusy(true); markSaving(key, true); setError(''); setNotice('');
    try {
      const saved = await api.post('/api/project-workspace/round', { ...record, project_id: project.id, archive_revision:project.archive?.revision||0, revision: stored.revision, quick_outcome:"",quick_action:"",quick_request_id:"", ...(k100 ? {k100} : {}) });
      setStored(saved); setRecord(saved.record); setDirty(false); markDirty(key, false); setLatest(null);
      try {
        const verified = await api.get(`/api/project-workspace/round?project_id=${project.id}`);
        if (verified.revision === saved.revision && JSON.stringify(verified.record) === JSON.stringify(saved.record)) setNotice(`已保存并核实 · 版本 ${saved.revision}。${savedOutcome(saved.record)}${saved.k100 ? ' 新 K100：' + saved.k100.message : ''}`);
        else { setLatest(verified); setNotice('保存成功，但读回发现更新的版本，请核对最新记录。'); }
      } catch(e) { setNotice(`保存成功 · 版本 ${saved.revision}，读回暂失败，请稍后查看最新记录核实。`); }
      markSaving(key, false); onSavedRound?.();
    } catch(e) { setError(e.message); }
    finally { setBusy(false); markSaving(key, false); }
  }
  return <section className="project-judgement round-surface" aria-label="本轮推进">
    <h2>调整正式安排</h2>
    {!stored && !error && <p role="status">正在读取本项目工作记录…</p>}
    {stored?.record?.action && <p className="drawer-next-action">{stored.record.action}</p>}
    <details open={stored?.record ? true : undefined}><summary>{stored?.record ? `当前：${stored.record.status}` : '记录实际进展（可选）'}</summary>
    <form onSubmit={save}><fieldset disabled={project.archive?.archived || busy || externallyBusy || !stored}>
      {guide.blocked && <p className="readonly-banner">明确暂勿联系，仅做内部准备。</p>}
      <label className="native-field"><span>执行状态</span><select value={record.status} onChange={change('status')}>{['准备中','已发出等待反馈','已收到反馈','本轮完成','暂停跟进'].map(status => <option key={status}>{status}</option>)}</select></label>
      <label className="native-field"><span>实际反馈</span><textarea rows={2} value={record.feedback} onChange={change('feedback')} placeholder="有新反馈时，粘贴原话或简述实际结果" maxLength={6000} /></label>
      <div className="round-fields"><label className="native-field"><span>下次跟进日期（可选）</span><input type="date" value={record.due} onInput={change('due')} onChange={change('due')} /></label></div>
      <label className="native-field"><span>下一步</span><textarea rows={2} value={record.next_step} onChange={change('next_step')} placeholder="已有 AI 建议可直接保留，有变化再改" maxLength={6000} /></label>
      <details><summary>事实、联系人和场景（可选）</summary>
      { [['facts','已有事实'],['judgement','自己的补充判断'],['action','本轮动作'],['contact','联系人'],['owner','责任人']].map(([field,label]) => <label className="native-field" key={field}><span>{label}</span><textarea rows={2} value={record[field]} onChange={change(field)} maxLength={6000} /></label>)}
      <label className="native-field"><span>场景</span><select value={record.scenario} onChange={change('scenario')}>{Object.entries(scenarios).map(([id,item]) => <option key={id} value={id}>{item.label}</option>)}</select></label>
      <label className="native-field"><span>客情／暂停原因</span><select value={record.relationship} onChange={change('relationship')}>{Object.entries(relationships).map(([id,label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      <p>场景目标：{guide.goal}</p><p>验收参考：{guide.acceptance}</p>
      </details>
      {stored?.record?.relationship === 'no_contact' && record.relationship !== 'no_contact' && <label className="native-field"><span>恢复联系的新事实依据</span><textarea value={record.recontact_basis} onChange={change('recontact_basis')} maxLength={6000} /></label>}
      {draft && <details><summary>场景话术参考</summary>{record.scenario !== 'collaboration' && <label className="native-field"><span>对外主题</span><input value={record.topic || ''} onChange={change('topic')} maxLength={6000} /></label>}<pre className="round-draft">{draft}</pre><button type="button" onClick={async () => { try { await navigator.clipboard.writeText(draft); setNotice('草稿已复制，未发送。'); } catch { setNotice('请手动选择文字复制。'); } }}>复制草稿</button></details>}
      <K100RoundFields projectId={project.id} onChange={setK100} refreshKey={stored?.revision} />
      <button type="submit" className="plain-action">{busy ? '保存并核实中…' : '保存进展'}</button><span>{dirty ? ' · 有未保存修改' : stored?.revision ? ` · 版本 ${stored.revision}` : ''}</span>
    </fieldset></form></details>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <button className="plain-action" disabled={busy || externallyBusy} onClick={inspectLatest}>查看最新记录（保留当前输入）</button>
    {latest && <div className="round-latest"><h3>最新已存版本 {latest.revision}</h3>{latest.record ? <><p>场景：{scenarios[latest.record.scenario]?.label} · {latest.record.status}</p><p>客情／暂停原因：{relationships[latest.record.relationship]}</p>{[['facts','事实'],['judgement','判断'],['action','动作'],['feedback','反馈'],['contact','联系人'],['owner','责任人'],['due','复盘日期'],['next_step','下一步'],['topic','对外主题'],['recontact_basis','重新联系依据']].map(([k,label]) => <p key={k}>{label}：{latest.record[k] || '尚未记录'}</p>)}</> : <p>本项目尚无已存记录。</p>}<p>可先将最新内容与当前输入比较；明确合并后再保存。</p><button disabled={busy || externallyBusy} onClick={() => { setStored(latest); setLatest(null); if (!dirty) setRecord({ ...emptyRound(), ...latest.record }); setNotice('已采用最新版本号；当前编辑内容保留，请完成合并后保存。'); }}>以最新版本为基础，保留输入继续合并</button></div>}
    <details><summary>工作记录历史 · {stored?.history.length || 0} 个版本</summary>{[...(stored?.history || [])].reverse().map(h => <article key={h.revision}><h3>版本 {h.revision} · {h.record.saved_at}</h3><p>{scenarios[h.record.scenario]?.label} · {h.record.status} · {relationships[h.record.relationship]}</p>{[['contact','联系人'],['facts','事实'],['judgement','判断'],['action','动作'],['owner','责任人'],['due','复盘日期'],['feedback','反馈'],['next_step','下一步'],['topic','对外主题'],['recontact_basis','重新联系依据']].map(([k,label]) => h.record[k] && <p key={k}>{label}：{h.record[k]}</p>)}</article>)}</details>

  </section>;
}
