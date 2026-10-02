const API_BASE = "http://127.0.0.1:8766";
const DEMO_PREFIX = "演示·";
const ACTIONABLE_SCHEDULE_WINDOW_MINUTES = 60;

const state = {
  liveDashboard: null,
  dashboard: null,
  workflow: {},
  demoMode: false,
  selectedCustomer: null,
  activeContextKey: null,
  expandedProject: null,
  intelCache: {},
  contextIndex: {},
  lastReceipt: null,
  focusTab: "background",
  returnSectionAfterSubmit: null,
  activeTool: null,
  prospecting: null,
  accountAdvancement: null,
  selectedAccountId: "",
  accountStageFilter: "",
  manualTodoDraft: null,
  newsCustomer: null,
  flowGroups: [],
  activeWorkspace: "today",
  acceleratorFilter: "todo",
  acceleratorPane: "next",
  acceleratorFilterLocked: false,
  pathScope: "customer",
  routeFilterProject: "",
  globalRouteFilterProject: "",
};

function apiUrl(path) {
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE}${path}`;
}

async function getJson(url, options = {}) {
  const response = await fetch(apiUrl(url), options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "请求失败");
  }
  return payload;
}

async function postJson(url, payload = {}) {
  return getJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function deepClone(value) {
  if (value == null) return value;
  return JSON.parse(JSON.stringify(value));
}

function compactText(value = "", limit = 80) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function displayTime(value = "") {
  const text = String(value || "").trim();
  if (!text) return "待触发";
  return text.replace("T", " ").replace("+08:00", "").slice(0, 16);
}

function keyPart(value = "") {
  return String(value || "")
    .replace(/\s+/g, " ")
    .replace(/[^\w\u4e00-\u9fff.%+-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 90);
}

function workflowKey(type, ...parts) {
  return [type, ...parts.map(keyPart)].filter(Boolean).join(":");
}

function workflowState() {
  return state.workflow || {};
}

function workflowRecord(bucket, key) {
  return workflowState()?.[bucket]?.[key] || null;
}

function isProjectReportWorkflowRecord(record = {}) {
  const haystack = [
    record.kind,
    record.source_view,
    record.status,
    record.title,
    record.key,
    record.item?.source_view,
    record.item?.source,
    record.item?.source_scope,
    record.item?.source_type,
  ].filter(Boolean).join(" ");
  return /项目群日报|PM日报|项目日报|飞书日报|pm_daily|pm_item/.test(haystack);
}

function isHiddenWorkflow(bucket, key) {
  const record = workflowRecord(bucket, key);
  return Boolean(record?.hidden || record?.status === "已闭环" || record?.status === "已处理");
}

function isSupersededSchedule(item = {}) {
  const key = scheduleWorkflowKey(item);
  const record = workflowRecord("schedule_status", key);
  const replacementId = record?.receipt?.todo?.id || record?.todo?.id || "";
  return Boolean(replacementId && replacementId !== key);
}

function receiptForScheduleItem(item = {}) {
  const todoId = scheduleTodoId(item, scheduleWorkflowKey(item));
  const directRecord = workflowRecord("schedule_status", scheduleWorkflowKey(item));
  if (directRecord?.receipt) return directRecord.receipt;
  return (workflowState().receipts || []).find((receipt) => receipt?.todo?.id === todoId) || null;
}

function enrichScheduleItem(item = {}) {
  const receipt = receiptForScheduleItem(item);
  if (!receipt) return item;
  const todo = receipt.todo || {};
  return {
    ...item,
    latest_receipt: receipt,
    status: receipt.status || item.status,
    resolution: receipt.resolution || todo.resolution || item.resolution,
    next_step: receipt.next_step || todo.next_step || item.next_step,
    deadline: todo.deadline || item.deadline,
    calendar: todo.calendar || item.calendar,
  };
}

function actionWorkflowKey(item = {}) {
  if (item.context_type === "schedule") {
    return workflowKey("schedule-action", item.workflow_key || item.id || item.todo_id || item.customer, item.action || item.title || item.next_step || item.deadline);
  }
  return item.workflow_key || workflowKey("action", item.customer, item.action || item.title || item.task);
}

function riskWorkflowKey(item = {}) {
  return item.workflow_key || workflowKey("risk", item.customer, item.task || item.title || item.risk);
}

function pmWorkflowKey(day = {}, item = {}) {
  return item.workflow_key || workflowKey("pm", day.date || day, item.name || item.topic || item.group || "项目群日报", item.summary || item.task || item.title);
}

function scheduleWorkflowKey(item = {}) {
  return item.workflow_key || item.id || workflowKey("schedule", item.customer, item.title || item.next_step, item.deadline);
}

function scheduleTodoId(item = {}, fallback = "") {
  return item.todo_id || item.id || fallback || "";
}

const routineUnmatchedCalendarPatterns = [
  "AI应用分享",
  "AI 应用分享",
  "应用分享",
  "大客&广告周常分享",
  "大客广告周常分享",
  "周常分享",
  "周常",
  "分享会",
  "内部分享",
  "培训",
  "例会",
  "小组周会",
  "部门会议",
  "全员",
];

function isRoutineUnmatchedCalendarItem(item = {}) {
  const source = item.source_type || item.source_scope || "";
  if (source !== "feishu_calendar") return false;
  if (item.matched_customer) return false;
  if ((item.customer || "") !== "待匹配日程") return false;
  const text = [item.title, item.evidence, item.action, item.next_step, item.projectLine]
    .filter(Boolean)
    .join(" ");
  const normalized = text.replace(/\s+/g, "");
  return routineUnmatchedCalendarPatterns.some((pattern) => text.includes(pattern) || normalized.includes(pattern));
}

function registerContext(type, item = {}, key = "") {
  const finalKey = key || workflowKey(type, item.customer || item.name, item.title || item.action || item.task || item.summary);
  state.contextIndex[finalKey] = { type, item, key: finalKey };
  return finalKey;
}

function generatedWorkflowItem(record = {}, target) {
  const source = record.item || {};
  const customer = record.customer || source.customer || source.name || "未绑定客户";
  if (target === "risk") {
    return {
      customer,
      projectLine: source.projectLine || "客户项目线",
      priority: source.priority || findCustomer(customer)?.priority || "P1",
      level: "message",
      label: record.status || "工作台转风险",
      date: source.date || "",
      status: "风险观察",
      task: source.task || source.title || record.title || source.summary || "待确认风险",
      risk: source.risk || source.summary || record.title || "来自工作台的风险",
      recommendation: source.recommendation || source.next_step || "进入客户作战室确认责任人和截止时间",
      source: "workflow_item",
      workflow_key: record.key,
    };
  }
  return {
    customer,
    priority: source.priority || findCustomer(customer)?.priority || "P1",
    stage: source.stage || "工作台转入",
    action: source.action || source.task || source.title || record.title || source.summary || "项目群动态",
    risk: source.risk || source.summary || "来自工作台的动态摘要",
    signal: source.signal || record.source_view || "工作台转入",
    source: "workflow_item",
    workflow_key: record.key,
  };
}

function dedupeByKey(items, keyGetter) {
  const seen = new Set();
  const output = [];
  items.forEach((item) => {
    const key = keyGetter(item);
    if (!key || seen.has(key)) return;
    seen.add(key);
    output.push(item);
  });
  return output;
}

function compactScheduleIntent(item = {}) {
  const fields = [
    item.title,
    item.next_step,
    item.action,
    item.source_type === "feishu_calendar" || item.source_scope === "feishu_calendar" ? item.evidence : "",
  ];
  return fields.join(" ").toLowerCase().replace(/[^\w\u4e00-\u9fff]+/g, "");
}

function scheduleDeadlineKey(item = {}) {
  return normalizeDateTime(item.deadline || "").slice(0, 16);
}

function commonPrefixLength(left = "", right = "") {
  let count = 0;
  const limit = Math.min(left.length, right.length);
  while (count < limit && left[count] === right[count]) count += 1;
  return count;
}

function charNgrams(text = "", size = 2) {
  if (!text) return new Set();
  if (text.length <= size) return new Set([text]);
  const grams = new Set();
  for (let index = 0; index <= text.length - size; index += 1) {
    grams.add(text.slice(index, index + size));
  }
  return grams;
}

function scheduleTextSimilarity(left = "", right = "") {
  const leftGrams = charNgrams(left);
  const rightGrams = charNgrams(right);
  if (!leftGrams.size || !rightGrams.size) return 0;
  let overlap = 0;
  leftGrams.forEach((gram) => {
    if (rightGrams.has(gram)) overlap += 1;
  });
  return overlap / new Set([...leftGrams, ...rightGrams]).size;
}

const scheduleAnchorMarkers = [
  "收敛7月上线排期",
  "7月上线",
  "人群包",
  "抽奖",
  "分享裂变",
  "分享有礼",
  "搜索优化",
  "示例预算",
  "示例预算",
  "48.2万",
  "482万",
  "框架补回",
  "框架承接",
  "o2o",
  "二期",
];

function sharedScheduleMarkers(left = "", right = "") {
  return scheduleAnchorMarkers.filter((marker) => left.includes(marker.toLowerCase()) && right.includes(marker.toLowerCase()));
}

function similarScheduleItems(left = {}, right = {}) {
  const leftId = scheduleTodoId(left, scheduleWorkflowKey(left));
  const rightId = scheduleTodoId(right, scheduleWorkflowKey(right));
  if (leftId && rightId && leftId === rightId) return true;
  if (scheduleDeadlineKey(left) !== scheduleDeadlineKey(right)) return false;
  const leftCustomer = left.customer || left.name || "";
  const rightCustomer = right.customer || right.name || "";
  if (leftCustomer && rightCustomer && !customerMatchText(leftCustomer, rightCustomer)) return false;
  const leftText = compactScheduleIntent(left);
  const rightText = compactScheduleIntent(right);
  if (Math.min(leftText.length, rightText.length) < 14) return false;
  if (commonPrefixLength(leftText, rightText) >= 18) return true;
  const sharedMarkers = sharedScheduleMarkers(leftText, rightText);
  if (
    sharedMarkers.length >= 3
    && sharedMarkers.some((marker) => ["收敛7月上线排期", "7月上线", "人群包", "抽奖", "分享裂变", "分享有礼", "搜索优化"].includes(marker))
  ) {
    return true;
  }
  return scheduleTextSimilarity(leftText, rightText) >= 0.45;
}

function scheduleItemRank(item = {}) {
  const source = item.source_type || item.source_scope || "";
  const firstParty = source === "feishu_calendar" ? 0 : 1;
  return [
    firstParty,
    parseTime(item.created_at || item.updated_at || item.submitted_at || ""),
    compactScheduleIntent(item).length,
    String(scheduleTodoId(item, scheduleWorkflowKey(item))),
  ];
}

function preferredScheduleItem(left = {}, right = {}) {
  const leftRank = scheduleItemRank(left);
  const rightRank = scheduleItemRank(right);
  for (let index = 0; index < leftRank.length; index += 1) {
    if (rightRank[index] > leftRank[index]) return right;
    if (rightRank[index] < leftRank[index]) return left;
  }
  return right;
}

function dedupeScheduleItems(items = []) {
  return items.reduce((output, item) => {
    const matchIndex = output.findIndex((existing) => similarScheduleItems(existing, item));
    if (matchIndex < 0) {
      output.push(item);
    } else {
      output[matchIndex] = preferredScheduleItem(output[matchIndex], item);
    }
    return output;
  }, []);
}

function applyWorkflowToPayload(payload = {}) {
  const next = deepClone(payload);
  state.workflow = next.workflow_state || {};

  const generatedActions = Object.values(workflowState().generated_actions || {})
    .filter((record) => !isProjectReportWorkflowRecord(record))
    .map((record) => generatedWorkflowItem(record, "action"));
  const baseActions = (next.battle_actions || []).map((item) => (
    item.context_type === "schedule" ? enrichScheduleItem(item) : item
  ));
  next.battle_actions = dedupeByKey([...generatedActions, ...baseActions], (item) => actionWorkflowKey(item))
    .filter((item) => {
      if (item.context_type === "schedule") {
        return !isHiddenWorkflow("schedule_status", scheduleWorkflowKey(item)) && !isSupersededSchedule(item);
      }
      return !isHiddenWorkflow("action_status", actionWorkflowKey(item));
    });

  const generatedRisks = Object.values(workflowState().generated_risks || {})
    .filter((record) => !isProjectReportWorkflowRecord(record))
    .map((record) => generatedWorkflowItem(record, "risk"));
  const baseRisks = next.risk_alerts || [];
  const activeActionKeys = new Set(next.battle_actions.map((item) => workflowKey("action", item.customer, item.action)));
  next.risk_alerts = dedupeByKey([...generatedRisks, ...baseRisks], (item) => riskWorkflowKey(item))
    .filter((item) => !isHiddenWorkflow("risk_status", riskWorkflowKey(item)))
    .filter((item) => !activeActionKeys.has(workflowKey("action", item.customer, item.task)));

  next.risk_todos = (next.risk_todos || [])
    .map((item) => enrichScheduleItem(item))
    .filter((item) => !isRoutineUnmatchedCalendarItem(item))
    .filter((item) => !isHiddenWorkflow("schedule_status", scheduleWorkflowKey(item)))
    .filter((item) => !isSupersededSchedule(item));
  next.risk_todos = dedupeScheduleItems(next.risk_todos);

  return next;
}

function scheduleMinutesLeft(item = {}) {
  const value = Number(item.minutes_left);
  return Number.isFinite(value) ? value : null;
}

function isScheduleDueForAction(item = {}) {
  const bucket = item.schedule_bucket || "";
  const minutesLeft = scheduleMinutesLeft(item);
  const deadlineMinutesLeft = item.deadline ? Math.round((parseTime(item.deadline) - Date.now()) / 60000) : null;
  const effectiveMinutesLeft = minutesLeft !== null ? minutesLeft : deadlineMinutesLeft;
  if (bucket === "overdue") return true;
  return bucket === "today" && effectiveMinutesLeft !== null && effectiveMinutesLeft <= ACTIONABLE_SCHEDULE_WINDOW_MINUTES;
}

function workbenchSeed() {
  return window.WORKBENCH_DATA || {};
}

function normalizeDateTime(value = "") {
  const source = String(value || "").trim();
  if (!source) return "";
  if (/[+-]\d{2}:\d{2}$/.test(source)) return source;
  const normalized = source.replace(" ", "T");
  if (/T\d{2}:\d{2}$/.test(normalized)) return `${normalized}:00+08:00`;
  if (/T\d{2}:\d{2}:\d{2}$/.test(normalized)) return `${normalized}+08:00`;
  return normalized;
}

function parseTime(value = "") {
  return Date.parse(normalizeDateTime(value)) || 0;
}

function normalizeCustomerName(value = "") {
  return String(value)
    .replace(/[()（）]/g, " ")
    .replace(/[、,，/&]/g, " ")
    .replace(/有限责任公司|股份有限公司|有限公司|分公司|集团|项目|体系/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function customerTokens(value = "") {
  return normalizeCustomerName(value)
    .split(" ")
    .map((item) => item.trim())
    .filter((item) => item.length >= 2);
}

function sharesCustomerToken(left = "", right = "") {
  const leftTokens = customerTokens(left);
  const rightTokens = new Set(customerTokens(right));
  return leftTokens.some((token) => rightTokens.has(token));
}

function customerAliases(item = {}) {
  return [item.name, item.source_customer, item.projectLine]
    .filter(Boolean);
}

function findCustomer(name = "") {
  if (!name) return null;
  return state.dashboard?.deal_board?.find((item) => customerAliases(item).some((alias) => (
    alias === name
    || alias.includes(name)
    || name.includes(alias)
    || sharesCustomerToken(alias, name)
  ))) || null;
}

function fallbackCustomerFromContext(name = "", context = null) {
  const item = context?.item || {};
  const customerName = name || item.customer || item.name || "待匹配事项";
  return {
    name: customerName,
    source_customer: customerName,
    bucket: "active",
    priority: "P2",
    stage: item.source_type === "feishu_calendar" ? "飞书日程待匹配" : "待匹配事项",
    amount: "",
    owner: item.calendar?.organizer || "待确认",
    next_action: contextAction(context, {}),
    risk: contextEvidence(context, {}),
    signal: contextSourceLabel(context),
    projectLine: item.projectLine || "待匹配日程",
  };
}

function inferCustomerFromText(text = "") {
  const source = String(text || "");
  return state.dashboard?.deal_board?.find((item) => customerAliases(item).some((alias) => alias && source.includes(alias))) || null;
}

function normalizeKnowledgeKey(value = "") {
  return String(value || "")
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/[^\w\u4e00-\u9fff]+/g, "")
    .replace(/20\d{6}$/g, "");
}

function knowledgeRecordScore(item = {}) {
  const fields = [
    item.summary,
    item.preview,
    item.title,
    item.raw_title,
    item.path,
    ...(item.actions || []),
    ...(item.risks || []),
    ...(item.signals || []),
  ];
  return fields.filter(Boolean).join("").length + String(item.path || "").split("/").length * 6;
}

function preferredKnowledgeRecord(left = {}, right = {}) {
  if (knowledgeRecordScore(right) > knowledgeRecordScore(left)) return right;
  return left;
}

function dedupeKnowledgeItems(items = []) {
  const records = new Map();
  items.forEach((item) => {
    const project = normalizeKnowledgeKey(item.project || (item.projects || []).join("-") || "未归类");
    const title = normalizeKnowledgeKey(item.raw_title || item.title || item.summary || item.preview || item.path);
    const day = String(item.updated_at || "").slice(0, 10);
    const key = [project, title, day].filter(Boolean).join("|");
    if (!key || !records.has(key)) {
      records.set(key || `${records.size}`, item);
      return;
    }
    records.set(key, preferredKnowledgeRecord(records.get(key), item));
  });
  return [...records.values()];
}

function groupedKnowledge(items = []) {
  const groups = {};
  dedupeKnowledgeItems(items).forEach((item) => {
    const project = item.project || "未归类";
    if (!groups[project]) groups[project] = [];
    groups[project].push(item);
  });
  return Object.entries(groups)
    .map(([project, history]) => ({
      project,
      history: [...history].sort((a, b) => parseTime(b.updated_at) - parseTime(a.updated_at)),
    }))
    .sort((a, b) => parseTime(b.history[0]?.updated_at) - parseTime(a.history[0]?.updated_at));
}

function workbenchDateLabel(value = "") {
  const time = parseTime(value);
  if (!time) return "当前数据";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    timeZone: "Asia/Shanghai",
  }).format(new Date(time));
}

function countKnowledgeUpdates(items = [], reference = "") {
  const ref = parseTime(reference) || Date.now();
  const sevenDays = 7 * 24 * 60 * 60 * 1000;
  return items.filter((item) => ref - parseTime(item.updated_at) <= sevenDays).length;
}

function reportSignalsCount(messageDigest = {}) {
  const latest = messageDigest.days?.[0];
  if (!latest) return 0;
  return (latest.items || []).filter((item) => Number(item.message_count || 0) > 0).length;
}

function classifyRisk(item = {}) {
  if (item.priority === "P0" || item.level === "overdue" || /超期|高/.test(item.label || "")) return "high";
  if (item.priority === "P1" || item.level === "today" || item.level === "soon" || /中/.test(item.label || "")) return "medium";
  return "low";
}

function riskSummary(alerts = []) {
  return alerts.reduce((acc, item) => {
    acc[classifyRisk(item)] += 1;
    return acc;
  }, { high: 0, medium: 0, low: 0 });
}

function projectStatus(group) {
  const deal = findCustomer(group.project);
  if (deal?.stage) return deal.stage;
  const latest = group.history[0] || {};
  if (latest.risks?.length) return "有风险记录";
  if (latest.actions?.length) return "有行动记录";
  return "已沉淀";
}

function projectSummary(group) {
  const latest = group.history[0] || {};
  return latest.summary || latest.preview || "暂无最新摘要";
}

function projectRecentNode(group) {
  const latest = group.history[0] || {};
  return latest.actions?.[0]
    || latest.risks?.[0]
    || latest.signals?.[0]
    || latest.preview
    || "暂无最近节点";
}

function buildPrepItems(payload) {
  const latest = payload.message_digest?.days?.[0];
  const activeDeals = payload.deal_board?.filter((item) => item.bucket === "active") || [];
  return activeDeals.slice(0, 4).map((item) => {
    const digestMatch = latest?.items?.find((entry) => sharesCustomerToken(entry.name, item.name));
    return {
      customer: item.name,
      badge: item.stage || "待准备",
      mustConfirm: item.next_action || "补齐下一步动作",
      cannotPromise: item.risk || "暂无明确风险",
      talkingPoints: digestMatch?.actions?.[0]?.task || item.signal || "先把本周判断、边界和客户关心的问题压缩成 1 页。",
    };
  });
}

function workbenchSources() {
  return "销售知识库、项目群日报、纷享销客";
}

function statusPillLabel(priority = "") {
  if (priority === "P0") return "优先跟进";
  if (priority === "P1") return "本周重点";
  return "持续跟进";
}

function snapshotSyncLabel(payload = {}) {
  if (payload.capture_status === "demo") return "演示模式";
  if (!payload.last_sync) return "未同步";
  return `同步于 ${String(payload.last_sync).replace("T", " ").replace("+08:00", "")}`;
}

function percentageValue(raw, fallbackText = "") {
  if (Number.isFinite(raw)) return Math.max(0, Math.min(1, raw));
  const match = String(fallbackText).match(/-?\d+(?:\.\d+)?/);
  if (!match) return 0;
  return Math.max(0, Math.min(1, Number(match[0]) / 100));
}

function workbenchValueCards(payload) {
  const latestReport = payload.message_digest?.days?.[0];
  const risks = riskSummary(payload.risk_alerts || []);
  const schedules = payload.risk_todos || [];
  const calendarStatus = payload.calendar_status || {};
  return [
    {
      label: "今日优先动作",
      value: currentActionCount(payload),
      hint: "按风险和时效排序",
      action: "打开动作清单",
      section: "section-actions",
    },
    {
      label: "今日日程",
      value: schedules.length,
      hint: calendarStatus.feishu_count
        ? `飞书 ${calendarStatus.feishu_count} / deadline ${calendarStatus.deadline_count || 0}`
        : schedules[0]?.countdown_label || "飞书日程 / deadline",
      action: "打开日程",
      section: "section-schedule",
    },
    {
      label: "高风险客户",
      value: risks.high,
      hint: "先看会失控的客户",
      action: "打开风险雷达",
      section: "section-risks",
    },
    {
      label: "项目群日报",
      value: reportSignalsCount(payload.message_digest || {}),
      hint: latestReport ? `${latestReport.date} 已归纳` : "暂无项目群日报",
      action: "打开项目群日报",
      section: "section-reports",
    },
    {
      label: "知识沉淀更新",
      value: countKnowledgeUpdates(payload.knowledge_timeline || [], payload.generated_at),
      hint: "最近 7 天更新",
      action: "打开知识沉淀",
      section: "section-knowledge",
    },
    {
      label: "达成率",
      value: payload.fxiaoke_status?.quarter?.attainment_rate || "--",
      hint: payload.fxiaoke_status?.quarter?.achieved_amount || "经营快照",
      action: "查看业绩快照",
      section: "section-snapshot",
    },
  ];
}

function queueGroupForPayloadAction(item = {}) {
  const contextType = item.context_type || "action";
  const key = contextType === "schedule" ? scheduleWorkflowKey(item) : actionWorkflowKey(item);
  return actionQueueGroup(item, key);
}

function currentActionCount(payload = {}) {
  return (payload.battle_actions || []).filter((item) => {
    const group = queueGroupForPayloadAction(item);
    return group?.id === "focus" || group?.id === "overdue";
  }).length;
}

function scrollToSection(sectionId) {
  const element = document.querySelector(`#${sectionId}`);
  if (!element) return;
  element.scrollIntoView({ behavior: "smooth", block: "start" });
}

function workspaceForSection(sectionId, navPane = "") {
  if (sectionId === "section-overview") return navPane === "war" ? "customer" : "today";
  return {
    "section-accounts": "accounts",
    "section-actions": "today",
    "section-risks": "customer",
    "section-focus": "customer",
    "section-schedule": "deadline",
    "section-reports": "daily",
    "section-snapshot": "snapshot",
    "section-pricing": "pricing",
    "section-knowledge": "knowledge",
  }[sectionId] || "";
}

function workspaceForTool(tool = "") {
  return {
    "manual-todo": "capture",
    "customer-news": "news",
    prospecting: "prospecting",
  }[tool] || "";
}

function acceleratorPaneForSection(sectionId, navPane = "") {
  if (navPane) return navPane;
  return {
    "section-overview": "next",
    "section-actions": "next",
    "section-risks": "war",
    "section-focus": "war",
  }[sectionId] || "";
}

function resetAcceleratorViewport() {
  const shell = document.querySelector(".main-shell");
  if (shell) shell.scrollTo({ top: 0, left: 0, behavior: "auto" });
  window.scrollTo({ top: 0, left: 0, behavior: "auto" });
}

function openAcceleratorSection(sectionId, navPane = "") {
  const workspace = workspaceForSection(sectionId, navPane);
  if (!workspace) return false;
  state.activeWorkspace = workspace;
  const pane = acceleratorPaneForSection(sectionId, navPane);
  if (pane) {
    state.acceleratorPane = pane;
  } else if (workspace === "today") {
    state.acceleratorPane = "next";
  } else if (workspace === "customer") {
    state.acceleratorPane = "war";
  }
  if (state.acceleratorPane === "path") {
    state.pathScope = "customer";
    state.routeFilterProject = "";
  }
  state.acceleratorFilterLocked = false;
  setActiveNav(sectionId, navPane);
  closeToolWindow();
  renderActiveWorkspace();
  if (workspace === "accounts") ensureAccountWorkspaceData();
  resetAcceleratorViewport();
  return true;
}

function setActiveNav(sectionId, navPane = "") {
  state.activeTool = null;
  document.querySelectorAll("[data-section-nav]").forEach((button) => {
    const buttonPane = button.dataset.acceleratorNavPane || "";
    button.classList.toggle("is-active", button.dataset.sectionNav === sectionId && buttonPane === navPane);
  });
  document.querySelectorAll("[data-tool-open]").forEach((button) => {
    button.classList.remove("is-active");
  });
}

function demoCatalog() {
  return [
    {
      name: `${DEMO_PREFIX}星海汽车商城框架扩容`,
      bucket: "active",
      priority: "P0",
      stage: "采购锁单阶段",
      amount: "86万",
      owner: "工作台用户 / 商务",
      next_action: "今天拉齐采购口径并补书面依据",
      risk: "演示项目的验收范围尚待确认",
      signal: "合成演示：下一轮范围讨论已安排，尚无最终确认。",
      status: "采购锁单阶段",
      demo_intel: {
        message_signals: [{
          kind: "群消息",
          source: "演示项目群",
          date: "2026-06-22",
          snippet: "合成演示：团队计划召开范围评审，结论待确认。",
        }],
        local_signals: [{
          source: "演示知识卡",
          updated_at: "2026-06-22 18:46",
          snippet: "框架扩容需要补齐采购口径、金额归属和盖章路径。",
        }],
        public_signals: [],
      },
    },
    {
      name: `${DEMO_PREFIX}松果宠物 GEO 试点`,
      bucket: "active",
      priority: "P1",
      stage: "方案确认中",
      amount: "24万/年",
      owner: "工作台用户",
      next_action: "确认试点品牌、签约主体和预算归属",
      risk: "试点门店范围和预算主体还没有最终落锤",
      signal: "客户对 GEO + AI 有明确兴趣，但试点范围和预算主体待定。",
      status: "方案确认中",
      demo_intel: {
        message_signals: [{
          kind: "群消息",
          source: "演示项目群",
          date: "2026-06-22",
          snippet: "客户更倾向先做单品牌诊断，再逐步放大到区域门店。",
        }],
        local_signals: [{
          source: "演示知识卡",
          updated_at: "2026-06-22 18:30",
          snippet: "GEO 成果要按半年或一年服务周期来谈，不能按短期投放承诺。",
        }],
        public_signals: [],
      },
    },
    {
      name: `${DEMO_PREFIX}车企私域运营托管`,
      bucket: "active",
      priority: "P1",
      stage: "商务复核",
      amount: "62万",
      owner: "工作台用户 / 交付",
      next_action: "补齐项目经理配置和分阶段验收方案",
      risk: "客户希望快启动，但内部需要先锁 PM 和资源",
      signal: "业务已经动起来，但交付和项目经理配置仍是主要顾虑。",
      status: "商务复核",
      demo_intel: {
        message_signals: [{
          kind: "群消息",
          source: "演示项目群",
          date: "2026-06-21",
          snippet: "客户已认可先按分阶段目标启动，但需要看到 PM 和资源安排。",
        }],
        local_signals: [{
          source: "演示知识卡",
          updated_at: "2026-06-22 17:50",
          snippet: "项目启动条件已经接近满足，当前关键是把交付证据链补完整。",
        }],
        public_signals: [],
      },
    },
    {
      name: `${DEMO_PREFIX}华南连锁宠物 AI 外呼`,
      bucket: "active",
      priority: "P1",
      stage: "需求澄清",
      amount: "48万",
      owner: "工作台用户",
      next_action: "补齐外呼名单来源和转化口径",
      risk: "数据来源、合规边界和转化定义还不够清晰",
      signal: "客户对外呼和门店增长有兴趣，但需要先明确名单和归因口径。",
      status: "需求澄清",
      demo_intel: {
        message_signals: [{
          kind: "群消息",
          source: "演示项目群",
          date: "2026-06-22",
          snippet: "客户希望先用一个城市跑试点，再决定是否扩展到全国门店。",
        }],
        local_signals: [{
          source: "演示知识卡",
          updated_at: "2026-06-22 16:20",
          snippet: "需要把名单来源、合规边界和门店落地动作一次讲清。",
        }],
        public_signals: [],
      },
    },
    {
      name: `${DEMO_PREFIX}区域商超 AI 导购`,
      bucket: "active",
      priority: "P2",
      stage: "首轮演示",
      amount: "36万",
      owner: "工作台用户",
      next_action: "安排下周门店场景演示",
      risk: "业务 owner 明确，但预算批准流程偏慢",
      signal: "客户对到店导购兴趣明确，当前需要拿场景演示推动预算。",
      status: "首轮演示",
      demo_intel: {
        message_signals: [{
          kind: "群消息",
          source: "演示项目群",
          date: "2026-06-20",
          snippet: "门店负责人愿意提供 1 家试点店，预算需要总经理签批。",
        }],
        local_signals: [{
          source: "演示知识卡",
          updated_at: "2026-06-22 15:10",
          snippet: "如果演示效果成立，客户愿意把导购场景接进下半年预算。",
        }],
        public_signals: [],
      },
    },
    {
      name: `${DEMO_PREFIX}零售集团会员增长`,
      bucket: "potential",
      priority: "P2",
      stage: "线索培育",
      amount: "55万",
      owner: "工作台用户",
      next_action: "先拿到业务 owner 的首轮会",
      risk: "还没有进入正式立项流程",
      signal: "高层有意愿，但缺一场能把问题说透的首轮会。",
      status: "线索培育",
      demo_intel: {
        message_signals: [],
        local_signals: [{
          source: "演示知识卡",
          updated_at: "2026-06-22 14:20",
          snippet: "适合作为下周重点破冰对象，先做高层问题诊断。",
        }],
        public_signals: [],
      },
    },
  ];
}

function buildDemoBattleActions(items) {
  return items
    .filter((item) => item.bucket === "active")
    .slice(0, 5)
    .map((item) => ({
      customer: item.name,
      priority: item.priority,
      stage: item.stage,
      action: item.next_action,
      risk: item.risk,
      signal: item.signal,
    }));
}

function buildDemoRiskAlerts(items) {
  return [
    {
      customer: items[0].name,
      priority: "P0",
      level: "overdue",
      label: "采购口径未锁定",
      task: "补齐框架扩容的书面确认",
      risk: "预算和框架价解释口径仍未完全统一",
      recommendation: "今天内把采购口径、金额归属和盖章路径拉平",
      source: "demo_mode",
    },
    {
      customer: items[1].name,
      priority: "P1",
      level: "today",
      label: "试点主体待确认",
      task: "明确试点品牌、签约主体和服务周期",
      risk: "试点范围不清会拖慢报价和签约节奏",
      recommendation: "先收敛到 1 个品牌 / 1 个区域试点",
      source: "demo_mode",
    },
    {
      customer: items[2].name,
      priority: "P1",
      level: "soon",
      label: "交付资源待补齐",
      task: "补充 PM 配置和验收方案",
      risk: "客户希望快启动，但内部资源还没完全锁定",
      recommendation: "先定 PM，再给客户分阶段验收承诺",
      source: "demo_mode",
    },
    {
      customer: items[3].name,
      priority: "P1",
      level: "message",
      label: "名单和合规边界待澄清",
      task: "补齐名单来源、归因和授权方式",
      risk: "口径不清会影响试点能否落地",
      recommendation: "把试点范围和名单授权做成 1 页说明",
      source: "demo_mode",
    },
  ];
}

function buildDemoCustomers(items, liveCustomers = {}) {
  const next = {
    active: [],
    potential: [],
    reference: deepClone(liveCustomers.reference || []),
    excluded: deepClone(liveCustomers.excluded || []),
  };
  items.forEach((item) => {
    next[item.bucket]?.push({
      name: item.name,
      status: item.stage,
      owner: item.owner,
      note: item.risk,
    });
  });
  return next;
}

function buildDemoFxiaokeStatus(items) {
  const generatedAt = workbenchSeed().generatedAt || "2026-06-22 18:46";
  return {
    ok: true,
    capture_status: "demo",
    last_sync: normalizeDateTime(generatedAt),
    source_label: "演示模式经营快照",
    snapshot_note: "以下客户和金额为演示填充，用于首页展示联动。",
    quarter: {
      period: "2026 Q2",
      target_amount: "300.00万",
      achieved_amount: "213.60万",
      gap_amount: "86.40万",
      attainment_rate: "71.20%",
      attainment_rate_raw: 0.712,
    },
    preview: {
      opportunities: [
        { name: items[0].name, status: "已签约 86万" },
        { name: items[2].name, status: "已签约 62万" },
        { name: items[1].name, status: "待签约 24万/年" },
        { name: items[3].name, status: "推进中 48万" },
        { name: items[4].name, status: "演示排期 36万" },
      ],
      accounts: items.map((item) => ({
        name: item.name,
        status: item.bucket === "active" ? "首页关注客户" : "演示储备客户",
      })),
    },
    pipeline: {
      visible_updated_at: `${String(generatedAt).slice(0, 10)} 演示数据`,
      customer_signed_breakdown_status: "演示客户 5 个",
    },
  };
}

function buildDemoDashboard(basePayload) {
  const base = deepClone(basePayload || {});
  const items = demoCatalog();
  base.generated_at = workbenchSeed().generatedAt || base.generated_at || "";
  base.deal_board = items;
  base.battle_actions = buildDemoBattleActions(items);
  base.risk_alerts = buildDemoRiskAlerts(items);
  base.customers = buildDemoCustomers(items, base.customers || {});
  base.fxiaoke_status = buildDemoFxiaokeStatus(items);
  return base;
}

function updateModeToggle() {
  document.querySelectorAll("[data-mode-toggle]").forEach((button) => {
    const isDemo = button.dataset.modeToggle === "demo";
    button.classList.toggle("is-active", isDemo === state.demoMode);
  });
}

function renderTopbar(payload) {
  document.querySelector("#topbarMeta").textContent = `${workbenchDateLabel(payload.generated_at)} · 数据来源：${workbenchSources()}`;
  document.querySelector("#generatedAt").textContent = state.demoMode
    ? `演示模式 · 基于 ${payload.generated_at || workbenchSeed().generatedAt || "静态样例"}`
    : `更新于 ${payload.generated_at || "未知时间"}`;
}

function accountAttentionCount(payload = state.dashboard || {}) {
  const prospectingSummary = payload.prospecting?.summary || state.prospecting?.summary || {};
  return (prospectingSummary.pending_count || 0)
    + (prospectingSummary.verify_count || 0)
    + (state.accountAdvancement?.today_actions?.length || 0);
}

function refreshAccountNavCount(payload = state.dashboard || {}) {
  const count = accountAttentionCount(payload);
  ["#navAccountsCount", "#navAccountsSideCount"].forEach((selector) => {
    const node = document.querySelector(selector);
    if (node) node.textContent = count || "";
  });
}

function renderSidebar(payload) {
  const latestReport = payload.message_digest?.days?.[0];
  const setNavCount = (selector, value) => {
    const node = document.querySelector(selector);
    if (node) node.textContent = value;
  };
  const prospectingSummary = payload.prospecting?.summary || state.prospecting?.summary || {};
  refreshAccountNavCount(payload);
  setNavCount("#navOverviewCount", currentActionCount(payload));
  setNavCount("#navWarCount", "");
  setNavCount("#navScheduleCount", payload.risk_todos?.length || 0);
  setNavCount("#navRiskCount", payload.risk_alerts?.length || 0);
  setNavCount("#navReportCount", latestReport?.items?.length || payload.message_digest?.days?.length || 0);
  setNavCount("#navNewsCount", payload.deal_board?.filter((item) => item.bucket === "active").length || 0);
  setNavCount("#navProspectingCount", (prospectingSummary.pending_count || 0) + (prospectingSummary.verify_count || 0));
  setNavCount("#navKnowledgeCount", groupedKnowledge(payload.knowledge_timeline || []).reduce((sum, group) => sum + (group.history?.length || 0), 0));
  setNavCount("#navSnapshotCount", "");
  setNavCount("#navPricingCount", "");

  const activeDeals = payload.deal_board?.filter((item) => item.bucket === "active") || [];
  document.querySelector("#activeCustomerList").innerHTML = activeDeals.length
    ? activeDeals.map((item) => `
      <button class="active-customer ${state.selectedCustomer === item.name ? "is-selected" : ""}" type="button" data-customer="${escapeHtml(item.name)}">
        <span>${escapeHtml(item.name)}</span>
        <strong>${escapeHtml(item.priority)}</strong>
      </button>
    `).join("")
    : '<div class="empty-inline">暂无活跃客户</div>';
}

function primaryScheduleItem(payload) {
  const bucketRank = {
    overdue: 0,
    today: 1,
    week: 2,
    unscheduled: 3,
    later: 4,
  };
  return [...(payload.risk_todos || [])].sort((left, right) => (
    (bucketRank[left.schedule_bucket || "unscheduled"] ?? 3)
    - (bucketRank[right.schedule_bucket || "unscheduled"] ?? 3)
  ))[0];
}

function focusCardAttributes(card) {
  if (card.customer) {
    return `data-customer="${escapeHtml(card.customer)}"${card.contextKey ? ` data-context-key="${escapeHtml(card.contextKey)}"` : ""}`;
  }
  if (card.section) {
    return `data-jump-section="${escapeHtml(card.section)}"`;
  }
  return "";
}

function reportPreviewText(value = "") {
  const text = String(value || "").trim();
  return text
    .replace(/，?共\s*\d+\s*条有效消息。?/g, "。")
    .replace(/，?群内产生\s*\d+\s*条有效消息。?/g, "。")
    .replace(/沟通时段\s*[^。；;]+。?/g, "")
    .replace(/群内暂无有效消息/g, "今天没有形成明确推进")
    .replace(/。。+/g, "。")
    .replace(/；。/g, "。")
    .trim();
}

function buildFocusBriefCards(payload) {
  const action = payload.battle_actions?.[0];
  const schedule = primaryScheduleItem(payload);
  const scheduleCustomer = schedule?.customer || "待匹配事项";
  const scheduleTitle = schedule?.title || schedule?.next_step || "待跟进";
  const latestReport = payload.message_digest?.days?.[0];
  const activeGroups = latestReport?.items?.filter((item) => Number(item.message_count || 0) > 0) || [];
  const quarter = payload.fxiaoke_status?.quarter || {};
  const actionKey = action ? registerContext("action", action, actionWorkflowKey(action)) : "";
  const scheduleKey = schedule ? registerContext("schedule", schedule, scheduleWorkflowKey(schedule)) : "";

  return [
    {
      tone: "action",
      badge: action?.priority || "动作",
      metric: `${payload.battle_actions?.length || 0} 个`,
      title: action ? `${action.customer} · ${action.action}` : "暂无必须立即推进的动作",
      text: action?.risk || action?.signal || "今天没有被系统判定为优先处理的客户动作。",
      customer: action?.customer || "",
      contextKey: actionKey,
      section: "section-actions",
    },
    {
      tone: "schedule",
      badge: schedule?.countdown_label || "日程",
      metric: `${payload.risk_todos?.length || 0} 条`,
      title: schedule ? (scheduleTitle.includes(scheduleCustomer) ? scheduleTitle : `${scheduleCustomer} · ${scheduleTitle}`) : "暂无飞书日程或 deadline",
      text: schedule?.next_step || schedule?.time_label || "同步飞书日程和工作台 deadline 后，这里会优先显示最近需要处理的事项。",
      customer: schedule?.customer || "",
      contextKey: scheduleKey,
      section: "section-schedule",
    },
    {
      tone: "report",
      badge: latestReport?.date || "日报",
      metric: `${activeGroups.length || latestReport?.items?.length || 0} 个群`,
      title: latestReport ? "今日项目群日报已生成" : "今天还没有项目群日报",
      text: reportPreviewText(latestReport?.overview_points?.[0] || latestReport?.summary || "生成后会按项目群汇总进展、问题、计划和协同事项。"),
      section: "section-reports",
    },
    {
      tone: "snapshot",
      badge: snapshotSyncLabel(payload.fxiaoke_status || {}),
      metric: quarter.attainment_rate || "--",
      title: "销售经营快照",
      text: `目标 ${quarter.target_amount || "待读取"} / 已签约 ${quarter.achieved_amount || "待读取"}`,
      section: "section-snapshot",
    },
  ];
}

function renderFocusBrief(payload) {
  const container = document.querySelector("#todayFocusBrief");
  if (!container) return;
  const cards = buildFocusBriefCards(payload);
  container.innerHTML = `
    <div class="focus-brief-head">
      <div>
        <span class="section-kicker">今日焦点</span>
        <h2>先处理这几项</h2>
      </div>
      <p>动作、日程、项目群日报和业绩快照合并到一个入口，下面再看完整明细。</p>
    </div>
    <div class="focus-brief-grid">
      ${cards.map((card) => `
        <button class="focus-brief-card ${escapeHtml(card.tone)}" type="button" ${focusCardAttributes(card)}>
          <span class="focus-brief-badge">${escapeHtml(card.badge)}</span>
          <strong>${escapeHtml(card.metric)}</strong>
          <h3>${escapeHtml(card.title)}</h3>
          <p>${escapeHtml(card.text)}</p>
        </button>
      `).join("")}
    </div>
  `;
}

function salesBrainStepClass(status = "") {
  if (String(status).includes("本次")) return "is-current";
  if (String(status).includes("已")) return "is-done";
  return "is-pending";
}

function salesBrainPanelHtml(payload = {}) {
  const brain = payload.sales_brain || {};
  const buckets = brain.judgment_buckets || [];
  const todayQueue = brain.today_queue || [];
  const tomorrowPlan = brain.tomorrow_plan || [];
  const steps = brain.ten_steps || [];
  return `
    <div class="sales-brain-head">
      <div>
        <span>销售主脑</span>
        <h2>今天怎么打，处理完去哪</h2>
      </div>
      <strong>${escapeHtml(todayQueue.length || payload.battle_actions?.length || 0)} 条今日判断</strong>
    </div>
    <div class="sales-brain-steps" aria-label="10 步销售闭环">
      ${steps.map((step) => `
        <span class="sales-brain-step ${salesBrainStepClass(step.status)}">
          <strong>${escapeHtml(step.step || "")}</strong>
          <em>${escapeHtml(step.status || "")}</em>
        </span>
      `).join("")}
    </div>
    <div class="sales-brain-grid">
      <section class="sales-brain-block">
        <h3>系统现在怎么判断</h3>
        <div class="sales-brain-buckets">
          ${buckets.map((bucket) => `
            <div class="sales-brain-bucket">
              <strong>${escapeHtml(bucket.type || "")}<em>${escapeHtml(bucket.count ?? "")}</em></strong>
              <p>${escapeHtml(bucket.meaning || "")}</p>
              <span>${escapeHtml(bucket.destination || "")}</span>
            </div>
          `).join("") || '<div class="sales-brain-empty">暂无判断桶。</div>'}
        </div>
      </section>
      <section class="sales-brain-block">
        <h3>今日前三件事为什么出现</h3>
        <div class="sales-brain-queue">
          ${todayQueue.slice(0, 3).map((item) => `
            <article class="sales-brain-row">
              <strong>${escapeHtml(item.customer || "待匹配事项")}</strong>
              <p>${escapeHtml(item.action || "待处理")}</p>
              <dl>
                <dt>为什么今天</dt><dd>${escapeHtml(item.why_today || "")}</dd>
                <dt>本次目标</dt><dd>${escapeHtml(item.target || "")}</dd>
                <dt>处理后</dt><dd>${escapeHtml(item.exit || item.destination || "")}</dd>
              </dl>
            </article>
          `).join("") || '<div class="sales-brain-empty">当前没有必须今天处理的事项。</div>'}
        </div>
      </section>
      <section class="sales-brain-block">
        <h3>明日预案</h3>
        <div class="sales-brain-queue">
          ${tomorrowPlan.map((item) => `
            <article class="sales-brain-row compact">
              <strong>${escapeHtml(item.customer || "待匹配事项")}</strong>
              <p>${escapeHtml(item.title || "准备下一步")}</p>
              <span>${escapeHtml(item.trigger || "下一次提醒")}</span>
              <small>${escapeHtml(item.prepare || "")}</small>
            </article>
          `).join("") || '<div class="sales-brain-empty">明日预案会在今日回执后生成。</div>'}
        </div>
      </section>
    </div>
  `;
}

function renderSalesBrainPanel(payload = {}) {
  const container = document.querySelector("#salesBrainPanel");
  if (!container) return;
  container.innerHTML = "";
}

function renderStats(payload) {
  document.querySelector("#statsGrid").innerHTML = workbenchValueCards(payload).map((card) => `
    <button class="stat-card" type="button" data-jump-section="${escapeHtml(card.section)}">
      <div>
        <div class="stat-value">${escapeHtml(card.value)}</div>
        <div class="stat-label">${escapeHtml(card.label)}</div>
        <div class="stat-hint">${escapeHtml(card.hint)}</div>
      </div>
      <span class="stat-action">${escapeHtml(card.action || "查看详情")}</span>
    </button>
  `).join("");
}

function activeDeals() {
  return state.dashboard?.deal_board?.filter((item) => item.bucket === "active") || [];
}

function setToolChrome({ kicker = "侧边工具", title = "工具窗口", subtitle = "", body = "" } = {}) {
  const windowEl = document.querySelector("#sideToolWindow");
  if (!windowEl) return;
  document.body.classList.add("tool-mode");
  windowEl.dataset.tool = state.activeTool || "";
  document.querySelector("#toolWindowKicker").textContent = kicker;
  document.querySelector("#toolWindowTitle").textContent = title;
  document.querySelector("#toolWindowSubtitle").textContent = subtitle;
  document.querySelector("#toolWindowBody").innerHTML = body;
  document.querySelector("#toolBackdrop").hidden = false;
  windowEl.hidden = false;
}

function setActiveTool(tool) {
  document.querySelectorAll("[data-section-nav]").forEach((button) => {
    const isGlobalPath = tool === "global-paths" && button.dataset.sectionNav === "section-knowledge";
    button.classList.toggle("is-active", isGlobalPath);
  });
  document.querySelectorAll("[data-tool-open]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.toolOpen === tool);
  });
}

function closeToolWindow() {
  const closingTool = state.activeTool;
  state.activeTool = null;
  document.body.classList.remove("tool-mode");
  document.querySelector("#toolBackdrop").hidden = true;
  const windowEl = document.querySelector("#sideToolWindow");
  windowEl.hidden = true;
  windowEl.dataset.tool = "";
  document.querySelectorAll("[data-tool-open]").forEach((button) => button.classList.remove("is-active"));
  if (closingTool === "global-paths") {
    setActiveNav("section-overview");
  }
}

function globalPathRecordHtml(record = {}) {
  const title = record.title || record.raw_title || record.type || "未命名记录";
  const actions = (record.actions || []).filter(Boolean);
  const risks = (record.risks || []).filter(Boolean);
  const signals = (record.signals || []).filter(Boolean);
  return `
    <article class="global-route-record">
      <div class="global-route-record-head">
        <span>${escapeHtml(record.type || "知识库记录")}</span>
        <strong>${escapeHtml(title)}</strong>
        <em>${escapeHtml(record.updated_at || "暂无时间")}</em>
      </div>
      ${routeFullTextHtml(routeRecordText(record))}
      <div class="global-route-signal-grid">
        ${actions.length ? `<div><span>行动</span><p>${escapeHtml(actions[0])}</p></div>` : ""}
        ${risks.length ? `<div><span>风险</span><p>${escapeHtml(risks[0])}</p></div>` : ""}
        ${signals.length ? `<div><span>信号</span><p>${escapeHtml(signals[0])}</p></div>` : ""}
      </div>
      <small>${escapeHtml(routeRecordSource(record))}</small>
    </article>
  `;
}

function globalPathGroupHtml(group = {}) {
  const history = group.history || [];
  const latest = history[0] || {};
  return `
    <section class="global-route-group">
      <div class="global-route-group-head">
        <div>
          <span>知识沉淀</span>
          <strong>${escapeHtml(group.project || "未归类")}</strong>
        </div>
        <em>${history.length} 条沉淀</em>
      </div>
      <p>${escapeHtml(projectSummary(group))}</p>
      <div class="global-route-meta">
        ${acceleratorMicroRow("最近节点", latest.updated_at || "暂无时间")}
        ${acceleratorMicroRow("当前判断", projectStatus(group))}
      </div>
      <div class="global-route-record-list">
        ${globalKnowledgeUnitsHtml(history.slice(0, 8))}
      </div>
    </section>
  `;
}

function renderGlobalPathsTool() {
  const allGroups = groupedKnowledge(state.dashboard?.knowledge_timeline || []);
  if (state.globalRouteFilterProject && !allGroups.some((group) => group.project === state.globalRouteFilterProject)) {
    state.globalRouteFilterProject = "";
  }
  const groups = state.globalRouteFilterProject
    ? allGroups.filter((group) => group.project === state.globalRouteFilterProject)
    : allGroups;
  const total = allGroups.reduce((sum, group) => sum + (group.history?.length || 0), 0);
  const body = `
    <section class="tool-card global-route-summary">
      <div class="tool-metric-row">
        <div>
          <span>知识沉淀</span>
          <strong>${escapeHtml(allGroups.length)}</strong>
        </div>
        <div>
          <span>知识沉淀</span>
          <strong>${escapeHtml(total)}</strong>
        </div>
      </div>
      <p>这里是全局销售知识库沉淀，只做完整阅读和项目回溯；不会绑定当前客户，也不会生成今日行动。</p>
    </section>
    <section class="tool-card global-route-library">
      <div class="tool-section-head">
        <div>
          <h3>全局知识沉淀</h3>
          <p>需要处理客户时，从“现在处理”或客户作战室进入；这里保持只读。</p>
        </div>
      </div>
      <div class="global-route-filter">
        <button class="${state.globalRouteFilterProject ? "" : "is-active"}" type="button" data-global-route-filter="">全部</button>
        ${allGroups.map((group) => `
          <button class="${state.globalRouteFilterProject === group.project ? "is-active" : ""}" type="button" data-global-route-filter="${escapeHtml(group.project)}">
            ${escapeHtml(group.project)} <span>${group.history?.length || 0}</span>
          </button>
        `).join("")}
      </div>
      <div class="global-route-list">
        ${groups.length ? groups.map(globalPathGroupHtml).join("") : '<div class="tool-empty">当前没有知识沉淀。</div>'}
      </div>
    </section>
  `;
  setToolChrome({
    kicker: "全局资料库",
    title: "全局知识沉淀",
    subtitle: "只读销售知识库里的客户 / 项目沉淀，不进入当前客户处理闭环。",
    body,
  });
}

function globalWorkspaceConfig(workspace = state.activeWorkspace) {
  return {
    accounts: {
      kicker: "AI 客户准入",
      title: "候选客户判断台",
      subtitle: "AI 每天先筛一批客户；你只判断去向：列明、补证据、观察或剔除。",
      state: "",
    },
    deadline: {
      kicker: "全局时间系统",
      title: "下次提醒",
      subtitle: "所有 Deadline 和飞书日程统一在这里看；点击具体事项后才进入客户作战室。",
      state: "全局",
    },
    knowledge: {
      kicker: "全局资料库",
      title: "全局知识沉淀",
      subtitle: "只读销售知识库里的客户 / 项目沉淀，不绑定当前客户。",
      state: "只读",
    },
    capture: {
      kicker: "执行入口",
      title: "销售捕捉",
      subtitle: "把临时想到的客户动作接入今日队列或 Deadline；这里是主工作区，不继承当前客户。",
      state: "可写",
    },
    news: {
      kicker: "客户情报",
      title: "客户新闻关联",
      subtitle: "选择客户后查看公开新闻、本地知识和群消息信号；只做判断依据，不自动生成待办。",
      state: "只读",
    },
    prospecting: {
      kicker: "自动任务",
      title: "战略客户雷达",
      subtitle: "自动扫描新客户线索，按购买能力、业务触发、业务平台切口和供应商路径先进入独立核验。",
      state: "待核验",
    },
    snapshot: {
      kicker: "经营判断",
      title: "业绩快照",
      subtitle: "季度目标、签约额和客户签约明细。这里不和今日待办混在一起。",
      state: "只读",
    },
    pricing: {
      kicker: "报价工具",
      title: "私有化计算器",
      subtitle: "独立报价护栏，可选关联客户，但默认不进入客户作战室。",
      state: "工具",
    },
    daily: {
      kicker: "只读日报",
      title: "项目群日报",
      subtitle: "只读项目群动态，不生成今日行动、反馈链或 Deadline。",
      state: "只读",
    },
  }[workspace] || {
    kicker: "全局工作区",
    title: "工作区",
    subtitle: "这些内容不继承当前客户作战室。",
    state: "全局",
  };
}

function globalSnapshotWorkspaceHtml() {
  const snapshot = state.dashboard?.fxiaoke_status || {};
  if (!snapshot?.ok) {
    return '<section class="global-panel"><h3>业绩快照暂时不可用</h3><p>经营数据读取失败或尚未同步。</p></section>';
  }
  const quarter = snapshot.quarter || {};
  const preview = snapshot.preview || {};
  const signedItems = preview.opportunities || [];
  const progress = percentageValue(quarter.attainment_rate_raw, quarter.attainment_rate);
  return `
    <section class="global-panel global-snapshot-hero">
      <div class="attainment-ring" style="--progress:${progress}">
        <div class="attainment-ring-inner">
          <strong>${escapeHtml(quarter.attainment_rate || "--")}</strong>
          <span>达成率</span>
        </div>
      </div>
      <div class="global-metric-grid">
        ${acceleratorMicroRow("本季度目标", quarter.target_amount || "待读取")}
        ${acceleratorMicroRow("已签约", quarter.achieved_amount || "待读取")}
        ${acceleratorMicroRow("差额", quarter.gap_amount || "待读取")}
        ${acceleratorMicroRow("同步状态", snapshotSyncLabel(snapshot))}
      </div>
    </section>
    <section class="global-panel">
      <div class="global-section-head">
        <h3>签约明细</h3>
        <span>点击客户后再进入客户作战室</span>
      </div>
      <div class="global-record-grid">
        ${signedItems.length ? signedItems.map((item) => {
          const key = registerContext("snapshot", item, workflowKey("snapshot", item.name, item.status));
          return `
            <button class="global-record-card" type="button" data-customer="${escapeHtml(item.name)}" data-context-key="${escapeHtml(key)}">
              <strong>${escapeHtml(item.name || "签约客户")}</strong>
              <p>${escapeHtml(item.status || "已同步")}</p>
            </button>
          `;
        }).join("") : '<div class="tool-empty">当前没有可展示的签约明细。</div>'}
      </div>
    </section>
  `;
}

function globalDeadlineWorkspaceHtml() {
  const payload = state.dashboard || {};
  const todos = payload.risk_todos || [];
  const calendarStatus = payload.calendar_status || {};
  const statusLine = calendarStatus.error || (
    calendarStatus.fetched_at
      ? `${calendarStatus.label || "飞书日程"} · ${String(calendarStatus.fetched_at).replace("T", " ").replace("+08:00", "")}`
      : calendarStatus.label || "飞书日程待同步"
  );
  const grouped = scheduleGroupDefinitions().map(([bucket, label]) => {
    const groupItems = todos.filter((item) => (item.schedule_bucket || "unscheduled") === bucket);
    if (!groupItems.length) return "";
    return `
      <section class="global-panel">
        <div class="global-section-head">
          <h3>${escapeHtml(label)}</h3>
          <span>${groupItems.length} 条</span>
        </div>
        <div class="global-record-grid">
          ${groupItems.slice(0, 12).map(renderScheduleCard).join("")}
        </div>
      </section>
    `;
  }).join("");
  return `
    <section class="global-panel">
      <div class="global-metric-grid">
        ${acceleratorMicroRow("同步状态", statusLine)}
        ${acceleratorMicroRow("飞书日程", `${calendarStatus.feishu_count || 0} 条`)}
        ${acceleratorMicroRow("工作台 Deadline", `${calendarStatus.deadline_count || 0} 条`)}
        ${acceleratorMicroRow("待匹配", `${calendarStatus.unmatched_count || 0} 条`)}
      </div>
    </section>
    ${renderScheduleReceiptBanner()}
    ${grouped || '<section class="global-panel"><div class="tool-empty">当前没有日程或 Deadline。</div></section>'}
  `;
}

function globalKnowledgeWorkspaceHtml() {
  const allGroups = groupedKnowledge(state.dashboard?.knowledge_timeline || []);
  if (state.globalRouteFilterProject && !allGroups.some((group) => group.project === state.globalRouteFilterProject)) {
    state.globalRouteFilterProject = "";
  }
  const groups = state.globalRouteFilterProject
    ? allGroups.filter((group) => group.project === state.globalRouteFilterProject)
    : allGroups;
  const total = allGroups.reduce((sum, group) => sum + (group.history?.length || 0), 0);
  return `
    <section class="global-panel">
      <div class="global-metric-grid">
        ${acceleratorMicroRow("沉淀对象", `${allGroups.length} 个`)}
        ${acceleratorMicroRow("沉淀记录", `${total} 条`)}
        ${acceleratorMicroRow("使用方式", "只读回溯")}
        ${acceleratorMicroRow("状态写入", "不生成待办")}
      </div>
    </section>
    <section class="global-panel">
      <div class="global-route-filter">
        <button class="${state.globalRouteFilterProject ? "" : "is-active"}" type="button" data-global-route-filter="">全部</button>
        ${allGroups.map((group) => `
          <button class="${state.globalRouteFilterProject === group.project ? "is-active" : ""}" type="button" data-global-route-filter="${escapeHtml(group.project)}">
            ${escapeHtml(group.project)} <span>${group.history?.length || 0}</span>
          </button>
        `).join("")}
      </div>
      <div class="global-route-list">
        ${groups.length ? groups.map(globalPathGroupHtml).join("") : '<div class="tool-empty">当前没有知识沉淀。</div>'}
      </div>
    </section>
  `;
}

function globalDailyWorkspaceHtml() {
  const messageDigest = state.dashboard?.message_digest || {};
  const latestDate = messageDigest.latest_date;
  if (!latestDate) {
    return '<section class="global-panel"><h3>暂无项目群日报</h3><p>今天还没有生成项目群日报。</p></section>';
  }
  const staleText = messageDigest.is_stale
    ? `最新项目群日报 ${latestDate}，今天 ${messageDigest.expected_date || ""} 未生成`
    : `今天 ${latestDate} 项目群日报已生成`;
  return `
    <section class="global-panel">
      <div class="global-metric-grid">
        ${acceleratorMicroRow("日报状态", staleText)}
        ${acceleratorMicroRow("承接规则", "只读")}
        ${acceleratorMicroRow("生成待办", "否")}
        ${acceleratorMicroRow("写入 Deadline", "否")}
      </div>
    </section>
    ${(messageDigest.days || []).map((day) => `
      <article class="global-panel report-card">
        <div class="report-card-head">
          <h3>${escapeHtml(day.date)} 项目群日报</h3>
          <span class="health-badge health-${escapeHtml(day.health || "灰")}">${escapeHtml(activityLabel(day.health || "灰"))}</span>
        </div>
        <div class="daily-report">
          <section class="daily-report-summary">
            <p>${escapeHtml(reportPreviewText(day.summary || "暂无摘要"))}</p>
            <div class="daily-report-metrics">
              <span>覆盖项目群 <strong>${escapeHtml(day.file_count || 0)}</strong></span>
              <span>归纳素材 <strong>${escapeHtml(day.message_count || 0)}</strong></span>
              <span>活跃项目群 <strong>${escapeHtml((day.items || []).filter((item) => Number(item.message_count || 0) > 0).length)}</strong></span>
            </div>
          </section>
          ${renderDailyReportBlock("一、今日进展概述", day.overview_points || [], "今日没有形成明确进展。")}
          ${renderDailyReportBlock("二、群内问题与待对齐点", day.issue_points || [], "群内没有形成需要单独提示的问题。")}
          ${renderDailyReportBlock("三、后续计划", day.plan_points || [], "后续计划暂时没有新的变化。")}
          ${renderDailyReportBlock("四、需要关注事项", day.coordination_points || [], "当前没有需要额外关注的项目背景。")}
          <section class="daily-report-section">
            <h4>五、项目群明细</h4>
            ${(day.items || []).map((item, index) => {
              registerContext("pm_item", {
                ...item,
                customer: item.name,
                title: `${item.name} 项目群动态`,
                date: day.date,
              }, pmWorkflowKey(day, item));
              return renderGroupReportSection(item, index);
            }).join("") || '<div class="focus-empty">今天没有可展示的项目群动态。</div>'}
          </section>
        </div>
      </article>
    `).join("")}
  `;
}

function globalPricingWorkspaceHtml() {
  return `
    <section class="global-panel global-pricing-workspace">
      ${acceleratorPricingDetailHtml()}
    </section>
  `;
}

function globalCaptureWorkspaceHtml() {
  return `<section class="global-panel global-capture-workspace">${manualTodoBodyHtml()}</section>`;
}

function globalNewsWorkspaceHtml() {
  const customer = state.newsCustomer || "";
  const intel = customer ? state.intelCache[customer] : null;
  return `<section class="global-panel global-news-workspace">${customerNewsBodyHtml(customer, intel, Boolean(customer && !intel))}</section>`;
}

function globalProspectingWorkspaceHtml() {
  return `<section class="global-panel global-prospecting-workspace">${prospectingBodyHtml(state.prospecting, !state.prospecting)}</section>`;
}

function accountAdvancementStage(stageId = "") {
  const stages = state.accountAdvancement?.stages || [];
  return stages.find((stage) => stage.id === stageId) || { id: stageId, label: stageId || "未分组", short: stageId || "未分组" };
}

function accountPipelineGateSpec(stageId = "") {
  const map = {
    discover: {
      method: "ABM 入口",
      title: "先确认是不是值得进入候选池",
      rule: "看公开信号、客户主体、近期触发和基础规模；没有证据时只能补证据或观察。",
      action: "列明 / 补证据 / 观察 / 剔除",
    },
    qualify: {
      method: "ABM 定级",
      title: "判断切口是否成立",
      rule: "规模、业务触发、业务平台切口和近期问题至少要能说清楚，不能只靠一个关键词。",
      action: "补规模证据 / 列明 / 暂缓",
    },
    path: {
      method: "渠道联合开门",
      title: "先找进入路径，再决定直连客户",
      rule: "确认供应商、集成商、内部系统边界和利益一致性，找到能带入的人。",
      action: "联系渠道 / 补负责人 / 采纳下一步",
    },
    contact: {
      method: "MEDDICC 接触",
      title: "把业务负责人和痛点问清楚",
      rule: "进入客户接触后，必须补齐负责人、痛点、指标和下一次沟通时间。",
      action: "约访 / 调研 / 写入 Deadline",
    },
    opportunity: {
      method: "MEDDICC 商机",
      title: "围绕预算、方案和采购路径推进",
      rule: "商机阶段要看预算、决策链、竞品/供应商路径、采购窗口和明确下一步。",
      action: "推进方案 / 报价 / 回执",
    },
    next: {
      method: "Deadline 回流",
      title: "未闭环事项到点再回到今日",
      rule: "没有到触发时间的事项只在 Deadline，不制造伪紧急。",
      action: "等待 / 到点提醒 / 闭环",
    },
  };
  return map[stageId] || map.qualify;
}

function pendingProspectingLeads() {
  const payload = state.prospecting?.leads?.length
    ? state.prospecting
    : (state.dashboard?.prospecting || state.prospecting || {});
  const leads = payload.leads || [];
  return leads.filter((lead) => {
    const decision = lead.decision || "pending";
    if (decision === "stale" || lead.actionability === "stale") return false;
    return decision === "pending" || decision === "verify";
  });
}

function accountPipelineItems(ignoreFilter = false) {
  const payload = state.accountAdvancement;
  const accounts = payload?.accounts || [];
  const leads = pendingProspectingLeads().map((lead) => ({
    kind: "lead",
    id: `lead:${lead.id || lead.company || lead.title || ""}`,
    stage: "discover",
    lead,
    name: lead.company || lead.customer || lead.name || "待核验客户",
    priority: lead.decision === "verify" ? "补证" : "AI",
    opportunity: lead.title || lead.signal || "公开线索待核验",
    status_note: lead.time_window_label || lead.status || "待核验",
    channel_count: 0,
    gap_count: lead.decision === "verify" ? 1 : 2,
  }));
  const accountItems = accounts.map((account) => ({
    kind: "account",
    id: account.id || account.name,
    stage: account.stage || "qualify",
    account,
    name: account.name || "未命名客户",
    priority: account.priority || "P?",
    opportunity: account.opportunity || account.status_note || "暂无机会判断",
    status_note: account.status_note || account.opportunity || "暂无状态备注",
    channel_count: account.channel_count || 0,
    gap_count: account.gaps?.length || 0,
  }));
  const filter = state.accountStageFilter || "";
  const items = [...leads, ...accountItems];
  return !ignoreFilter && filter ? items.filter((item) => item.stage === filter) : items;
}

function findPipelineItem(id = "") {
  return accountPipelineItems(true).find((item) => item.id === id) || null;
}

function selectedPipelineItem() {
  const selected = findPipelineItem(state.selectedAccountId || "");
  if (!selected) return null;
  if (state.accountStageFilter && selected.stage !== state.accountStageFilter) return null;
  return selected;
}

function ensureSelectedAccount() {
  const accounts = state.accountAdvancement?.accounts || [];
  if (!accounts.length) {
    state.selectedAccountId = "";
    return null;
  }
  let selected = accounts.find((account) => account.id === state.selectedAccountId);
  if (selected && (!state.accountStageFilter || selected.stage === state.accountStageFilter)) return selected;
  state.selectedAccountId = "";
  return null;
}

function accountGapChipsHtml(gaps = []) {
  if (!gaps.length) return '<span class="account-chip is-ok">证据暂够</span>';
  return gaps.map((gap) => `<span class="account-chip">${escapeHtml(gap)}</span>`).join("");
}

function accountStageRailHtml(payload = {}) {
  const stages = payload.stages || [];
  const allItems = accountPipelineItems(true);
  return `
    <div class="account-stage-rail" role="group" aria-label="账户推进阶段">
      <button class="account-stage ${state.accountStageFilter ? "" : "is-active"}" type="button" data-account-stage-filter="">
        <span>全管线</span>
        <strong>${escapeHtml(allItems.length)}</strong>
        <em>账户 + 线索</em>
      </button>
      ${stages.map((stage) => `
        <button class="account-stage ${state.accountStageFilter === stage.id ? "is-active" : ""}" type="button" data-account-stage-filter="${escapeHtml(stage.id)}">
          <span>${escapeHtml(stage.label)}</span>
          <strong>${escapeHtml(allItems.filter((item) => item.stage === stage.id).length)}</strong>
          <em>${escapeHtml(accountPipelineGateSpec(stage.id).method)}</em>
        </button>
      `).join("")}
    </div>
  `;
}

function accountRowHtml(item = {}) {
  const selected = item.id === state.selectedAccountId;
  const stage = accountAdvancementStage(item.stage);
  return `
    <button class="account-row ${selected ? "is-selected" : ""}" type="button" data-account-select="${escapeHtml(item.id)}">
      <span class="account-row-rank ${item.kind === "lead" ? "is-ai" : ""}">${escapeHtml(item.priority || "P?")}</span>
      <span class="account-row-main">
        <strong>${escapeHtml(compactText(item.name || "未命名客户", 34))}</strong>
        <em>${escapeHtml(compactText(item.opportunity || item.status_note || "暂无机会判断", 72))}</em>
      </span>
      <span class="account-row-meta">
        <small>${escapeHtml(stage.short || stage.label)}</small>
        <small>${item.kind === "lead" ? "待判断" : `${escapeHtml(item.channel_count || 0)} 条路径`}</small>
      </span>
    </button>
  `;
}

function accountListHtml(items = []) {
  if (!items.length) {
    return '<div class="account-empty">当前阶段没有对象。切回“全管线”看所有账户和线索。</div>';
  }
  return items.map(accountRowHtml).join("");
}

function accountChannelHtml(channel = {}) {
  return `
    <article class="account-channel">
      <div>
        <strong>${escapeHtml(channel.name || "待确认渠道")}</strong>
        <span>${escapeHtml(channel.status || "待核验")} · ${escapeHtml(channel.value || "渠道价值待补")}</span>
      </div>
      <p>${escapeHtml(compactText(channel.signal || channel.conflict || "暂无项目线索", 120))}</p>
      <small>${escapeHtml(compactText(channel.next_action || "下一步待补", 96))}</small>
    </article>
  `;
}

function accountActionHtml(action = {}) {
  const stage = accountAdvancementStage(action.stage);
  return `
    <article class="account-action">
      <div>
        <span>${escapeHtml(action.priority || "P?")} · ${escapeHtml(stage.label || "推进")}</span>
        <strong>${escapeHtml(compactText(action.customer || "客户", 34))}</strong>
      </div>
      <p>${escapeHtml(compactText(action.title || "补齐下一步", 112))}</p>
      <footer>
        <em>${escapeHtml(action.source || "客户机会表")}</em>
        <small>${escapeHtml(action.write_policy || "确认后再进入执行链")}</small>
      </footer>
      <div class="account-action-buttons">
        <button class="account-small-button primary" type="button" data-account-capture="${escapeHtml(action.account_id || "")}" data-account-capture-title="${escapeHtml(action.title || "")}" data-account-capture-source="${escapeHtml(action.source || "")}" data-account-capture-target="now">采纳为今日执行</button>
        <button class="account-small-button" type="button" data-account-capture="${escapeHtml(action.account_id || "")}" data-account-capture-title="${escapeHtml(action.title || "")}" data-account-capture-source="${escapeHtml(action.source || "")}" data-account-capture-target="scheduled">放入 Deadline</button>
      </div>
    </article>
  `;
}

function accountGateChecksHtml(account = {}) {
  const checks = [
    { label: "规模证据", ok: Boolean(account.revenue_evidence) },
    { label: "近期触发", ok: Boolean(account.recent_signal) },
    { label: "业务平台切口", ok: Boolean(account.cut_in) },
    { label: "进入路径", ok: Boolean(account.channel_count) },
  ];
  return checks.map((check) => `<span class="account-check ${check.ok ? "is-ok" : ""}">${escapeHtml(check.label)} · ${check.ok ? "已补" : "待补"}</span>`).join("");
}

function accountGatePanelHtml(stageId = "", account = {}) {
  const gate = accountPipelineGateSpec(stageId);
  return `
    <section class="account-gate-panel">
      <div>
        <span>${escapeHtml(gate.method)}</span>
        <strong>${escapeHtml(gate.title)}</strong>
        <p>${escapeHtml(gate.rule)}</p>
      </div>
      <div class="account-gate-actions">
        <em>${escapeHtml(gate.action)}</em>
        <div class="account-check-row">${accountGateChecksHtml(account)}</div>
      </div>
    </section>
  `;
}

function selectedLeadPanelHtml(item = {}) {
  const lead = item.lead || {};
  const gate = accountPipelineGateSpec("discover");
  return `
    <section class="account-detail">
      <div class="account-detail-head">
        <div>
          <span>${escapeHtml(item.priority || "AI")} · ${escapeHtml(accountAdvancementStage("discover").label)}</span>
          <h3>${escapeHtml(item.name || "待核验客户")}</h3>
          <p>${escapeHtml(lead.signal || lead.title || "公开线索待核验")}</p>
        </div>
        <strong>${escapeHtml(lead.status || "待核验")}</strong>
      </div>
      <section class="account-gate-panel">
        <div>
          <span>${escapeHtml(gate.method)}</span>
          <strong>${escapeHtml(gate.title)}</strong>
          <p>${escapeHtml(gate.rule)}</p>
        </div>
        <div class="account-gate-actions">
          <em>${escapeHtml(gate.action)}</em>
          <div class="account-check-row">
            <span class="account-check ${lead.actionability === "actionable" ? "is-ok" : lead.actionability === "stale" ? "is-stale" : ""}">时间窗口 · ${escapeHtml(lead.time_window_label || "待补")}</span>
            <span class="account-check ${lead.revenue_evidence?.status && lead.revenue_evidence.status !== "pending_public_lookup" ? "is-ok" : ""}">规模证据 · ${lead.revenue_evidence?.label || "待核验"}</span>
            <span class="account-check ${lead.source_url ? "is-ok" : ""}">公开信源 · ${lead.source_url ? "已补" : "待补"}</span>
            <span class="account-check ${lead.entry_strategy ? "is-ok" : ""}">破局判断 · ${lead.entry_strategy ? "已补" : "待补"}</span>
          </div>
          <div class="account-decision-inline">${lead.id ? prospectDecisionButtons(lead) : ""}</div>
        </div>
      </section>
      <div class="account-section">
        <h4>公开信号</h4>
        <p>${escapeHtml(lead.title || lead.signal || "待补公开线索标题。")}</p>
      </div>
      ${lead.subject_names?.length ? `
        <div class="account-section">
          <h4>采购范围</h4>
          <p>${escapeHtml(lead.subject_names.slice(0, 6).join("、"))}</p>
        </div>
      ` : ""}
      <div class="account-section">
        <h4>时间窗口</h4>
        <p>${escapeHtml(lead.deadline ? `截止 ${lead.deadline}；${lead.time_window?.note || "等待判断"}` : lead.time_window?.note || "待补公告截止时间。")}</p>
      </div>
      <div class="account-section">
        <h4>业务平台切口 / 破局判断</h4>
        <p>${escapeHtml(lead.entry_strategy || lead.next_step || "先补客户规模、业务触发、现有供应商和预算窗口，再决定是否列明。")}</p>
      </div>
      <div class="account-detail-actions">
        ${lead.source_url ? `<a class="button button-secondary" href="${escapeHtml(lead.source_url)}" target="_blank" rel="noreferrer">看来源</a>` : ""}
      </div>
    </section>
  `;
}

function selectedAccountPanelHtml(item = {}) {
  if (!item) {
    return `
      <section class="account-detail">
        <div class="account-empty">先从左侧选择一个线索或账户；这里会显示该阶段的判断门槛、证据缺口和允许动作。</div>
      </section>
    `;
  }
  if (item.kind === "lead") return selectedLeadPanelHtml(item);
  const account = item.account || {};
  const stage = accountAdvancementStage(account.stage);
  const channels = account.channels || [];
  const deadlines = account.deadlines || [];
  return `
    <section class="account-detail">
      <div class="account-detail-head">
        <div>
          <span>${escapeHtml(account.priority || "P?")} · ${escapeHtml(stage.label || "推进")}</span>
          <h3>${escapeHtml(account.name || "未命名客户")}</h3>
          <p>${escapeHtml(account.status_note || account.opportunity || "暂无状态备注")}</p>
        </div>
        <strong>${escapeHtml(account.updated_at || "待更新")}</strong>
      </div>
      ${accountGatePanelHtml(account.stage, account)}
      <div class="account-evidence-grid">
        ${acceleratorMicroRow("行业", account.industry || "待补")}
        ${acceleratorMicroRow("来源", account.source_type || "待补")}
        ${acceleratorMicroRow("渠道路径", `${account.channel_count || 0} 条`)}
        ${acceleratorMicroRow("下次提醒", `${account.deadline_count || 0} 条`)}
      </div>
      <div class="account-section">
        <h4>业务平台切口</h4>
        <p>${escapeHtml(account.cut_in || "待补齐可进入场景。")}</p>
      </div>
      <div class="account-section">
        <h4>机会判断</h4>
        <p>${escapeHtml(account.opportunity || "待补齐客户为什么值得推进。")}</p>
      </div>
      <div class="account-section">
        <h4>下一步建议</h4>
        <p>${escapeHtml(account.next_action || "先补证据和路径，再生成销售动作。")}</p>
        <div class="account-gap-row">${accountGapChipsHtml(account.gaps || [])}</div>
      </div>
      <div class="account-section">
        <h4>渠道 / 供应商路径</h4>
        <div class="account-channel-list">
          ${channels.length ? channels.map(accountChannelHtml).join("") : '<div class="account-empty">还没有匹配到供应商渠道，先从公开招采和行业服务商补路径。</div>'}
        </div>
      </div>
      <div class="account-detail-actions">
        <button class="button button-primary" type="button" data-account-capture="${escapeHtml(account.id || "")}" data-account-capture-title="${escapeHtml(account.next_action || "")}" data-account-capture-source="${escapeHtml(account.next_action_source || "")}" data-account-capture-target="now">采纳为今日执行</button>
        <button class="button button-secondary" type="button" data-account-capture="${escapeHtml(account.id || "")}" data-account-capture-title="${escapeHtml(account.next_action || "")}" data-account-capture-source="${escapeHtml(account.next_action_source || "")}" data-account-capture-target="scheduled">放入 Deadline</button>
        <button class="button button-secondary" type="button" data-news-customer="${escapeHtml(account.name || "")}">看客户新闻</button>
        <button class="button button-secondary" type="button" data-section-nav="section-schedule">看下次提醒</button>
      </div>
      ${deadlines.length ? `
        <div class="account-section">
          <h4>已在 Deadline 的跟进</h4>
          <div class="account-deadline-list">
            ${deadlines.map((item) => `<span>${escapeHtml(compactText(item.title || item.next_step || "跟进事项", 70))} · ${escapeHtml(displayTime(item.deadline || ""))}</span>`).join("")}
          </div>
        </div>
      ` : ""}
    </section>
  `;
}

function findAccountAdvancement(accountId = "") {
  return (state.accountAdvancement?.accounts || []).find((account) => account.id === accountId) || null;
}

function accountCaptureDraft(account = {}, options = {}) {
  const stage = accountAdvancementStage(account.stage);
  const gaps = account.gaps?.length ? `证据缺口：${account.gaps.join("、")}` : "证据缺口：暂无";
  const source = options.source || account.next_action_source || "客户机会表";
  const title = options.title || account.next_action || account.suggested_play || "补齐客户推进下一步";
  return {
    target: options.target || "now",
    customer: account.name || "",
    title: compactText(title, 78),
    next_step: title,
    evidence: [
      `来源：${source}`,
      `阶段：${stage.label || "账户推进"}`,
      gaps,
      account.opportunity ? `机会判断：${account.opportunity}` : "",
      account.recent_signal ? `近期证据：${account.recent_signal}` : "",
    ].filter(Boolean).join("\n"),
    priority: account.priority?.startsWith("P0") ? "P0" : account.priority?.startsWith("P1") ? "P1" : "P2",
    sync_calendar: false,
  };
}

function accountAdvancementWorkspaceHtml() {
  const payload = state.accountAdvancement;
  if (!payload) {
    return '<section class="account-system"><div class="account-loading">正在读取账户推进管线...</div></section>';
  }
  if (!payload.ok && !payload.accounts?.length) {
    return `<section class="account-system"><div class="account-loading">账户推进数据暂时不可用：${escapeHtml(payload.error || "读取失败")}</div></section>`;
  }
  const selected = selectedPipelineItem();
  const visibleItems = accountPipelineItems();
  const actions = payload.today_actions || [];
  const leadCount = pendingProspectingLeads().length;
  const allItems = accountPipelineItems(true);
  const sourceStatus = payload.source?.status === "cache" ? "显示缓存" : "实时同步";
  return `
    <section class="account-system">
      <section class="account-overview">
        <div>
          <span>当前判断</span>
          <h3>先决定客户去向，再生成今天动作</h3>
          <p>未列明的客户只停在候选池；采纳下一步后，才进入今日队列或 Deadline。</p>
          <div class="account-overview-actions">
            <button class="account-small-button primary" type="button" data-prospecting-run>立即补扫标讯</button>
            <button class="account-small-button" type="button" data-section-nav="section-overview">看今日队列</button>
          </div>
        </div>
        <div class="account-kpis">
          ${acceleratorMicroRow("可判断对象", `${allItems.length} 个`)}
          ${acceleratorMicroRow("待判断线索", `${leadCount} 条`)}
          ${acceleratorMicroRow("待采纳", `${actions.length} 条`)}
          ${acceleratorMicroRow("数据状态", sourceStatus)}
        </div>
      </section>
      ${accountStageRailHtml(payload)}
      <section class="account-main-grid">
        <aside class="account-list-panel">
          <div class="account-panel-title">
            <span>当前阶段对象</span>
            <strong>${escapeHtml(visibleItems.length)} / ${escapeHtml(allItems.length)}</strong>
          </div>
          <div class="account-list">${accountListHtml(visibleItems)}</div>
        </aside>
        ${selectedAccountPanelHtml(selected)}
        <aside class="account-action-panel">
          <div class="account-panel-title">
            <span>待采纳下一步</span>
            <strong>${escapeHtml(actions.length)} 条</strong>
          </div>
          <div class="account-action-list">
            ${actions.length ? actions.map(accountActionHtml).join("") : '<div class="account-empty">当前没有新的下一步建议。</div>'}
          </div>
        </aside>
      </section>
    </section>
  `;
}

function globalWorkspaceBodyHtml(workspace = state.activeWorkspace) {
  if (workspace === "accounts") return accountAdvancementWorkspaceHtml();
  if (workspace === "deadline") return globalDeadlineWorkspaceHtml();
  if (workspace === "knowledge") return globalKnowledgeWorkspaceHtml();
  if (workspace === "capture") return globalCaptureWorkspaceHtml();
  if (workspace === "news") return globalNewsWorkspaceHtml();
  if (workspace === "prospecting") return globalProspectingWorkspaceHtml();
  if (workspace === "snapshot") return globalSnapshotWorkspaceHtml();
  if (workspace === "pricing") return globalPricingWorkspaceHtml();
  if (workspace === "daily") return globalDailyWorkspaceHtml();
  return '<section class="global-panel"><div class="tool-empty">请选择一个工作区。</div></section>';
}

function renderGlobalWorkspace() {
  const root = document.querySelector("#globalWorkspace");
  if (!root) return;
  const config = globalWorkspaceConfig(state.activeWorkspace);
  document.querySelector("#globalWorkspaceKicker").textContent = config.kicker;
  document.querySelector("#globalWorkspaceTitle").textContent = config.title;
  document.querySelector("#globalWorkspaceSubtitle").textContent = config.subtitle;
  document.querySelector("#globalWorkspaceState").textContent = config.state;
  document.querySelector("#globalWorkspaceBody").innerHTML = globalWorkspaceBodyHtml(state.activeWorkspace);
}

function renderActiveWorkspace() {
  const accelerator = document.querySelector("#section-overview.accelerator-workbench");
  const global = document.querySelector("#globalWorkspace");
  const brain = document.querySelector("#salesBrainPanel");
  const isCustomerWorkspace = ["today", "customer"].includes(state.activeWorkspace);
  document.body.dataset.workspace = state.activeWorkspace;
  if (brain) brain.hidden = !isCustomerWorkspace;
  if (accelerator) accelerator.hidden = !isCustomerWorkspace;
  if (global) global.hidden = isCustomerWorkspace;
  if (isCustomerWorkspace) {
    renderAcceleratorWorkbench();
  } else {
    renderGlobalWorkspace();
  }
}

function prospectingStatusText(status = "") {
  if (status === "ok") return "扫描完成";
  if (status === "running") return "正在扫描";
  if (status === "no_result") return "本次未命中";
  if (status === "no_import") return "回传为空";
  if (status === "waiting_for_codex_agent") return "等待 Codex 回传";
  if (status === "search_unavailable") return "搜索源不可用";
  if (status === "waiting") return "等待首次扫描";
  return status || "自动任务已配置";
}

function prospectDecisionClass(lead = {}) {
  if (lead.decision === "stale" || lead.actionability === "stale") return "is-stale";
  return `is-${lead.decision || "pending"}`;
}

function prospectDecisionButtons(lead = {}) {
  const decision = lead.decision || "pending";
  if (decision === "stale" || lead.actionability === "stale") {
    return `<span class="prospect-decision-done">${lead.background_only ? "结果公告 · 仅作供应商背景" : "滞后信号 · 不进今日判断"}</span>`;
  }
  if (decision === "accepted") {
    return `<span class="prospect-decision-done">已列明${lead.added_customer_name ? ` · ${escapeHtml(lead.added_customer_name)}` : ""}</span>`;
  }
  if (decision === "watch") {
    return '<span class="prospect-decision-done">已放入观察</span>';
  }
  if (decision === "verify") {
    return '<span class="prospect-decision-done">待 AI 补证据</span>';
  }
  if (decision === "ignored") {
    return '<span class="prospect-decision-done">已剔除</span>';
  }
  return `
    <button class="prospect-decision-button primary" type="button" data-prospecting-decision="accept" data-lead-id="${escapeHtml(lead.id || "")}">列明</button>
    <button class="prospect-decision-button" type="button" data-prospecting-decision="verify" data-lead-id="${escapeHtml(lead.id || "")}">AI 补证据</button>
    <button class="prospect-decision-button" type="button" data-prospecting-decision="watch" data-lead-id="${escapeHtml(lead.id || "")}">观察</button>
    <button class="prospect-decision-button muted" type="button" data-prospecting-decision="ignore" data-lead-id="${escapeHtml(lead.id || "")}">剔除</button>
  `;
}

function prospectRevenueEvidenceHtml(lead = {}) {
  const evidence = lead.revenue_evidence || {};
  const label = evidence.label || lead.scale_rule || "营收待公开核验";
  const source = evidence.source || "";
  const sourceText = evidence.source_text || "";
  return `
    <div class="prospect-breakthrough prospect-revenue-evidence">
      <span>公开营收证据</span>
      <p>${escapeHtml(label)}${source ? ` · ${escapeHtml(source)}` : ""}</p>
      ${sourceText ? `<small>${escapeHtml(sourceText)}</small>` : ""}
    </div>
  `;
}

function prospectingBodyHtml(payload = state.prospecting, loading = false, error = "") {
  const task = payload?.task || {};
  const summary = payload?.summary || {};
  const leads = payload?.leads || [];
  return loading ? `
    <div class="tool-card tool-loading">正在调用知了标讯并核对公告时间窗口...</div>
  ` : `
    <section class="tool-card prospect-task-card">
      <div class="tool-metric-row">
        <div>
          <span>自动扫描</span>
          <strong>${escapeHtml(task.schedule || "每天 06:00")}</strong>
        </div>
        <div>
          <span>待判断 / 补证据</span>
          <strong>${escapeHtml((summary.pending_count ?? leads.length) + (summary.verify_count || 0))}</strong>
        </div>
        <div>
          <span>已列明</span>
          <strong>${escapeHtml(summary.accepted_count || 0)}</strong>
        </div>
        <div>
          <span>滞后信号</span>
          <strong>${escapeHtml(summary.stale_count || 0)}</strong>
        </div>
      </div>
      <p>${escapeHtml(task.rule || "战略客户雷达：按购买能力、业务触发、业务平台切口和进入路径筛选公开线索")}</p>
      <div class="tool-status-line">
        <span>${escapeHtml(task.source_label || "知了标讯")}</span>
        <span>${escapeHtml(prospectingStatusText(task.last_run_status))}</span>
        <span>上次 ${escapeHtml(displayTime(task.last_run_at))}</span>
        <span>下次 ${escapeHtml(displayTime(task.next_run_at))}</span>
      </div>
      ${task.last_run_error ? `<p class="tool-error">${escapeHtml(task.last_run_error)}</p>` : ""}
    </section>
    ${error ? `<div class="tool-card tool-error">${escapeHtml(error)}</div>` : ""}
    <section class="tool-card">
      <div class="tool-section-head">
        <div>
          <h3>待判断的客户线索</h3>
          <p>只有你确认列明后，客户才会继续进入切口、路径和销售动作。</p>
        </div>
        <button class="tool-mini-button" type="button" data-prospecting-run>立即补扫标讯</button>
      </div>
      <div class="prospect-list">
        ${leads.length ? leads.map((lead) => `
          <article class="prospect-lead ${escapeHtml(prospectDecisionClass(lead))}">
            <div class="prospect-lead-head">
              <strong>${escapeHtml(lead.company || "待核验客户")}</strong>
              <span>${escapeHtml(lead.icp_tier_label || lead.status || "待核验")}</span>
            </div>
            <h4>${escapeHtml(lead.title || "公开网页线索")}</h4>
            <p>${escapeHtml(lead.signal || "")}</p>
            <div class="chip-row">
              <span class="chip amber">${escapeHtml(lead.signal_type || "公开信号")}</span>
              ${lead.source_provider ? `<span class="chip">${escapeHtml(lead.source_provider)}</span>` : ""}
              <span class="chip teal">${escapeHtml(lead.scale_rule || lead.revenue_evidence?.label || "营收待公开核验")}</span>
              ${lead.purchase_signal ? `<span class="chip">${escapeHtml(lead.purchase_signal)}</span>` : ""}
              ${lead.time_window_label ? `<span class="chip ${lead.actionability === "stale" ? "danger" : "teal"}">${escapeHtml(lead.time_window_label)}</span>` : ""}
              ${lead.supplier_path ? `<span class="chip">${escapeHtml(lead.supplier_path)}</span>` : ""}
              ${(lead.keyword_hits || []).slice(0, 4).map((tag) => `<span class="chip">${escapeHtml(tag)}</span>`).join("")}
            </div>
            <div class="prospect-reasons">
              ${(lead.why_matched || []).slice(0, 3).map((reason) => `<span>${escapeHtml(reason)}</span>`).join("")}
            </div>
            ${prospectRevenueEvidenceHtml(lead)}
            ${lead.time_window ? `
              <div class="prospect-breakthrough prospect-time-window">
                <span>时间窗口</span>
                <p>${escapeHtml(lead.time_window.note || lead.time_window_label || "待补时间窗口")}</p>
              </div>
            ` : ""}
            <div class="prospect-breakthrough">
              <span>破局建议</span>
              <p>${escapeHtml(lead.entry_strategy || lead.next_step || "先核验客户规模、业务触发、现有供应商和预算窗口，再决定是否列明。")}</p>
            </div>
            <div class="prospect-next">
              <span>${escapeHtml(lead.next_step || "核验后再决定是否列明")}</span>
              ${lead.source_url ? `<a class="mini-link" href="${escapeHtml(lead.source_url)}" target="_blank" rel="noreferrer">来源</a>` : ""}
            </div>
            <div class="prospect-decision-bar">
              ${prospectDecisionButtons(lead)}
            </div>
          </article>
        `).join("") : '<div class="tool-empty">当前没有符合时间窗口的候选标讯；系统会在每天 06:00 自动扫描。</div>'}
      </div>
    </section>
  `;
}

function renderProspectingTool(payload = state.prospecting, loading = false, error = "") {
  setToolChrome({
    kicker: "候选客户发现",
    title: "标讯与客户准入",
    subtitle: "知了标讯发现公开招采，工作台负责时间窗口、客户适配和准入判断。",
    body: prospectingBodyHtml(payload, loading, error),
  });
}

async function loadProspecting() {
  if (state.activeWorkspace === "prospecting") {
    renderGlobalWorkspace();
  } else if (state.activeTool === "prospecting") {
    renderProspectingTool(state.prospecting, !state.prospecting);
  }
  try {
    const payload = await getJson("/api/prospecting");
    state.prospecting = payload;
    if (state.liveDashboard) state.liveDashboard.prospecting = payload;
    if (state.dashboard) {
      state.dashboard.prospecting = payload;
      renderSidebar(state.dashboard);
    }
    refreshAccountNavCount(state.dashboard || {});
    if (state.activeWorkspace === "prospecting") {
      renderGlobalWorkspace();
    } else if (state.activeWorkspace === "accounts") {
      renderGlobalWorkspace();
    } else if (state.activeTool === "prospecting") {
      renderProspectingTool(payload);
    } else if (["today", "customer"].includes(state.activeWorkspace)) {
      renderAcceleratorWorkbench();
    }
  } catch (error) {
    if (state.activeWorkspace === "prospecting") {
      document.querySelector("#globalWorkspaceBody").innerHTML = `<section class="global-panel">${prospectingBodyHtml(state.prospecting, false, error.message)}</section>`;
    } else if (state.activeTool === "prospecting") {
      renderProspectingTool(state.prospecting, false, error.message);
    }
  }
}

async function ensureAccountWorkspaceData() {
  const tasks = [];
  if (!state.accountAdvancement) tasks.push(loadAccountAdvancement());
  if (!state.prospecting?.leads?.length) tasks.push(loadProspecting());
  if (!tasks.length) return;
  await Promise.allSettled(tasks);
  if (state.activeWorkspace === "accounts") renderGlobalWorkspace();
}

async function runProspectingNow() {
  const staysInAccounts = state.activeWorkspace === "accounts";
  const runButtons = [...document.querySelectorAll("[data-prospecting-run]")];
  runButtons.forEach((button) => {
    button.disabled = true;
    button.dataset.idleLabel = button.textContent;
    button.textContent = "扫描中...";
  });
  if (state.activeWorkspace === "prospecting") {
    document.querySelector("#globalWorkspaceBody").innerHTML = `<section class="global-panel">${prospectingBodyHtml(state.prospecting, true)}</section>`;
  } else if (!staysInAccounts) {
    renderProspectingTool(state.prospecting, true);
  }
  try {
    const payload = await postJson("/api/prospecting/run", {});
    state.prospecting = payload;
    if (state.liveDashboard) state.liveDashboard.prospecting = payload;
    if (state.dashboard) {
      state.dashboard.prospecting = payload;
      renderSidebar(state.dashboard);
    }
    if (staysInAccounts) {
      state.selectedAccountId = "";
      renderGlobalWorkspace();
    } else if (state.activeWorkspace === "prospecting") {
      renderGlobalWorkspace();
    } else {
      renderProspectingTool(payload);
    }
  } catch (error) {
    if (staysInAccounts) {
      renderGlobalWorkspace();
    } else if (state.activeWorkspace === "prospecting") {
      document.querySelector("#globalWorkspaceBody").innerHTML = `<section class="global-panel">${prospectingBodyHtml(state.prospecting, false, error.message)}</section>`;
    } else {
      renderProspectingTool(state.prospecting, false, error.message);
    }
  } finally {
    runButtons.forEach((button) => {
      if (!button.isConnected) return;
      button.disabled = false;
      button.textContent = button.dataset.idleLabel || "立即补扫标讯";
    });
  }
}

async function updateProspectingLead(leadId, target) {
  if (!leadId || !target) return;
  try {
    const result = await postJson("/api/prospecting/lead", { id: leadId, target });
    const payload = result.prospecting || state.prospecting;
    state.prospecting = payload;
    if (state.liveDashboard) state.liveDashboard.prospecting = payload;
    if (state.dashboard) {
      state.dashboard.prospecting = payload;
      renderSidebar(state.dashboard);
    }
    refreshAccountNavCount(state.dashboard || {});
    if (target === "accept") {
      await loadDashboard({ preventDefaultSelection: true });
      if (state.dashboard) {
        state.dashboard.prospecting = payload;
        renderSidebar(state.dashboard);
      }
      refreshAccountNavCount(state.dashboard || {});
    }
    if (state.activeWorkspace === "prospecting") {
      renderGlobalWorkspace();
    } else if (state.activeTool === "prospecting") {
      renderProspectingTool(payload);
    } else if (["today", "customer"].includes(state.activeWorkspace)) {
      renderAcceleratorWorkbench();
    }
  } catch (error) {
    if (state.activeWorkspace === "prospecting") {
      document.querySelector("#globalWorkspaceBody").innerHTML = `<section class="global-panel">${prospectingBodyHtml(state.prospecting, false, error.message)}</section>`;
    } else {
      renderProspectingTool(state.prospecting, false, error.message);
    }
  }
}

function renderSignalList(items = [], emptyText = "暂无关联信息") {
  if (!items.length) return `<div class="tool-empty">${escapeHtml(emptyText)}</div>`;
  return items.slice(0, 5).map((item) => {
    const title = item.title || item.source || item.kind || "关联信号";
    const detail = item.impact_judgment || item.recommended_action || item.snippet || item.summary || item.url || item.source_url || "";
    const date = item.published_at || item.updated_at || item.date || "";
    const sourceUrl = item.url || item.source_url || "";
    return `
      <article class="news-signal">
        <div>
          <strong>${escapeHtml(title)}</strong>
          <span>${escapeHtml(date)}</span>
        </div>
        ${item.signal_type ? `<span class="mini-state">${escapeHtml(item.signal_type)}</span>` : ""}
        <p>${escapeHtml(compactText(detail || title, 110))}</p>
        ${sourceUrl ? `<a class="mini-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">来源</a>` : ""}
      </article>
    `;
  }).join("");
}

function customerNewsBodyHtml(customer = state.newsCustomer, intel = customer ? state.intelCache[customer] : null, loading = false, error = "") {
  const deals = activeDeals();
  const selected = customer || "";
  return `
    <section class="tool-card">
      <div class="tool-section-head">
        <div>
          <h3>客户新闻关联</h3>
          <p>现有客户最新新闻由 Codex 自动搜索回传；这里只做情报判断，不直接写入待办。</p>
        </div>
      </div>
      <div class="news-customer-list">
        ${deals.length ? deals.map((item) => `
          <button class="news-customer-button ${item.name === selected ? "is-active" : ""}" type="button" data-news-customer="${escapeHtml(item.name)}">
            <span>${escapeHtml(item.name)}</span>
            <strong>${escapeHtml(item.priority || "P2")}</strong>
          </button>
        `).join("") : '<div class="tool-empty">当前没有活跃客户。</div>'}
      </div>
    </section>
    <section class="tool-card">
      <div class="tool-section-head">
        <div>
          <h3>${escapeHtml(selected || "先选择客户")}</h3>
          <p>${selected ? (loading ? "正在读取 Codex 回传新闻和知识库信号..." : `Codex 回传 ${displayTime(intel?.public_updated_at) || "待更新"}；公开新闻 / 本地知识 / 群消息只做判断依据。`) : "这个入口是全局客户情报工具，不默认继承当前作战室客户。"}</p>
        </div>
      </div>
      ${error ? `<div class="tool-error">${escapeHtml(error)}</div>` : ""}
      <div class="news-columns">
        <div>
          <h4>最新公开新闻</h4>
          ${selected ? (loading ? '<div class="tool-empty">读取中...</div>' : renderSignalList(intel?.public_signals || [], "暂未收到 Codex 回传的最新新闻。")) : '<div class="tool-empty">先从上方选择一个客户。</div>'}
        </div>
        <div>
          <h4>本地与群消息</h4>
          ${selected ? (loading ? '<div class="tool-empty">读取中...</div>' : renderSignalList([...(intel?.local_signals || []), ...(intel?.message_signals || [])], "暂未关联到本地信号。")) : '<div class="tool-empty">不会自动用当前客户填充。</div>'}
        </div>
      </div>
    </section>
  `;
}

function renderCustomerNewsTool(customer = state.newsCustomer, intel = customer ? state.intelCache[customer] : null, loading = false, error = "") {
  setToolChrome({
    kicker: "客户情报",
    title: "客户新闻关联",
    subtitle: "按现有客户自动关联公开新闻和本地信号，作为作战室判断依据。",
    body: customerNewsBodyHtml(customer, intel, loading, error),
  });
}

async function loadCustomerNews(customer) {
  if (!customer) {
    if (state.activeWorkspace === "news") renderGlobalWorkspace();
    else renderCustomerNewsTool("");
    return;
  }
  state.newsCustomer = customer;
  const cached = state.intelCache[customer];
  if (state.activeWorkspace === "news") renderGlobalWorkspace();
  else renderCustomerNewsTool(customer, cached, !cached);
  if (cached) return;
  try {
    const payload = await getJson(`/api/intel?q=${encodeURIComponent(customer)}`);
    state.intelCache[customer] = payload;
    if (state.activeWorkspace === "news" && state.newsCustomer === customer) {
      renderGlobalWorkspace();
    } else if (state.activeTool === "customer-news" && state.newsCustomer === customer) {
      renderCustomerNewsTool(customer, payload);
    }
  } catch (error) {
    if (state.activeWorkspace === "news" && state.newsCustomer === customer) {
      document.querySelector("#globalWorkspaceBody").innerHTML = `<section class="global-panel">${customerNewsBodyHtml(customer, null, false, error.message)}</section>`;
    } else if (state.activeTool === "customer-news" && state.newsCustomer === customer) {
      renderCustomerNewsTool(customer, null, false, error.message);
    }
  }
}

function manualTodoDeadlineDefault() {
  const date = new Date(Date.now() + 24 * 60 * 60 * 1000);
  date.setHours(10, 0, 0, 0);
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function manualTodoBodyHtml(message = "") {
  const deals = activeDeals();
  const draft = state.manualTodoDraft || {};
  const selected = draft.customer || state.selectedCustomer || deals[0]?.name || "";
  const target = draft.target || "now";
  const title = draft.title || "";
  const nextStep = draft.next_step || "";
  const evidence = draft.evidence || "";
  const priority = draft.priority || "P2";
  const deadline = draft.deadline || manualTodoDeadlineDefault();
  const syncCalendar = Boolean(draft.sync_calendar);
  const dealNames = new Set(deals.map((item) => item.name));
  return `
    <section class="tool-card manual-todo-intro">
      <div class="tool-metric-row">
        <div>
          <span>出口</span>
          <strong>未处理 / 下次提醒</strong>
        </div>
        <div>
          <span>承接</span>
          <strong>客户作战室</strong>
        </div>
      </div>
      <p>手动补充的待办会进入同一条销售闭环：现在处理的事项进入未处理队列；安排到下次的事项进入 Deadline，到点后再回到首页。</p>
      <p>它不是知识库写作入口，而是把你临时想到的客户动作、会后事项、报备跟进或内部协同捕捉进工作台。</p>
    </section>
    <section class="tool-card">
      <form id="manualTodoForm" class="manual-todo-form">
        <div class="manual-target-row" role="radiogroup" aria-label="待办进入哪里">
          <label><input type="radio" name="target" value="now" ${target === "scheduled" ? "" : "checked"} /><span>现在处理</span></label>
          <label><input type="radio" name="target" value="scheduled" ${target === "scheduled" ? "checked" : ""} /><span>安排到下次</span></label>
        </div>
        <label>
          <span>客户 / 项目</span>
          <input class="input" name="customer" list="manualTodoCustomers" value="${escapeHtml(selected)}" placeholder="例如：星海汽车商城" />
        </label>
        <datalist id="manualTodoCustomers">
          ${selected && !dealNames.has(selected) ? `<option value="${escapeHtml(selected)}"></option>` : ""}
          ${deals.map((item) => `<option value="${escapeHtml(item.name)}"></option>`).join("")}
        </datalist>
        <label>
          <span>待办事项</span>
          <input class="input" name="title" value="${escapeHtml(title)}" placeholder="例如：确认 O2O 闭环链路图口径" required />
        </label>
        <label>
          <span>下一步动作</span>
          <textarea class="input text-area" name="next_step" rows="3" placeholder="写清楚下一步要推进什么、找谁确认、交付什么。" required>${escapeHtml(nextStep)}</textarea>
        </label>
        <label>
          <span>依据 / 背景</span>
          <textarea class="input text-area" name="evidence" rows="2" placeholder="可选：这条待办来自哪次沟通或什么判断。">${escapeHtml(evidence)}</textarea>
        </label>
        <div class="manual-grid">
          <label>
            <span>优先级</span>
            <select class="input" name="priority">
              <option value="P1" ${priority === "P1" ? "selected" : ""}>P1</option>
              <option value="P0" ${priority === "P0" ? "selected" : ""}>P0</option>
              <option value="P2" ${priority === "P2" ? "selected" : ""}>P2</option>
            </select>
          </label>
          <label>
            <span>下次时间</span>
            <input class="input" name="deadline" type="datetime-local" value="${escapeHtml(deadline)}" />
          </label>
        </div>
        <label class="manual-check">
          <input type="checkbox" name="sync_calendar" ${syncCalendar ? "checked" : ""} />
          <span>同步飞书提醒</span>
        </label>
        <div class="form-actions">
          <button class="button button-primary" type="submit">加入工作台</button>
          <span id="manualTodoResult" class="form-result">${escapeHtml(message)}</span>
        </div>
      </form>
    </section>
  `;
}

function renderManualTodoTool(message = "") {
  setToolChrome({
    kicker: "执行入口",
    title: "销售捕捉",
    subtitle: "把临时想到的客户动作接入今日队列或 Deadline；它先进入执行闭环，不直接写入知识库。",
    body: manualTodoBodyHtml(message),
  });
}

async function submitManualTodo(form) {
  const result = form.querySelector("#manualTodoResult");
  const data = Object.fromEntries(new FormData(form).entries());
  data.sync_calendar = Boolean(form.querySelector('input[name="sync_calendar"]')?.checked);
  if (!String(data.title || "").trim()) {
    result.textContent = "先填写待办事项。";
    return;
  }
  if (!String(data.next_step || "").trim()) {
    result.textContent = "先填写下一步动作。";
    return;
  }
  if (data.target === "scheduled" && !String(data.deadline || "").trim()) {
    result.textContent = "安排到下次时需要填写时间。";
    return;
  }
  result.textContent = "正在加入工作台...";
  try {
    const payload = await postJson("/api/manual-todo", data);
    const todo = payload.todo || {};
    state.workflow = payload.workflow_state || state.workflow;
    state.manualTodoDraft = null;
    if (payload.dashboard) {
      state.liveDashboard = payload.dashboard;
    }
    state.activeWorkspace = data.target === "scheduled" ? "deadline" : "today";
    state.acceleratorPane = "next";
    state.acceleratorFilter = data.target === "scheduled" ? "followup" : "todo";
    state.acceleratorFilterLocked = true;
    state.lastReceipt = { status: `已销售捕捉：${todo.title || data.title}` };
    closeToolWindow();
    refreshRenderedDashboard({
      preserveCustomer: todo.customer || data.customer,
      preserveContextKey: todo.id || "",
      preventDefaultSelection: true,
    });
    setActiveNav(data.target === "scheduled" ? "section-schedule" : "section-overview");
    resetAcceleratorViewport();
  } catch (error) {
    result.textContent = error.message;
  }
}

function openToolWindow(tool) {
  const workspace = workspaceForTool(tool);
  if (workspace) {
    state.activeTool = tool;
    state.activeWorkspace = workspace;
    document.body.classList.remove("tool-mode");
    const backdrop = document.querySelector("#toolBackdrop");
    const windowEl = document.querySelector("#sideToolWindow");
    if (backdrop) backdrop.hidden = true;
    if (windowEl) {
      windowEl.hidden = true;
      windowEl.dataset.tool = "";
    }
    setActiveTool(tool);
    renderActiveWorkspace();
    resetAcceleratorViewport();
    if (tool === "prospecting") loadProspecting();
    if (tool === "customer-news" && state.newsCustomer) loadCustomerNews(state.newsCustomer);
    return;
  }
  state.activeTool = tool;
  setActiveTool(tool);
  if (tool === "manual-todo") {
    renderManualTodoTool();
    return;
  }
  if (tool === "global-paths") {
    renderGlobalPathsTool();
    return;
  }
  if (tool === "prospecting") {
    renderProspectingTool(state.prospecting, !state.prospecting);
    loadProspecting();
    return;
  }
  if (tool === "customer-news") {
    const customer = state.newsCustomer || "";
    renderCustomerNewsTool(customer, customer ? state.intelCache[customer] : null, Boolean(customer && !state.intelCache[customer]));
    if (customer) loadCustomerNews(customer);
  }
}

function renderPerformanceStrip(payload) {
  const container = document.querySelector("#performanceStrip");
  if (!container) return;
  const snapshot = payload.fxiaoke_status || {};
  if (!snapshot.ok) {
    container.innerHTML = `
      <div class="performance-empty">
        <strong>销售经营快照暂时不可用</strong>
        <span>点击右上角“同步业绩快照”重新读取纷享销客。</span>
      </div>
    `;
    return;
  }

  const quarter = snapshot.quarter || {};
  const signedItems = snapshot.preview?.opportunities || [];
  const signedPreview = signedItems.slice(0, 3);
  const signedCount = signedItems.length;

  container.innerHTML = `
    <div class="performance-head">
      <div>
        <span>销售经营快照</span>
        <strong>${escapeHtml(quarter.period || "本季度")}</strong>
      </div>
      <button class="mini-action" type="button" data-jump-section="section-snapshot">${escapeHtml(snapshotSyncLabel(snapshot))}</button>
    </div>
    <div class="performance-kpis">
      <button class="performance-kpi primary" type="button" data-jump-section="section-snapshot">
        <span>达成率</span>
        <strong>${escapeHtml(quarter.attainment_rate || "--")}</strong>
      </button>
      <button class="performance-kpi" type="button" data-jump-section="section-snapshot">
        <span>本季度目标</span>
        <strong>${escapeHtml(quarter.target_amount || "待读取")}</strong>
      </button>
      <button class="performance-kpi" type="button" data-jump-section="section-snapshot">
        <span>已签约</span>
        <strong>${escapeHtml(quarter.achieved_amount || "待读取")}</strong>
      </button>
      <button class="performance-kpi" type="button" data-jump-section="section-snapshot">
        <span>差额</span>
        <strong>${escapeHtml(quarter.gap_amount || "待读取")}</strong>
      </button>
    </div>
    <div class="performance-signed">
      <div class="performance-signed-title">
        <strong>客户签约明细</strong>
        <span>${escapeHtml(signedCount)} 条</span>
      </div>
      <div class="performance-signed-list">
        ${signedPreview.length
          ? signedPreview.map((item) => {
            const key = registerContext("snapshot", item, workflowKey("snapshot", item.name, item.status));
            return `
              <button class="performance-signed-item" type="button" data-customer="${escapeHtml(item.name)}" data-context-key="${escapeHtml(key)}">
                <strong>${escapeHtml(item.name)}</strong>
                <span>${escapeHtml(item.status)}</span>
              </button>
            `;
          }).join("")
          : '<div class="performance-signed-empty">暂无客户签约明细</div>'}
      </div>
    </div>
  `;
}

function renderSchedulePreview(payload) {
  const container = document.querySelector("#schedulePreview");
  if (!container) return;
  const todos = payload.risk_todos || [];
  const calendarStatus = payload.calendar_status || {};
  const topItems = todos.slice(0, 3);
  const statusLine = calendarStatus.fetched_at
    ? String(calendarStatus.fetched_at).replace("T", " ").replace("+08:00", "")
    : calendarStatus.label || "待同步";

  container.innerHTML = `
    <div class="schedule-preview-meta">
      <strong>${escapeHtml(todos.length)} 条</strong>
      <span>飞书 ${escapeHtml(calendarStatus.feishu_count || 0)} / deadline ${escapeHtml(calendarStatus.deadline_count || 0)} / 待匹配 ${escapeHtml(calendarStatus.unmatched_count || 0)}</span>
      <p>${escapeHtml(statusLine)}</p>
    </div>
    <div class="schedule-preview-list">
      ${topItems.length ? topItems.map((item) => {
        const key = registerContext("schedule", item, scheduleWorkflowKey(item));
        const customer = item.customer || "待匹配事项";
        const title = item.title || item.next_step || "待跟进";
        return `
          <button class="schedule-preview-card" type="button" data-customer="${escapeHtml(customer)}" data-context-key="${escapeHtml(key)}">
            <span>${escapeHtml(item.countdown_label || item.time_label || "待安排")}</span>
            <strong>${escapeHtml(title.includes(customer) ? title : `${customer} · ${title}`)}</strong>
          </button>
        `;
      }).join("") : '<div class="focus-empty">当前没有日程或 deadline。</div>'}
    </div>
    <button class="mini-action" type="button" data-jump-section="section-schedule">查看全部日程</button>
  `;
}

function renderSalesFlowSummary(payload = {}) {
  const container = document.querySelector("#salesFlowSummary");
  if (!container) return;
  const actions = payload.battle_actions || [];
  const todos = payload.risk_todos || [];
  const followupTodos = todos.filter((item) => isCustomerFollowupSchedule(item));
  const deals = payload.deal_board || [];
  const quarter = payload.fxiaoke_status?.quarter || {};
  const nowCount = currentActionCount(payload);
  const overdueCount = actions.filter((item) => item.schedule_bucket === "overdue").length
    || followupTodos.filter((item) => item.schedule_bucket === "overdue").length;
  const arrangedCount = followupTodos.filter((item) => ["week", "later", "unscheduled"].includes(item.schedule_bucket)).length;
  const activeCount = deals.filter((item) => item.bucket === "active").length;
  const potentialCount = deals.filter((item) => item.bucket === "potential").length;
  const cards = [
    {
      label: "今日事项",
      value: nowCount,
      note: overdueCount ? `${overdueCount} 条已超期` : "按优先级排序",
      section: "section-actions",
      tone: overdueCount ? "danger" : "primary",
    },
    {
      label: "等待 / 已安排",
      value: arrangedCount,
      note: "在 Deadline 到点后回首页",
      section: "section-schedule",
      tone: "teal",
    },
    {
      label: "活跃客户",
      value: activeCount,
      note: "已列明并真实推进",
      section: "section-actions",
      tone: "amber",
    },
    {
      label: "观察池",
      value: potentialCount,
      note: "未正式接触，不抢今日节奏",
      section: "section-actions",
      tone: "muted",
    },
    {
      label: "季度缺口",
      value: quarter.gap_amount || "--",
      note: `达成率 ${quarter.attainment_rate || "--"}`,
      section: "section-snapshot",
      tone: "primary",
    },
  ];

  container.innerHTML = cards.map((card) => `
    <button class="sales-flow-chip ${escapeHtml(card.tone)}" type="button" data-jump-section="${escapeHtml(card.section)}">
      <span>${escapeHtml(card.label)}</span>
      <strong>${escapeHtml(card.value)}</strong>
      <em>${escapeHtml(card.note)}</em>
    </button>
  `).join("");
}

function actionQueueGroup(item = {}, key = "") {
  if (item.context_type === "schedule") {
    const status = workflowRecord("schedule_status", key)?.status || item.status || "";
    if (item.schedule_bucket === "overdue") {
      return { id: "overdue", title: "超时", note: "已经过了回到你手上的时间，需要重新处理或改期" };
    }
    if (!isScheduleDueForAction(item)) {
      return { id: "todo", title: "继续跟进", note: "已经有状态和下一次时间，到点后再回到未处理" };
    }
    return { id: "focus", title: "未处理", note: "今天真正需要推进或回填的客户事项" };
  }
  const status = workflowRecord("action_status", key)?.status || "";
  if (/待客户反馈|待内部支持|内部支持|推进中|继续推进/.test(status)) {
    return { id: "todo", title: "继续跟进", note: "已经有状态和下一次时间，到点后再回到未处理" };
  }
  if (item.priority === "P0" || item.priority === "P1") {
    return { id: "focus", title: "未处理", note: "今天真正需要推进或回填的客户事项" };
  }
  return null;
}

function scheduleActionStatusLabel(status = "") {
  if (/已转动作|已转日程/.test(status)) return "待提交跟进结果";
  return status;
}

function flowGroupRank(id = "") {
  return {
    focus: 1,
    todo: 2,
    feedback: 3,
    overdue: 4,
  }[id] || 9;
}

function queueGroupTemplates() {
  return [
    {
      id: "focus",
      title: "未处理",
      note: "今天真正需要推进或回填的客户事项",
      empty: "当前没有必须立即推进的客户事项。",
    },
    {
      id: "todo",
      title: "继续跟进",
      note: "已经安排下一次时间，到点后再回到未处理",
      empty: "暂时没有等待下一次触发的客户 Deadline。",
    },
    {
      id: "feedback",
      title: "已处理",
      note: "最近已经回填的处理结果，用来确认本轮承接",
      empty: "暂时没有需要复看的回填反馈。",
    },
    {
      id: "overdue",
      title: "超时",
      note: "已经过了回到你手上的时间，需要重新处理或改期",
      empty: "没有超时任务。",
    },
  ];
}

function flowRowDueLabel(item = {}, contextType = "action") {
  if (contextType === "feedback") {
    return item.submitted_at ? String(item.submitted_at).replace("T", " ").replace("+08:00", "") : "已回填";
  }
  if (contextType === "schedule") {
    return item.countdown_label || item.time_label || "已安排";
  }
  if (item.deadline) return String(item.deadline).replace("T", " ").replace("+08:00", "");
  return item.stage || item.priority || "待推进";
}

function flowRowTitle(item = {}, contextType = "action") {
  if (contextType === "feedback") return item.title || item.next_step || "已处理记录";
  if (contextType === "schedule") return item.title || item.next_step || item.action || "待跟进";
  return item.action || item.next_action || item.task || item.title || "待推进";
}

function flowRowSignal(item = {}, status = "") {
  return item.resolution || item.latest_receipt?.resolution || item.risk || item.signal || item.evidence || status || "暂无风险说明";
}

function flowRowStage(item = {}, contextType = "action", status = "") {
  if (contextType === "feedback") return status || item.status || "已回填";
  if (contextType === "schedule") return status || item.status || "日程回填";
  if (/待客户反馈/.test(status)) return "等待客户";
  if (/待内部支持|内部支持/.test(status)) return "等内部";
  if (/推进中|继续推进/.test(status)) return "推进中";
  return item.stage || status || "待处理";
}

function pushQueueGroupItem(groups, group, entry) {
  let bucket = groups.find((groupItem) => groupItem.id === group.id);
  if (!bucket) {
    bucket = { ...group, items: [] };
    groups.push(bucket);
  }
  bucket.items.push(entry);
}

function isFeishuSchedule(item = {}) {
  return item.source_type === "feishu_calendar" || item.source_scope === "feishu_calendar";
}

function isCustomerFollowupSchedule(item = {}) {
  return !isFeishuSchedule(item) && item.customer !== "待匹配日程";
}

function homepageScheduleRank(item = {}) {
  const source = item.source_type || item.source_scope || "";
  if (source === "workflow_receipt") return 0;
  if (source === "workbench" || source === "knowledge") return 1;
  if (source === "transcript_intake") return 2;
  return 1;
}

function appendFutureScheduleGroups(groups, usedKeys) {
  const todos = state.dashboard?.risk_todos || [];
  const futureItems = todos
    .filter((item) => isCustomerFollowupSchedule(item))
    .filter((item) => !isScheduleDueForAction(item))
    .sort((left, right) => (
      homepageScheduleRank(left) - homepageScheduleRank(right)
      || parseTime(left.deadline || "") - parseTime(right.deadline || "")
    ))
    .map((item) => {
      const scheduleItem = { ...item, context_type: "schedule" };
      const key = registerContext("schedule", scheduleItem, scheduleWorkflowKey(scheduleItem));
      if (usedKeys.has(key)) return null;
      const recordStatus = workflowRecord("schedule_status", key)?.status || scheduleItem.status || "已安排";
      return { item: scheduleItem, key, status: scheduleActionStatusLabel(recordStatus), contextType: "schedule" };
    })
    .filter(Boolean)
    .slice(0, 6);
  if (!futureItems.length) return;
  futureItems.forEach((entry) => {
    usedKeys.add(entry.key);
    pushQueueGroupItem(groups, actionQueueGroup(entry.item, entry.key), entry);
  });
}

function recentFeedbackItems(usedKeys) {
  const activeSchedules = (state.dashboard?.risk_todos || [])
    .filter((item) => isCustomerFollowupSchedule(item))
    .map((item) => ({ ...item, context_type: "schedule" }));
  const activeTodoIds = new Set(
    activeSchedules
      .map((item) => String(item.id || item.todo_id || ""))
      .filter(Boolean),
  );
  return (workflowState().receipts || [])
    .filter((receipt) => receipt && receipt.customer && receipt.title)
    .filter((receipt) => {
      const todoId = String(receipt.todo?.id || "");
      if (todoId && activeTodoIds.has(todoId)) return false;
      const receiptSchedule = {
        id: todoId,
        customer: receipt.customer,
        title: receipt.title,
        next_step: receipt.next_step || receipt.todo?.next_step || "",
        action: receipt.title,
        deadline: receipt.todo?.deadline || receipt.deadline || "",
      };
      return !activeSchedules.some((active) => similarScheduleItems(active, receiptSchedule));
    })
    .sort((left, right) => parseTime(right.submitted_at || "") - parseTime(left.submitted_at || ""))
    .slice(0, 8)
    .map((receipt) => {
      const item = {
        customer: receipt.customer,
        title: receipt.title,
        status: receipt.status || "已回填",
        resolution: receipt.resolution || "",
        next_step: receipt.next_step || receipt.todo?.next_step || "",
        deadline: receipt.todo?.deadline || receipt.deadline || "",
        submitted_at: receipt.submitted_at || "",
        relative_path: receipt.relative_path || "",
        context_type: "feedback",
      };
      const key = registerContext("feedback", item, workflowKey("feedback", receipt.customer, receipt.title, receipt.submitted_at || ""));
      if (usedKeys.has(key)) return null;
      return { item, key, status: item.status, contextType: "feedback" };
    })
    .filter(Boolean);
}

function appendRecentFeedbackGroup(groups, usedKeys) {
  recentFeedbackItems(usedKeys).forEach((entry) => {
    usedKeys.add(entry.key);
    pushQueueGroupItem(groups, {
      id: "feedback",
      title: "已处理",
      note: "最近已经回填的事项，确认本轮处理结果和下一次承接",
    }, entry);
  });
}

function renderPriorityList(actions = []) {
  const container = document.querySelector("#priorityList");
  const groups = [];
  const usedKeys = new Set();
  actions.forEach((item) => {
      const contextType = item.context_type || "action";
      const key = registerContext(contextType, item, contextType === "schedule" ? scheduleWorkflowKey(item) : actionWorkflowKey(item));
      usedKeys.add(key);
      const rawStatus = contextType === "schedule"
        ? workflowRecord("schedule_status", key)?.status || item.status || item.countdown_label || "待跟进"
        : workflowRecord("action_status", key)?.status || "待处理";
      const status = contextType === "schedule" ? scheduleActionStatusLabel(rawStatus) : rawStatus;
      const group = actionQueueGroup(item, key);
      if (group) {
        pushQueueGroupItem(groups, group, { item, key, status, contextType });
      }
  });
  appendFutureScheduleGroups(groups, usedKeys);
  appendRecentFeedbackGroup(groups, usedKeys);
  groups.sort((left, right) => flowGroupRank(left.id) - flowGroupRank(right.id));
  const orderedGroups = queueGroupTemplates().map((template) => {
    const group = groups.find((groupItem) => groupItem.id === template.id);
    return group ? { ...template, ...group } : { ...template, items: [] };
  });
  state.flowGroups = orderedGroups;

  if (!orderedGroups.some((group) => group.items.length)) {
    container.innerHTML = '<div class="focus-empty">当前没有到点或超期的客户事项；未闭环事项会在 Deadline 到点后回到这里。</div>';
    return;
  }

  container.innerHTML = orderedGroups.map((group) => `
    <section class="queue-group queue-${escapeHtml(group.id)}">
      <div class="queue-group-head">
        <div>
          <strong>${escapeHtml(group.title)}</strong>
          <span>${escapeHtml(group.note)}</span>
        </div>
        <em>${group.items.length}</em>
      </div>
      <div class="queue-group-list">
        ${group.items.length ? group.items.map(({ item, key, status, contextType }) => `
      <button class="priority-card sales-flow-row ${state.activeContextKey === key ? "is-selected" : ""}" type="button" data-customer="${escapeHtml(item.customer)}" data-context-key="${escapeHtml(key)}">
        <div class="flow-row-main">
          <div>
            <h3>${escapeHtml(item.customer || "待匹配客户")}</h3>
            <p>${escapeHtml(flowRowTitle(item, contextType))}</p>
          </div>
        </div>
        <div class="flow-row-state">
          <span class="queue-priority ${escapeHtml(priorityClass(item.priority || (contextType === "feedback" ? "done" : "")))}">${escapeHtml(item.priority || (contextType === "schedule" ? "日程" : contextType === "feedback" ? "反馈" : "P2"))}</span>
          <span>${escapeHtml(flowRowStage(item, contextType, status))}</span>
          <strong>${escapeHtml(flowRowDueLabel(item, contextType))}</strong>
        </div>
        <div class="flow-row-risk">${escapeHtml(flowRowSignal(item, status))}</div>
        <div class="flow-row-cta">
          <span>${contextType === "feedback" ? "查看回填" : contextType === "schedule" ? "回填日程结果" : "推进客户状态"}</span>
        </div>
      </button>
        `).join("") : `<div class="queue-empty">${escapeHtml(group.empty || "当前没有事项")}</div>`}
      </div>
    </section>
  `).join("");
}

function acceleratorFilterForGroup(groupId = "") {
  if (groupId === "focus") return "todo";
  if (groupId === "feedback") return "feedback";
  if (groupId === "overdue") return "overdue";
  return "followup";
}

function acceleratorEntries() {
  return (state.flowGroups || []).flatMap((group) => (group.items || []).map((entry) => ({
    ...entry,
    groupId: group.id,
    groupTitle: group.title,
    filter: acceleratorFilterForGroup(group.id),
  })));
}

function acceleratorScore(entry = {}) {
  const item = entry.item || {};
  if (entry.groupId === "overdue") return 88;
  if (entry.groupId === "focus") return item.priority === "P0" ? 86 : item.priority === "P1" ? 78 : 72;
  if (entry.groupId === "todo") return item.priority === "P0" ? 76 : item.priority === "P1" ? 70 : 64;
  if (entry.groupId === "feedback") return /已处理|已闭环/.test(entry.status || item.status || "") ? 72 : 66;
  return 62;
}

function acceleratorScoreGrade(score = 0) {
  if (score >= 80) return "A级";
  if (score >= 70) return "B级";
  if (score >= 60) return "C级";
  return "D级";
}

function acceleratorScoreParts(score = 0, entry = {}) {
  const urgency = Math.min(30, Math.max(12, Math.round(score * 0.34)));
  const closure = Math.min(25, Math.max(10, Math.round(score * 0.27)));
  const value = Math.min(20, Math.max(8, Math.round(score * 0.20)));
  const risk = Math.min(15, Math.max(5, entry.groupId === "overdue" ? 13 : Math.round(score * 0.11)));
  const info = Math.max(4, Math.min(10, score - urgency - closure - value - risk));
  return { urgency, closure, value, risk, info };
}

function acceleratorEntryByKey(key = "") {
  return acceleratorEntries().find((entry) => entry.key === key) || null;
}

function acceleratorActiveEntry() {
  return state.activeContextKey ? acceleratorEntryByKey(state.activeContextKey) : null;
}

function acceleratorFilterLabel(filter = "todo") {
  return {
    todo: "未处理",
    feedback: "已处理",
    followup: "继续跟进",
    overdue: "超时",
  }[filter] || "未处理";
}

function acceleratorSourceLabel(context, entry) {
  if (!context) return "今日行动";
  const item = context.item || entry?.item || {};
  if (context.type === "schedule" && (item.source_type === "transcript_intake" || item.source_scope === "transcript_intake")) return "录音/TXT提取";
  if (context.type === "schedule") return "下次提醒";
  if (context.type === "feedback") return "处理记录";
  if (context.type === "risk") return "风险雷达";
  return contextSourceLabel(context);
}

function acceleratorContextCustomer(context, entry) {
  const item = context?.item || entry?.item || {};
  const name = item.customer || item.name || state.selectedCustomer || "";
  if (!name && !context && !entry) return null;
  return findCustomer(name)
    || fallbackCustomerFromContext(name || "待匹配事项", context || { type: entry?.contextType || "action", item });
}

function acceleratorLoopState(context, customer, entry) {
  const item = context?.item || entry?.item || {};
  const customerName = customer?.name || item.customer || item.name || "";
  const status = contextStatus(context);
  const receipt = latestReceiptForContext(context, customer);
  const deadline = item.deadline || receipt?.todo?.deadline || receipt?.deadline || "";
  const isCarryover = isFollowupCarryover(context, entry, receipt);
  const hasReceipt = receiptIsDisplayable(receipt);
  const isClosed = /已处理|已闭环/.test(`${status} ${receipt?.status || ""}`);
  const hasClosedReceipt = /已处理|已闭环/.test(String(receipt?.status || ""));
  const isReadonly = ["pm_item", "snapshot", "route"].includes(context?.type || "");
  const canSubmit = contextCanSubmitEvidence(context);
  const hasRoute = routeGroupsForScope(customerName, 1).length > 0;
  const hasDeadline = Boolean(deadline);
  const deadlineTime = parseTime(deadline);
  const isDeadlineDue = hasDeadline && deadlineTime > 0 && deadlineTime <= Date.now();
  const isWaiting = !isClosed && (
    hasDeadline
    || /待客户反馈|待内部支持|推进中|待跟进/.test(status)
    || entry?.filter === "followup"
  );
  const isCurrent = canSubmit && !isClosed && (!hasReceipt || isDeadlineDue || entry?.filter === "overdue" || entry?.filter === "todo");
  return { status, receipt, deadline, hasReceipt, hasClosedReceipt, isClosed, isReadonly, canSubmit, hasRoute, hasDeadline, isDeadlineDue, isWaiting, isCurrent };
}

function acceleratorStepClass(stateName = "pending") {
  return `is-${stateName}`;
}

function acceleratorProcessStepHtml(step = {}) {
  return `
    <div class="accelerator-process-pill ${acceleratorStepClass(step.state)}">
      <em>${escapeHtml(step.icon || "")}</em>
      <span>
        <strong>${escapeHtml(step.title || "")}</strong>
        <small>${escapeHtml(step.detail || "")}</small>
      </span>
    </div>
  `;
}

function acceleratorProcessHtml(context, entry) {
  const customer = acceleratorContextCustomer(context, entry);
  const loop = acceleratorLoopState(context, customer, entry);
  const source = acceleratorSourceLabel(context, entry);
  const deadlineLabel = loop.deadline ? displayDateTime(loop.deadline) : "未生成";
  const actionDetail = loop.isClosed
    ? "已闭环"
    : loop.isCurrent
      ? "现在处理"
      : loop.isReadonly
        ? "只读查看"
        : loop.isWaiting
          ? (loop.isDeadlineDue ? "已到点" : "等待下次")
          : loop.status || "待处理";
  const receiptDetail = loop.isClosed
    ? "已闭环"
    : loop.hasClosedReceipt
      ? "已闭环"
      : loop.hasReceipt
        ? `已回填 · ${loop.receipt?.status || "未闭环"}`
        : loop.canSubmit
          ? "待提交"
          : "无提交动作";
  const nextDetail = loop.isClosed
    ? "已移出待处理"
    : loop.isDeadlineDue
      ? `已到点 · ${deadlineLabel}`
      : loop.hasDeadline
        ? `已安排 · ${deadlineLabel}`
        : "未生成";
  const currentActionState = loop.isClosed
    ? "done"
    : loop.isCurrent
      ? "active"
      : loop.isReadonly
        ? "readonly"
        : loop.isWaiting
          ? "waiting"
          : "pending";
  const receiptState = loop.isClosed || loop.hasClosedReceipt
    ? "done"
    : loop.hasReceipt
      ? "waiting"
    : loop.canSubmit
      ? "pending"
      : "readonly";
  const nextState = loop.isClosed
    ? "done"
    : loop.hasDeadline
      ? "waiting"
      : "pending";
  const steps = [
    {
      icon: "源",
      title: "来源信号",
      detail: source,
      state: context ? "readonly" : "pending",
    },
    {
      icon: "办",
      title: "当前动作",
      detail: actionDetail,
      state: currentActionState,
    },
    {
      icon: "记",
      title: "处理回执",
      detail: receiptDetail,
      state: receiptState,
    },
    {
      icon: "时",
      title: "下次承接",
      detail: nextDetail,
      state: nextState,
    },
    {
      icon: "图",
      title: "客户背景",
      detail: loop.hasRoute ? "经营地图只读" : "待沉淀",
      state: loop.hasRoute ? "readonly" : "pending",
    },
  ];
  return steps.map(acceleratorProcessStepHtml).join("");
}

function acceleratorIdleProcessHtml() {
  return [
    { icon: "1", title: "先选事项", detail: "左侧今日队列", state: "pending" },
    { icon: "2", title: "进入作战室", detail: "只承接一个客户", state: "pending" },
    { icon: "3", title: "提交回执", detail: "闭环或继续推进", state: "pending" },
    { icon: "4", title: "下次承接", detail: "未闭环进 Deadline", state: "pending" },
    { icon: "5", title: "客户背景", detail: "经营地图只读", state: "pending" },
  ].map(acceleratorProcessStepHtml).join("");
}

function acceleratorCapsuleHtml(id, icon, title, sub, status, active, tone = "neutral") {
  return `
    <button class="accelerator-capsule is-state-${escapeHtml(tone)} ${active ? "is-active" : ""}" type="button" data-accelerator-pane="${escapeHtml(id)}">
      <span class="accelerator-avatar">${escapeHtml(icon)}</span>
      <span><strong>${escapeHtml(title)}</strong><small>${escapeHtml(sub)}</small></span>
      <span class="accelerator-capsule-status">${escapeHtml(status)}</span>
    </button>
    <div class="accelerator-drop ${active ? "is-open" : ""}">
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(sub)}</p>
    </div>
  `;
}

function acceleratorCapsulesHtml(context, customer, entry) {
  return "";
}

function acceleratorMicroRow(label, value) {
  return `<div class="micro-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value || "-")}</strong></div>`;
}

function routeRecordText(record = {}) {
  return record.full_summary || record.summary || record.preview || record.actions?.[0] || record.risks?.[0] || record.signals?.[0] || "暂无完整内容";
}

function routeFullTextHtml(text = "") {
  const value = String(text || "").trim();
  if (!value) return "";
  return `<div class="accelerator-route-fulltext">${escapeHtml(value)}</div>`;
}

function routeRecordSource(record = {}) {
  return [
    record.type || "知识库记录",
    record.updated_at || "",
    record.path ? `知识库/${record.path}` : record.source_note || "",
  ].filter(Boolean).join(" · ");
}

function knowledgeDirectionKey(record = {}) {
  const title = record.knowledge_direction_title || record.knowledge_direction || "";
  if (!title) return "";
  return [
    normalizeKnowledgeKey(title),
    String(record.updated_at || "").slice(0, 10),
    normalizeKnowledgeKey(record.knowledge_index_path || ""),
  ].filter(Boolean).join("|");
}

function knowledgeUnits(history = []) {
  const directionGroups = new Map();
  const singles = [];
  history.forEach((record) => {
    const key = knowledgeDirectionKey(record);
    if (!key) {
      singles.push({ kind: "record", record, sort: parseTime(record.updated_at) });
      return;
    }
    if (!directionGroups.has(key)) {
      directionGroups.set(key, {
        kind: "direction",
        records: [],
        title: record.knowledge_direction_title || record.knowledge_direction || record.project || "同方向沟通",
        summary: record.knowledge_direction_summary || "",
        indexPath: record.knowledge_index_path || "",
        sort: 0,
      });
    }
    const unit = directionGroups.get(key);
    unit.records.push(record);
    unit.sort = Math.max(unit.sort, parseTime(record.updated_at));
    if (!unit.summary && record.knowledge_direction_summary) unit.summary = record.knowledge_direction_summary;
  });
  const units = [...singles];
  directionGroups.forEach((unit) => {
    if (unit.records.length <= 1) {
      units.push({ kind: "record", record: unit.records[0], sort: unit.sort });
      return;
    }
    unit.records.sort((a, b) => parseTime(b.updated_at) - parseTime(a.updated_at));
    units.push(unit);
  });
  return units.sort((left, right) => (right.sort || 0) - (left.sort || 0));
}

function knowledgeTopicRecordHtml(record = {}) {
  const title = record.knowledge_topic || record.title || record.raw_title || "未命名沟通";
  const action = (record.actions || []).filter(Boolean)[0];
  return `
    <article class="knowledge-topic-record">
      <div>
        <span>${escapeHtml(record.updated_at || "暂无时间")}</span>
        <strong>${escapeHtml(title)}</strong>
      </div>
      ${routeFullTextHtml(routeRecordText(record))}
      ${action ? `<div class="knowledge-topic-action"><span>建议动作</span><p>${escapeHtml(action)}</p></div>` : ""}
      <small>${escapeHtml(routeRecordSource(record))}</small>
    </article>
  `;
}

function knowledgeDirectionHtml(unit = {}) {
  return `
    <article class="knowledge-direction-group">
      <div class="knowledge-direction-head">
        <span>同方向沟通</span>
        <strong>${escapeHtml(unit.title || "业务方向")}</strong>
        <em>${unit.records?.length || 0} 个主题</em>
      </div>
      ${routeFullTextHtml(unit.summary || "这些沟通同属一个客户方向，但对应不同子议题，应按主题包拆开阅读。")}
      <div class="knowledge-topic-list">
        ${(unit.records || []).map(knowledgeTopicRecordHtml).join("")}
      </div>
      ${unit.indexPath ? `<small class="knowledge-index-source">索引：知识库/${escapeHtml(unit.indexPath)}</small>` : ""}
    </article>
  `;
}

function knowledgeUnitsHtml(history = []) {
  return knowledgeUnits(history).map((unit) => (
    unit.kind === "direction" ? knowledgeDirectionHtml(unit) : acceleratorRouteRecordHtml(unit.record)
  )).join("");
}

function globalKnowledgeUnitsHtml(history = []) {
  return knowledgeUnits(history).map((unit) => (
    unit.kind === "direction" ? knowledgeDirectionHtml(unit) : globalPathRecordHtml(unit.record)
  )).join("");
}

function routeFullLines(title, lines = []) {
  const cleanLines = (lines || []).filter(Boolean);
  if (!cleanLines.length) return "";
  return `
    <div class="accelerator-route-lines">
      <span>${escapeHtml(title)}</span>
      ${cleanLines.map((line) => `<p>${escapeHtml(line)}</p>`).join("")}
    </div>
  `;
}

function acceleratorRouteRecordHtml(record = {}) {
  const title = record.title || record.raw_title || record.type || "未命名记录";
  const signals = record.signals || [];
  const risks = record.risks || [];
  const actions = record.actions || [];
  return `
    <div class="accelerator-route-record">
      <div class="accelerator-route-record-head">
        <span>${escapeHtml(record.type || "知识库记录")}</span>
        <strong>${escapeHtml(title)}</strong>
        <em>${escapeHtml(record.updated_at || "暂无时间")}</em>
      </div>
      ${routeFullTextHtml(routeRecordText(record))}
      <div class="accelerator-route-record-grid">
        ${routeFullLines("行动", actions)}
        ${routeFullLines("风险", risks)}
        ${routeFullLines("信号", signals)}
      </div>
      <small>${escapeHtml(routeRecordSource(record))}</small>
    </div>
  `;
}

function acceleratorRouteGroupHtml(group = {}, index = 0) {
  const history = group.history || [];
  const latest = history[0] || {};
  return `
    <section class="accelerator-route-group ${index === 0 ? "is-primary" : ""}">
      <div class="accelerator-route-group-head">
        <span>知识沉淀</span>
        <strong>${escapeHtml(group.project || "未归类")}</strong>
        <em>${history.length} 条</em>
      </div>
      <p>${escapeHtml(projectSummary(group))}</p>
      <div class="micro-list">
        ${acceleratorMicroRow("最近节点", latest.updated_at || "暂无时间")}
        ${acceleratorMicroRow("当前判断", projectStatus(group))}
      </div>
      <div class="accelerator-route-record-list">
        ${knowledgeUnitsHtml(history)}
      </div>
    </section>
  `;
}

function workflowLineKey(line = {}) {
  return [
    line.kind || "",
    normalizeKnowledgeKey(line.title || ""),
    normalizeKnowledgeKey(line.time || ""),
  ].join("|");
}

function pushWorkflowLine(lines, line) {
  if (!line?.title) return;
  const key = workflowLineKey(line);
  if (lines.some((item) => workflowLineKey(item) === key)) return;
  lines.push(line);
}

function customerReceipts(customerName = "") {
  return (workflowState().receipts || [])
    .filter((receipt) => receipt?.customer && customerMatchText(customerName, receipt.customer))
    .sort((left, right) => parseTime(right.submitted_at || "") - parseTime(left.submitted_at || ""));
}

function workflowReceiptLine(receipt = {}, label = "反馈链") {
  const nextDeadline = receipt.todo?.deadline || receipt.deadline || "";
  const submittedAt = displayDateTime(receipt.submitted_at || "");
  return {
    kind: "receipt",
    tone: /已闭环|已处理/.test(receipt.status || "") ? "done" : "waiting",
    label,
    title: receipt.title || receipt.next_step || "处理回执",
    summary: receipt.resolution || receipt.result || receipt.next_step || "处理结果已记录",
    status: receipt.status || "已回填",
    time: nextDeadline ? `下次 ${displayDateTime(nextDeadline)}` : submittedAt,
  };
}

function workflowScheduleLine(schedule = {}) {
  const key = scheduleWorkflowKey(schedule);
  const status = workflowRecord("schedule_status", key)?.status || schedule.status || schedule.countdown_label || "已安排";
  return {
    kind: "schedule",
    tone: schedule.schedule_bucket === "overdue" ? "overdue" : "waiting",
    label: schedule.schedule_bucket === "overdue" ? "超时提醒" : "下次提醒",
    title: schedule.title || schedule.next_step || schedule.action || "待跟进",
    summary: schedule.next_step || schedule.action || schedule.evidence || "等待到点后回到今日队列",
    status: scheduleActionStatusLabel(status),
    time: schedule.deadline ? displayDateTime(schedule.deadline) : schedule.countdown_label || schedule.time_label || "",
  };
}

function customerWorkflowLines(context, customer, entry) {
  const item = context?.item || entry?.item || {};
  const customerName = customer?.name || item.customer || item.name || "";
  const lines = [];
  if (context && !["route", "pm_item", "snapshot"].includes(context.type)) {
    const currentType = entry?.filter === "feedback" || context.type === "feedback" ? "已处理记录" : "当前推进";
    pushWorkflowLine(lines, {
      kind: "current",
      tone: entry?.filter === "overdue" ? "overdue" : entry?.filter === "feedback" ? "done" : "current",
      label: currentType,
      title: contextTitle(context, customer),
      summary: contextEvidence(context, customer) || contextAction(context, customer) || "当前选中事项",
      status: contextStatus(context),
      time: flowRowDueLabel(item, entry?.contextType || context.type || "action"),
    });
  }
  const receipt = latestReceiptForContext(context, customer);
  if (receiptIsDisplayable(receipt)) {
    pushWorkflowLine(lines, workflowReceiptLine(receipt, "最近回执"));
  }
  const currentScheduleKey = context?.type === "schedule" ? scheduleWorkflowKey(item) : "";
  focusSchedules(customerName).filter((schedule) => scheduleWorkflowKey(schedule) !== currentScheduleKey).slice(0, 4).forEach((schedule) => {
    pushWorkflowLine(lines, workflowScheduleLine(schedule));
  });
  const latestReceiptTitle = receiptIsDisplayable(receipt) ? normalizeKnowledgeKey(receipt.title || receipt.next_step || "") : "";
  customerReceipts(customerName)
    .filter((receiptItem) => !latestReceiptTitle || normalizeKnowledgeKey(receiptItem.title || receiptItem.next_step || "") !== latestReceiptTitle)
    .slice(0, 5)
    .forEach((receiptItem) => {
    pushWorkflowLine(lines, workflowReceiptLine(receiptItem, "历史回执"));
  });
  return lines;
}

function acceleratorWorkflowLineHtml(line = {}) {
  return `
    <article class="accelerator-workflow-line is-${escapeHtml(line.tone || "neutral")}">
      <div class="accelerator-workflow-line-head">
        <span>${escapeHtml(line.label || "推进节点")}</span>
        <em>${escapeHtml(line.status || "待确认")}</em>
      </div>
      <strong>${escapeHtml(line.title || "未命名事项")}</strong>
      <p>${escapeHtml(compactText(line.summary || "", 128))}</p>
      ${line.time ? `<small>${escapeHtml(line.time)}</small>` : ""}
    </article>
  `;
}

function acceleratorWorkflowLaneHtml(lines = [], customerName = "") {
  return `
    <section class="accelerator-path-lane accelerator-path-workline">
      <div class="accelerator-path-lane-head">
        <span>工作推进线</span>
        <strong>${escapeHtml(customerName || "当前客户")}</strong>
        <em>${lines.length} 条</em>
      </div>
      <div class="accelerator-workflow-list">
        ${lines.length ? lines.map(acceleratorWorkflowLineHtml).join("") : '<div class="accelerator-empty compact">当前没有推进记录。</div>'}
      </div>
    </section>
  `;
}

function acceleratorKnowledgeLaneHtml(groups = [], allGroups = [], customerName = "", total = 0) {
  return `
    <section class="accelerator-path-lane accelerator-path-knowledge">
      <div class="accelerator-path-lane-head">
        <span>知识沉淀线</span>
        <strong>${escapeHtml(customerName || "客户背景")}</strong>
        <em>${total} 条</em>
      </div>
      ${allGroups.length ? `
        <div class="accelerator-route-filter">
          <button class="${state.routeFilterProject ? "" : "is-active"}" type="button" data-route-filter-project="">全部</button>
          ${allGroups.map((group) => `
            <button class="${state.routeFilterProject === group.project ? "is-active" : ""}" type="button" data-route-filter-project="${escapeHtml(group.project)}">
              ${escapeHtml(group.project)} <span>${group.history?.length || 0}</span>
            </button>
          `).join("")}
        </div>
        <div class="accelerator-route-groups">
          ${groups.map(acceleratorRouteGroupHtml).join("")}
        </div>
      ` : '<div class="accelerator-empty compact">这个客户还没有知识沉淀。</div>'}
    </section>
  `;
}

function acceleratorProjectPathHtml(context, customer, entry) {
  const item = context?.item || entry?.item || {};
  const customerName = customer?.name || item.customer || item.name || "";
  const operatingMap = customerOperatingMap(customerName);
  const scopedGroups = routeGroupsForScope(customerName, 200);
  const allGroups = scopedGroups;
  if (state.routeFilterProject && !allGroups.some((group) => group.project === state.routeFilterProject)) {
    state.routeFilterProject = "";
  }
  const groups = state.routeFilterProject
    ? allGroups.filter((group) => group.project === state.routeFilterProject)
    : allGroups;
  const total = allGroups.reduce((sum, group) => sum + (group.history?.length || 0), 0);
  const workflowLines = customerWorkflowLines(context, customer, entry);

  return `
    <article class="accelerator-card accelerator-route-history accelerator-path-workspace">
      <div class="accelerator-route-title">
        <h4>客户经营地图</h4>
        <span>${escapeHtml(customerName)} · 推进 ${workflowLines.length} 条 / 沉淀 ${total} 条</span>
      </div>
      <div class="accelerator-operating-map">
        <section>
          <span>项目线</span>
          <strong>${escapeHtml((operatingMap?.project_lines || []).join(" / ") || customer?.stage || item.stage || "待补齐")}</strong>
        </section>
        <section>
          <span>预算 / 金额</span>
          <strong>${escapeHtml(operatingMap?.budget || customer?.amount || item.amount || "预算待确认")}</strong>
        </section>
        <section>
          <span>关键人</span>
          <strong>${escapeHtml(operatingMap?.key_people || customer?.owner || item.owner || "关键人待补齐")}</strong>
        </section>
        <section>
          <span>供应商 / 竞品路径</span>
          <strong>${escapeHtml(operatingMap?.supplier_path || "供应商/竞品路径待补齐")}</strong>
        </section>
        <section class="wide">
          <span>下一步打法</span>
          <strong>${escapeHtml(operatingMap?.next_play || customer?.next_action || item.next_action || "等待下一步动作")}</strong>
        </section>
        <section>
          <span>外部情报</span>
          <strong>${escapeHtml(`${operatingMap?.public_signal_count || 0} 条`)}</strong>
        </section>
      </div>
      <div class="accelerator-path-split">
        ${acceleratorWorkflowLaneHtml(workflowLines, customerName)}
        ${acceleratorKnowledgeLaneHtml(groups, allGroups, customerName, total)}
      </div>
    </article>
  `;
}

function renderAcceleratorEvidence(context, customer) {
  if (!contextCanSubmitEvidence(context)) {
    return `
      <article class="accelerator-card">
        <h4>这类内容不需要提交证据</h4>
        <p>已处理记录、项目群日报和经营快照只用于查看，不会在这里生成新的销售待办。</p>
      </article>
    `;
  }
  return `<article class="accelerator-card">${renderEvidenceForm(context, customer)}</article>`;
}

function isFollowupCarryover(context, entry, receipt) {
  if (!receiptIsDisplayable(receipt)) return false;
  const status = contextStatus(context);
  return entry?.filter === "followup"
    || context?.type === "schedule"
    || /推进中|继续推进|待客户反馈|待内部支持/.test(status);
}

function acceleratorSnapshotDetailHtml() {
  const snapshot = state.dashboard?.fxiaoke_status || {};
  if (!snapshot?.ok) {
    return `
      <article class="accelerator-card">
        <h4>业绩快照</h4>
        <p>经营快照暂时不可用。它只用于判断经营状态，不进入今日待办。</p>
      </article>
    `;
  }
  const quarter = snapshot.quarter || {};
  const preview = snapshot.preview || {};
  const signedItems = preview.opportunities || [];
  return `
    <article class="accelerator-card">
      <h4>业绩快照</h4>
      <p>这里是经营判断，不和今天待办混在一起。</p>
      <div class="micro-list">
        ${acceleratorMicroRow("达成率", quarter.attainment_rate || "--")}
        ${acceleratorMicroRow("本季度目标", quarter.target_amount || "待读取")}
        ${acceleratorMicroRow("已签约", quarter.achieved_amount || "待读取")}
        ${acceleratorMicroRow("差额", quarter.gap_amount || "待读取")}
        ${acceleratorMicroRow("同步状态", snapshotSyncLabel(snapshot))}
      </div>
    </article>
    <article class="accelerator-card">
      <h4>签约明细</h4>
      <div class="micro-list">
        ${signedItems.length ? signedItems.slice(0, 5).map((item) => acceleratorMicroRow(item.name || "客户", item.status || "已同步")).join("") : acceleratorMicroRow("当前", "没有可展示的签约明细")}
      </div>
    </article>
  `;
}

function inlinePricingValues() {
  return {
    actualDays: pricingInputs.actualDays?.value || "",
    internalCost: pricingInputs.internalCost?.value || "",
    quotedDays: pricingInputs.quotedDays?.value || "",
    billingRate: pricingInputs.billingRate?.value || "",
    targetMargin: pricingInputs.targetMargin?.value || "",
    selfCostEnabled: Boolean(pricingInputs.selfCostEnabled?.checked),
  };
}

function pricingNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : 0;
}

function computePricing(values = {}) {
  const actualDays = pricingNumber(values.actualDays);
  const internalCost = pricingNumber(values.internalCost);
  const quotedDays = pricingNumber(values.quotedDays);
  const billingRate = pricingNumber(values.billingRate);
  const targetRate = pricingNumber(values.targetMargin) / 100;
  const revenue = quotedDays * billingRate;
  const selfCost = values.selfCostEnabled ? revenue * 0.1 : 0;
  const internalTotal = actualDays * internalCost;
  const totalCost = selfCost + internalTotal;
  const grossProfit = revenue - totalCost;
  const marginRate = revenue > 0 ? grossProfit / revenue : 0;
  const passed = revenue > 0 && marginRate >= targetRate;
  return { revenue, selfCost, internalTotal, grossProfit, marginRate, targetRate, passed };
}

function pricingReportText(values = {}, model = computePricing(values)) {
  const actualDays = pricingNumber(values.actualDays);
  const internalCost = pricingNumber(values.internalCost);
  const quotedDays = pricingNumber(values.quotedDays);
  const billingRate = pricingNumber(values.billingRate);
  const selfCostLine = values.selfCostEnabled
    ? `同时按成交额 10% 计自成本 ${cny.format(model.selfCost)}`
    : "本次暂不计自成本";
  const marginJudgement = model.passed ? "达到当前底线，可以进入报备沟通" : "没有达到当前底线，建议先调整报价、范围或交付成本";
  return [
    "审批负责人，报备一下这个私有化/定制报价口径。",
    "",
    `1. 报价口径：按 ${quotedDays || 0} 人天、对客单价 ${cny.format(billingRate)} 计算，预计成交金额 ${cny.format(model.revenue)}。`,
    `2. 成本口径：实际评估 ${actualDays || 0} 人天，内部人天成本 ${cny.format(internalCost)}，内部成本 ${cny.format(model.internalTotal)}；${selfCostLine}。`,
    `3. 毛利结果：预计毛利 ${cny.format(model.grossProfit)}，毛利率 ${percent(model.marginRate)}，目标毛利率 ${percent(model.targetRate)}，${marginJudgement}。`,
    "4. 销售判断：客户如果继续压价，优先压范围或拆阶段，不建议直接降低对客人天单价，避免后续交付和毛利失控。",
    "5. 需要确认：是否按这个口径对外沟通；如果需要继续跟进报备结果，我会在工作台里单独做销售捕捉。",
  ].join("\n");
}

function pricingReportBlockHtml(values = {}, model = computePricing(values)) {
  return `
    <div class="pricing-report-box">
      <div class="pricing-report-head">
        <div>
          <strong>审批负责人报备话术</strong>
          <span>根据当前人天、成本和毛利自动生成；不自动进入待办。</span>
        </div>
        <button class="tool-mini-button" type="button" data-pricing-script-copy>复制话术</button>
      </div>
      <textarea class="pricing-report-output" readonly data-pricing-script-output>${escapeHtml(pricingReportText(values, model))}</textarea>
      <span class="pricing-copy-state" data-pricing-copy-state></span>
    </div>
  `;
}

function acceleratorPricingResultHtml(values = {}) {
  const model = computePricing(values);
  return `
    <div class="accelerator-pricing-result-grid">
      ${acceleratorMicroRow("成交金额", cny.format(model.revenue))}
      ${acceleratorMicroRow("自成本", cny.format(model.selfCost))}
      ${acceleratorMicroRow("内部成本", cny.format(model.internalTotal))}
      ${acceleratorMicroRow("毛利", cny.format(model.grossProfit))}
      ${acceleratorMicroRow("毛利率", percent(model.marginRate))}
      ${acceleratorMicroRow("目标毛利率", percent(model.targetRate))}
    </div>
    <p>${model.passed ? "已达目标" : "未达目标"}。当前毛利率 ${percent(model.marginRate)}，目标毛利率 ${percent(model.targetRate)}。${adviceForMargin(model.marginRate)}</p>
    ${pricingReportBlockHtml(values, model)}
  `;
}

function acceleratorPricingDetailHtml() {
  const values = inlinePricingValues();
  return `
    <article class="accelerator-card accelerator-pricing-card">
      <h4>私有化计算器</h4>
      <p>独立报价护栏，不绑定当前客户；需要时再从结果进入具体客户作战室。</p>
      <div class="accelerator-pricing-form">
        <label><span>实际人天</span><input type="number" min="0" data-inline-pricing="actualDays" value="${escapeHtml(values.actualDays)}" /></label>
        <label><span>内部人天成本</span><input type="number" min="0" data-inline-pricing="internalCost" value="${escapeHtml(values.internalCost)}" /></label>
        <label><span>报价天数</span><input type="number" min="0" data-inline-pricing="quotedDays" value="${escapeHtml(values.quotedDays)}" /></label>
        <label><span>对客单价</span><input type="number" min="0" data-inline-pricing="billingRate" value="${escapeHtml(values.billingRate)}" /></label>
        <label><span>目标毛利率</span><input type="number" min="0" data-inline-pricing="targetMargin" value="${escapeHtml(values.targetMargin)}" /></label>
        <label class="accelerator-pricing-toggle"><input type="checkbox" data-inline-pricing="selfCostEnabled" ${values.selfCostEnabled ? "checked" : ""} /><span>启用自成本 10%</span></label>
      </div>
      <div class="accelerator-pricing-result" data-inline-pricing-result>${acceleratorPricingResultHtml(values)}</div>
    </article>
  `;
}

function acceleratorDetailHtml(context, customer, entry) {
  const pane = state.acceleratorPane || "next";
  const item = context?.item || entry?.item || {};
  const title = contextTitle(context, customer);
  const action = contextAction(context, customer) || title;
  const evidence = contextEvidence(context, customer) || action;
  const status = contextStatus(context);
  const receipt = latestReceiptForContext(context, customer);
  const deadline = item.deadline || receipt?.todo?.deadline || receipt?.deadline || "";
  const isCarryover = isFollowupCarryover(context, entry, receipt);
  if (pane === "war") {
    return `
      <div class="accelerator-detail-grid">
        <article class="accelerator-card">
          <h4>当前这件事</h4>
          <div class="micro-list">
            ${acceleratorMicroRow("客户", customer?.name || item.customer || "未绑定客户")}
            ${acceleratorMicroRow("待完成", title)}
            ${acceleratorMicroRow("目标", action)}
            ${acceleratorMicroRow("依据", evidence)}
          </div>
        </article>
        <article class="accelerator-card">
          <h4>处理状态</h4>
          <div class="micro-list">
            ${acceleratorMicroRow("当前", status)}
            ${acceleratorMicroRow("处理后", "生成反馈链；未闭环进入 Deadline")}
            ${acceleratorMicroRow("下次", deadline ? displayDateTime(deadline) : "提交结果后确认")}
          </div>
        </article>
      </div>
    `;
  }
  if (pane === "path") {
    return acceleratorProjectPathHtml(context, customer, entry);
  }
  if (pane === "score") {
    const score = acceleratorScore(entry);
    const parts = acceleratorScoreParts(score, entry);
    return `
      <article class="accelerator-card">
        <h4>行动评分</h4>
        <div class="accelerator-detail-grid">
          <div class="accelerator-mini-card">
            <span class="accelerator-queue-score">${score}</span>
            <strong>${acceleratorScoreGrade(score)} · ${score >= 80 ? "今天先处理" : score >= 70 ? "今天跟进" : "观察推进"}</strong>
            <p>行动评分只用于今日排序，不自动生成新待办。</p>
          </div>
          <div class="micro-list">
            ${acceleratorMicroRow("推进紧迫", `${parts.urgency}/30`)}
            ${acceleratorMicroRow("闭环清晰", `${parts.closure}/25`)}
            ${acceleratorMicroRow("价值窗口", `${parts.value}/20`)}
            ${acceleratorMicroRow("风险压力", `${parts.risk}/15`)}
            ${acceleratorMicroRow("信息完整", `${parts.info}/10`)}
          </div>
        </div>
      </article>
    `;
  }
  if (pane === "timeline") {
    return `
      <article class="accelerator-card">
        <h4>反馈链</h4>
        ${renderReceiptSummary(receipt, "最新反馈链")}
        <div class="micro-list">
          ${acceleratorMicroRow("当前事项", title)}
          ${acceleratorMicroRow("处理状态", receipt?.status || "待提交处理结果")}
          ${acceleratorMicroRow("下一步", receipt?.next_step || action || "提交证据后确认")}
        </div>
      </article>
    `;
  }
  if (pane === "deadline") {
    const schedules = focusSchedules(customer?.name || item.customer || "").slice(0, 4);
    return `
      <article class="accelerator-card">
        <h4>下次提醒</h4>
        <p>这里不是第二个待办列表，只放已经处理过但还要继续推进的事情。到点后再回到未处理。</p>
        <div class="micro-list">
          ${schedules.length ? schedules.map((schedule) => acceleratorMicroRow(schedule.title || schedule.next_step || "跟进事项", schedule.deadline ? displayDateTime(schedule.deadline) : schedule.countdown_label || "待确认")).join("") : acceleratorMicroRow("当前", deadline ? displayDateTime(deadline) : "暂无下次提醒")}
        </div>
      </article>
    `;
  }
  if (pane === "daily") {
    return `
      <article class="accelerator-card">
        <h4>项目群日报</h4>
        <p>这里只阅读项目群动态，打开后不会改变任何销售状态。</p>
        <div class="micro-list">
          ${acceleratorMicroRow("项目进展", "各项目今天发生了什么、推进到哪里。")}
          ${acceleratorMicroRow("群内待对齐点", "群里提到但还没统一口径的信息。")}
          ${acceleratorMicroRow("后续计划", "本周 / 下周计划和排期变化。")}
          ${acceleratorMicroRow("需要关注事项", "只标记需要你知道的背景，不自动变成销售待办。")}
          ${acceleratorMicroRow("分项目摘要", "按项目群摘要阅读，不混入客户作战室。")}
        </div>
      </article>
    `;
  }
  if (pane === "snapshot") {
    return `<div class="accelerator-detail-grid">${acceleratorSnapshotDetailHtml()}</div>`;
  }
  if (pane === "pricing") {
    return acceleratorPricingDetailHtml();
  }
  return `
    <div class="accelerator-detail-grid">
      <article class="accelerator-card">
        <h4>${escapeHtml(isCarryover ? "本轮承接" : title)}</h4>
        <p>${escapeHtml(isCarryover ? "这条事项已经有上一轮处理结果；先看上次回填，再决定这次是否需要更新推进。" : (evidence || "这是当前选中事项的回填区。已闭环会移出队列；未闭环会进入 Deadline。"))}</p>
        ${isCarryover ? renderReceiptSummary(receipt, "上次回填") : ""}
        <div class="micro-list">
          ${acceleratorMicroRow("当前事项", title)}
          ${acceleratorMicroRow("本次状态", status || "待处理")}
          ${acceleratorMicroRow("下次时间", deadline ? displayDateTime(deadline) : "提交后确认")}
        </div>
        <div class="accelerator-action-row">
          <button class="accelerator-submit" type="button" data-accelerator-pane="next">${escapeHtml(isCarryover ? "更新推进结果" : "处理这个事项")}</button>
          <button class="accelerator-pill" type="button" data-accelerator-pane="path" data-path-scope="customer">客户经营地图</button>
        </div>
      </article>
      ${renderAcceleratorEvidence(context, customer)}
    </div>
  `;
}

function acceleratorEmptyWarRoomHtml(visibleCount = 0) {
  return `
    <article class="accelerator-card accelerator-empty-warroom">
      <h4>先从左侧选择一个客户事项</h4>
      <p>首页只负责回答今天怎么打；点开具体事项后，这里才承接处理、提交回执、下次提醒和客户经营地图。</p>
      <div class="micro-list">
        ${acceleratorMicroRow("当前队列", `${visibleCount} 项`)}
        ${acceleratorMicroRow("处理出口", "已闭环 / 待客户反馈 / 需内部支持 / 继续推进")}
        ${acceleratorMicroRow("未闭环", "进入下次提醒")}
        ${acceleratorMicroRow("项目群日报", "只读，不生成待办")}
      </div>
    </article>
  `;
}

function missionMetricButton(filter, label, value, note, activeFilter) {
  const active = activeFilter === filter ? "is-active" : "";
  return `
    <button class="mission-metric ${active}" type="button" data-accelerator-filter-open="${escapeHtml(filter)}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </button>
  `;
}

function missionQueueItemHtml(entry, selectedEntryKey = "") {
  const context = state.contextIndex[entry.key];
  const item = entry.item || {};
  const contextType = entry.contextType || context?.type || "action";
  const score = acceleratorScore(entry);
  const title = flowRowTitle(item, contextType);
  const customer = item.customer || item.name || "待匹配客户";
  return `
    <button class="mission-queue-item ${selectedEntryKey === entry.key ? "is-selected" : ""}" type="button" data-customer="${escapeHtml(customer)}" data-context-key="${escapeHtml(entry.key)}">
      <span class="mission-customer-mark">${escapeHtml(customer.slice(0, 1))}</span>
      <span class="mission-queue-copy">
        <strong>${escapeHtml(customer)}</strong>
        <p>${escapeHtml(title)}</p>
        <small>
          <span>${escapeHtml(entry.groupTitle || acceleratorFilterLabel(entry.filter))}</span>
          <span>${escapeHtml(flowRowDueLabel(item, contextType))}</span>
        </small>
      </span>
      <span class="mission-score">${escapeHtml(score)}</span>
    </button>
  `;
}

function missionIdleDetailHtml(visibleCount = 0) {
  return `
    <section class="mission-idle">
      <span class="mission-idle-kicker">等待选择事项</span>
      <h3>先选一条动作，再打开客户作战室</h3>
      <p>首页只负责分流：现在必须处理、已安排回流、材料包待确认和超时事项。点击具体事项后，这里才承接处理、提交回执、下一次提醒和客户经营地图。</p>
      <div class="mission-idle-grid">
        <div><span>当前队列</span><strong>${escapeHtml(visibleCount)} 项</strong></div>
        <div><span>处理出口</span><strong>闭环 / 反馈 / 内部支持</strong></div>
        <div><span>未闭环</span><strong>进入 Deadline</strong></div>
        <div><span>日报边界</span><strong>只读，不生成待办</strong></div>
      </div>
    </section>
  `;
}

function renderAcceleratorWorkbench() {
  const root = document.querySelector("#section-overview.accelerator-workbench");
  if (!root) return;
  const isCustomerWorkspace = ["today", "customer"].includes(state.activeWorkspace);
  root.hidden = !isCustomerWorkspace;
  const global = document.querySelector("#globalWorkspace");
  if (global) global.hidden = isCustomerWorkspace;
  document.body.dataset.workspace = state.activeWorkspace;
  if (!isCustomerWorkspace) {
    renderGlobalWorkspace();
    return;
  }
  root.classList.add("mission-flow-workbench");
  const entries = acceleratorEntries();
  const counts = entries.reduce((acc, entry) => {
    acc[entry.filter] = (acc[entry.filter] || 0) + 1;
    return acc;
  }, {});
  if (!state.acceleratorFilterLocked) {
    if (state.activeWorkspace === "today" && counts.todo) {
      state.acceleratorFilter = "todo";
    } else if (state.activeWorkspace === "today" && counts.overdue) {
      state.acceleratorFilter = "overdue";
    } else if (state.acceleratorFilter === "todo" && !counts.todo && counts.followup) {
      state.acceleratorFilter = "followup";
    }
  }
  if (!["todo", "feedback", "followup", "overdue"].includes(state.acceleratorFilter)) {
    state.acceleratorFilter = "todo";
  }
  if (!["next", "war", "path", "score", "timeline", "deadline"].includes(state.acceleratorPane)) {
    state.acceleratorPane = "next";
  }
  root.classList.toggle("is-customer-path-mode", state.acceleratorPane === "path");
  root.classList.toggle("is-readonly-mode", false);

  const queue = document.querySelector("#acceleratorQueue");
  const activeEntry = acceleratorActiveEntry();
  if (!state.acceleratorFilterLocked && state.activeWorkspace !== "today" && activeEntry?.filter && state.acceleratorFilter !== activeEntry.filter) {
    state.acceleratorFilter = activeEntry.filter;
  }
  const activeContext = activeEntry ? state.contextIndex[activeEntry.key] : null;
  const activeCustomer = acceleratorContextCustomer(activeContext, activeEntry);
  const visibleEntries = entries.filter((entry) => entry.filter === state.acceleratorFilter);
  const selectedEntryKey = activeEntry?.key || state.activeContextKey || "";

  const item = activeContext?.item || activeEntry?.item || {};
  const hasActiveMatter = Boolean(activeContext || activeEntry || activeCustomer);
  root.classList.toggle("has-active-matter", hasActiveMatter);
  const title = hasActiveMatter ? contextTitle(activeContext, activeCustomer) : "选择一条今日事项后进入处理";
  const source = hasActiveMatter ? acceleratorSourceLabel(activeContext, activeEntry) : "今日队列";
  const status = hasActiveMatter ? contextStatus(activeContext) : "未选择";
  const dueLabel = hasActiveMatter ? flowRowDueLabel(item, activeEntry?.contextType || activeContext?.type || "action") : "等待选择";
  const customerName = activeCustomer?.name || item.customer || item.name || "";
  const isCustomerPathView = state.acceleratorPane === "path";
  const headName = hasActiveMatter ? (isCustomerPathView ? `${customerName} · 经营地图` : customerName) : "当前客户作战室";
  const headSub = hasActiveMatter
    ? (isCustomerPathView ? "工作推进线、知识沉淀线和长期打法分开承接" : title)
    : "左侧选择一个具体事项后再展开，不默认替你选客户";
  const headSource = isCustomerPathView ? "客户作战室" : source;
  const headStatus = isCustomerPathView ? "工作 / 知识分层" : status;
  const headDue = isCustomerPathView ? "当前客户" : dueLabel;

  const paneTitle = hasActiveMatter ? ({
    next: "本次要处理",
    war: "客户作战室",
    path: "客户经营地图",
    score: "行动评分",
    timeline: "反馈链",
    deadline: "下次提醒",
  }[state.acceleratorPane] || "本次要处理") : "等待选择事项";
  const paneCaption = hasActiveMatter
    ? (isCustomerPathView ? `${customerName} · 工作推进 / 知识沉淀` : `${customerName} · ${source} · ${status}`)
    : "这里不是信息展示区；只承接你点开的那条事项。";
  const filterNote = {
    todo: "现在必须处理",
    followup: "已安排回流",
    feedback: "已处理反馈",
    overdue: "超时需要重排",
  }[state.acceleratorFilter] || "行动收件箱";
  const queueHtml = visibleEntries.length
    ? visibleEntries.map((entry) => missionQueueItemHtml(entry, selectedEntryKey)).join("")
    : `<div class="mission-empty">${escapeHtml(acceleratorFilterLabel(state.acceleratorFilter))}里暂时没有事项。</div>`;

  root.innerHTML = `
    <section class="mission-hero">
      <div class="mission-copy">
        <span>今日工作台</span>
        <h2>待处理事项</h2>
        <p>只处理已经明确要执行、到点回流或超时重排的事项。</p>
      </div>
      <div class="mission-metrics" aria-label="行动分流">
        ${missionMetricButton("todo", "现在必须处理", counts.todo || 0, "今日行动", state.acceleratorFilter)}
        ${missionMetricButton("followup", "已安排回流", counts.followup || 0, "到点再提醒", state.acceleratorFilter)}
        ${missionMetricButton("feedback", "已处理反馈", counts.feedback || 0, "回执复看", state.acceleratorFilter)}
        ${missionMetricButton("overdue", "超时任务", counts.overdue || 0, "需要重排", state.acceleratorFilter)}
      </div>
    </section>

    <section class="mission-workspace">
      <aside class="mission-inbox">
        <header>
          <span>${escapeHtml(filterNote)}</span>
          <h3>行动收件箱</h3>
          <p id="acceleratorQueueMeta">今天 · ${escapeHtml(acceleratorFilterLabel(state.acceleratorFilter))} ${visibleEntries.length} 项</p>
        </header>
        <div class="mission-filter-row" role="group" aria-label="行动队列筛选">
          ${["todo", "followup", "feedback", "overdue"].map((filter) => `
            <button class="accelerator-filter ${state.acceleratorFilter === filter ? "is-active" : ""}" type="button" data-accelerator-filter="${escapeHtml(filter)}">${escapeHtml(acceleratorFilterLabel(filter))} ${counts[filter] || 0}</button>
          `).join("")}
        </div>
        <div id="acceleratorQueue" class="mission-queue">${queueHtml}</div>
      </aside>

      <section class="mission-room ${hasActiveMatter ? "has-active-matter" : ""}">
        <section class="mission-room-head">
          <div class="mission-room-title">
            <span id="acceleratorCustomerLogo" class="mission-room-mark">${escapeHtml(hasActiveMatter ? (isCustomerPathView ? "图" : customerName.slice(0, 1)) : "待")}</span>
            <span>
              <h1 id="acceleratorCustomerName">${escapeHtml(headName)}</h1>
              <p id="acceleratorCustomerSub">${escapeHtml(headSub)}</p>
            </span>
          </div>
          <div class="accelerator-head-facts mission-facts">
            <div><span>来源</span><strong id="acceleratorSourceFact">${escapeHtml(headSource)}</strong></div>
            <div><span>状态</span><strong id="acceleratorStatusFact">${escapeHtml(headStatus)}</strong></div>
            <div><span>责任</span><strong id="acceleratorOwnerFact">当前销售</strong></div>
            <div><span>下一触发</span><strong id="acceleratorTriggerFact">${escapeHtml(headDue)}</strong></div>
          </div>
        </section>

        <section class="accelerator-process mission-process" aria-label="当前动作闭环摘要，可横向滑动">
          <div id="acceleratorProcessTrack" class="accelerator-process-track">${hasActiveMatter ? acceleratorProcessHtml(activeContext, activeEntry) : acceleratorIdleProcessHtml()}</div>
        </section>

        <nav class="accelerator-tabs mission-tabs" aria-label="作战室视图">
          <button class="accelerator-tab ${state.acceleratorPane === "next" ? "is-active" : ""}" type="button" data-accelerator-pane="next">当前这件事</button>
          <button class="accelerator-tab ${state.acceleratorPane === "timeline" ? "is-active" : ""}" type="button" data-accelerator-pane="timeline">处理记录</button>
          <button class="accelerator-tab ${state.acceleratorPane === "deadline" ? "is-active" : ""}" type="button" data-accelerator-pane="deadline">下次提醒</button>
          <button class="accelerator-tab ${state.acceleratorPane === "path" ? "is-active" : ""}" type="button" data-accelerator-pane="path" data-path-scope="customer">客户经营地图</button>
        </nav>

        <section class="mission-detail-shell">
          <div id="acceleratorCapsules" class="accelerator-capsules mission-capsules">${hasActiveMatter ? acceleratorCapsulesHtml(activeContext, activeCustomer, activeEntry) : ""}</div>
          <section class="accelerator-detail mission-detail">
            <header class="accelerator-detail-head">
              <div>
                <p>当前承接面</p>
                <h3 id="acceleratorDockTitle">${escapeHtml(paneTitle)}</h3>
                <small id="acceleratorDockCaption">${escapeHtml(paneCaption)}</small>
              </div>
              <div class="accelerator-dock-state">
                <span id="acceleratorStatusPill">${escapeHtml(headStatus)}</span>
                <strong id="acceleratorDockCustomer">${escapeHtml(hasActiveMatter ? customerName : "未选择")}</strong>
              </div>
            </header>
            <div id="acceleratorDetailBody" class="accelerator-detail-body">${hasActiveMatter ? acceleratorDetailHtml(activeContext, activeCustomer, activeEntry) : missionIdleDetailHtml(visibleEntries.length)}</div>
          </section>
        </section>
        <div class="accelerator-readonly mission-readonly">项目群日报：只读项目动态，不自动生成销售待办</div>
      </section>
    </section>
  `;
}

function priorityClass(priority) {
  return `priority-${String(priority || "P2").toLowerCase()}`;
}

function renderRiskPanel(alerts = []) {
  const summary = riskSummary(alerts);
  document.querySelector("#riskSummary").innerHTML = `
    <div class="risk-pill"><strong>${summary.high}</strong><span>高风险</span></div>
    <div class="risk-pill"><strong>${summary.medium}</strong><span>中风险</span></div>
    <div class="risk-pill"><strong>${summary.low}</strong><span>低风险</span></div>
  `;
  document.querySelector("#riskList").innerHTML = alerts.length
    ? alerts.slice(0, 4).map((item) => {
      const key = registerContext("risk", item, riskWorkflowKey(item));
      const status = workflowRecord("risk_status", key)?.status || item.status || "风险观察";
      return `
      <button class="risk-card ${classifyRisk(item)} ${state.activeContextKey === key ? "is-selected" : ""}" type="button" data-customer="${escapeHtml(item.customer)}" data-context-key="${escapeHtml(key)}">
        <div class="eyebrow risk-${escapeHtml(classifyRisk(item))}">${escapeHtml(item.label || "风险提醒")}</div>
        <h3>${escapeHtml(item.customer)}</h3>
        <p>${escapeHtml(item.risk)}</p>
        <div class="chip-row">
          <span class="chip red">${escapeHtml(item.task)}</span>
          <span class="chip amber">${escapeHtml(status)}</span>
        </div>
      </button>
    `;
    }).join("")
    : '<div class="focus-empty">当前没有识别到风险提醒。</div>';
}

function renderSnapshot(payload) {
  const container = document.querySelector("#snapshotContent");
  if (!payload?.ok) {
    container.innerHTML = '<div class="focus-empty">经营快照暂时不可用。</div>';
    return;
  }

  const quarter = payload.quarter || {};
  const preview = payload.preview || {};
  const progress = percentageValue(quarter.attainment_rate_raw, quarter.attainment_rate);
  const signedItems = preview.opportunities || [];

  container.innerHTML = `
    <div class="snapshot-top">
      <div class="attainment-ring" style="--progress:${progress}">
        <div class="attainment-ring-inner">
          <strong>${escapeHtml(quarter.attainment_rate || "--")}</strong>
          <span>达成率</span>
        </div>
      </div>
      <div class="snapshot-metrics">
        <div class="snapshot-metric">
          <span>本季度目标</span>
          <strong>${escapeHtml(quarter.target_amount || "待读取")}</strong>
        </div>
        <div class="snapshot-metric">
          <span>已签约</span>
          <strong>${escapeHtml(quarter.achieved_amount || "待读取")}</strong>
        </div>
        <div class="snapshot-metric">
          <span>差额</span>
          <strong>${escapeHtml(quarter.gap_amount || "待读取")}</strong>
        </div>
        <div class="snapshot-metric">
          <span>状态</span>
          <strong>${escapeHtml(snapshotSyncLabel(payload))}</strong>
        </div>
      </div>
    </div>
    <div class="signed-list">
      ${signedItems.length
        ? signedItems.map((item) => {
          const key = registerContext("snapshot", item, workflowKey("snapshot", item.name, item.status));
          return `
          <button class="signed-item" type="button" data-customer="${escapeHtml(item.name)}" data-context-key="${escapeHtml(key)}">
            <strong>${escapeHtml(item.name)}</strong>
            <p>${escapeHtml(item.status)}</p>
          </button>
        `;
        }).join("")
        : '<div class="focus-empty">当前没有可展示的签约明细。</div>'}
    </div>
  `;
}

function pmWorkflowButtons(key, hidden = false) {
  return "";
}

function workflowButtonsForContext(context) {
  if (!context) return "";
  const hidden = workflowRecord(`${context.type}_status`, context.key)?.hidden;
  if (hidden) return "";
  if (context.type === "pm_item") {
    return "";
  }
  if (context.type === "risk") {
    return `
      <button class="mini-action" type="button" data-workflow-convert="action" data-context-key="${escapeHtml(context.key)}">转动作</button>
      <button class="mini-action" type="button" data-workflow-convert="schedule" data-context-key="${escapeHtml(context.key)}">转日程</button>
      <button class="mini-action mini-action-muted" type="button" data-workflow-convert="resolved" data-context-key="${escapeHtml(context.key)}">风险解除</button>
    `;
  }
  if (context.type === "action") {
    return `
      <button class="mini-action" type="button" data-workflow-convert="schedule" data-context-key="${escapeHtml(context.key)}">转日程</button>
      <button class="mini-action mini-action-muted" type="button" data-workflow-convert="done" data-context-key="${escapeHtml(context.key)}">标记处理</button>
    `;
  }
  if (context.type === "schedule") {
    return `
      <button class="mini-action" type="button" data-workflow-convert="action" data-context-key="${escapeHtml(context.key)}">转动作</button>
      <button class="mini-action" type="button" data-workflow-convert="risk" data-context-key="${escapeHtml(context.key)}">转风险</button>
      <button class="mini-action mini-action-muted" type="button" data-workflow-convert="ignore" data-context-key="${escapeHtml(context.key)}">忽略</button>
    `;
  }
  return "";
}

function renderDigestSummary(messageDigest = {}) {
  const latest = messageDigest.days?.[0];
  const container = document.querySelector("#digestSummary");
  if (!latest) {
    container.innerHTML = '<div class="focus-empty">今天还没有项目群日报。</div>';
    return;
  }

  const sourceCards = latest.items?.length ? latest.items.map((item) => ({
    title: item.name,
    text: reportPreviewText(item.summary),
    customer: "",
    source: item,
  })) : (latest.actions || []).map((item) => ({
    title: item.topic || "待办",
    text: reportPreviewText(item.task || ""),
    customer: "",
    source: item,
  }));
  const cards = sourceCards.map((card) => {
    const item = {
      ...card.source,
      customer: card.customer,
      title: card.title,
      summary: card.text,
      date: latest.date,
    };
    const key = pmWorkflowKey(latest, { ...card.source, name: card.customer || card.title, summary: card.text });
    return { ...card, item, key, record: workflowRecord("pm_item_status", key) };
  }).filter((card) => !card.record?.hidden).slice(0, 3);

  if (!cards.length) {
    container.innerHTML = '<div class="focus-empty">今天没有可展示的项目群动态。</div>';
    return;
  }

  container.innerHTML = cards.map((card) => {
    const key = registerContext("pm_item", card.item, card.key);
    const topics = card.item.topics || [];
    return `
    <article class="digest-card clickable-card" data-jump-section="section-reports" data-context-key="${escapeHtml(key)}">
      <div class="eyebrow">${escapeHtml(latest.date)}</div>
      <h3>${escapeHtml(card.title)}</h3>
      <p>${escapeHtml(card.text)}</p>
      <div class="chip-row">
        <span class="chip teal">结构化日报</span>
        ${topics.slice(0, 3).map((tag) => `<span class="chip">${escapeHtml(tag)}</span>`).join("")}
      </div>
    </article>
  `;
  }).join("");
}

function contextTitle(context, customer) {
  const item = context?.item || {};
  if (!context) return customer?.next_action || "客户跟进";
  if (context.type === "action") return item.action || item.title || "今日动作";
  if (context.type === "risk") return item.task || item.title || "风险待处理";
  if (context.type === "pm_item") return item.title || item.name || item.summary || "项目群动态";
  if (context.type === "schedule") return item.title || item.next_step || "日程 / deadline";
  if (context.type === "feedback") return item.title || item.next_step || "已处理记录";
  if (context.type === "snapshot") return item.status || "签约明细";
  if (context.type === "route") return item.project || item.title || "知识沉淀节点";
  return customer?.next_action || "客户跟进";
}

function contextEvidence(context, customer) {
  const item = context?.item || {};
  if (!context) return customer?.risk || "";
  return item.evidence || item.risk || item.summary || item.signal || item.status || item.task || "";
}

function contextAction(context, customer) {
  const item = context?.item || {};
  if (!context) return customer?.next_action || "";
  return item.action || item.recommendation || item.next_step || item.task || customer?.next_action || "";
}

function contextSourceLabel(context) {
  if (!context) return "客户作战室";
  if (context.type === "action") return "今日优先动作";
  if (context.type === "risk") return "风险雷达";
  if (context.type === "pm_item") return "项目群日报";
  if (context.type === "schedule" && (context.item?.source_type === "transcript_intake" || context.item?.source_scope === "transcript_intake")) return "录音/TXT提取候选";
  if (context.type === "schedule") return "今日日程";
  if (context.type === "feedback") return "已处理";
  if (context.type === "snapshot") return "经营快照";
  if (context.type === "route") return "知识沉淀";
  return "客户作战室";
}

function contextStatus(context) {
  if (!context) return "客户视图";
  if (context.type === "action") return workflowRecord("action_status", context.key)?.status || "待处理";
  if (context.type === "risk") return workflowRecord("risk_status", context.key)?.status || context.item.status || "风险观察";
  if (context.type === "pm_item") return "日报只读";
  if (context.type === "schedule") return workflowRecord("schedule_status", context.key)?.status || context.item.countdown_label || context.item.status || "待跟进";
  if (context.type === "feedback") return context.item.status || "已回填";
  if (context.type === "snapshot") return "经营数据";
  return "待处理";
}

function contextWorkflowRecord(context) {
  if (!context) return null;
  const bucket = {
    action: "action_status",
    risk: "risk_status",
    schedule: "schedule_status",
    pm_item: "pm_item_status",
  }[context.type];
  return bucket ? workflowRecord(bucket, context.key) : null;
}

function contextProjectPath(context) {
  const record = contextWorkflowRecord(context);
  return record?.project_path || record?.receipt?.relative_path || context?.item?.resolution_path || "";
}

function latestReceiptForContext(context, customer) {
  if (context?.item?.latest_receipt) return context.item.latest_receipt;
  const recordReceipt = contextWorkflowRecord(context)?.receipt;
  if (recordReceipt) return recordReceipt;
  const customerName = customer?.name || context?.item?.customer || "";
  const contextTodoId = context?.type === "schedule" ? scheduleTodoId(context.item, context.key) : "";
  const title = contextTitle(context, customer);
  const matched = (workflowState().receipts || []).find((receipt) => {
    if (!receipt || receipt.customer !== customerName) return false;
    const receiptTodoId = receipt.todo?.id || "";
    return (contextTodoId && receiptTodoId === contextTodoId)
      || receipt.title === title
      || receipt.next_step === title
      || title.includes(receipt.title || "");
  }) || null;
  if (matched) return matched;
  if (receiptIsDisplayable(state.lastReceipt) && (!customerName || state.lastReceipt.customer === customerName)) {
    return state.lastReceipt;
  }
  return null;
}

function renderLatestReceipt(context, customer) {
  const receipt = latestReceiptForContext(context, customer);
  return renderReceiptSummary(receipt, "最近一次回填");
}

function defaultDeadlineValue(context) {
  const raw = context?.item?.deadline || "";
  if (!raw) return "";
  const normalized = normalizeDateTime(raw);
  const timestamp = Date.parse(normalized);
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (timestamp <= Date.now()) {
    date.setDate(new Date().getDate() + 1);
    date.setHours(10, 0, 0, 0);
  }
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function renderContextPanel(context, customer) {
  const title = contextTitle(context, customer);
  const evidence = contextEvidence(context, customer);
  const action = contextAction(context, customer);
  const sourceLabel = contextSourceLabel(context);
  const status = contextStatus(context);
  const projectPath = contextProjectPath(context);
  return `
    <section class="focus-section focus-context">
      <div class="context-head">
        <div>
          <h4>当前承接事项</h4>
          <strong>${escapeHtml(title)}</strong>
        </div>
        <span class="status-pill">${escapeHtml(status)}</span>
      </div>
      <p>${escapeHtml(evidence || "暂无原始依据")}</p>
      ${context?.type !== "pm_item" && action ? `<p>建议动作：${escapeHtml(action)}</p>` : ""}
      <div class="chip-row">
        <span class="chip teal">${escapeHtml(sourceLabel)}</span>
        ${projectPath ? `<span class="chip teal">已有工作推进记录</span>` : ""}
        ${workflowButtonsForContext(context)}
      </div>
    </section>
  `;
}

function evidenceStatusChoices(currentStatus = "") {
  return [
    {
      value: "已处理",
      label: "已闭环",
      note: "本事项结束，从待处理移除",
    },
    {
      value: "待客户反馈",
      label: "待客户反馈",
      note: "已推进，等客户回复",
    },
    {
      value: "待内部支持",
      label: "需内部支持",
      note: "需要内部资源继续配合",
    },
    {
      value: "推进中",
      label: "继续推进",
      note: "还没结束，保留下次动作",
    },
  ].map((item) => ({
    ...item,
    active: item.value === currentStatus,
  }));
}

function currentEvidenceStatus(context) {
  const status = contextStatus(context);
  if (/继续跟进|继续推进/.test(status)) return "推进中";
  if (context?.type === "schedule" && !/已处理|已闭环|待客户反馈|待内部支持|推进中/.test(status)) return "推进中";
  return ["已处理", "已闭环", "待客户反馈", "待内部支持", "推进中"].includes(status)
    ? status.replace("已闭环", "已处理")
    : "";
}

function renderEvidenceForm(context, customer) {
  const title = contextTitle(context, customer);
  const action = contextAction(context, customer);
  const evidence = contextEvidence(context, customer);
  const disabled = state.demoMode ? "disabled" : "";
  const lastReceipt = latestReceiptForContext(context, customer);
  const currentStatus = currentEvidenceStatus(context);
  const statusChoices = evidenceStatusChoices(currentStatus);
  const isCarryover = isFollowupCarryover(context, { filter: "" }, lastReceipt);
  const formTitle = isCarryover ? "更新这次推进" : "处理这个事项";
  const formCaption = isCarryover
    ? "上次回填已在左侧展示；这里只记录这一次新的客户反馈、内部进展或改期结果。"
    : "这是当前选中事项的回填区。已闭环会移出队列；未闭环会进入日程 / Deadline。";
  const summaryLabel = isCarryover ? "本轮承接事项" : "当前事项";
  const resolutionPlaceholder = isCarryover
    ? "例如：客户今天仍未反馈，已补电话沟通；或内部已确认下一轮会议时间。"
    : "例如：已把口径发给客户确认，客户要求补一版预算说明。";
  return `
    <form id="evidenceForm" class="evidence-form ${currentStatus === "已处理" ? "is-closed" : ""}">
      <input type="hidden" name="customer" value="${escapeHtml(customer?.name || "")}" />
      <input type="hidden" name="title" value="${escapeHtml(title)}" />
      <input type="hidden" name="evidence" value="${escapeHtml(evidence)}" />
      <input type="hidden" name="action" value="${escapeHtml(action)}" />
      <input type="hidden" name="workflow_key" value="${escapeHtml(context?.key || workflowKey("action", customer?.name, title))}" />
      <input type="hidden" name="pm_item_key" value="${escapeHtml(context?.type === "pm_item" ? context.key : "")}" />
      <input type="hidden" name="todo_id" value="${escapeHtml(context?.type === "schedule" ? scheduleTodoId(context.item, context.key) : "")}" />
      <input type="hidden" name="object_type" value="${escapeHtml(context?.type === "risk" ? "risk" : context?.type === "schedule" ? "schedule" : "action")}" />
      <input type="hidden" name="source_view" value="${escapeHtml(contextSourceLabel(context))}" />
      <input type="hidden" name="status" value="${escapeHtml(currentStatus)}" />
      <div class="evidence-head">
        <div>
          <h4>${escapeHtml(formTitle)}</h4>
          <p>${escapeHtml(formCaption)}</p>
        </div>
        ${receiptIsDisplayable(lastReceipt) ? `<span class="receipt-pill">上次回填：${escapeHtml(lastReceipt.status || "已提交")}</span>` : ""}
      </div>
      <div class="submit-task-summary">
        <span>${escapeHtml(summaryLabel)}</span>
        <strong>${escapeHtml(title)}</strong>
        <p>${escapeHtml(evidence || action || "暂无原始依据")}</p>
      </div>
      <div class="evidence-status-grid" role="group" aria-label="处理出口">
        ${statusChoices.map((choice) => `
          <button class="status-choice ${choice.active ? "is-active" : ""}" type="button" data-evidence-status="${escapeHtml(choice.value)}" ${disabled}>
            <strong>${escapeHtml(choice.label)}</strong>
            <span>${escapeHtml(choice.note)}</span>
          </button>
        `).join("")}
      </div>
      <label class="field-compact">
        <span>这次实际推进到哪了</span>
        <textarea name="resolution" class="input text-area" rows="3" placeholder="${escapeHtml(resolutionPlaceholder)}" ${disabled}></textarea>
      </label>
      <div class="followup-grid">
        <label class="field-compact">
          <span>下一步动作</span>
          <textarea name="next_step" class="input text-area" rows="2" placeholder="未闭环时必填，例如：明天 10 点前补邮件确认。" ${disabled}>${escapeHtml(action || "")}</textarea>
        </label>
        <label class="field-compact">
          <span>下一次时间</span>
          <input name="deadline" class="input" type="datetime-local" value="${escapeHtml(defaultDeadlineValue(context))}" ${disabled} />
        </label>
      </div>
      <div class="evidence-calendar-row">
        <label class="check-row evidence-check">
          <input name="sync_calendar" type="checkbox" ${currentStatus === "已处理" ? "" : "checked"} ${disabled} />
          <span>未闭环时同步飞书任务提醒</span>
        </label>
        <span class="evidence-rule">已闭环不建提醒；未闭环必须有下一步和时间。</span>
      </div>
      <div class="form-actions">
        <button class="button button-primary" type="submit" ${disabled}>提交处理结果</button>
        <span id="evidenceResult" class="form-result">${state.demoMode ? "演示模式不写入真实证据。" : ""}</span>
      </div>
    </form>
  `;
}

function applyEvidenceStatusChoice(form, status) {
  if (!form) return;
  const statusInput = form.querySelector('input[name="status"]');
  if (statusInput) statusInput.value = status;
  form.classList.toggle("is-closed", status === "已处理");
  form.querySelectorAll("[data-evidence-status]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.evidenceStatus === status);
  });
  const syncCalendar = form.querySelector('input[name="sync_calendar"]');
  if (syncCalendar) syncCalendar.checked = status !== "已处理";
  const result = form.querySelector("#evidenceResult");
  if (result) {
    result.textContent = status === "已处理"
      ? "将闭环并从待处理移除。"
      : "未闭环会生成或保留下一步跟进。";
  }
}

function contextCanSubmitEvidence(context) {
  if (!context) return false;
  return ["action", "risk", "schedule"].includes(context.type);
}

function setLoopEmptyVisible(visible) {
  const panel = document.querySelector("#section-loop-empty");
  if (panel) panel.hidden = !visible;
}

function receiptIsDisplayable(receipt) {
  return Boolean(receipt?.submitted_at || receipt?.title || receipt?.todo || receipt?.relative_path);
}

function displayDateTime(value = "") {
  return String(value || "").replace("T", " ").replace("+08:00", "");
}

function renderReceiptSummary(receipt, label = "最近回执") {
  if (!receiptIsDisplayable(receipt)) return "";
  const submittedAt = displayDateTime(receipt.submitted_at || "");
  const nextDeadline = receipt.todo?.deadline || receipt.deadline || "";
  const resultText = receipt.resolution || receipt.result || receipt.next_step || receipt.title || "处理结果已记录";
  return `
    <section class="latest-receipt">
      <div class="latest-receipt-head">
        <div>
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(receipt.status || "已提交")}</strong>
        </div>
        ${submittedAt ? `<em>${escapeHtml(submittedAt)}</em>` : ""}
      </div>
      <p>${escapeHtml(resultText)}</p>
      <div class="chip-row">
        ${receipt.next_step ? `<span class="chip teal">下一步：${escapeHtml(receipt.next_step)}</span>` : ""}
        ${nextDeadline ? `<span class="chip amber">下次：${escapeHtml(displayDateTime(nextDeadline))}</span>` : ""}
        ${receipt.relative_path ? `<span class="chip">工作回执已留存</span>` : ""}
      </div>
    </section>
  `;
}

function renderLoopIdlePanel() {
  const container = document.querySelector("#loopEmptyContent");
  if (!container) return;
  const latestReceipt = receiptIsDisplayable(state.lastReceipt) ? state.lastReceipt : null;
  container.innerHTML = `
    <div class="loop-empty-head">
      <strong>等待主对象</strong>
      <p>左侧今日行动队列选中一条事项后，本列承接处理、回填、下一次时间。</p>
    </div>
    <div class="loop-step-grid">
      <div class="loop-step">
        <span>01</span>
        <strong>选主对象</strong>
        <p>未处理、已处理、继续跟进、超时只保留一条归属。</p>
      </div>
      <div class="loop-step">
        <span>02</span>
        <strong>提交结果</strong>
        <p>已闭环移出队列；未闭环必须留下下一步和时间。</p>
      </div>
      <div class="loop-step">
        <span>03</span>
        <strong>回到 Deadline</strong>
        <p>下一次触发前只保留在日程系统，到点再回到未处理。</p>
      </div>
    </div>
    ${latestReceipt ? renderReceiptSummary(latestReceipt, "最新回执") : '<div class="loop-note">当前没有正在展开的事项。</div>'}
  `;
}

function renderLifecyclePanel(context = null, customer = null) {
  const container = document.querySelector("#lifecycleContent");
  const meta = document.querySelector("#lifecycleMeta");
  if (!container) return;
  if (!context && !customer) {
    if (meta) meta.textContent = "未选择";
    container.innerHTML = `
      <div class="lifecycle-empty">
        <strong>反馈链</strong>
        <p>选中主对象后，这里只串当前客户的回执、下一次 Deadline 和知识沉淀。</p>
      </div>
    `;
    return;
  }

  const customerName = customer?.name || context?.item?.customer || "未绑定客户";
  const receipt = latestReceiptForContext(context, customer);
  const nextDeadline = context?.item?.deadline || receipt?.todo?.deadline || receipt?.deadline || "";
  const route = customerName ? focusRoutes(customerName)[0] : null;
  const title = contextTitle(context, customer);
  const evidence = contextEvidence(context, customer);
  const nodes = [
    {
      label: "当前",
      title,
      text: evidence || contextAction(context, customer) || "暂无原始依据",
    },
    receiptIsDisplayable(receipt) ? {
      label: "回执",
      title: receipt.status || "已提交",
      text: receipt.resolution || receipt.result || receipt.next_step || receipt.title || "处理结果已记录",
    } : null,
    nextDeadline ? {
      label: "Deadline",
      title: displayDateTime(nextDeadline),
      text: receipt?.next_step || contextAction(context, customer) || "等待下一次触发",
    } : null,
    route ? {
      label: "知识沉淀",
      title: route.project || customerName,
      text: route.history?.[0]?.summary || route.history?.[0]?.title || "已有知识沉淀记录",
    } : null,
  ].filter(Boolean);

  if (meta) meta.textContent = contextSourceLabel(context);
  container.innerHTML = `
    <div class="lifecycle-current">
      <span>${escapeHtml(customerName)}</span>
      <strong>${escapeHtml(contextStatus(context))}</strong>
    </div>
    <div class="lifecycle-timeline">
      ${nodes.map((node) => `
        <section class="lifecycle-node">
          <em>${escapeHtml(node.label)}</em>
          <strong>${escapeHtml(node.title)}</strong>
          <p>${escapeHtml(node.text)}</p>
        </section>
      `).join("")}
    </div>
  `;
}

function setJourneyStage(activeIndex = 0) {
  document.querySelectorAll(".journey-status-tabs span").forEach((tab, index) => {
    tab.classList.toggle("is-active", index === activeIndex);
  });
}

function renderCustomerFocus(item, intel = null, loading = false) {
  const container = document.querySelector("#customerFocus");
  const meta = document.querySelector("#customerFocusMeta");
  const panel = document.querySelector("#section-focus");
  const journeyBoard = document.querySelector(".journey-board");
  if (!item) {
    journeyBoard?.classList.remove("has-focus");
    setJourneyStage(0);
    if (panel) panel.hidden = true;
    setLoopEmptyVisible(true);
    renderLoopIdlePanel();
    renderLifecyclePanel(null, null);
    meta.textContent = "选择事项";
    container.className = "focus-empty";
    container.textContent = "先从今日行动队列或日程选择一条具体事项。";
    return;
  }
  if (panel) panel.hidden = false;
  journeyBoard?.classList.add("has-focus");
  setJourneyStage(1);
  setLoopEmptyVisible(false);

  const context = state.activeContextKey ? state.contextIndex[state.activeContextKey] : null;
  renderLifecyclePanel(context, item);
  meta.textContent = `${item.priority} / ${item.stage} · ${contextSourceLabel(context)}`;
  const intelBlocks = intel
    ? renderIntelBlocks(intel)
    : `
      <div class="intel-block"><h4>最近群消息</h4><div class="empty-inline">${loading ? "正在读取..." : "暂无命中"}</div></div>
      <div class="intel-block"><h4>内部沉淀</h4><div class="empty-inline">${loading ? "正在读取..." : "暂无命中"}</div></div>
      <div class="intel-block"><h4>外部动态</h4><div class="empty-inline">${loading ? "正在读取..." : "暂无命中"}</div></div>
    `;

  container.className = "customer-focus";
  container.innerHTML = `
    <div class="focus-main">
      <div>
        <h3>${escapeHtml(item.name)}</h3>
        <div class="focus-tags">
          <span class="status-pill ${escapeHtml(priorityClass(item.priority))}">${escapeHtml(statusPillLabel(item.priority))}</span>
          <span class="chip teal">${escapeHtml(item.stage)}</span>
          ${item.amount ? `<span class="chip amber">${escapeHtml(item.amount)}</span>` : ""}
        </div>
      </div>
    </div>
    <div class="focus-work-surface">
      <div class="focus-handle">
        ${contextCanSubmitEvidence(context) ? renderEvidenceForm(context, item) : ""}
        ${renderLatestReceipt(context, item)}
        ${renderContextPanel(context, item)}
      </div>
      ${renderFocusBackgroundTabs(item, intelBlocks)}
    </div>
  `;
}

function renderIntelBlocks(payload = {}) {
  const blocks = [
    ["最近群消息", payload.message_signals, (item) => `
      <div class="intel-item">
        <strong>${escapeHtml(item.kind || "群消息")} · ${escapeHtml(item.source || "未标记")}</strong>
        ${item.date ? `<p>${escapeHtml(item.date)}</p>` : ""}
        <p>${escapeHtml(item.snippet || item.summary || "暂无摘要")}</p>
      </div>
    `],
    ["内部沉淀", payload.local_signals, (item) => `
      <div class="intel-item">
        <strong>${escapeHtml(item.source || "知识库")}</strong>
        ${item.updated_at ? `<p>${escapeHtml(item.updated_at)}</p>` : ""}
        <p>${escapeHtml(item.snippet || "暂无摘要")}</p>
      </div>
    `],
    ["外部动态", payload.public_signals, (item) => `
      <div class="intel-item">
        <strong>${escapeHtml(item.title || "外部结果")}</strong>
        ${item.signal_type ? `<p>${escapeHtml(item.signal_type)}</p>` : ""}
        ${item.published_at ? `<p>${escapeHtml(item.published_at)}</p>` : ""}
        <p>${escapeHtml(item.impact_judgment || item.summary || item.recommended_action || "Codex 回传情报，只作判断依据。")}</p>
        ${(item.url || item.source_url) ? `<p><a class="external-link" href="${escapeHtml(item.url || item.source_url)}" target="_blank" rel="noreferrer">打开链接</a></p>` : ""}
      </div>
    `],
  ];

  return blocks.map(([title, items, renderer]) => `
    <div class="intel-block">
      <h4>${escapeHtml(title)}</h4>
      ${items?.length ? items.slice(0, 3).map(renderer).join("") : '<div class="empty-inline">暂无命中</div>'}
    </div>
  `).join("");
}

function customerMatchText(customerName = "", value = "") {
  const text = String(value || "");
  if (!customerName || !text) return false;
  const customer = findCustomer(customerName) || { name: customerName };
  const aliases = [
    customerName,
    normalizeCustomerName(customerName),
    ...customerAliases(customer),
  ]
    .filter(Boolean)
    .filter((item, index, arr) => arr.indexOf(item) === index);
  return aliases.some((alias) => text.includes(alias) || alias.includes(text)) || sharesCustomerToken(text, customerName);
}

function customerOperatingMap(customerName = "") {
  const maps = state.dashboard?.sales_brain?.customer_maps || [];
  return maps.find((item) => (
    item.customer === customerName
    || customerMatchText(customerName, item.customer || "")
    || customerMatchText(item.customer || "", customerName)
  )) || null;
}

function routeGroupSearchText(group = {}) {
  return [
    group.project,
    ...(group.history || []).flatMap((item) => [
      item.title,
      item.raw_title,
      item.summary,
      item.preview,
      item.path,
      ...(item.projects || []),
      ...(item.actions || []),
      ...(item.risks || []),
      ...(item.signals || []),
    ]),
  ].filter(Boolean).join(" ");
}

function routeGroupsForScope(customerName = "", limit = 5) {
  const groups = groupedKnowledge(state.dashboard?.knowledge_timeline || []);
  const scoped = customerName
    ? groups.filter((group) => customerMatchText(customerName, routeGroupSearchText(group)))
    : groups;
  return scoped.slice(0, limit);
}

function itemMatchesCustomer(item = {}, customerName = "") {
  const haystack = [
    item.customer,
    item.name,
    item.project,
    item.title,
    item.next_step,
    item.action,
    item.summary,
    item.status,
    item.raw_title,
  ].filter(Boolean).join(" ");
  return customerMatchText(customerName, haystack);
}

function compactList(items = [], renderer, fallback = "暂无相关记录") {
  return items.length
    ? `<div class="focus-compact-list">${items.map(renderer).join("")}</div>`
    : `<div class="focus-empty compact">${escapeHtml(fallback)}</div>`;
}

function focusSchedules(customerName = "") {
  return dedupeScheduleItems((state.dashboard?.risk_todos || [])
    .filter((item) => itemMatchesCustomer(item, customerName))
  ).slice(0, 5);
}

function focusRoutes(customerName = "") {
  return routeGroupsForScope(customerName, 3);
}

function focusReports(customerName = "") {
  const days = state.dashboard?.message_digest?.days || [];
  return days.slice(0, 3).flatMap((day) => (day.items || [])
    .filter((item) => itemMatchesCustomer(item, customerName))
    .slice(0, 3)
    .map((item) => ({ ...item, date: day.date })))
    .slice(0, 5);
}

function focusSnapshotItems(customerName = "") {
  const items = state.dashboard?.fxiaoke_status?.preview?.opportunities || [];
  return items.filter((item) => itemMatchesCustomer(item, customerName)).slice(0, 4);
}

function focusTabButton(id, label, count = "") {
  const active = state.focusTab === id;
  return `<button class="focus-tab ${active ? "is-active" : ""}" type="button" aria-selected="${active ? "true" : "false"}" data-focus-tab="${escapeHtml(id)}">${escapeHtml(label)}${count ? `<span>${escapeHtml(count)}</span>` : ""}</button>`;
}

function focusTabPanel(id, body) {
  return `<section class="focus-tab-panel ${state.focusTab === id ? "is-active" : ""}" data-focus-tab-panel="${escapeHtml(id)}">${body}</section>`;
}

function renderFocusBackgroundTabs(item, intelBlocks) {
  if (!["map", "schedule", "route", "snapshot"].includes(state.focusTab)) {
    state.focusTab = "map";
  }
  const schedules = focusSchedules(item.name);
  const routes = focusRoutes(item.name);
  const snapshots = focusSnapshotItems(item.name);
  const operatingMap = customerOperatingMap(item.name);
  const mapBody = operatingMap ? `
    <div class="operating-map-grid">
      <section class="focus-section">
        <h4>项目线</h4>
        <strong>${escapeHtml((operatingMap.project_lines || []).join(" / ") || item.stage || "待补齐")}</strong>
      </section>
      <section class="focus-section">
        <h4>预算 / 金额</h4>
        <strong>${escapeHtml(operatingMap.budget || item.amount || "预算待确认")}</strong>
      </section>
      <section class="focus-section">
        <h4>关键人</h4>
        <strong>${escapeHtml(operatingMap.key_people || item.owner || "关键人待补齐")}</strong>
      </section>
      <section class="focus-section">
        <h4>供应商 / 竞品路径</h4>
        <strong>${escapeHtml(operatingMap.supplier_path || "供应商/竞品路径待补齐")}</strong>
      </section>
      <section class="focus-section wide">
        <h4>下一步打法</h4>
        <strong>${escapeHtml(operatingMap.next_play || item.next_action || "等待下一步动作")}</strong>
      </section>
      <section class="focus-section">
        <h4>外部情报</h4>
        <strong>${escapeHtml(`${operatingMap.public_signal_count || 0} 条`)}</strong>
      </section>
    </div>
    <div class="focus-intel">${intelBlocks}</div>
  ` : `
    <div class="operating-map-empty">
      <strong>经营地图待沉淀</strong>
      <p>先处理当前事项；提交回执或导入客户情报后，这里会沉淀项目线、预算、关键人、供应商路径和下一步打法。</p>
    </div>
    <div class="focus-intel">${intelBlocks}</div>
  `;
  const scheduleBody = compactList(schedules, (schedule) => {
    const key = registerContext("schedule", schedule, scheduleWorkflowKey(schedule));
    const title = schedule.title || schedule.next_step || "待跟进";
    return `
      <button class="focus-compact-row" type="button" data-customer="${escapeHtml(schedule.customer || item.name)}" data-context-key="${escapeHtml(key)}">
        <strong>${escapeHtml(schedule.countdown_label || schedule.time_label || "待安排")}</strong>
        <span>${escapeHtml(title)}</span>
      </button>
    `;
  }, "这个客户当前没有日程或 deadline。");
  const routeBody = compactList(routes, (group) => `
    <button class="focus-compact-row" type="button" data-project-route="${escapeHtml(group.project)}">
      <strong>${escapeHtml(group.project)}</strong>
      <span>${escapeHtml(projectRecentNode(group))}</span>
    </button>
  `, "这个客户当前没有知识沉淀。");
  const snapshotBody = compactList(snapshots, (snapshot) => `
    <button class="focus-compact-row" type="button" data-jump-section="section-snapshot">
      <strong>${escapeHtml(snapshot.name || item.name)}</strong>
      <span>${escapeHtml(snapshot.status || "暂无签约明细")}</span>
    </button>
  `, "经营快照里暂时没有这个客户的签约明细。");

  return `
    <div class="focus-background">
      <div class="focus-tabs" role="tablist" aria-label="客户背景资料">
        ${focusTabButton("map", "经营地图", operatingMap ? String(operatingMap.public_signal_count || 0) : "")}
        ${focusTabButton("schedule", "日程", String(schedules.length))}
        ${focusTabButton("route", "知识沉淀", String(routes.length))}
        ${focusTabButton("snapshot", "经营快照", String(snapshots.length))}
      </div>
      <div class="focus-tab-panels">
        ${focusTabPanel("map", mapBody)}
        ${focusTabPanel("schedule", scheduleBody)}
        ${focusTabPanel("route", routeBody)}
        ${focusTabPanel("snapshot", snapshotBody)}
      </div>
    </div>
  `;
}

function renderCustomerCards(items = []) {
  document.querySelector("#customerCards").innerHTML = items.length
    ? items.filter((item) => item.bucket !== "excluded").map((item) => `
      <button class="customer-card ${state.selectedCustomer === item.name ? "is-selected" : ""}" type="button" data-customer="${escapeHtml(item.name)}">
        <div class="customer-card-head">
          <h3>${escapeHtml(item.name)}</h3>
          <span class="status-pill ${escapeHtml(priorityClass(item.priority))}">${escapeHtml(item.priority)}</span>
        </div>
        <div class="muted">${escapeHtml(item.stage || item.status || "未标记阶段")}</div>
        ${item.amount ? `<p>${escapeHtml(item.amount)}</p>` : ""}
        <p>本周目标：${escapeHtml(item.next_action || "暂无")}</p>
        <p>风险一句话：${escapeHtml(item.risk || "暂无")}</p>
      </button>
    `).join("")
    : '<div class="focus-empty">当前没有客户作战卡。</div>';
}

function renderKnowledgeRoutes(items = []) {
  const groups = groupedKnowledge(items);
  const total = groups.reduce((sum, group) => sum + (group.history?.length || 0), 0);
  document.querySelector("#knowledgeMeta").textContent = `${groups.length} 个客户 / ${total} 条沉淀`;
  if (!groups.length) {
    document.querySelector("#knowledgeRoutes").innerHTML = '<div class="focus-empty">当前没有知识沉淀。</div>';
    return;
  }

  document.querySelector("#knowledgeRoutes").innerHTML = `
    <div class="route-header">
      <span>知识沉淀</span>
      <span>沉淀摘要</span>
      <span>最近节点</span>
      <span>状态</span>
    </div>
    ${groups.map((group) => {
      const active = state.expandedProject === group.project;
      const deal = findCustomer(group.project);
      const key = registerContext("route", {
        project: group.project,
        title: group.history[0]?.title || group.project,
        summary: projectSummary(group),
        action: group.history[0]?.actions?.[0] || deal?.next_action || "",
        risk: group.history[0]?.risks?.[0] || deal?.risk || "",
      }, workflowKey("route", group.project, group.history[0]?.updated_at || ""));
      return `
        <button class="route-row ${active ? "is-active" : ""}" type="button" data-project-route="${escapeHtml(group.project)}" data-context-key="${escapeHtml(key)}">
          <div class="route-row-head">
            <strong>${escapeHtml(group.project)}</strong>
            <span>${escapeHtml(projectSummary(group))}</span>
            <span>${escapeHtml(projectRecentNode(group))}</span>
            <span>${escapeHtml(projectStatus(group))}</span>
          </div>
          ${active ? `
            <div class="route-body">
              <div class="route-column">
                <h4>当前判断</h4>
                <p>${escapeHtml(projectSummary(group))}</p>
              </div>
              <div class="route-column">
                <h4>最近节点</h4>
                <div class="line-list">
                  ${group.history.slice(0, 12).map((item) => `<div>${escapeHtml(item.updated_at)} · ${escapeHtml(item.title || item.raw_title || "未命名记录")}</div>`).join("")}
                </div>
              </div>
              <div class="route-column">
                <h4>行动记录</h4>
                <div class="line-list">
                  ${(group.history[0]?.actions?.length ? group.history[0].actions.slice(0, 4) : [deal?.next_action || "暂无行动记录"]).map((line) => `<div>${escapeHtml(line)}</div>`).join("")}
                </div>
              </div>
            </div>
          ` : ""}
        </button>
      `;
    }).join("")}
  `;
}

function scheduleSourceLabel(item = {}) {
  if (item.source_type === "feishu_calendar") return "飞书日程";
  if (item.source_scope === "transcript_intake" || item.source_type === "transcript_intake") return "录音/TXT提取";
  if (item.source_scope === "pm_daily" || item.source_type === "pm_daily") return "项目群日报遗留";
  if (item.source_scope === "workflow_receipt") return "工作回执 deadline";
  if (item.source_scope === "knowledge") return "历史回执 deadline";
  return "工作台 deadline";
}

function activityLabel(value = "灰") {
  return {
    红: "高活跃",
    黄: "中活跃",
    绿: "低活跃",
    灰: "无消息",
  }[value] || value;
}

function reportParagraphs(items = []) {
  return items
    .filter(Boolean)
    .map((item) => `<p>${escapeHtml(item)}</p>`)
    .join("");
}

function reportNumberedList(items = [], fallback = "暂无。") {
  const values = items.filter(Boolean);
  if (!values.length) return `<p>${escapeHtml(fallback)}</p>`;
  return `<ol>${values.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>`;
}

function renderDailyReportBlock(title, items, fallback) {
  return `
    <section class="daily-report-section">
      <h4>${escapeHtml(title)}</h4>
      ${reportNumberedList(items, fallback)}
    </section>
  `;
}

function renderGroupReportSection(item = {}, index = 0) {
  const discussionPoints = item.discussion_points || [];
  const progressItems = item.progress || [];
  const openPoints = item.open_points || [];
  const mentions = item.mentions || [];
  const topics = item.topics?.length ? item.topics.join("、") : "日常沟通";
  const countLabel = Number(item.message_count || 0) ? "已归纳" : "暂无新增";
  return `
    <section class="daily-report-group">
      <div class="daily-report-group-head">
        <h4>${index + 1}. ${escapeHtml(item.name || "未命名项目群")}</h4>
        <span class="health-badge health-${escapeHtml(item.health || "灰")}">${escapeHtml(countLabel)}</span>
      </div>
      <div class="daily-report-row">
        <strong>今日主题</strong>
        <p>${escapeHtml(topics)}</p>
      </div>
      <div class="daily-report-row">
        <strong>结构化摘要</strong>
        <p>${escapeHtml(reportPreviewText(item.summary || "今天暂无有效沟通。"))}</p>
      </div>
      ${discussionPoints.length ? `
      <div class="daily-report-row">
        <strong>关键讨论</strong>
        ${reportParagraphs(discussionPoints)}
      </div>` : ""}
      ${progressItems.length ? `
      <div class="daily-report-row">
        <strong>项目进展</strong>
        ${reportParagraphs(progressItems)}
      </div>` : ""}
      ${openPoints.length ? `
      <div class="daily-report-row">
        <strong>群内待对齐点</strong>
        ${reportParagraphs(openPoints)}
      </div>` : ""}
      ${mentions.length ? `
      <div class="daily-report-row">
        <strong>需要关注事项</strong>
        ${reportParagraphs(mentions)}
      </div>` : ""}
    </section>
  `;
}

function scheduleGroupDefinitions() {
  return [
    ["overdue", "已超期"],
    ["today", "今天"],
    ["week", "本周 / 未来 7 天"],
    ["unscheduled", "待确认时间"],
    ["later", "后续"],
  ];
}

function renderScheduleCard(item) {
  const key = registerContext("schedule", item, scheduleWorkflowKey(item));
  const record = workflowRecord("schedule_status", key);
  const status = record?.status || item.status || "待跟进";
  const title = item.title || item.next_step || "日程";
  const customer = item.customer || "待匹配事项";
  const titleText = title.includes(customer) ? title : `${customer} · ${title}`;
  const matchedLabel = item.matched_customer === false ? "待匹配客户" : scheduleSourceLabel(item);
  const calendarStatus = item.calendar?.status || "";
  const canSyncReminder = item.deadline && !isFeishuSchedule(item) && ["failed", "skipped", ""].includes(calendarStatus);
  const candidateCount = Number(item.transcript_candidate_count || 0);
  const actionLabel = isScheduleDueForAction(item)
    ? "打开回填"
    : "查看/回填";
  return `
    <article class="prep-card schedule-card clickable-card ${state.activeContextKey === key ? "is-selected" : ""}" data-customer="${escapeHtml(customer)}" data-context-key="${escapeHtml(key)}">
      <div class="eyebrow">${escapeHtml(item.time_label || item.countdown_label || "待跟进")}</div>
      <h3>${escapeHtml(titleText)}</h3>
      <ul>
        <li>来源：${escapeHtml(matchedLabel)}</li>
        <li>下一步：${escapeHtml(item.next_step || "待补充")}</li>
        <li>状态：${escapeHtml(status)}</li>
      </ul>
      <div class="chip-row">
        <span class="chip amber">${escapeHtml(item.countdown_label || item.urgency || "deadline")}</span>
        ${candidateCount ? `<span class="chip teal">${escapeHtml(candidateCount)} 条候选</span>` : ""}
        ${item.calendar?.app_link ? `<a class="mini-link" href="${escapeHtml(item.calendar.app_link)}" target="_blank" rel="noreferrer">打开飞书</a>` : ""}
        <button class="mini-action" type="button" data-customer="${escapeHtml(customer)}" data-context-key="${escapeHtml(key)}">${escapeHtml(actionLabel)}</button>
        ${canSyncReminder ? `<button class="mini-action" type="button" data-retry-calendar="${escapeHtml(item.id)}">${calendarStatus === "failed" ? "重试提醒" : "同步提醒"}</button>` : ""}
      </div>
    </article>
  `;
}

function renderScheduleReceiptBanner() {
  const receipt = state.lastReceipt;
  if (!receipt || !receipt.submitted_at) return "";
  const status = receipt.status || "已提交";
  const title = receipt.title || "处理结果";
  const submittedAt = String(receipt.submitted_at || "").replace("T", " ").replace("+08:00", "");
  const nextDeadline = receipt.todo?.deadline || receipt.deadline || "";
  const nextStep = receipt.next_step || receipt.todo?.next_step || "";
  return `
    <section class="schedule-receipt-banner">
      <div>
        <strong>本轮已回填：${escapeHtml(status)}</strong>
        <span>${escapeHtml(receipt.customer || "客户事项")} · ${escapeHtml(title)}</span>
      </div>
      <p>${escapeHtml(nextStep || receipt.resolution || "处理结果已记录。")}</p>
      <div class="chip-row">
        ${submittedAt ? `<span class="chip teal">提交：${escapeHtml(submittedAt)}</span>` : ""}
        ${nextDeadline ? `<span class="chip amber">下次：${escapeHtml(String(nextDeadline).replace("T", " ").replace("+08:00", ""))}</span>` : ""}
        ${receipt.relative_path ? `<span class="chip">工作回执已留存</span>` : ""}
      </div>
    </section>
  `;
}

function renderScheduleSection(payload) {
  const todos = payload.risk_todos || [];
  const calendarStatus = payload.calendar_status || {};
  const prepItems = buildPrepItems(payload);
  const statusLine = calendarStatus.error || (
    calendarStatus.fetched_at
      ? `${calendarStatus.label || "飞书日程"} · ${String(calendarStatus.fetched_at).replace("T", " ").replace("+08:00", "")}`
      : calendarStatus.label || "飞书日程待同步"
  );
  const meta = `
    <div class="schedule-sync-meta">
      <strong>${escapeHtml(statusLine)}</strong>
      <span>飞书 ${calendarStatus.feishu_count || 0} 条 / 工作台 deadline ${calendarStatus.deadline_count || 0} 条 / 待匹配 ${calendarStatus.unmatched_count || 0} 条</span>
    </div>
  `;
  const grouped = scheduleGroupDefinitions().map(([bucket, label]) => {
    const groupItems = todos.filter((item) => (item.schedule_bucket || "unscheduled") === bucket);
    if (!groupItems.length) return "";
    return `
      <section class="schedule-group">
        <div class="schedule-group-head">
          <strong>${escapeHtml(label)}</strong>
          <span>${groupItems.length} 条</span>
        </div>
        <div class="schedule-group-grid">
          ${groupItems.slice(0, 8).map(renderScheduleCard).join("")}
        </div>
      </section>
    `;
  }).join("");
  const prepCards = prepItems.slice(0, todos.length ? 2 : 4).map((item) => `
    <article class="prep-card clickable-card" data-customer="${escapeHtml(item.customer)}">
      <div class="eyebrow">${escapeHtml(item.badge)}</div>
      <h3>${escapeHtml(item.customer)}</h3>
      <ul>
        <li>必须确认：${escapeHtml(item.mustConfirm)}</li>
        <li>不能直接答应：${escapeHtml(item.cannotPromise)}</li>
        <li>建议口径：${escapeHtml(item.talkingPoints)}</li>
      </ul>
    </article>
  `);
  const prepGroup = prepCards.length ? `
    <section class="schedule-group">
      <div class="schedule-group-head">
        <strong>会前准备</strong>
        <span>${prepCards.length} 条</span>
      </div>
      <div class="schedule-group-grid">${prepCards.join("")}</div>
    </section>
  ` : "";
  document.querySelector("#scheduleList").innerHTML = `${renderScheduleReceiptBanner()}${meta}${grouped}${prepGroup}`
    || '<div class="focus-empty">当前没有日程或 deadline。</div>';
}

function renderSyncStatus(payload) {
  document.querySelector("#syncStatus").innerHTML = `
    <strong>${escapeHtml(payload.label || "同步状态未知")}</strong>
    <span>${escapeHtml(payload.detail || "")}</span>
  `;
}

function renderReports(messageDigest = {}) {
  const latestDate = messageDigest.latest_date;
  if (!latestDate) {
    document.querySelector("#reportMeta").textContent = "今天还没有生成项目群日报";
    document.querySelector("#reportList").innerHTML = '<div class="focus-empty">暂无项目群日报。</div>';
    return;
  }

  document.querySelector("#reportMeta").textContent = messageDigest.is_stale
    ? `最新项目群日报 ${latestDate}，今天 ${messageDigest.expected_date || ""} 未生成`
    : `今天 ${latestDate} 项目群日报已生成`;

  document.querySelector("#reportList").innerHTML = messageDigest.days.map((day) => `
    <article class="report-card">
      <div class="report-card-head">
        <h3>${escapeHtml(day.date)} 项目群日报</h3>
        <span class="health-badge health-${escapeHtml(day.health || "灰")}">${escapeHtml(activityLabel(day.health || "灰"))}</span>
      </div>
      <div class="daily-report">
        <section class="daily-report-summary">
          <p>${escapeHtml(reportPreviewText(day.summary || "暂无摘要"))}</p>
          <div class="daily-report-metrics">
            <span>覆盖项目群 <strong>${escapeHtml(day.file_count || 0)}</strong></span>
            <span>归纳素材 <strong>${escapeHtml(day.message_count || 0)}</strong></span>
            <span>活跃项目群 <strong>${escapeHtml((day.items || []).filter((item) => Number(item.message_count || 0) > 0).length)}</strong></span>
          </div>
        </section>
        ${renderDailyReportBlock("一、今日进展概述", day.overview_points || [], "今日没有形成明确进展。")}
        ${renderDailyReportBlock("二、群内问题与待对齐点", day.issue_points || [], "群内没有形成需要单独提示的问题。")}
        ${renderDailyReportBlock("三、后续计划", day.plan_points || [], "后续计划暂时没有新的变化。")}
        ${renderDailyReportBlock("四、需要关注事项", day.coordination_points || [], "当前没有需要额外关注的项目背景。")}
        <section class="daily-report-section">
          <h4>五、项目群明细</h4>
          ${(day.items || []).map((item, index) => {
            registerContext("pm_item", {
              ...item,
              customer: item.name,
              title: `${item.name} 项目群动态`,
              date: day.date,
            }, pmWorkflowKey(day, item));
            return renderGroupReportSection(item, index);
          }).join("") || '<div class="focus-empty">今天没有可展示的项目群动态。</div>'}
        </section>
      </div>
    </article>
  `).join("");
}

const pricingInputs = {
  actualDays: document.querySelector("#pricingActualDays"),
  internalCost: document.querySelector("#pricingInternalCost"),
  quotedDays: document.querySelector("#pricingQuotedDays"),
  billingRate: document.querySelector("#pricingBillingRate"),
  targetMargin: document.querySelector("#pricingTargetMargin"),
  selfCostEnabled: document.querySelector("#pricingSelfCostEnabled"),
};

const cny = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  maximumFractionDigits: 0,
});

function numericValue(input) {
  const value = Number(input.value);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function percent(value) {
  if (!Number.isFinite(value)) return "0%";
  return `${(value * 100).toFixed(1).replace(/\.0$/, "")}%`;
}

function adviceForMargin(rate) {
  if (rate >= 0.5) return "优秀，项目盈利能力很强";
  if (rate >= 0.4) return "健康，行业良好水平";
  if (rate >= 0.3) return "及格，需关注成本控制";
  if (rate >= 0.2) return "偏低，建议优化报价或降低成本";
  return "不健康，项目可能亏损";
}

function renderPricingCalculator() {
  const actualDays = numericValue(pricingInputs.actualDays);
  const internalCost = numericValue(pricingInputs.internalCost);
  const quotedDays = numericValue(pricingInputs.quotedDays);
  const billingRate = numericValue(pricingInputs.billingRate);
  const targetRate = numericValue(pricingInputs.targetMargin) / 100;
  const revenue = quotedDays * billingRate;
  const selfCost = pricingInputs.selfCostEnabled.checked ? revenue * 0.1 : 0;
  const internalTotal = actualDays * internalCost;
  const totalCost = selfCost + internalTotal;
  const grossProfit = revenue - totalCost;
  const marginRate = revenue > 0 ? grossProfit / revenue : 0;
  const passed = revenue > 0 && marginRate >= targetRate;
  const values = {
    actualDays: pricingInputs.actualDays.value,
    internalCost: pricingInputs.internalCost.value,
    quotedDays: pricingInputs.quotedDays.value,
    billingRate: pricingInputs.billingRate.value,
    targetMargin: pricingInputs.targetMargin.value,
    selfCostEnabled: pricingInputs.selfCostEnabled.checked,
  };
  const model = { revenue, selfCost, internalTotal, grossProfit, marginRate, targetRate, passed };

  document.querySelector("#pricingResult").innerHTML = `
    <div class="pricing-metric">
      <span>成交金额</span>
      <strong>${cny.format(revenue)}</strong>
    </div>
    <div class="pricing-metric">
      <span>自成本</span>
      <strong>${cny.format(selfCost)}</strong>
    </div>
    <div class="pricing-metric">
      <span>内部成本</span>
      <strong>${cny.format(internalTotal)}</strong>
    </div>
    <div class="pricing-metric ${grossProfit < 0 ? "negative" : ""}">
      <span>毛利</span>
      <strong>${cny.format(grossProfit)}</strong>
    </div>
    <div class="pricing-metric ${passed ? "pass" : "fail"}">
      <span>毛利率</span>
      <strong>${percent(marginRate)}</strong>
    </div>
    <div class="pricing-metric">
      <span>目标毛利率</span>
      <strong>${percent(targetRate)}</strong>
    </div>
    <div class="pricing-advice">
      ${passed ? "已达目标" : "未达目标"}。当前毛利率 ${percent(marginRate)}，目标毛利率 ${percent(targetRate)}。${adviceForMargin(marginRate)}
    </div>
    ${pricingReportBlockHtml(values, model)}
  `;
}

function syncInlinePricingInput(control) {
  const key = control?.dataset?.inlinePricing || "";
  const target = pricingInputs[key];
  if (!target) return;
  if (control.type === "checkbox") {
    target.checked = control.checked;
  } else {
    target.value = control.value;
  }
  renderPricingCalculator();
  const result = document.querySelector("[data-inline-pricing-result]");
  if (result) result.innerHTML = acceleratorPricingResultHtml(inlinePricingValues());
}

function applyPricingPreset(name) {
  const presets = {
    general: {
      actualDays: "",
      internalCost: "1500",
      quotedDays: "",
      billingRate: "2000",
      targetMargin: "30",
      selfCostEnabled: true,
    },
  };
  const preset = presets[name];
  if (!preset) return;
  pricingInputs.actualDays.value = preset.actualDays;
  pricingInputs.internalCost.value = preset.internalCost;
  pricingInputs.quotedDays.value = preset.quotedDays;
  pricingInputs.billingRate.value = preset.billingRate;
  pricingInputs.targetMargin.value = preset.targetMargin;
  pricingInputs.selfCostEnabled.checked = preset.selfCostEnabled;
  renderPricingCalculator();
}

function applyDashboard(payload, options = {}) {
  state.contextIndex = {};
  state.dashboard = payload;
  if (payload.prospecting?.leads?.length || !state.prospecting?.leads?.length) {
    state.prospecting = payload.prospecting || state.prospecting;
  }
  renderTopbar(payload);
  renderSidebar(payload);
  renderSalesBrainPanel(payload);
  renderFocusBrief(payload);
  renderPerformanceStrip(payload);
  renderSalesFlowSummary(payload);
  renderStats(payload);
  renderSchedulePreview(payload);
  renderPriorityList(payload.battle_actions || []);
  renderRiskPanel(payload.risk_alerts || []);
  renderSnapshot(payload.fxiaoke_status || {});
  renderDigestSummary(payload.message_digest || {});
  renderCustomerCards(payload.deal_board || []);
  renderKnowledgeRoutes(payload.knowledge_timeline || []);
  renderScheduleSection(payload);
  renderReports(payload.message_digest || {});

  const requestedCustomer = options.clearSelection ? "" : (options.preserveCustomer || state.selectedCustomer);
  const requestedContextKey = options.clearSelection ? "" : (options.preserveContextKey || state.activeContextKey);
  const requestedContext = requestedContextKey ? state.contextIndex[requestedContextKey] : null;
  let selected = findCustomer(requestedCustomer);
  let selectedContextKey = requestedContext ? requestedContextKey : null;
  if (!selected && requestedContext) {
    selected = fallbackCustomerFromContext(requestedCustomer, requestedContext);
  }
  if (!selected && options.preventDefaultSelection && requestedCustomer) {
    selected = fallbackCustomerFromContext(requestedCustomer, {
      type: options.contextType || "action",
      key: requestedContextKey || "",
      item: {
        customer: requestedCustomer,
        title: options.title || "",
        evidence: options.evidence || "",
        action: options.action || "",
        next_step: options.nextStep || "",
      },
    });
    selectedContextKey = null;
  }
  if (!selected && options.allowDefaultSelection && !options.preventDefaultSelection) {
    const defaultContextEntry = Object.entries(state.contextIndex).find(([, context]) => {
      const item = context.item || {};
      return ["action", "schedule", "risk"].includes(context.type) && (item.customer || item.name);
    });
    if (defaultContextEntry) {
      const [defaultContextKey, defaultContext] = defaultContextEntry;
      selected = fallbackCustomerFromContext(defaultContext.item?.customer || defaultContext.item?.name || "", defaultContext);
      selectedContextKey = defaultContextKey;
    }
    selected = selected
      || payload.deal_board?.find((item) => item.bucket === "active")
      || payload.deal_board?.[0]
      || null;
  }
  if (selected) {
    selectCustomer(selected.name, { scroll: false, contextKey: selectedContextKey });
  } else if (options.clearSelection) {
    state.selectedCustomer = null;
    state.activeContextKey = null;
    renderCustomerFocus(null);
  } else {
    renderCustomerFocus(null);
  }
  renderActiveWorkspace();
}

function refreshRenderedDashboard(options = {}) {
  if (!state.liveDashboard) return;
  const rawPayload = state.demoMode
    ? buildDemoDashboard(state.liveDashboard)
    : deepClone(state.liveDashboard);
  const payload = applyWorkflowToPayload(rawPayload);
  applyDashboard(payload, options);
}

function setDemoMode(enabled) {
  state.demoMode = Boolean(enabled);
  updateModeToggle();
  refreshRenderedDashboard();
}

async function loadDashboard(options = {}) {
  const payload = await getJson("/api/dashboard");
  state.liveDashboard = payload;
  refreshRenderedDashboard({
    allowDefaultSelection: Boolean(options.allowDefaultSelection) && !options.preventDefaultSelection && !options.clearSelection,
    ...options,
  });
}

async function loadAccountAdvancement() {
  try {
    const payload = await getJson("/api/account-advancement");
    state.accountAdvancement = payload;
    if (!state.selectedAccountId || !payload.accounts?.some((account) => account.id === state.selectedAccountId)) {
      state.selectedAccountId = "";
    }
    if (state.dashboard) renderSidebar(state.dashboard);
    refreshAccountNavCount(state.dashboard || {});
    if (state.activeWorkspace === "accounts") {
      renderGlobalWorkspace();
    } else if (["today", "customer"].includes(state.activeWorkspace)) {
      renderAcceleratorWorkbench();
    }
  } catch (error) {
    state.accountAdvancement = {
      ok: false,
      error: error.message,
      accounts: [],
      stages: [],
      summary: { account_count: 0, channel_count: 0, deadline_account_count: 0, gap_count: 0 },
    };
    if (state.activeWorkspace === "accounts") {
      renderGlobalWorkspace();
    } else if (["today", "customer"].includes(state.activeWorkspace)) {
      renderAcceleratorWorkbench();
    }
  }
}

async function refreshWorkbench() {
  const results = await Promise.allSettled([
    loadDashboard({ preserveCustomer: state.selectedCustomer, preserveContextKey: state.activeContextKey, preventDefaultSelection: true }),
    loadAccountAdvancement(),
  ]);
  const failed = results.find((result) => result.status === "rejected");
  if (failed) {
    state.lastReceipt = { status: `刷新失败：${failed.reason?.message || "部分数据未更新"}` };
    refreshRenderedDashboard({ preserveCustomer: state.selectedCustomer, preserveContextKey: state.activeContextKey, preventDefaultSelection: true });
  }
}

async function loadSyncStatus() {
  try {
    const payload = await getJson("/api/messages/status");
    renderSyncStatus(payload);
  } catch (error) {
    renderSyncStatus({
      label: "同步链路检查失败",
      detail: error.message,
    });
  }
}

async function syncMessages() {
  const button = document.querySelector("#syncMessages");
  const result = document.querySelector("#syncResult");
  button.textContent = "生成中...";
  result.textContent = "正在同步并生成项目群日报...";
  try {
    const payload = await getJson("/api/messages/sync", { method: "POST" });
    result.textContent = payload.output.join("\n");
    state.liveDashboard = deepClone(state.liveDashboard || {});
    await loadSyncStatus();
    await loadDashboard();
  } catch (error) {
    result.textContent = error.message;
  } finally {
    button.textContent = "生成日报";
  }
}

async function syncFxiaokeSnapshot() {
  const button = document.querySelector("#syncFxiaoke");
  const original = button.textContent;
  button.textContent = "同步中...";
  button.disabled = true;
  try {
    await postJson("/api/fxiaoke/sync-preview", {});
    await loadDashboard();
  } catch (error) {
    state.lastReceipt = { status: `业绩快照同步失败：${error.message}` };
    refreshRenderedDashboard();
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

async function syncCalendar() {
  const button = document.querySelector("#syncCalendar");
  const original = button.textContent;
  button.textContent = "同步中...";
  button.disabled = true;
  try {
    await postJson("/api/calendar/sync", {});
    await loadDashboard();
  } catch (error) {
    state.lastReceipt = { status: `日程同步失败：${error.message}` };
    refreshRenderedDashboard();
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

async function loadIntelForCustomer(name) {
  const current = findCustomer(name);
  if (!current) return;
  if (state.demoMode && current.demo_intel) {
    renderCustomerFocus(current, current.demo_intel, false);
    return;
  }
  if (state.intelCache[name]) {
    renderCustomerFocus(current, state.intelCache[name], false);
    return;
  }
  renderCustomerFocus(current, null, true);
  try {
    const payload = await getJson(`/api/intel?q=${encodeURIComponent(name)}`);
    state.intelCache[name] = payload;
    if (state.selectedCustomer === current.name) {
      renderCustomerFocus(current, payload, false);
    }
  } catch (error) {
    renderCustomerFocus(current, {
      message_signals: [],
      local_signals: [{
        source: "客户情报读取失败",
        updated_at: "",
        snippet: error.message,
      }],
      public_signals: [],
    }, false);
  }
}

async function convertWorkflowContext(contextKey, target) {
  const context = state.contextIndex[contextKey];
  if (!context) return;
  if (state.demoMode) {
    state.lastReceipt = { status: "演示模式不写入真实状态" };
    refreshRenderedDashboard();
    return;
  }
  const item = context.item || {};
  const customer = item.customer || item.name || inferCustomerFromText(`${item.summary || ""} ${item.task || ""}`)?.name || state.selectedCustomer || "未绑定客户";
  const sourceTitle = contextTitle(context, findCustomer(customer) || {});
  const sourceText = contextEvidence(context, findCustomer(customer) || {});
  const targetLabel = {
    risk: "已转风险",
    action: "已转动作",
    schedule: "已转日程",
    ignore: "已忽略",
    resolved: "风险解除",
    done: "已处理",
  }[target] || "已转动作";
  const actionItem = {
    customer,
    title: sourceTitle,
    action: item.action || item.task || item.summary || sourceTitle,
    risk: sourceText,
    signal: contextSourceLabel(context),
    date: item.date || "",
  };
  const payload = {
    kind: context.type,
    key: contextKey,
    target,
    status: targetLabel,
    customer,
    title: sourceTitle,
    source_view: contextSourceLabel(context),
    item: target === "risk"
      ? {
        customer,
        title: sourceTitle,
        task: sourceTitle,
        risk: sourceText,
        summary: item.summary || sourceText,
        recommendation: item.next_step || item.action || "进入客户作战室确认责任人和截止时间",
        date: item.date || "",
      }
      : actionItem,
  };
  const result = await postJson("/api/workflow/update", payload);
  state.workflow = result.workflow_state || state.workflow;
  state.lastReceipt = { status: `${sourceTitle} ${targetLabel}` };
  await loadDashboard({
    preserveCustomer: customer,
    preserveContextKey: contextKey,
    preventDefaultSelection: true,
  });
  setActiveNav("section-overview");
}

async function retryCalendar(todoId) {
  state.lastReceipt = { status: "正在同步飞书任务提醒" };
  await postJson("/api/risk-todos/calendar/retry", { todo_id: todoId });
  await loadDashboard();
}

async function submitEvidenceForm(form) {
  const result = form.querySelector("#evidenceResult");
  result.textContent = "正在提交...";
  const data = Object.fromEntries(new FormData(form).entries());
  const returnSection = state.returnSectionAfterSubmit || "section-overview";
  if (!data.status) {
    result.textContent = "先选择一个处理出口。";
    return;
  }
  if (!String(data.resolution || "").trim()) {
    result.textContent = "先填写这次实际推进到哪了。";
    return;
  }
  if (data.status !== "已处理") {
    if (!String(data.next_step || "").trim()) {
      result.textContent = "未闭环时需要填写下一步动作。";
      return;
    }
    if (!String(data.deadline || "").trim()) {
      result.textContent = "未闭环时需要填写下一次时间。";
      return;
    }
  }
  data.sync_calendar = form.querySelector('input[name="sync_calendar"]').checked;
  try {
    const payload = await postJson("/api/risk-evidence", data);
    state.lastReceipt = payload.receipt || { status: "已提交" };
    result.textContent = `${payload.message}；${payload.receipt?.status || "已提交"}`;
    const isScheduleSubmit = data.object_type === "schedule";
    const shouldClearSelection = isScheduleSubmit || payload.receipt?.status === "已闭环";
    await loadDashboard({
      preserveCustomer: shouldClearSelection ? "" : data.customer,
      preserveContextKey: shouldClearSelection ? "" : data.workflow_key,
      preventDefaultSelection: true,
      clearSelection: shouldClearSelection,
      contextType: data.object_type,
      title: data.title,
      evidence: data.evidence,
      action: data.action,
      nextStep: data.next_step,
    });
    if (payload.todo?.id) {
      renderScheduleSection(state.dashboard || {});
      if (returnSection === "section-schedule") {
        openAcceleratorSection("section-schedule");
      } else {
        openAcceleratorSection("section-overview");
      }
      state.returnSectionAfterSubmit = null;
      return;
    }
    if (data.object_type === "schedule") {
      renderScheduleSection(state.dashboard || {});
      if (returnSection === "section-schedule") {
        openAcceleratorSection("section-schedule");
      } else {
        openAcceleratorSection("section-overview");
      }
      state.returnSectionAfterSubmit = null;
      return;
    }
    if (payload.receipt?.status === "已闭环") {
      openAcceleratorSection("section-overview");
      state.returnSectionAfterSubmit = null;
      return;
    }
    openAcceleratorSection("section-overview");
    state.returnSectionAfterSubmit = null;
  } catch (error) {
    result.textContent = error.message;
  }
}

function selectCustomer(name, options = {}) {
  const context = options.contextKey ? state.contextIndex[options.contextKey] : null;
  const item = findCustomer(name) || (context ? fallbackCustomerFromContext(name, context) : null);
  if (!item) return;
  state.activeWorkspace = "customer";
  const nextContextKey = options.contextKey || null;
  if (state.selectedCustomer !== item.name || state.activeContextKey !== nextContextKey) {
    state.focusTab = "background";
  }
  state.selectedCustomer = item.name;
  state.activeContextKey = nextContextKey;
  if (!options.preservePane) {
    state.acceleratorPane = "next";
    state.pathScope = "customer";
    state.routeFilterProject = "";
  }
  renderSidebar(state.dashboard);
  renderPriorityList(state.dashboard?.battle_actions || []);
  renderRiskPanel(state.dashboard?.risk_alerts || []);
  renderCustomerCards(state.dashboard?.deal_board || []);
  renderKnowledgeRoutes(state.dashboard?.knowledge_timeline || []);
  renderScheduleSection(state.dashboard || {});
  const knownCustomer = findCustomer(item.name);
  renderCustomerFocus(item, state.intelCache[item.name] || null, Boolean(knownCustomer) && !state.intelCache[item.name] && !(state.demoMode && item.demo_intel));
  if (knownCustomer) {
    loadIntelForCustomer(item.name);
  }
  renderAcceleratorWorkbench();
  if (options.scroll === true) {
    scrollToSection("section-focus");
  }
}

document.querySelector("#refreshDashboard").addEventListener("click", refreshWorkbench);
document.querySelector("#syncMessages").addEventListener("click", syncMessages);
document.querySelector("#syncFxiaoke").addEventListener("click", syncFxiaokeSnapshot);
document.querySelector("#syncCalendar").addEventListener("click", syncCalendar);
document.querySelectorAll("[data-mode-toggle]").forEach((button) => {
  button.addEventListener("click", () => setDemoMode(button.dataset.modeToggle === "demo"));
});
document.querySelector("#presetGeneralPrivate").addEventListener("click", () => applyPricingPreset("general"));
Object.values(pricingInputs).forEach((input) => {
  input.addEventListener("input", renderPricingCalculator);
  input.addEventListener("change", renderPricingCalculator);
});

document.addEventListener("input", (event) => {
  const inlinePricing = event.target.closest("[data-inline-pricing]");
  if (inlinePricing) syncInlinePricingInput(inlinePricing);
});

document.addEventListener("change", (event) => {
  const inlinePricing = event.target.closest("[data-inline-pricing]");
  if (inlinePricing) syncInlinePricingInput(inlinePricing);
});

document.addEventListener("submit", (event) => {
  if (event.target.matches("#evidenceForm")) {
    event.preventDefault();
    submitEvidenceForm(event.target);
  }
  if (event.target.matches("#manualTodoForm")) {
    event.preventDefault();
    submitManualTodo(event.target);
  }
});

document.addEventListener("click", (event) => {
  if (event.target.closest("a.mini-link")) {
    event.stopPropagation();
    return;
  }

  const statusChoice = event.target.closest("[data-evidence-status]");
  if (statusChoice) {
    event.preventDefault();
    event.stopPropagation();
    applyEvidenceStatusChoice(statusChoice.closest("form"), statusChoice.dataset.evidenceStatus);
    return;
  }

  const acceleratorFilter = event.target.closest("[data-accelerator-filter]");
  if (acceleratorFilter) {
    event.preventDefault();
    event.stopPropagation();
    state.acceleratorFilter = acceleratorFilter.dataset.acceleratorFilter || "todo";
    state.acceleratorFilterLocked = true;
    renderAcceleratorWorkbench();
    return;
  }

  const acceleratorFilterOpen = event.target.closest("[data-accelerator-filter-open]");
  if (acceleratorFilterOpen) {
    event.preventDefault();
    event.stopPropagation();
    state.acceleratorFilter = acceleratorFilterOpen.dataset.acceleratorFilterOpen || "todo";
    state.acceleratorFilterLocked = true;
    renderAcceleratorWorkbench();
    return;
  }

  const acceleratorPane = event.target.closest("[data-accelerator-pane]");
  if (acceleratorPane) {
    event.preventDefault();
    event.stopPropagation();
    state.acceleratorPane = acceleratorPane.dataset.acceleratorPane || "next";
    if (state.acceleratorPane === "path") {
      state.pathScope = acceleratorPane.dataset.pathScope || "customer";
      state.routeFilterProject = "";
    }
    renderAcceleratorWorkbench();
    return;
  }

  const routeFilter = event.target.closest("[data-route-filter-project]");
  if (routeFilter) {
    event.preventDefault();
    event.stopPropagation();
    state.routeFilterProject = routeFilter.dataset.routeFilterProject || "";
    renderAcceleratorWorkbench();
    return;
  }

  const globalRouteFilter = event.target.closest("[data-global-route-filter]");
  if (globalRouteFilter) {
    event.preventDefault();
    event.stopPropagation();
    state.globalRouteFilterProject = globalRouteFilter.dataset.globalRouteFilter || "";
    if (state.activeWorkspace === "knowledge") {
      renderGlobalWorkspace();
    } else {
      renderGlobalPathsTool();
    }
    return;
  }

  if (event.target.closest("#acceleratorRefresh")) {
    event.preventDefault();
    event.stopPropagation();
    loadDashboard({ preserveCustomer: state.selectedCustomer, preserveContextKey: state.activeContextKey, preventDefaultSelection: true });
    return;
  }

  const pricingCopy = event.target.closest("[data-pricing-script-copy]");
  if (pricingCopy) {
    event.preventDefault();
    event.stopPropagation();
    const box = pricingCopy.closest(".pricing-report-box");
    const output = box?.querySelector("[data-pricing-script-output]");
    const stateNode = box?.querySelector("[data-pricing-copy-state]");
    const text = output?.value || output?.textContent || "";
    if (!text.trim()) {
      if (stateNode) stateNode.textContent = "暂无可复制话术";
      return;
    }
    const onDone = () => {
      if (stateNode) stateNode.textContent = "已复制，可直接粘贴报备";
    };
    const onFail = () => {
      output?.focus();
      output?.select();
      document.execCommand?.("copy");
      onDone();
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(onDone).catch(onFail);
    } else {
      onFail();
    }
    return;
  }

  const convertButton = event.target.closest("[data-workflow-convert]");
  if (convertButton) {
    event.preventDefault();
    event.stopPropagation();
    convertWorkflowContext(convertButton.dataset.contextKey, convertButton.dataset.workflowConvert).catch((error) => {
      state.lastReceipt = { status: error.message };
      refreshRenderedDashboard();
    });
    return;
  }

  const retryButton = event.target.closest("[data-retry-calendar]");
  if (retryButton) {
    event.preventDefault();
    event.stopPropagation();
    retryCalendar(retryButton.dataset.retryCalendar).catch((error) => {
      state.lastReceipt = { status: error.message };
      refreshRenderedDashboard();
    });
    return;
  }

  const accountStageFilter = event.target.closest("[data-account-stage-filter]");
  if (accountStageFilter) {
    event.preventDefault();
    event.stopPropagation();
    state.accountStageFilter = accountStageFilter.dataset.accountStageFilter || "";
    renderGlobalWorkspace();
    return;
  }

  const accountSelect = event.target.closest("[data-account-select]");
  if (accountSelect) {
    event.preventDefault();
    event.stopPropagation();
    state.selectedAccountId = accountSelect.dataset.accountSelect || "";
    renderGlobalWorkspace();
    return;
  }

  const accountCapture = event.target.closest("[data-account-capture]");
  if (accountCapture) {
    event.preventDefault();
    event.stopPropagation();
    const account = findAccountAdvancement(accountCapture.dataset.accountCapture);
    if (!account) return;
    state.selectedAccountId = account.id || state.selectedAccountId;
    state.manualTodoDraft = accountCaptureDraft(account, {
      title: accountCapture.dataset.accountCaptureTitle || "",
      source: accountCapture.dataset.accountCaptureSource || "",
      target: accountCapture.dataset.accountCaptureTarget || "now",
    });
    openToolWindow("manual-todo");
    return;
  }

  const toolOpen = event.target.closest("[data-tool-open]");
  if (toolOpen) {
    event.preventDefault();
    event.stopPropagation();
    if (toolOpen.dataset.toolOpen === "manual-todo") state.manualTodoDraft = null;
    openToolWindow(toolOpen.dataset.toolOpen);
    return;
  }

  if (event.target.closest("#toolClose") || event.target.closest("#toolBackdrop")) {
    event.preventDefault();
    event.stopPropagation();
    closeToolWindow();
    return;
  }

  const prospectingRun = event.target.closest("[data-prospecting-run]");
  if (prospectingRun) {
    event.preventDefault();
    event.stopPropagation();
    runProspectingNow();
    return;
  }

  const prospectingDecision = event.target.closest("[data-prospecting-decision]");
  if (prospectingDecision) {
    event.preventDefault();
    event.stopPropagation();
    updateProspectingLead(prospectingDecision.dataset.leadId, prospectingDecision.dataset.prospectingDecision);
    return;
  }

  const newsCustomer = event.target.closest("[data-news-customer]");
  if (newsCustomer) {
    event.preventDefault();
    event.stopPropagation();
    state.newsCustomer = newsCustomer.dataset.newsCustomer || "";
    openToolWindow("customer-news");
    return;
  }

  const sectionNav = event.target.closest("[data-section-nav]");
  if (sectionNav) {
    event.preventDefault();
    event.stopPropagation();
    const sectionId = sectionNav.dataset.sectionNav;
    const acceleratorNavPane = sectionNav.dataset.acceleratorNavPane || "";
    if (openAcceleratorSection(sectionId, acceleratorNavPane)) return;
    setActiveNav(sectionId, acceleratorNavPane);
    closeToolWindow();
    scrollToSection(sectionId);
    return;
  }

  const statJump = event.target.closest("[data-jump-section]");
  if (statJump) {
    event.preventDefault();
    event.stopPropagation();
    const sectionId = statJump.dataset.jumpSection;
    if (openAcceleratorSection(sectionId)) return;
    setActiveNav(sectionId);
    closeToolWindow();
    scrollToSection(sectionId);
    return;
  }

  const focusTab = event.target.closest("[data-focus-tab]");
  if (focusTab) {
    event.preventDefault();
    event.stopPropagation();
    state.focusTab = focusTab.dataset.focusTab || "background";
    document.querySelectorAll("[data-focus-tab]").forEach((button) => {
      const active = button.dataset.focusTab === state.focusTab;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
    document.querySelectorAll("[data-focus-tab-panel]").forEach((panel) => {
      panel.classList.toggle("is-active", panel.dataset.focusTabPanel === state.focusTab);
    });
    return;
  }

  const customerTarget = event.target.closest("[data-customer]");
  if (customerTarget) {
    const sourceSection = customerTarget.closest("#section-schedule") ? "section-schedule" : null;
    const context = customerTarget.dataset.contextKey ? state.contextIndex[customerTarget.dataset.contextKey] : null;
    state.returnSectionAfterSubmit = sourceSection && context?.type === "schedule" ? sourceSection : null;
    state.activeWorkspace = "customer";
    state.acceleratorFilterLocked = false;
    closeToolWindow();
    setActiveNav("section-overview", "war");
    selectCustomer(customerTarget.dataset.customer, {
      scroll: false,
      contextKey: customerTarget.dataset.contextKey || null,
    });
    return;
  }

  const routeTarget = event.target.closest("[data-project-route]");
  if (routeTarget) {
    const project = routeTarget.dataset.projectRoute;
    state.expandedProject = state.expandedProject === project ? null : project;
    renderKnowledgeRoutes(state.dashboard?.knowledge_timeline || []);
    const matched = findCustomer(project);
    if (matched) {
      selectCustomer(matched.name, {
        scroll: false,
        contextKey: routeTarget.dataset.contextKey || null,
      });
    }
  }
});

renderPricingCalculator();
updateModeToggle();
loadSyncStatus();
loadDashboard().catch((error) => {
  document.querySelector("#statsGrid").innerHTML = `<div class="focus-empty">${escapeHtml(error.message)}</div>`;
});
loadAccountAdvancement().catch((error) => {
  state.accountAdvancement = {
    ok: false,
    error: error.message,
    accounts: [],
    stages: [],
    summary: { account_count: 0, channel_count: 0, deadline_account_count: 0, gap_count: 0 },
  };
  if (state.activeWorkspace === "accounts") renderGlobalWorkspace();
});
