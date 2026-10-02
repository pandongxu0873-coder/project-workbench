export function publicUrl(value) {
  try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) ? url.href : ""; } catch { return ""; }
}
export function revenueRecord(item) {
  const evidence = item.revenue_evidence;
  if (evidence && typeof evidence === "object") {
    const verified = /^verified/.test(evidence.status || "") && typeof evidence.amount_yi === 'number' && Number.isFinite(evidence.amount_yi) && evidence.amount_yi > 0 && !!publicUrl(evidence.source_url) && evidence.period === 'annual' && !!evidence.entity && Number(evidence.year) >= 2000 && Number(evidence.year) < new Date().getFullYear() && String(evidence.source_text||'').includes(String(evidence.year)) && String(evidence.source_text||'').includes(evidence.entity) && /营业收入|营收/.test(evidence.source_text||"") && !/目标|预计|预测|季度|半年/i.test(evidence.source_text||"");
    return { amount: verified ? Number(evidence.amount_yi) : null, label: verified ? evidence.label || "营收来源已核验" : "营收待核实，不参与规模定级", url: publicUrl(evidence.source_url), checked: verified };
  }
  const match = String(evidence || "").match(/(?:营业收入|营收)[^\d]{0,6}([\d,.]+)\s*(亿元|亿)/);
  const url = String(item.source || "").split(/\s*[;；]\s*/).map(publicUrl).find(Boolean) || "";
  return { amount: null, label: evidence || "营收待核实", url, checked: false };
}
export function discoveryLane(lead, today) {
  if (lead.decision === "ignored") return "ignored";
  const deadline = String(lead.deadline || "").slice(0, 10);
  const dated = /^\d{4}-\d{2}-\d{2}$/.test(deadline);
  if (/(中标|成交公告|成交结果|采购结果|终止|废标)/.test(lead.title || "") || (dated && deadline < today)) return "history";
  if (dated && deadline >= today) return "current";
  if (lead.decision === "stale") return "history";
  return "potential";
}
export function outreachRoute(record = {}) {
  if (!record.checked_at || !record.ownership_evidence) return "先查 CRM 主体、负责人和保护状态；未查到不等于无人持有。";
  if (record.protection === "other") return "存在他人保护，暂停对外建联，先协调保护归属。";
  if (record.owner_scope === "other_k100") return "其他 K100 同事名下，默认不对外跟进；需明确协作或交接后再推进。";
  if (["direct", "channel", "standard"].includes(record.owner_scope)) return "先找对应团队负责人协商联合，明确分工与归属；尚不代表对方已同意。";
  if (record.owner_scope === "unowned") return "先按公司规则核实并认领主体，完成后再建联。";
  if (record.owner_scope !== "mine" || record.protection === "unknown") return "主体归属或保护状态尚未明确，先内部核实。";
  if (record.demand === "none") return "本轮没有明确需求，保留培育；按约定的新信号或复访日期再联系。";
  if (record.demand === "later") return "已有供应商服务，保留约定复访窗口；先确认续约时间、未满足需求与评估条件，不预设会替换。";
  if (record.demand === "confirmed") return "需求已有沟通依据，下一次确认预算、决策链、采购节点和成功标准，再协同售前/技术。";
  return "可安排首次建联；先验证今年需求、现供应商情况及负责人，不预设客户会换供应商。";
}

// Preserve remote edits; conflicting fields require a fresh, explicit edit.
export function mergeQualification(base, local, latest) {
  const merged = { ...latest }, conflicts = [];
  const boundary = ['owner_scope', 'protection', 'owner_name', 'checked_at', 'ownership_evidence'];
  const changedBoundary = boundary.some(k => (latest[k] || '') !== (base[k] || ''));
  for (const key of ['owner_scope','protection','owner_name','checked_at','ownership_evidence','demand','contact_result','next_date']) {
    if ((local[key] || '') === (base[key] || '')) continue;
    if ((boundary.includes(key) && changedBoundary) || ((latest[key] || '') !== (base[key] || '') && latest[key] !== local[key])) conflicts.push(key);
    else merged[key] = local[key];
  }
  return { merged, conflicts };
}
