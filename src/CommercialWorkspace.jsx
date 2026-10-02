import React, { useEffect, useRef, useState } from "react";
import { useDiscardChanges } from "./DiscardDialog.jsx";
import { installLiveRefresh } from "./liveRefresh.js";
import { commercialOutputKey, commercialText } from "./commercialFreshness.js";
import { api } from "./api";

const COSTS = [["own_labor", "自有人力预算金额"], ["pco", "PCO预算金额"], ["formal", "正式预算金额"], ["travel", "差旅预算金额"], ["procurement", "代采预算金额"], ["token", "Token预算金额"], ["presales", "售前预算金额"], ["other", "其他预算金额"]];
const empty = (projectId, revision = 0) => ({ project_id: projectId, revision, requirement: "", effort: "", rate: "", budget: {}, customer_confirmed: false, budget_verified: false, confirmation_source: "", confirmation_excerpt: "", version: "", sample: false });
const CHOICE_KEY = "sales-workbench-commercial-project";
const customerMatches = (left, right) => { const clean = value => String(value || '').replaceAll('entities/', '').replace(/[\s\[\]]/g, '').toLowerCase(); const a=clean(left),b=clean(right); return !a || a===b || (Math.min(a.length,b.length)>=2 && (a.includes(b)||b.includes(a))); };
const money = (value) => Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 2 });

export default function CommercialWorkspace({ focusSection, incomingQuote, initialProjectId = "", navigate, registerNavigationGuard, onProjectSelected }) {
  const askDiscard = useDiscardChanges();
  const liveDraft = useRef(null);
  const emailHeading=useRef(null),focusedEmail=useRef('');
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(initialProjectId || "");
  const [draft, setDraft] = useState(null);
  const [result, setResult] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const requestVersion = useRef(0);
  liveDraft.current = { draft, result, busy };
  const project = projects.find((item) => item.id === projectId);
  useEffect(() => {
    return registerNavigationGuard?.(async () => !busy && (!dirty || await askDiscard("商务草稿尚未保存，离开会放弃本次修改。")));
  }, [dirty, busy, registerNavigationGuard, askDiscard]);

  useEffect(() => {
    let active = true;
    api.get("/api/project-workspace").then((data) => {
      if (!active) return;
      const available = data.projects || [];
      setProjects(available);
      let remembered = "";
      try { remembered = localStorage.getItem(CHOICE_KEY) || ""; } catch { /* Selection persistence is optional. */ }
      const selected = initialProjectId || remembered;
      const target = available.find(item => item.id === selected);
      const candidates = incomingQuote?.values.customer ? available.filter(item => customerMatches(incomingQuote.values.customer, item.customer)) : [];
      const validSelection = incomingQuote?.values.customer && (!target || !customerMatches(incomingQuote.values.customer,target.customer)) ? (candidates.length === 1 ? candidates[0].id : '') : target?.id || '';
      setProjectId(validSelection); onProjectSelected?.(validSelection, available.find(item=>item.id===validSelection)||{});
    }).catch((err) => active && setError(err.message));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const version = ++requestVersion.current;
    setDraft(null); setResult(null); setError(""); setNotice(""); setDirty(false);
    if (!projectId) { setBusy(false); return; }
    setBusy(true);
    api.get(`/api/commercial/draft?project_id=${encodeURIComponent(projectId)}`).then((data) => {
      if (requestVersion.current !== version) return;
      setDraft(data.draft); setResult(data);
      try { localStorage.setItem(CHOICE_KEY, projectId); } catch { /* No business data in browser storage. */ }
    }).catch((err) => requestVersion.current === version && setError(err.message))
      .finally(() => requestVersion.current === version && setBusy(false));
  }, [projectId]);

  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (event) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(()=>{
    if(focusSection!=='customer-email'||busy||!result||draft?.project_id!==initialProjectId||!project||!emailHeading.current||focusedEmail.current===initialProjectId)return;
    const frame=requestAnimationFrame(()=>{if(emailHeading.current){focusedEmail.current=initialProjectId;emailHeading.current.scrollIntoView({block:'start',behavior:'instant'});emailHeading.current.focus({preventScroll:true});}});
    return()=>cancelAnimationFrame(frame);
  },[focusSection,busy,result,draft?.project_id,initialProjectId,project]);

  function edit(patch) {
    if (["requirement", "effort", "rate", "version", "confirmation_excerpt", "confirmation_source"].some(key => key in patch)) patch.customer_confirmed = false;
    if ("confirmation_source" in patch) patch.confirmation_fingerprint = "";
    if ("budget" in patch) patch.budget_verified = false;
    setDraft((value) => ({ ...value, ...patch })); setDirty(true); setResult(null); setNotice(""); setError("");
  }
  const availableQuote = result?.latest_quote || incomingQuote;
  async function importQuote() {
    if (!availableQuote || !draft || busy || (dirty && !await askDiscard('带入这版报价会替换当前未保存的金额与预算。'))) return;
    const v = availableQuote.values;
    if (!customerMatches(v.customer, project?.customer)) { setError('报价客户与当前项目不一致，请先选择对应客户的项目。'); return; }
    setDraft(current => ({ ...empty(projectId, current.revision), requirement: v.requirement, version: v.version || `报价第${availableQuote.revision}版`,
      effort: v.effort, rate: v.rate, budget: v.costs, self_cost_enabled: v.selfCostEnabled, budget_verified: v.costsConfirmed,
      quote_id: availableQuote.quote_id, quote_revision: availableQuote.revision, quote_requirement: v.requirement, quote_version_label: v.version }));
    setDirty(true); setResult(null); setError(''); setNotice('人天、金额和成本口径已带入。客户确认依据仍按本项目本次版本核对。');
  }
  async function choose(value) {
    if (busy || (dirty && !await askDiscard("切换项目会放弃当前未保存的修改。"))) return;
    setProjectId(value); onProjectSelected?.(value, projects.find(item=>item.id===value)||{});
    if (!value) { try { localStorage.removeItem(CHOICE_KEY); } catch { /* Optional preference. */ } }
  }
  async function run(save) {
    const version = requestVersion.current;
    setBusy(true); setError(""); setNotice("");
    try {
      const data = await api.post(`/api/commercial/${save ? "draft" : "preview"}`, draft);
      if (version !== requestVersion.current) return;
      setResult(data);
      if (save) { setDraft(data.draft); setDirty(false); setNotice(`已保存本机草稿（第 ${data.draft.revision} 版），未发送、未审批。`); }
      else { setDraft(value => ({ ...value, customer_confirmed: data.draft.customer_confirmed, confirmation_fingerprint: data.draft.confirmation_fingerprint })); setNotice("预览已更新；修改尚未保存时，请再点击保存。"); }
    } catch (err) { if (version === requestVersion.current) setError(err.message); }
    finally { if (version === requestVersion.current) setBusy(false); }
  }
  async function reload() {
    if (dirty && !await askDiscard("重新加载会放弃当前未保存的修改。")) return;
    const version = ++requestVersion.current;
    setBusy(true); setError("");
    try {
      const data = await api.get(`/api/commercial/draft?project_id=${encodeURIComponent(projectId)}`);
      if (version !== requestVersion.current) return;
      setDraft(data.draft); setResult(data); setDirty(false); setNotice("已重新读取本项目的本机草稿。");
    } catch (err) { if (version === requestVersion.current) setError(err.message); }
    finally { if (version === requestVersion.current) setBusy(false); }
  }
  function acceptChecked(data) {
    setResult(data);
    setDraft(value => ({ ...value, customer_confirmed: data.draft.customer_confirmed, confirmation_fingerprint: data.draft.confirmation_fingerprint }));
  }
  useEffect(() => installLiveRefresh(async () => {
    const current = liveDraft.current, version = requestVersion.current;
    if (!current.draft || !current.result || current.busy) return;
    try {
      const checked = await api.post('/api/commercial/preview', current.draft);
      if (version !== requestVersion.current || liveDraft.current.draft !== current.draft || liveDraft.current.busy) return;
      if (commercialOutputKey(checked) !== commercialOutputKey(current.result)) {
        acceptChecked(checked); setNotice('依据或联系状态已变化，话术已更新；你的输入已保留。');
      }
    } catch (err) { if (version === requestVersion.current && liveDraft.current.draft === current.draft) { setResult(null); setError(`话术需要重新核对：${err.message}。输入已保留。`); } }
  }), []);
  async function copy(kind) {
    if (busy) return;
    const version = requestVersion.current;
    setBusy(true); setError('');
    try {
      const checked = await api.post('/api/commercial/preview', draft);
      if (version !== requestVersion.current) return;
      acceptChecked(checked);
      if (commercialOutputKey(checked) !== commercialOutputKey(result)) {
        setNotice('依据或联系状态已变化，旧话术未复制。请查看更新后的内容。'); return;
      }
      const text = commercialText(checked, kind);
      if (!text) { setNotice('当前联系状态不生成客户邮件。'); return; }
      await navigator.clipboard.writeText(text); setNotice('已核对最新依据并复制草稿；尚未发送或提交审批。');
    } catch (err) { setResult(null); setError(`复制未完成：${err.message}。输入已保留，请重新计算并预览。`); }
    finally { if (version === requestVersion.current) setBusy(false); }
  }
  async function loadSample() {
    if (dirty && !await askDiscard("载入合成样例会替换当前未保存内容。")) return;
    edit({ ...empty(projectId, draft.revision), requirement: "示例需求：项目文档检索", effort: "24", rate: "2000", budget: { own_labor: "30000" }, sample: true });
    setNotice("已载入用户提供的合成样例，仅供核对；不是本项目的新申请，也未自动保存。");
  }

  return <div className="page-stack commercial-workspace">
    <header className="page-header"><div><p className="page-eyebrow">商务材料 · 本机草稿</p><h1>报价与审批</h1><p className="page-subtitle">选定项目，把人日、预算和客户确认依据放在一起。内部审批与客户邮件分开生成。</p></div></header>
    <section className="performance-surface">
      <label className="native-field"><span>关联项目（必选）</span><select value={projectId} onChange={(event) => choose(event.target.value)} disabled={busy}><option value="">请选择真实项目</option>{projects.map((item) => <option key={item.id} value={item.id}>{item.customer} · {item.title}</option>)}</select></label>
      {project && <p className="page-subtitle">来源：{project.source_path} · 此处不会改动客户状态或公司 CRM。</p>}
      {availableQuote && <p>可带入：{availableQuote.values.customer || '独立报价'} · {availableQuote.values.effort} 人日 · ¥{money(availableQuote.calculation.revenue)} · 第 {availableQuote.revision} 版 {draft && <button disabled={busy} onClick={importQuote}>使用这版报价</button>}</p>}
      {!projectId && <p>先选择项目，避免不同客户的报价、确认截图和审批材料串在一起。</p>}
    </section>
    {error && <p className="form-error" role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {busy && <p role="status">正在读取或保存本项目草稿…</p>}
    {draft && <>
      <section className="performance-surface"><div className="section-heading"><div><h2>本次需求与预算</h2><p>{draft.self_cost_enabled ? '沿用独立报价：八项预算另计成交额10%自成本，毛利按合计成本计算。' : '八项预算合计。空白按0计算，仍须核实。'}</p>{draft.quote_id && <p>沿用报价第 {draft.quote_revision} 版；改价请从独立计算器保存并带入新版。</p>}</div></div>
        {draft.sample && <p className="form-warning">合成样例模式：仅用于检查 24 人日 / 48,000 元 / 37.5% 模板结果，不可作为新申请。</p>}
        <fieldset disabled={busy} style={{ border: 0, padding: 0, minWidth: 0 }}><div className="pricing-form">
          <label className="native-field"><span>需求名称</span><input readOnly={Boolean(draft.quote_id && draft.quote_requirement)} value={draft.requirement} onChange={(event) => edit({ requirement: event.target.value })} /></label>
          <label className="native-field"><span>本次需求 / 附件版本</span><input readOnly={Boolean(draft.quote_id && draft.quote_version_label)} value={draft.version} placeholder="填写本次真实版本，不复用历史版本" onChange={(event) => edit({ version: event.target.value })} /></label>
          <label className="native-field"><span>拟确认 / 客户确认人日</span><input type="number" min="0" step="0.001" readOnly={Boolean(draft.quote_id)} value={draft.effort} onChange={(event) => edit({ effort: event.target.value })} /></label>
          <label className="native-field"><span>对客单价（元/人日）</span><input type="number" min="0" step="0.01" readOnly={Boolean(draft.quote_id)} value={draft.rate} onChange={(event) => edit({ rate: event.target.value })} /></label>
          {COSTS.map(([key, label]) => <label className="native-field" key={key}><span>{label}（元）</span><input type="number" min="0" step="0.01" placeholder="0" readOnly={Boolean(draft.quote_id)} value={draft.budget[key] ?? ""} onChange={(event) => edit({ budget: { ...draft.budget, [key]: event.target.value } })} /></label>)}
        </div>
        <label className="check-field"><input type="checkbox" checked={draft.budget_verified} onChange={(event) => edit({ budget_verified: event.target.checked })} /><span>八项预算均已核实，0 元项已确认无成本</span></label>
        <h3>客户确认依据</h3>
        <label className="native-field"><span>本项目关联的客户回复材料</span><select value={draft.confirmation_source} onChange={(event) => edit({ confirmation_source: event.target.value })}><option value="">请选择已归档的真实客户回复</option>{(project?.sources || []).filter((source) => source.exists && source.path !== project.source_path).map((source) => <option key={source.path} value={source.path}>{source.path}</option>)}</select></label>
        <p className="page-subtitle">没有对应来源时，先保留草稿，并通过知识库归档本次回复原文或截图；其他沟通材料不等于客户确认。</p>
        <label className="native-field"><span>客户确认原文摘录</span><textarea rows={3} value={draft.confirmation_excerpt} onChange={(event) => edit({ confirmation_excerpt: event.target.value })} placeholder="保留客户真实表述，不补写或合成确认" /></label>
        <label className="check-field"><input type="checkbox" checked={draft.customer_confirmed} onChange={(event) => edit({ customer_confirmed: event.target.checked })} /><span>我已核对：上述回复明确确认本次版本的完整需求和对应人日</span></label>
        <div className="form-footer"><button type="button" onClick={() => run(false)}>计算并预览</button><button type="button" onClick={() => run(true)}>保存本机草稿</button><button type="button" onClick={reload}>重新加载已保存版本</button></div>
        <details><summary>核对合成模板 / 清空输入</summary><p>合成样例不会默认填入任何项目，也不会自动保存。</p><button type="button" onClick={loadSample}>载入虚构示例（24 人日）</button><button type="button" onClick={async () => { if (!dirty || await askDiscard("清空会移除当前未保存的内容。")) edit(empty(projectId, draft.revision)); }}>清空为新草稿</button></details>
        </fieldset>
      </section>
      {result && <section className="performance-surface">
        <div className="metric-strip"><div><span>对客报价</span><strong>¥{money(result.calculation.revenue)}</strong></div><div><span>预算成本</span><strong>¥{money(result.calculation.budget_total)}</strong></div><div><span>毛利</span><strong>¥{money(result.calculation.gross_profit)}</strong></div><div><span>毛利率</span><strong>{result.calculation.margin_percent === null ? "待计算" : `${result.calculation.margin_percent}%`}</strong></div></div>
        <p>{result.approval_ready ? "确认材料已填写，可供人工复核；不代表内部已批准。" : `待核实草稿：${result.blocking_reasons.join("；")}`}</p>
        <h2>给审批负责人的内部审批话术</h2><label className="native-field"><span>仅内部使用，包含成本与毛利</span><textarea readOnly rows={18} value={result.internal_approval} /></label><button type="button" disabled={busy || result.stale_quote} onClick={() => copy("internal")}>复制内部审批草稿</button>
        {result.contact_blocked ? <p ref={emailHeading} tabIndex={-1} className="readonly-banner">客户明确暂勿联系：本页仅保留内部报价核对与审批准备，不生成客户邮件。恢复联系需回到项目记录新事实依据。</p> : result.customer_email && <><h2 ref={emailHeading} tabIndex={-1}>给客户的确认邮件</h2><p>{project?.title} · {draft.revision>0?'已保存本机草稿':'尚未保存的模板'}</p><p>不包含内部成本和毛利。收件人与抄送需核对；本页仅准备本机草稿，不发送邮件。</p><label className="native-field"><span>邮件草稿</span><textarea readOnly rows={9} value={`主题：${result.customer_email.subject}\n\n${result.customer_email.body}`} /></label><button type="button" disabled={busy || result.stale_quote} onClick={() => copy("customer")}>复制客户邮件草稿</button></>}

        <p className="page-subtitle">{result.delivery_status} · {dirty ? "当前修改尚未保存" : `已读取版本 ${draft.revision}`}</p>
      </section>}
      {navigate && <button type="button" disabled={busy} onClick={() => navigate("projects", { projectId })}>返回该项目推进</button>}
    </>}
  </div>;
}
