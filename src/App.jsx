import AgentWorkspace from './AgentWorkspace.jsx';
import BusinessOverview from './BusinessOverview.jsx';
import {Stack as AgentStack,SquaresFour as AgentSidebar,UsersThree as AgentTree,CalendarDots as AgentCalendar,Broadcast as AgentScan,FolderSimple as AgentBooks,Buildings as NavBuildings,ChartBar as NavChart,Calculator as NavCalculator,FileText as NavFile,ArrowsClockwise as NavSync,Sparkle as NavSparkle,Receipt as NavReceipt,ChatCircle as NavChat,Plus as NavPlus} from '@phosphor-icons/react';
import {ProgressComposer} from './ProgressComposer.jsx';
import ProjectNotifications from './ProjectNotifications.jsx';
import InvoiceVault from './InvoiceVault.jsx';
import { contextForProject } from './signalProjectContext.js';
import { SalesPursuit } from './SalesPursuit.jsx';
import { useWorkbenchMotion } from './WorkbenchMotion.jsx';
import { WorkbenchLoading, UpdateProgress } from './WorkbenchLoading.jsx';
import { needsWorkbenchData, EMPTY_WORKBENCH_VALUE } from './workbenchStartup.js';
import { selectQuoteIdentity, quoteIdentity as savedQuoteIdentity } from './quoteIdentity.js';
import { ProjectFollowups } from './ProjectFollowups.jsx';
import { MaterialLibrary } from "./MaterialLibrary.jsx";
import { CommunicationSync } from './CommunicationSync.jsx';
import { AIHot } from './AIHot.jsx';
import { APPROVAL_KEY, COST_FIELDS, restoreApproval, syncApprovalFromQuote, editApproval, formatApproval } from "./approvalDraft.js";
import { QUICK_QUOTE_KEY, restoreQuote, calculateQuote } from "./quickQuote.js";
import { shouldClearProject, OVERVIEW_KEY } from "./projectOverview.js";
import { createWorkbenchNavigation, readNavigationContext } from "./workbenchNavigation.js";
import { DiscardChangesProvider, NavigationGuardContext, useDiscardChanges } from "./DiscardDialog.jsx";
import { splitScheduleArchive, splitReceiptArchive, isScheduleAutoArchived } from './scheduleArchive.js';
import { splitCurrentActions, cutoffKey } from "./freshness.js";
import React, { useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { Dialog } from "@astryxdesign/core/Dialog";
import { TextArea } from "@astryxdesign/core/TextArea";
import { TextInput } from "@astryxdesign/core/TextInput";
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl";
import { gsap } from "gsap";
import {
  CartesianGrid,
  Line,
  LineChart,
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowRight,
  BarChart3,
  Bell,
  Bot,
  BrainCircuit,
  BookOpen,
  Building2,
  Calculator,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Clock3,
  Copy,
  Database,
  ExternalLink,
  FileCheck2,
  FileText,
  Inbox,
  ListTodo,
  Mail,
  MessageSquareText,
  Orbit,
  Paperclip,
  Plus,
  RefreshCw,
  RotateCcw,
  Send,
  ShieldCheck,
  Sparkles,
  Target,
  X,
} from "lucide-react";
import { api, loadWorkbenchData } from "./api.js";
import { ProjectWorkspace, ReportSync } from "./ProjectWorkspace.jsx";
import { CrmConnect } from "./CrmConnect.jsx";
import { ProjectContractAudit } from "./ProjectContractAudit.jsx";
import CommercialWorkspace from "./CommercialWorkspace.jsx";
import DiscoveryWorkspace from "./DiscoveryWorkspace.jsx";

const STAGE_ORDER = ["qualify", "path", "contact", "opportunity"];
const STATUS_OPTIONS = [
  { value: "已处理", label: "本轮闭环", description: "完成并从活动队列移除" },
  { value: "待客户反馈", label: "等待客户", description: "已推进，等待客户回应" },
  { value: "待内部支持", label: "等待内部", description: "需要内部资源或确认" },
  { value: "推进中", label: "继续推进", description: "明确下一步和触发时间" },
];
const ACCOUNT_STATE_OPTIONS = [
  { value: "active", label: "推进中" },
  { value: "paused", label: "暂停" },
  { value: "won", label: "已成交" },
  { value: "lost", label: "已流失" },
  { value: "archived", label: "已归档" },
];

const NAV_ITEMS = [
  { id: "agent", label: "工作空间", icon: AgentSidebar, primary: true },
  { id: "projects", label: "客户作战室", icon: AgentTree, primary: true },
  { id: "customers", label: "客户目录", icon: NavBuildings, primary: true },
  { id: "discover", label: "战略客户雷达", icon: AgentScan, primary: true },
  { id: "performance", label: "合同业绩", icon: NavChart, primary: true },
  { id: "pricing", label: "报价与审批", icon: NavCalculator, primary: true },
  { id: "reports", label: "项目群日报", icon: NavFile },
  { id: "communications", label: "同步资料", icon: NavSync },
  { id: "aihot", label: "AI Hot 资讯", icon: NavSparkle, intelligence: true },
  { id: "accounts", label: "客户登记", icon: NavBuildings, nested: true },
  { id: "reminders", label: "日程 / Deadline", icon: AgentCalendar },
  { id: "invoices", label: "发票夹", icon: NavReceipt, intelligence: true },
  { id: "knowledge", label: "材料库", icon: AgentBooks, intelligence: true },
];

const CONTINUOUS_STEPS = [
  "AI洞察",
  "选择客户",
  "生成打法 / 补证据",
  "人工确认",
  "进入作战室执行",
  "提交回执",
  "安排下一次触发",
];

function text(value, fallback = "") {
  if (value === null || value === undefined) return fallback;
  if (Array.isArray(value)) return value.map((item) => text(item)).filter(Boolean).join("；");
  if (typeof value === "object") return Object.values(value).map((item) => text(item)).filter(Boolean).join("；");
  return String(value).trim() || fallback;
}

function formatDateTime(value, fallback = "未设置") {
  if (!value) return fallback;
  return String(value).replace("T", " ").replace("+08:00", "").slice(0, 16);
}

function formatAmount(value) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

function defaultDeadline() {
  const date = new Date(Date.now() + 24 * 60 * 60 * 1000);
  date.setHours(10, 0, 0, 0);
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function itemKey(item = {}) {
  return item.workflow_key || item.id || item.todo_id || `${item.customer || "item"}:${item.action || item.title || item.next_step || "action"}:${item.deadline || ""}`;
}

function workroomRequestId(item = {}) {
  return text(item.workroom_request_id) || `workroom:${item.workflow_key || item.id || item.todo_id || itemKey(item)}`.slice(0, 500);
}

function itemTitle(item = {}) {
  const raw = item.action || item.title || item.next_step || item.task || "待处理事项";
  if (
    (item.source_type === "workflow_receipt" || item.source_scope === "workflow_receipt")
    && /确认录音候选[：:]\s*/.test(raw)
  ) {
    return raw.replace(/确认录音候选[：:]\s*/g, "");
  }
  return raw;
}

function itemSource(item = {}) {
  if (item.source_type === "feishu_calendar" || item.source_scope === "feishu_calendar") return item.source_cached ? "飞书日程（缓存）" : "飞书日程";
  if (item.source_type === "transcript_intake" || item.source_scope === "transcript_intake") return "录音候选";
  if (item.source_scope === "workflow_receipt") return "工作回执";
  if (item.source_scope === "manual") return "销售捕捉";
  return item.signal || item.source_view || item.source || "工作台";
}

function isTranscriptCandidate(item = {}) {
  return item.source_type === "transcript_intake" || item.source_scope === "transcript_intake";
}

function formalReminderItems(items = []) {
  return uniqueItems(items).filter((item) => !isTranscriptCandidate(item) && !isScheduleAutoArchived(item));
}

function futureReminderItems(reminders = [], actions = []) {
  const activeIds = new Set(actions.map((item) => item.todo_id || item.id || item.workflow_key).filter(Boolean));
  return formalReminderItems(reminders).filter((item) => !activeIds.has(item.id || item.todo_id || item.workflow_key));
}

function evidenceLabel(value, fallback = "待补") {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return text(value.label || value.source_text || value.source, fallback);
  }
  const parts = text(value, fallback).split("；").filter((part) => !["pending_public_lookup", "none"].includes(part.trim().toLowerCase()));
  return parts.join("；") || fallback;
}

function prospectAdmissionMissing(lead = {}) {
  const missing = [];
  if (!/^https?:\/\//.test(lead.source_url || lead.url || "")) missing.push("真实信源");
  if (!text(lead.purchase_signal || lead.title)) missing.push("业务触发");
  if (!text(lead.entry_strategy || lead.youzan_fit)) missing.push("业务平台切口");
  if (["stale", "needs_time_evidence"].includes(lead.actionability) || lead.decision === "stale") missing.push("有效时间窗口");
  return missing;
}

function isVisibleProspectCandidate(lead = {}) {
  if (lead.user_surface) return lead.user_surface === "candidate";
  return ["pending", "verify"].includes(lead.decision || "pending") && lead.actionability === "actionable";
}

function prospectSurfaceItems(leads = [], surface) {
  return leads
    .filter((lead) => surface === "candidate" ? isVisibleProspectCandidate(lead) : lead.user_surface === surface)
    .sort((left, right) => Number(left.surface_rank || 999) - Number(right.surface_rank || 999));
}

function uniqueItems(items = []) {
  const seen = new Set();
  return items.filter((item) => {
    const key = itemKey(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function sameCustomer(left = "", right = "") {
  const normalize = (value) => String(value).replace(/[（(].*?[）)]/g, "").replace(/股份|有限|集团|公司|[\s/、，,]/g, "");
  const a = normalize(left);
  const b = normalize(right);
  return Boolean(a && b && (a.includes(b) || b.includes(a)));
}

function stageLabel(stages = [], id = "") {
  return stages.find((item) => item.id === id)?.label || "待判断";
}

function motionAllowed() {
  return typeof window !== "undefined" && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function tapMotion(element) {
  if (!element || !motionAllowed()) return;
  gsap.killTweensOf(element);
  gsap.fromTo(element, { scale: 0.985 }, { scale: 1, duration: 0.18, ease: "power2.out", clearProps: "transform" });
}

function dateKey(value) {
  if (!value) return "";
  const match = String(value).match(/\d{4}-\d{2}-\d{2}/);
  return match?.[0] || "";
}

function matchingAccount(item = {}, data = {}) {
  const customer = item.customer || "";
  return (data.accounts?.accounts || []).find((entry) => entry.id === item.account_id)
    || (data.accounts?.accounts || []).find((entry) => sameCustomer(entry.name, customer));
}

function relatedKnowledge(item = {}, data = {}) {
  const customer = item.customer || "";
  return (data.dashboard?.knowledge_timeline || [])
    .filter((entry) => sameCustomer(entry.project || entry.raw_title, customer));
}

function buildExecutionTrend(dashboard = {}) {
  const end = new Date();
  end.setHours(12, 0, 0, 0);
  const rows = Array.from({ length: 14 }, (_, index) => {
    const date = new Date(end);
    date.setDate(end.getDate() - (13 - index));
    const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
    return {
      key,
      label: `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`,
      actions: 0,
      evidence: 0,
      receipts: 0,
    };
  });
  const byDate = new Map(rows.map((row) => [row.key, row]));
  for (const action of dashboard.battle_actions || []) {
    const row = byDate.get(dateKey(action.deadline || action.review_at || action.created_at));
    if (row) row.actions += 1;
  }
  for (const entry of dashboard.knowledge_timeline || []) {
    const row = byDate.get(dateKey(entry.updated_at));
    if (row) row.evidence += 1;
  }
  for (const receipt of dashboard.workflow_state?.receipts || []) {
    const row = byDate.get(dateKey(receipt.submitted_at));
    if (row) row.receipts += 1;
  }
  return rows;
}

function evidenceCompleteness(item = {}, data = {}) {
  const account = matchingAccount(item, data);
  const knowledge = relatedKnowledge(item, data);
  const checks = [
    { id: "source", label: "来源可追溯", ok: Boolean(item.source_type || item.source_scope || item.source || item.signal) },
    { id: "time", label: "时间已明确", ok: Boolean(item.deadline || item.review_at) },
    { id: "next", label: "下一步清楚", ok: Boolean(item.next_step || item.action || item.target) },
    { id: "account", label: "正式账户匹配", ok: Boolean(account) },
    { id: "invoices", label: "发票夹", icon: NavReceipt, intelligence: true },
  { id: "knowledge", label: "客户证据沉淀", ok: Boolean(knowledge.length) },
  ];
  const passed = checks.filter((check) => check.ok).length;
  return {
    checks,
    passed,
    total: checks.length,
    score: Math.round((passed / checks.length) * 100),
    missing: checks.filter((check) => !check.ok),
  };
}

function rankTodayActions(dashboard = {}) {
  const queue = dashboard.sales_brain?.today_queue || [];
  const actions = uniqueItems(splitCurrentActions(dashboard.battle_actions || []).current).map((item) => {
    const matched = queue.find((entry) => {
      const ids = [entry.workflow_key, entry.todo_id, entry.id].filter(Boolean);
      return ids.includes(item.workflow_key || item.todo_id || item.id)
        || (sameCustomer(entry.customer, item.customer) && dateKey(entry.deadline) === dateKey(item.deadline));
    }) || queue.find((entry) => sameCustomer(entry.customer, item.customer));
    return matched ? { ...matched, ...item, why_today: matched.why_today || item.why_today, target: matched.target || item.target, exit: matched.exit, destination: matched.destination } : item;
  });
  const priorityRank = { P0: 0, P1: 1, P2: 2, P3: 3 };
  const bucketRank = { overdue: 0, today: 1, week: 2, later: 3 };
  return actions.sort((left, right) => {
    const bucketDelta = (bucketRank[left.schedule_bucket] ?? 4) - (bucketRank[right.schedule_bucket] ?? 4);
    if (bucketDelta) return bucketDelta;
    const priorityDelta = (priorityRank[left.priority] ?? 9) - (priorityRank[right.priority] ?? 9);
    if (priorityDelta) return priorityDelta;
    const leftMinutes = Number.isFinite(Number(left.minutes_left)) ? Number(left.minutes_left) : Number.POSITIVE_INFINITY;
    const rightMinutes = Number.isFinite(Number(right.minutes_left)) ? Number(right.minutes_left) : Number.POSITIVE_INFINITY;
    if (leftMinutes !== rightMinutes) return leftMinutes - rightMinutes;
    return String(left.deadline || "").localeCompare(String(right.deadline || ""));
  });
}

function actionWhyNow(item = {}) {
  if (item.why_today) return item.why_today;
  if (item.schedule_bucket === "overdue") {
    return `已到本轮触发点，${item.countdown_label || "需要立即确认是否继续推进"}。`;
  }
  return item.risk || item.evidence || "当前信号已满足进入人工判断的条件。";
}

function actionRecommendation(item = {}) {
  const next = text(item.next_step || item.action || item.target, "进入客户作战室确认下一步");
  return next.replace(/^到点跟进：/, "").replace(/^检查客户反馈：/, "");
}

function compactSentence(value = "", max = 72) {
  const clean = text(value).replace(/\s+/g, " ");
  return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

function JourneyRail({ activeStep = 0, compact = false }) {
  return (
    <ol className={`journey-rail ${compact ? "is-compact" : ""}`} aria-label="连续操作进度">
      {CONTINUOUS_STEPS.map((label, index) => (
        <li key={label} className={index < activeStep ? "is-complete" : index === activeStep ? "is-active" : ""}>
          <span>{index < activeStep ? <CheckCircle2 size={13} /> : index + 1}</span>
          <strong>{label}</strong>
          {index < CONTINUOUS_STEPS.length - 1 ? <ArrowRight size={13} aria-hidden="true" /> : null}
        </li>
      ))}
    </ol>
  );
}

function handleRadioArrow(event, values, current, onChange) {
  if (!["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) return;
  event.preventDefault();
  const currentIndex = Math.max(0, values.indexOf(current));
  const direction = ["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1;
  const next = values[(currentIndex + direction + values.length) % values.length];
  onChange(next);
  event.currentTarget.parentElement?.querySelector(`[data-radio-value="${next}"]`)?.focus();
}

function sourceLink(value = "") {
  const match = String(value).match(/https?:\/\/[^\s；;]+/);
  return match?.[0] || "";
}

function StatusChip({ tone = "neutral", children }) {
  return <span className={`status-chip tone-${tone}`}>{children}</span>;
}

function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <header className="page-header">
      <div>
        {eyebrow ? <p className="page-eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

function EmptyMessage({ title, description, action }) {
  return (
    <div className="empty-state">
      <Inbox size={28} aria-hidden="true" />
      <strong>{title}</strong>
      <p>{description}</p>
      {action}
    </div>
  );
}

function ErrorScreen({ message, onRetry }) {
  return (
    <div className="error-screen" role="alert">
      <CircleAlert size={30} />
      <h1>工作台暂时没有读到数据</h1>
      <p>{message}</p>
      <Button label="重新读取" variant="primary" onClick={onRetry} />
    </div>
  );
}

function useWorkbench(enabled, view) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState([]);

  const [refreshVersion, setRefreshVersion] = useState(0);
  const readVersion = useRef(0);
  const pending = useRef(false);
  const context = useRef({enabled, view});
  context.current = {enabled, view};
  const refresh = useCallback(async ({ quiet = false, full = false } = {}) => {
    const {enabled, view} = context.current;
    const version = ++readVersion.current;
    if (!enabled && !full) {
      setData(null);
      setError('');
      if (view === 'projects' || view === 'knowledge') setRefreshVersion(value => value + 1);
      else window.dispatchEvent(new Event('workbench-refresh'));
      return;
    }
    pending.current = true;
    setLoading(true);
    setProgress([]);
    setError("");
    try {
      const next = await loadWorkbenchData({ onProgress: item => {
        if (version === readVersion.current) setProgress(current => [...current.filter(row => row.key !== item.key), item]);
      } });
      if (version === readVersion.current) { setData(next); setRefreshVersion(value => value + 1);
        if (full && view !== 'projects' && view !== 'knowledge') window.dispatchEvent(new Event('workbench-refresh')); }
    } catch (requestError) {
      if (version === readVersion.current) setError(requestError.message || "未知错误");
    } finally {
      if (version === readVersion.current) { pending.current = false; setLoading(false); }
    }
  }, []);

  useEffect(() => { if (enabled && !pending.current) refresh(); }, [enabled, refresh]);
  useEffect(() => () => { readVersion.current++; pending.current = false; }, []);

  return { data, error, loading, refresh, refreshVersion, progress };
}

function App() {
  const [initialContext] = useState(() => readNavigationContext(sessionStorage, window.history));
  const [navigationEpoch, setNavigationEpoch] = useState(0);
  const [pricingTab, setPricingTab] = useState(initialContext.pricingTab || "calculator");
  const [commercialFocus,setCommercialFocus]=useState('');
  const historyNavigation = useRef(null);
  const applyingHistory = useRef(false);
  const [view, setView] = useState(initialContext.view || "agent");
  const [captureOpen, setCaptureOpen] = useState(false);
  const { data, error, loading, refresh, refreshVersion, progress } = useWorkbench(needsWorkbenchData(view) || captureOpen, view);
  const pageRefreshKey = useMemo(() => ({ generated_at: refreshVersion }), [refreshVersion]);
  const [toast, setToast] = useState("");
  const [focusAction, setFocusAction] = useState(null);
  const [projectTitle, setProjectTitle] = useState(initialContext.projectTitle || "");
  const [projectCustomer, setProjectCustomer] = useState(initialContext.customer || "");
  const [overviewReset,setOverviewReset]=useState(0);
  const [pricingReset,setPricingReset]=useState(0);
  const [quickQuoteValues,setQuickQuoteValues]=useState(()=>restoreQuote(sessionStorage));
  const [quickApproval,setQuickApproval]=useState(()=>restoreApproval(sessionStorage));
  const [incomingQuote, setIncomingQuote] = useState(null);
  const [quoteConflict, setQuoteConflict] = useState(null);
  useEffect(() => { let active = true; const identity = quoteIdentity.current;
    if (identity?.revision > 0) api.get(`/api/quotes?quote_id=${encodeURIComponent(identity.quote_id)}`).then(data => {
      if (active && quoteIdentity.current === identity && data.versions?.length) {
        const latest = { ...data.versions.at(-1), quote_id: data.quote_id };
        setIncomingQuote(latest);
        if (data.revision > identity.revision) setQuoteConflict(latest);
        const baseline = data.versions.find(v => v.revision === identity.revision);
        if (baseline) quoteIdentity.current = savedQuoteIdentity({ ...baseline, quote_id: data.quote_id });
      }
    }).catch(() => {});
    return () => { active = false; };
  }, []);
  const [quoteSaving, setQuoteSaving] = useState(false);
  const quoteIdentity = useRef(null);
  if (!quoteIdentity.current) { try { quoteIdentity.current = JSON.parse(sessionStorage.getItem('workbench-quote-identity')); } catch {} if (!quoteIdentity.current || typeof quoteIdentity.current.quote_id !== 'string' || !Number.isInteger(quoteIdentity.current.revision)) quoteIdentity.current = { quote_id: crypto.randomUUID(), revision: 0 }; }
  const transferQuote = async values => {
    setQuoteSaving(true);
    try {
    const identity = selectQuoteIdentity(quoteIdentity.current, values, () => crypto.randomUUID());
    let saved;
    try { saved = await api.post('/api/quotes', { ...identity, values }); }
    catch (error) {
      try { const current = await api.get(`/api/quotes?quote_id=${encodeURIComponent(identity.quote_id)}`);
        if (current.revision > identity.revision) setQuoteConflict({ ...current.versions.at(-1), quote_id: current.quote_id });
      } catch {}
      throw error;
    }
    quoteIdentity.current = savedQuoteIdentity(saved);
    setQuoteConflict(null);
    try { sessionStorage.setItem('workbench-quote-identity', JSON.stringify(quoteIdentity.current)); } catch {}
    setIncomingQuote(saved);
    await navigate('pricing', { pricingTab: 'approval' });
    return saved;
    } finally { setQuoteSaving(false); }
  };
  useEffect(()=>{try{sessionStorage.setItem(QUICK_QUOTE_KEY,JSON.stringify(quickQuoteValues));}catch{}setQuickApproval(current=>syncApprovalFromQuote(current,quickQuoteValues,calculateQuote(quickQuoteValues)));},[quickQuoteValues]);
  useEffect(()=>{try{sessionStorage.setItem(APPROVAL_KEY,JSON.stringify(quickApproval));}catch{}},[quickApproval]);
  const [signalContext,setSignalContext]=useState(contextForProject(initialContext.signalContext,initialContext.projectId));
  const [projectContext, setProjectContext] = useState(initialContext.projectId || "");
  const [accountContext, setAccountContext] = useState(initialContext.accountId || "");
  useEffect(() => { try { sessionStorage.setItem("workbench-context", JSON.stringify({ view, projectId: projectContext, projectTitle, customer:projectCustomer, pricingTab, signalContext, accountId: accountContext })); } catch {} }, [view, projectContext, projectTitle, projectCustomer, pricingTab, signalContext, accountContext]);
  const navigationGuard = useRef(() => true);
  const navigationPending = useRef(false);
  const registerNavigationGuard = useCallback((guard) => { navigationGuard.current = guard; return () => { if (navigationGuard.current === guard) navigationGuard.current = () => true; }; }, []);

  const routeRef = useRef(null);
  routeRef.current = { view, projectId: projectContext, projectTitle, customer: projectCustomer, pricingTab, signalContext, accountId: accountContext };
  const selectProjectContext = useCallback((id, meta = {}) => {
    const next = { ...routeRef.current, projectId: id, accountId: '', projectTitle: meta.title || '', customer: meta.customer || '',signalContext:contextForProject(routeRef.current.signalContext,id) };
    if (id !== routeRef.current.projectId && !applyingHistory.current) historyNavigation.current?.push(next);
    else historyNavigation.current?.replace(next);
    routeRef.current = next;
    setAccountContext(''); setSignalContext(next.signalContext); setProjectContext(id); setProjectTitle(next.projectTitle); setProjectCustomer(next.customer);
  }, []);
  const selectAccountContext = useCallback((id) => {
    const next = { ...routeRef.current, accountId: id, projectId: '', projectTitle: '', customer: '', signalContext: null };
    if (id !== (routeRef.current.accountId || '') && !applyingHistory.current) historyNavigation.current?.push(next);
    else historyNavigation.current?.replace(next);
    routeRef.current = next;
    setAccountContext(id); setProjectContext(''); setProjectTitle(''); setProjectCustomer(''); setSignalContext(null);
  }, []);
  useEffect(() => {
    const controller = createWorkbenchNavigation({ window, initial: routeRef.current,
      canLeave: () => navigationGuard.current(),
      capture: () => ({ overview: sessionStorage.getItem(OVERVIEW_KEY), scroll: document.querySelector('.app-main')?.scrollTop || 0 }),
      apply: (next, snapshot = {}) => {
        applyingHistory.current = true;
        if (snapshot.overview) { try { sessionStorage.setItem(OVERVIEW_KEY, snapshot.overview); } catch {} }
        routeRef.current = next;
        setAccountContext(next.accountId || ''); setView(next.view || 'agent'); setProjectContext(next.projectId || ''); setSignalContext(contextForProject(next.signalContext,next.projectId));
        setProjectTitle(next.projectTitle || ''); setProjectCustomer(next.customer || '');
        setPricingTab(next.pricingTab || 'calculator'); setCommercialFocus(''); setFocusAction(null); setNavigationEpoch(v => v + 1);
        requestAnimationFrame(() => { if (next.view !== 'projects') document.querySelector('.app-main')?.scrollTo({ top: snapshot.scroll || 0 }); applyingHistory.current = false; });
      },
    });
    historyNavigation.current = controller;
    const remember = () => controller.remember();
    window.addEventListener('scroll', remember, true);
    return () => { controller.destroy(); window.removeEventListener('scroll', remember, true); };
  }, []);

  useEffect(() => {
    if(view!=="projects"){document.querySelector(".app-main")?.scrollTo({ top: 0, behavior: "instant" });window.scrollTo({top:0,behavior:"instant"});}
    document.querySelector("#main-content")?.focus({ preventScroll: true });
  }, [view]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(""), 4200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const motionRoot = useRef(null);
  useWorkbenchMotion(motionRoot, view);
  const waitingForView = needsWorkbenchData(view) && !data;

  const dashboard = data?.dashboard || EMPTY_WORKBENCH_VALUE;
  const accountData = data?.accounts || EMPTY_WORKBENCH_VALUE;
  const prospecting = data?.prospecting || EMPTY_WORKBENCH_VALUE;
  const reminders = data?.reminders || EMPTY_WORKBENCH_VALUE;
  const actionCount = uniqueItems(splitCurrentActions(dashboard.battle_actions || []).current).length;
  const candidateCount = prospectSurfaceItems(prospecting.leads || [], "candidate").length;
  const reminderCount = futureReminderItems(reminders.items || [], dashboard.battle_actions || []).length;
  const navCount = data ? { today: actionCount, accounts: `待判断 ${candidateCount}`, reminders: reminderCount } : {};

  const [notificationContext,setNotificationContext]=useState(null);
  const navigate = async (nextView, options = {}) => {
    if (navigationPending.current || historyNavigation.current?.busy()) return false;
    navigationPending.current = true;
    let allowed = false;
    try { allowed = await navigationGuard.current(); }
    finally { navigationPending.current = false; }
    if (!allowed) return false;
    const nextRoute = { ...routeRef.current, view: nextView };
    if (shouldClearProject(options)) {
      nextRoute.projectId = options.projectId;
      nextRoute.accountId = ''; setAccountContext('');
      if (!options.projectId || options.projectId !== projectContext) { nextRoute.projectTitle = options.projectTitle || ''; nextRoute.customer = options.customer || ''; }
    }
    nextRoute.signalContext=contextForProject(options.signalContext??nextRoute.signalContext,nextRoute.projectId);
    setSignalContext(nextRoute.signalContext);
    if (nextView === 'pricing') nextRoute.pricingTab = options.pricingTab || 'calculator';
    if (JSON.stringify(nextRoute) !== JSON.stringify(routeRef.current)) historyNavigation.current?.push(nextRoute);
    routeRef.current = nextRoute;
    setPricingTab(nextRoute.pricingTab);
    setCommercialFocus(nextView==='pricing'?(options.focusCommercial||''):'');
    if (shouldClearProject(options)) {setProjectContext(options.projectId);if(!options.projectId){setProjectTitle("");setProjectCustomer("");}else if(options.projectTitle){setProjectTitle(options.projectTitle);setProjectCustomer(options.customer||"");}}
    if(options.resetProjectFilter)setOverviewReset(Date.now());
    if(nextView==="pricing")setPricingReset(v=>v+1);
    setFocusAction(options.focusAction || null);
    setView(nextView);
    return true;
  };

  const openNotification=async item=>{const allowed=await navigate("projects",{projectId:item.project_id,projectTitle:item.title,customer:item.customer});if(allowed)setNotificationContext(item);return allowed;};

  return (
    <NavigationGuardContext.Provider value={registerNavigationGuard}><div className={"app-frame workbench-shell agent-shell view-"+view}>
      <a className="skip-link" href="#main-content">跳到主内容</a>
      <aside className="app-sidebar" aria-label="主导航">
        <div className="brand-block">
          <span className="brand-symbol"><AgentStack size={23} weight="fill"/></span><div><strong>项目管理工作台</strong><span>工作台用户 · 客户经营</span></div>
        </div>

        <nav className="nav-stack">
          {['agent','projects','reminders','discover','knowledge','communications'].map(key=>{const item=NAV_ITEMS.find(n=>n.id===key);return <NavButton key={key} item={item} active={view===key} onClick={()=>navigate(key,key==='projects'?{projectId:'',resetProjectFilter:true}:{})}/>})}
          <details className="sidebar-more"><summary>更多工具</summary>
            <button className="nav-button" onClick={()=>setCaptureOpen(true)}><NavPlus size={17}/>销售捕捉</button>
            {NAV_ITEMS.filter(n=>!['agent','projects','reminders','discover','knowledge','communications'].includes(n.id)&&!n.nested).map(item=><NavButton key={item.id} item={item} active={view===item.id} onClick={()=>navigate(item.id)}/>)}
          </details>
        </nav>

        <div className="sidebar-status">
          <span className="live-dot" />
          <div>
            <strong>{view==="aihot"?"公开资讯":view==="projects"?"项目分析":view==="customers"?"K100 客户主体":"本地历史登记"}</strong>
            <span>{view==="aihot"?"AIHOT · 本机缓存":view==="projects"?"基于已有材料，判断可核对":(data ? `${accountData.summary?.account_count||0} 条 · 实际归属以 CRM 核验` : "本机材料 · 按页面读取")}</span>
          </div>
        </div>
      </aside>

      <div className="app-body">
        <header className="app-topbar">
          <div>
            <strong>{NAV_ITEMS.find((item) => item.id === view)?.label || "项目管理工作台"}</strong>
            <span>{view === 'aihot' ? '公开资讯 · 本机缓存' : dashboard.generated_at ? `数据更新 ${formatDateTime(dashboard.generated_at)}` : "本机工作台"}</span>
          </div>
          <div className="topbar-actions">
            {view!=='agent'&&<button className="plain-action global-agent-link" onClick={()=>navigate('agent')}> <NavChat size={16}/>问 Agent</button>}<ProjectNotifications refreshKey={pageRefreshKey} onOpen={openNotification}/>
            <button className="plain-action" disabled={!historyNavigation.current?.canGoBack()} onClick={() => historyNavigation.current?.back()} title="返回上一步"><ChevronLeft size={16}/><span>返回</span></button>
            <button className="plain-action" onClick={() => navigate('agent', { projectId: '' })} title="回首页"><Building2 size={16}/></button>
            {error ? <StatusChip tone="warning">部分数据读取失败</StatusChip> : null}
            <Button
              label={needsWorkbenchData(view) ? "刷新数据" : "刷新当前页"}
              variant="ghost"
              isDisabled={loading}
              icon={<RefreshCw size={16} />}
              onClick={() => refresh({ quiet: true })}
            />
            <details className="topbar-more"><summary aria-label="更多数据操作">•••</summary><button className="plain-action full-update-button" disabled={loading} onClick={() => refresh({ full: true })} title="后台持续更新；此按钮仅用于手动重新核对全部视图">核对全部数据</button></details>
          </div>
        </header>
        {loading && !waitingForView && progress.length > 0 && <UpdateProgress progress={progress} />}

        <main ref={motionRoot} id="main-content" className="app-main" tabIndex="-1">
          {view === "agent" ? <AgentWorkspace navigate={navigate} refreshKey={refreshVersion} registerNavigationGuard={registerNavigationGuard}/> : null}
          {waitingForView ? (error ? <ErrorScreen message={error} onRetry={() => refresh()} /> : <WorkbenchLoading title={NAV_ITEMS.find(item => item.id === view)?.label || "当前页面"} progress={progress} />) : null}
          {projectContext && view !== "projects" && <div className="project-context-return"><button className="plain-action" onClick={() => navigate("projects", { projectId: projectContext })}>← 返回{projectTitle||"刚才项目"}</button><button className="plain-action" onClick={() => navigate("projects", { projectId:"",resetProjectFilter:true })}>项目总览</button></div>}
          {["projects","customers"].includes(view) ? <ProjectWorkspace directoryOnly={view==='customers'} onOpenNotification={openNotification} notificationContext={notificationContext} key={`${view}:${navigationEpoch}`} onBack={() => historyNavigation.current?.canGoBack() ? historyNavigation.current.back() : navigate('projects', { projectId: '' })} overviewReset={overviewReset} navigate={navigate} initialProjectId={view==='customers'?'':projectContext} initialAccountId={view==='customers'?'':accountContext} onAccountSelected={selectAccountContext} signalContext={signalContext} onProjectSelected={selectProjectContext} refreshKey={pageRefreshKey} onActionsChanged={() => refresh({ quiet: true })} registerNavigationGuard={registerNavigationGuard} /> : null}
          {view === "discover" && !waitingForView ? <DiscoveryWorkspace navigate={navigate} refresh={refresh} key={`discovery:${navigationEpoch}`} data={data} registerNavigationGuard={registerNavigationGuard} /> : null}
          {view === "today" && !waitingForView ? <SalesPursuit data={data} refresh={refresh} navigate={navigate} setToast={setToast} focusAction={focusAction} onFocusConsumed={() => setFocusAction(null)} /> : null}
          {view === "accounts" && !waitingForView ? <AccountsView data={data} refresh={refresh} navigate={navigate} setToast={setToast} /> : null}
          {view === "reminders" && !waitingForView ? <RemindersView focusAction={focusAction} onFocusConsumed={() => setFocusAction(null)} data={data} refresh={refresh} navigate={navigate} setToast={setToast} /> : null}
          {view === "invoices" ? <InvoiceVault registerNavigationGuard={registerNavigationGuard}/> : null}
          {view === "knowledge" ? <MaterialLibrary projectId={projectContext} navigate={navigate} refreshKey={pageRefreshKey} /> : null}
          {view === "communications" ? <CommunicationSync navigate={navigate} context={{projectId:projectContext,projectTitle,customer:projectCustomer}} onChanged={() => refresh({ quiet: true })} /> : null}
          {view === "aihot" ? <AIHot /> : null}
          {view === "reports" && !waitingForView ? <ReportsView dashboard={dashboard} refresh={refresh} /> : null}
          {view === "performance" && !waitingForView ? <PerformanceView refreshKey={pageRefreshKey.generated_at} dashboard={dashboard} projectId={projectContext} navigate={navigate} /> : null}
          {view === "pricing" ? <PricingWorkspace quoteConflict={quoteConflict} onResolveQuote={(merge) => { quoteIdentity.current = merge ? savedQuoteIdentity(quoteConflict) : null; if (!merge) quoteIdentity.current = { quote_id: crypto.randomUUID(), revision: 0 }; try { sessionStorage.setItem("workbench-quote-identity", JSON.stringify(quoteIdentity.current)); } catch {} setQuoteConflict(null); }} onNewQuote={() => { quoteIdentity.current = { quote_id: crypto.randomUUID(), revision: 0 }; try { sessionStorage.setItem("workbench-quote-identity", JSON.stringify(quoteIdentity.current)); } catch {} setQuoteConflict(null); setToast("已作为独立的新报价，当前输入保留；下次保存不会影响原报价。"); }} quoteSaving={quoteSaving} incomingQuote={incomingQuote} onTransferQuote={transferQuote} key={`pricing:${navigationEpoch}`} focusSection={commercialFocus} tab={pricingTab} values={quickQuoteValues} setValues={setQuickQuoteValues} approval={quickApproval} setApproval={setQuickApproval} resetKey={pricingReset} initialProjectId={projectContext} onProjectSelected={selectProjectContext} navigate={navigate} registerNavigationGuard={registerNavigationGuard} canSwitch={() => navigationGuard.current()} /> : null}
        </main>
      </div>

      <CaptureDialog
        isOpen={captureOpen}
        onOpenChange={setCaptureOpen}
        data={data}
        refresh={refresh}
        navigate={navigate}
        setToast={setToast}
      />
      {toast ? <div className="toast" role="status" aria-live="polite">{toast}</div> : null}
    </div></NavigationGuardContext.Provider>
  );
}

function NavButton({ item, active, count, onClick }) {
  const Icon = item.icon;
  return (
    <button
      className={`nav-button nav-${item.id} ${item.primary ? "is-primary" : "is-tool"} ${active ? "is-active" : ""}`}
      type="button"
      aria-current={active ? "page" : undefined}
      onClick={(event) => {
        tapMotion(event.currentTarget);
        onClick();
      }}
    >
      <Icon size={21} weight="duotone" aria-hidden="true" />
      <span>{item.label}</span>
      {Number.isFinite(count) || typeof count === "string" ? <strong>{count}</strong> : null}
    </button>
  );
}

function TodayView({ data, refresh, navigate, setToast, focusAction, onFocusConsumed }) {
  const [filter, setFilter] = useState("today");
  const [selected, setSelected] = useState(null);
  const [workroomItem, setWorkroomItem] = useState(null);
  const pageRef = useRef(null);
  const continuityRef = useRef(null);
  const dashboard = data.dashboard || {};
  const actions = useMemo(() => rankTodayActions(dashboard), [dashboard]);
  const historicalActions = splitCurrentActions(dashboard.battle_actions || []).history;
  const receipts = dashboard.workflow_state?.receipts || [];
  const completedReceipts = receipts.filter((receipt) => receipt.status === "已闭环");
  const primaryAction = actions.find(item => item.source_type !== "transcript_intake" && !(Number(item.minutes_left) < -7 * 24 * 60)) || null;
  const primaryActionId = primaryAction ? itemKey(primaryAction) : "";
  const actionGroups = useMemo(() => ({
    today: primaryAction ? [primaryAction] : [],
    todo: actions.filter((item) => itemKey(item) !== primaryActionId && item.schedule_bucket !== "overdue"),
    overdue: actions.filter((item) => itemKey(item) !== primaryActionId && (item.schedule_bucket === "overdue" || Number(item.minutes_left) < 0)),
  }), [actions, primaryAction, primaryActionId]);
  const sourceChecks = [
    Array.isArray(dashboard.battle_actions),
    Array.isArray(data.accounts?.accounts),
    Array.isArray(dashboard.knowledge_timeline),
    Array.isArray(dashboard.workflow_state?.receipts),
    Array.isArray(data.reminders?.items),
  ];
  const readySourceCount = sourceChecks.filter(Boolean).length;

  useEffect(() => {
    if (!focusAction) return;
    if (focusAction.source_type === 'project_round') navigate('projects', { projectId: focusAction.project_id, projectTitle: focusAction.project_title, customer: focusAction.customer });
    else setSelected(focusAction);
    onFocusConsumed?.();
  }, [focusAction, onFocusConsumed]);

  useLayoutEffect(() => {
    if (!pageRef.current) return undefined;
    const context = gsap.context(() => {
      const media = gsap.matchMedia();
      media.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.fromTo(
          ".daily-focus > *, .mission-queue",
          { autoAlpha: 0, y: 10 },
          { autoAlpha: 1, y: 0, duration: 0.28, stagger: 0.05, ease: "power2.out" },
        );
      });
      return () => media.revert();
    }, pageRef);
    return () => context.revert();
  }, []);

  useLayoutEffect(() => {
    if (!continuityRef.current || !selected || !motionAllowed()) return undefined;
    gsap.killTweensOf(continuityRef.current);
    gsap.fromTo(
      continuityRef.current,
      { autoAlpha: 0.35, y: 14 },
      { autoAlpha: 1, y: 0, duration: 0.38, ease: "power2.out", clearProps: "transform" },
    );
    return () => gsap.killTweensOf(continuityRef.current);
  }, [selected]);

  if (workroomItem) {
    return (
      <Workroom
        item={workroomItem}
        data={data}
        onBack={() => setWorkroomItem(null)}
        refresh={refresh}
        onNavigate={navigate}
        setToast={setToast}
        backLabel="返回 AI 行动面板"
      />
    );
  }

  const rows = filter === "feedback" ? completedReceipts : actionGroups[filter] || [];
  const queueMeta = {
    today: ["今天重点要处理", "当前只突出一件最需要你判断的事。"],
    todo: ["其余待办", "尚未进入超期状态的候选动作与待确认事项。"],
    feedback: ["推进后的反馈", "已闭环结果只作为回执查看，不重复进入活动队列。"],
    overdue: ["超时任务", "除当前焦点外仍然超期的事项，需要逐条确认继续、改期或关闭。"],
  };

  function revealAction(item, element) {
    if (item.source_type === 'project_round') { navigate('projects', { projectId: item.project_id, projectTitle: item.project_title, customer: item.customer }); return; }
    tapMotion(element);
    setSelected(item);
    window.requestAnimationFrame(() => {
      window.setTimeout(() => document.querySelector(".continuity-panel")?.scrollIntoView({ behavior: motionAllowed() ? "smooth" : "auto", block: "start" }), 40);
    });
  }

  return (
    <div className="page-stack today-dashboard" ref={pageRef}>
      <section className="daily-focus" aria-label="今日当前焦点">
        <header className="daily-focus-header">
          <div>
            <span className="focus-signal"><Sparkles size={15} />当前焦点</span>
            <p>系统只把一个行动放到最前面，最终判断仍由你确认。</p>
          </div>
          <div className="hero-freshness">
            <span><CircleCheck size={15} />执行链 <strong>{readySourceCount}/{sourceChecks.length}</strong> 已读取</span>
            <span><Clock3 size={15} />更新于 {formatDateTime(dashboard.generated_at, "刚刚").slice(-5)}</span>
          </div>
        </header>

        {primaryAction ? (
          <div className="daily-focus-body">
            <div className="daily-focus-main">
              <div className="focus-account-line">
                <span>{primaryAction.customer || "待绑定客户"}</span>
                <StatusChip tone="danger">{primaryAction.priority || "P0"}</StatusChip>
                <StatusChip tone={primaryAction.schedule_bucket === "overdue" ? "danger" : "warning"}>
                  {primaryAction.countdown_label || primaryAction.status || "待处理"}
                </StatusChip>
              </div>
              <h1>{compactSentence(itemTitle(primaryAction), 78)}</h1>
              <p className="focus-next-step">{actionRecommendation(primaryAction)}</p>
              <div className="focus-actions">
                <Button
                  label="进入当前客户作战室"
                  variant="primary"
                  onClick={() => setWorkroomItem(primaryAction)}
                />
                <Button
                  label="先查看证据与打法"
                  variant="secondary"
                  onClick={(event) => revealAction(primaryAction, event.currentTarget)}
                />
              </div>
            </div>

            <dl className="focus-decision-context">
              <div>
                <dt>为什么现在处理</dt>
                <dd>{actionWhyNow(primaryAction)}</dd>
              </div>
              <div>
                <dt>处理后的归宿</dt>
                <dd>完成则留下回执并离开活动队列；仍需推进则安排下一次明确触发。</dd>
              </div>
              <div>
                <dt>来源</dt>
                <dd>{itemSource(primaryAction)} · 截止 {formatDateTime(primaryAction.deadline || primaryAction.review_at)}</dd>
              </div>
            </dl>
          </div>
        ) : (
          <EmptyMessage title="今天没有需要立即判断的事项" description="已安排的行动会在触发时间到达后回到这里。" />
        )}
      </section>

      <section className="mission-queue" id="today-queue" aria-label="行动状态队列">
        <div className="mission-queue-header">
          <div>
            <strong>{queueMeta[filter]?.[0]}</strong>
            <span>{queueMeta[filter]?.[1]}</span>
          </div>
          <SegmentedControl value={filter} onChange={setFilter} label="行动状态">
            <SegmentedControlItem value="today" label={`今天重点 ${actionGroups.today.length}`} />
            <SegmentedControlItem value="todo" label={`其余待办 ${actionGroups.todo.length}`} />
            <SegmentedControlItem value="feedback" label={`推进反馈 ${completedReceipts.length}`} />
            <SegmentedControlItem value="overdue" label={`超时任务 ${actionGroups.overdue.length}`} />
          </SegmentedControl>
        </div>

        {filter !== "feedback" && rows.length ? (
          <div className="mission-list">
            {rows.map((item) => (
              <PriorityActionRow
                key={itemKey(item)}
                item={item}
                data={data}
                index={Math.max(0, actions.findIndex((entry) => itemKey(entry) === itemKey(item)))}
                selected={Boolean(selected) && itemKey(selected) === itemKey(item)}
                onClick={(element) => revealAction(item, element)}
                onEnter={(element) => {
                  tapMotion(element);
                  setSelected(item);
                  setWorkroomItem(item);
                }}
              />
            ))}
          </div>
        ) : filter === "feedback" && rows.length ? (
          <div className="queue-list recent-receipts">
            {rows.map((item) => <ReceiptRow key={`${item.submitted_at}-${item.title}`} receipt={item} />)}
          </div>
        ) : (
          <EmptyMessage
            title="这个状态暂时为空"
            description="状态变化并刷新后，事项会自动进入对应队列。"
          />
        )}
      </section>

      {historicalActions.length>0 && <details className="project-judgement"><summary>历史待核实／历史记录 · {historicalActions.length}</summary><p>超过30天的旧期限或明确标为需复核的旧记录移到这里，不再作为今天 P0 催办。原内容、回执和业务状态保留；有新约定时再按真实节点更新。</p>{historicalActions.map(item=><article key={itemKey(item)}><h3>{item.customer} · {item.title || item.action || '历史事项'}</h3><p>原期限 {item.deadline || item.review_at || '待核实'} · 历史待核实</p><p>{item.next_step || item.action}</p><button className="plain-action" onClick={()=>setWorkroomItem(item)}>查看原记录与回执</button></article>)}</details>}
      {selected ? (
        <AIContinuityPanel
          key={itemKey(selected)}
          panelRef={continuityRef}
          item={selected}
          data={data}
          index={Math.max(0, actions.findIndex((entry) => itemKey(entry) === itemKey(selected)))}
          onEnter={(draft) => setWorkroomItem({ ...selected, copilot_draft: draft })}
          setToast={setToast}
        />
      ) : null}
    </div>
  );
}

function MomentumChart({ data }) {
  return (
    <div className="momentum-panel">
      <div className="momentum-title">
        <div><strong>执行证据趋势</strong><span>近 14 天 · 同口径计数</span></div>
        <CircleAlert size={15} />
      </div>
      <div className="momentum-legend">
        <span className="legend-action">行动触发</span>
        <span className="legend-evidence">证据更新</span>
        <span className="legend-receipt">提交回执</span>
      </div>
      <div className="momentum-chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 10, bottom: 0, left: -26 }}>
            <CartesianGrid vertical={false} stroke="rgba(223, 231, 226, .09)" />
            <XAxis dataKey="label" tick={{ fill: "var(--app-text-muted)", fontSize: 10 }} axisLine={false} tickLine={false} interval={3} />
            <YAxis tick={{ fill: "var(--app-text-muted)", fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} />
            <Tooltip
              contentStyle={{ background: "var(--app-surface)", border: "1px solid rgba(51,51,47,.2)", borderRadius: 8, color: "var(--app-text)" }}
              labelStyle={{ color: "#a7b0aa" }}
            />
            <Line type="monotone" dataKey="actions" name="行动触发" stroke="var(--app-text)" strokeWidth={2} dot={{ r: 2, fill: "var(--app-text)" }} activeDot={{ r: 4 }} />
            <Line type="monotone" dataKey="evidence" name="证据更新" stroke="var(--app-info)" strokeWidth={2} dot={{ r: 2, fill: "var(--app-info)" }} activeDot={{ r: 4 }} />
            <Line type="monotone" dataKey="receipts" name="提交回执" stroke="var(--app-warning)" strokeWidth={2} dot={{ r: 2, fill: "var(--app-warning)" }} activeDot={{ r: 4 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function PriorityActionRow({ item, data, index, selected, onClick, onEnter }) {
  const overdue = item.schedule_bucket === "overdue" || Number(item.minutes_left) < 0;
  const completeness = evidenceCompleteness(item, data);
  return (
    <article className={`mission-row ${selected ? "is-selected" : ""}`}>
      <button className="mission-row-main" type="button" onClick={(event) => onClick(event.currentTarget)} aria-label={`查看 ${item.customer} 的证据与打法`}>
        <span className="priority-rank">{index + 1}</span>
        <span className="mission-copy">
          <span className="mission-account"><strong>{item.customer || "待绑定客户"}</strong><small>{item.priority || "P?"}</small><em>{itemSource(item)}</em></span>
          <span className="mission-title">{compactSentence(itemTitle(item), 72)}</span>
          <span className="mission-why">{compactSentence(actionWhyNow(item), 82)}</span>
        </span>
        <span className="mission-next">
          <small>建议下一步</small>
          <strong>{compactSentence(actionRecommendation(item), 72)}</strong>
        </span>
        <span className="mission-status">
          <StatusChip tone={overdue ? "danger" : item.schedule_bucket === "today" ? "warning" : "neutral"}>
            {item.countdown_label || item.status || "待处理"}
          </StatusChip>
          <time>{formatDateTime(item.deadline, "未设置")}</time>
          <small>{completeness.passed}/{completeness.total} 项证据</small>
        </span>
      </button>
      <button className="mission-enter" type="button" onClick={(event) => onEnter(event.currentTarget)}>
        进入作战室 <ArrowRight size={16} />
      </button>
    </article>
  );
}

function ConfidenceGauge({ value, label = "证据完整度" }) {
  return (
    <span className="confidence-gauge" aria-label={`${label} ${value}%`}>
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart innerRadius="78%" outerRadius="100%" data={[{ value, fill: "var(--app-text)" }]} startAngle={90} endAngle={-270}>
          <PolarAngleAxis type="number" domain={[0, 100]} dataKey="value" tick={false} />
          <RadialBar dataKey="value" background={{ fill: "rgba(221, 235, 226, .1)" }} cornerRadius={8} />
        </RadialBarChart>
      </ResponsiveContainer>
      <strong>{value}%</strong>
    </span>
  );
}

function AIContinuityPanel({ item, data, index, onEnter, setToast, panelRef }) {
  const customer = item.customer || "待绑定客户";
  const account = matchingAccount(item, data);
  const knowledge = relatedKnowledge(item, data).slice(0, 5);
  const baseDraft = actionRecommendation(item);
  const [draft, setDraft] = useState(baseDraft);
  const [assistantNote, setAssistantNote] = useState("已按客户、时间状态和下一步规则生成可编辑草稿。");
  const completeness = evidenceCompleteness(item, data);

  useEffect(() => {
    setDraft(actionRecommendation(item));
    setAssistantNote("已按客户、时间状态和下一步规则生成可编辑草稿。");
  }, [item]);

  const evidenceItems = [
    {
      icon: Clock3,
      label: "Deadline / 时间触发",
      detail: formatDateTime(item.deadline || item.review_at),
      status: item.schedule_bucket === "overdue" ? "已核验 · 超期" : "已核验",
      tone: item.schedule_bucket === "overdue" ? "warning" : "success",
    },
    {
      icon: Database,
      label: "正式账户主账本",
      detail: account ? `${stageLabel(data.accounts?.stages, account.stage)} · ${account.priority || "优先级待补"}` : "暂未匹配正式账户",
      status: account ? "已匹配" : "待匹配",
      tone: account ? "success" : "warning",
    },
    {
      icon: FileCheck2,
      label: "AI 知识库沉淀",
      detail: knowledge.length ? `${knowledge.length} 条与本客户直接相关` : "未找到直接相关沉淀",
      status: knowledge.length ? "已读取" : "待补充",
      tone: knowledge.length ? "success" : "warning",
    },
    {
      icon: ShieldCheck,
      label: "行动边界检查",
      detail: "仅生成建议，不自动发送、不自动改状态",
      status: "边界通过",
      tone: "success",
    },
  ];

  function applyPreset(type, element) {
    tapMotion(element);
    const base = actionRecommendation(item);
    if (type === "invite") {
      setDraft(`${customer}团队好，想基于上次沟通把下一轮推进收敛到“${compactSentence(base, 46)}”。建议本轮只确认关键参与人、预期结论和时间点，方便的话我们今天锁一下评审时间。`);
      setAssistantNote("已生成邀约草稿；仍需你确认收件人、称谓和具体时间后再发送。");
    } else if (type === "talking") {
      setDraft(`本轮只讲三件事：1）为什么现在要推进；2）需要谁参与并做什么判断；3）会议结束前必须确认的下一步与时间。核心动作：${base}`);
      setAssistantNote("已整理成会议口径，适合复制到邀约或作战室回执。");
    } else {
      setDraft(`预算口径确认清单：业务范围、交付边界、决策人、预算归属、采购路径、最晚确认时间。结合 ${customer} 当前状态，本轮先确认：${base}`);
      setAssistantNote("已补成预算口径清单；未知项保留为人工确认，不替你做事实判断。");
    }
  }

  function submitPrompt(event) {
    event.preventDefault();
    tapMotion(event.currentTarget.querySelector("button"));
    setAssistantNote("你的修改已保留在当前草稿，进入作战室后仍需确认并提交。");
    setToast("草稿已更新，尚未对外发送");
  }

  async function copyDraft() {
    try {
      await navigator.clipboard.writeText(draft);
      setToast("草稿已复制");
    } catch {
      setToast("复制失败，请手动选择草稿内容");
    }
  }

  function resetDraft() {
    setDraft(baseDraft);
    setAssistantNote("已恢复为本条行动的原始建议。");
    setToast("已恢复原始建议");
  }

  return (
    <section className="continuity-panel" ref={panelRef} aria-label={`${customer} AI 连续操作区`}>
      <header className="continuity-header">
        <div className="continuity-title">
          <span className="priority-rank">{index + 1}</span>
          <div><strong>{customer}</strong><small>{item.priority || "P?"}</small></div>
          <p>{compactSentence(itemTitle(item), 70)}</p>
        </div>
        <button className="continuity-primary" type="button" onClick={(event) => { tapMotion(event.currentTarget); onEnter(draft); }}>
          确认打法，进入作战室 <ArrowRight size={16} />
          <span>你确认后进入；系统不会自动发送或改变状态</span>
        </button>
      </header>

      <JourneyRail activeStep={3} compact />

      <div className="continuity-grid">
        <section className="insight-card">
          <div className="continuity-section-title">
            <span><BrainCircuit size={18} /></span>
            <div><strong>AI 洞察摘要</strong><small>基于当前账户与时间证据</small></div>
            <StatusChip tone="success">已读</StatusChip>
          </div>
          <p className="insight-lead">{actionWhyNow(item)}</p>
          <div className="insight-recommendation">
            <span>推荐节奏</span>
            <ul>
              <li><CircleCheck size={14} />先按当前触发点发起一次明确确认</li>
              <li><CircleCheck size={14} />把参与人、判断事项和会议出口写进邀约</li>
              <li><CircleCheck size={14} />若未确认，保留证据并安排下一次触发</li>
            </ul>
          </div>
          <div className="confidence-summary">
            <ConfidenceGauge value={completeness.score} />
            <div>
              <strong>证据完整度 {completeness.passed}/{completeness.total}</strong>
              <span>{completeness.missing.length ? `仍缺：${completeness.missing.map((check) => check.label).join("、")}` : "来源、时间、下一步、账户与客户沉淀均已齐。"}</span>
            </div>
          </div>
          <div className="completeness-checks" aria-label="证据完整度明细">
            {completeness.checks.map((check) => (
              <span key={check.id} className={check.ok ? "is-complete" : "is-missing"}>
                {check.ok ? <CircleCheck size={12} /> : <CircleAlert size={12} />}{check.label}
              </span>
            ))}
          </div>
        </section>

        <section className="evidence-card">
          <div className="continuity-section-title">
            <span><Orbit size={18} /></span>
            <div><strong>证据来源与处理</strong><small>只读合并，不改变原始记录</small></div>
          </div>
          <div className="evidence-processing-list">
            {evidenceItems.map(({ icon: Icon, label, detail, status, tone }) => (
              <div key={label}>
                <span className={`evidence-icon tone-${tone}`}><Icon size={15} /></span>
                <div><strong>{label}</strong><small>{detail}</small></div>
                <em className={`tone-${tone}`}>{status}</em>
              </div>
            ))}
          </div>
          <p className="processing-time">证据最后处理时间 {formatDateTime(data.dashboard?.generated_at, "刚刚")}</p>
        </section>

        <section className="copilot-card">
          <div className="continuity-section-title">
            <span><Bot size={18} /></span>
            <div><strong>智能草稿助手</strong><small>规则模板 · 仅生成草稿</small></div>
          </div>
          <div className="copilot-thread">
            <div className="user-bubble">先把这条行动变成一段能直接推进的口径。</div>
            <div className="assistant-bubble">
              <span><Bot size={14} /></span>
              <div><strong>草稿助手</strong><small>{assistantNote}</small><p>{draft}</p></div>
            </div>
          </div>
          <div className="copilot-presets">
            <button type="button" onClick={(event) => applyPreset("invite", event.currentTarget)}><Mail size={14} />生成正式邀约</button>
            <button type="button" onClick={(event) => applyPreset("talking", event.currentTarget)}><MessageSquareText size={14} />整理会议口径</button>
            <button type="button" onClick={(event) => applyPreset("budget", event.currentTarget)}><Target size={14} />生成预算清单</button>
          </div>
          <form className="copilot-input" onSubmit={submitPrompt}>
            <Paperclip size={16} aria-hidden="true" />
            <textarea rows={3} value={draft} onChange={(event) => setDraft(event.target.value)} aria-label="可编辑推进草稿" />
            <button type="submit" aria-label="保存当前草稿"><Send size={16} /></button>
          </form>
          <div className="copilot-utilities">
            <button type="button" onClick={copyDraft}><Copy size={14} />复制草稿</button>
            <button type="button" onClick={resetDraft}><RotateCcw size={14} />恢复建议</button>
          </div>
          <p className="copilot-boundary">当前为本地规则草稿，不会自动发送或创建跟进动作；需要你确认后执行。</p>
        </section>
      </div>
    </section>
  );
}

function FilterButton({ active, onClick, label, count }) {
  return (
    <button type="button" role="tab" aria-selected={active} className={active ? "is-active" : ""} onClick={onClick}>
      <span>{label}</span>
      <strong>{count}</strong>
    </button>
  );
}

function ActionRow({ item, onClick }) {
  const overdue = item.schedule_bucket === "overdue" || Number(item.minutes_left) < 0;
  return (
    <button className="action-row" type="button" onClick={onClick}>
      <span className={`action-priority ${overdue ? "is-overdue" : ""}`}>{item.priority || (overdue ? "超" : "待")}</span>
      <span className="action-copy">
        <span className="action-meta">
          <strong>{item.customer || "待绑定客户"}</strong>
          <span>{item.project_title || itemSource(item)}</span>
        </span>
        <span className="action-title">{itemTitle(item)}</span>
        <span className="action-subtitle">{item.risk || item.evidence || item.next_step || "打开后补充本轮处理结果"}</span>
        {item.message_delivery?.label ? (
          <span className={`action-delivery is-${item.message_delivery.status || "pending"}`}>
            <Bell size={12} />{item.message_delivery.label}
          </span>
        ) : null}
      </span>
      <span className="action-time">
        <StatusChip tone={overdue ? "danger" : item.schedule_bucket === "today" ? "warning" : "neutral"}>
          {item.source_type === "project_round" ? (item.deadline || "尚无约定日期") : item.countdown_label || item.stage || item.status || "待处理"}
        </StatusChip>
        <ChevronRight size={19} aria-hidden="true" />
      </span>
    </button>
  );
}

function ReceiptRow({ receipt }) {
  return (
    <article className="receipt-row">
      <CheckCircle2 size={19} aria-hidden="true" />
      <div>
        <strong>{receipt.customer || "客户事项"} · {receipt.title || "处理结果"}</strong>
        <p>{receipt.resolution || receipt.next_step || "处理结果已记录"}</p>
      </div>
      <div>
        <StatusChip tone={receipt.status === "已闭环" ? "success" : "info"}>{receipt.status || "已处理"}</StatusChip>
        <span>{formatDateTime(receipt.submitted_at, "")}</span>
      </div>
    </article>
  );
}

function Workroom({ item, data, onBack, refresh, onNavigate, setToast, backLabel = "返回行动队列" }) {
  const registerGuard = useContext(NavigationGuardContext), askDiscard = useDiscardChanges();
  const [status, setStatus] = useState("");
  const [resolution, setResolution] = useState(item.resolution || "");
  const [nextStep, setNextStep] = useState(item.copilot_draft || item.next_step || item.action || "");
  const [deadline, setDeadline] = useState(String(item.deadline || "").slice(0, 16));
  const [syncFeishu, setSyncFeishu] = useState(Boolean(item.calendar?.task_guid || item.calendar?.task_id));
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [receipt, setReceipt] = useState(null);
  const requestId = useRef(workroomRequestId(item));
  const workroomRef = useRef(null);
  const followupRef = useRef(null);
  const customer = item.customer || "待绑定客户";
  const account = matchingAccount(item, data);
  const deal = (data.dashboard?.deal_board || []).find((entry) => sameCustomer(entry.name, customer));
  const knowledge = relatedKnowledge(item, data).slice(0, 4);
  const completeness = evidenceCompleteness(item, data);
  const latestReceipt = (data.dashboard?.workflow_state?.receipts || [])
    .filter((entry) => (entry.action_id && [item.id, item.todo_id, item.workflow_key].includes(entry.action_id)) || (entry.todo?.id && [item.id, item.todo_id, item.workflow_key].includes(entry.todo.id)) || (entry.closed_todo?.todo?.id && [item.id, item.todo_id, item.workflow_key].includes(entry.closed_todo.todo.id)))
    .sort((left, right) => String(right.submitted_at || "").localeCompare(String(left.submitted_at || "")))[0];
  const isClosed = status === "已处理";
  const statusOption = STATUS_OPTIONS.find((option) => option.value === status);

  const dirty = !receipt && Boolean(status || resolution !== (item.resolution || '') || nextStep !== (item.copilot_draft || item.next_step || item.action || '') || deadline !== String(item.deadline || '').slice(0, 16) || syncFeishu !== Boolean(item.calendar?.task_guid || item.calendar?.task_id));
  const canLeave = useCallback(async () => !submitting && (!dirty || await askDiscard('这条行动的反馈尚未保存，离开会放弃本次修改。')), [submitting, dirty, askDiscard]);
  useEffect(() => registerGuard?.(canLeave), [registerGuard, canLeave]);
  useEffect(() => { const warn = event => { if (dirty || submitting) { event.preventDefault(); event.returnValue = ''; } }; window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [dirty, submitting]);
  const back = async () => { if (await canLeave()) onBack(); };
  useEffect(() => {
    if (item.source_type === 'project_round') { onNavigate('projects', { projectId: item.project_id, projectTitle: item.project_title, customer: item.customer }); return; }
    document.querySelector('.app-main')?.scrollTo({ top: 0, behavior: 'instant' });
  }, [item]);

  useLayoutEffect(() => {
    if (!workroomRef.current || !motionAllowed()) return undefined;
    const context = gsap.context(() => {
      gsap.fromTo(
        receipt ? ".completion-state" : [".workroom-page .page-header", ".journey-rail", ".action-form", ".context-column"],
        { autoAlpha: 0, y: 14 },
        { autoAlpha: 1, y: 0, duration: 0.38, stagger: 0.055, ease: "power2.out", clearProps: "transform" },
      );
    }, workroomRef);
    return () => context.revert();
  }, [receipt]);

  useLayoutEffect(() => {
    if (!followupRef.current || !status || isClosed || !motionAllowed()) return undefined;
    gsap.fromTo(
      followupRef.current,
      { autoAlpha: 0, height: 0, y: -8 },
      { autoAlpha: 1, height: "auto", y: 0, duration: 0.34, ease: "power2.out", clearProps: "height,transform" },
    );
    return () => gsap.killTweensOf(followupRef.current);
  }, [status, isClosed]);

  async function submit(event) {
    event.preventDefault();
    setFormError("");
    if (!status) return setFormError("先选择本轮处理出口。");
    if (!resolution.trim()) return setFormError("请写清这次实际推进到了哪里。");
    if (!isClosed && !nextStep.trim()) return setFormError("未闭环时必须写清下一步动作。");
    if (!isClosed && !deadline) return setFormError("未闭环时必须选择下一次触发时间。");
    setSubmitting(true);
    try {
      const payload = await api.post("/api/risk-evidence", {
        request_id: requestId.current,
        account_id: account?.id || item.account_id || "",
        project_id: item.project_id || "",
        archive_revision:item.project_archive?.revision||0,
        customer,
        title: itemTitle(item),
        evidence: item.risk || item.evidence || "",
        action: item.action || item.next_step || itemTitle(item),
        resolution,
        next_step: isClosed ? "" : nextStep,
        deadline: isClosed ? "" : deadline,
        status,
        source_view: itemSource(item),
        workflow_key: item.workflow_key || item.id || itemKey(item),
        object_type: item.context_type || (item.source_scope || item.source_type ? "schedule" : "action"),
        todo_id: item.todo_id || item.id || "",
        reminder_minutes: 10,
        sync_calendar: !isClosed && syncFeishu,
      });
      setReceipt(payload.receipt || { status: isClosed ? "已闭环" : status, todo: payload.todo });
      setToast(isClosed ? "本轮已闭环" : "本轮已处理，下一次提醒已安排");
      await refresh({ quiet: true });
    } catch (requestError) {
      setFormError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (receipt) {
    const hasNext = Boolean(receipt.todo?.deadline || receipt.next_step);
    return (
      <div className="page-stack" ref={workroomRef}>
        <button className="back-link" type="button" onClick={back}><ChevronLeft size={17} />{backLabel}</button>
        <JourneyRail activeStep={hasNext ? 6 : 5} />
        <section className="completion-state" role="status" aria-live="polite">
          <CheckCircle2 size={34} />
          <p className="page-eyebrow">处理结果已记录</p>
          <h1>{receipt.status === "已闭环" ? "这件事已经退出活动队列" : "本轮处理完成，系统会在下次触发时叫回"}</h1>
          <p>{receipt.resolution || resolution}</p>
          {hasNext ? (
            <dl className="completion-next">
              <div><dt>下一步</dt><dd>{receipt.next_step || receipt.todo?.next_step}</dd></div>
              <div><dt>触发时间</dt><dd>{formatDateTime(receipt.todo?.deadline)}</dd></div>
              <div><dt>飞书承接</dt><dd>{receipt.calendar?.message || "未启用"}</dd></div>
            </dl>
          ) : null}
          <div className="completion-actions">
            <Button label={backLabel} variant="primary" onClick={back} />
            {hasNext ? <Button label="查看下次提醒" variant="secondary" onClick={() => onNavigate("reminders")} /> : null}
            {account ? <Button label="回到账户推进" variant="ghost" onClick={() => onNavigate("accounts")} /> : null}
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="page-stack workroom-page" ref={workroomRef}>
      <button className="back-link" type="button" onClick={back}><ChevronLeft size={17} />{backLabel}</button>
      <PageHeader
        eyebrow="当前客户作战室"
        title={customer}
        subtitle={itemTitle(item)}
        actions={item.calendar?.app_link ? (
          <a className="external-button" href={item.calendar.app_link} target="_blank" rel="noreferrer">打开飞书<ExternalLink size={15} /></a>
        ) : null}
      />
      <JourneyRail activeStep={4} />

      <div className="workroom-layout">
        <form className="action-form" onSubmit={submit}>
          <div className="section-heading">
            <div><p>先处理这件事</p><h2>本轮结果与出口</h2></div>
            <StatusChip tone={isTranscriptCandidate(item) ? "info" : item.schedule_bucket === "overdue" ? "danger" : "warning"}>{item.countdown_label || item.status || "待处理"}</StatusChip>
          </div>

          <div className="status-choice" role="radiogroup" aria-label="本轮处理出口">
            {STATUS_OPTIONS.map((option, index) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={status === option.value}
                data-radio-value={option.value}
                tabIndex={status === option.value || (!status && index === 0) ? 0 : -1}
                className={status === option.value ? "is-selected" : ""}
                onClick={(event) => {
                  tapMotion(event.currentTarget);
                  setStatus(option.value);
                }}
                onKeyDown={(event) => handleRadioArrow(event, STATUS_OPTIONS.map((item) => item.value), status, setStatus)}
              >
                <strong>{option.label}</strong>
                <span>{option.description}</span>
              </button>
            ))}
          </div>

          <TextArea
            label="这次实际推进到哪了（必填）"
            value={resolution}
            onChange={setResolution}
            rows={3}
            placeholder="记录已确认事实、对方反馈和仍未解决的问题。"
          />

          {!isClosed && status ? (
            <div className="followup-fields" ref={followupRef}>
              <TextArea
                label="下一步动作（必填）"
                value={nextStep}
                onChange={setNextStep}
                rows={3}
                placeholder="写清找谁、确认什么、拿到什么结果。"
              />
              <label className="native-field">
                <span>下一次触发时间 <b>必填</b></span>
                <input type="datetime-local" value={deadline} onInput={(event) => setDeadline(event.currentTarget.value)} onChange={(event) => setDeadline(event.target.value)} required />
              </label>
              <label className="check-field">
                <input type="checkbox" checked={syncFeishu} onChange={(event) => setSyncFeishu(event.target.checked)} />
                <span><strong>同步飞书任务并启用私聊提醒</strong><small>到期前 10 分钟私聊；超期后每日汇总，不占用日历。</small></span>
              </label>
            </div>
          ) : null}

          {formError ? <p className="form-error" role="alert">{formError}</p> : null}
          {status ? (
            <section className="state-change-preview" aria-live="polite">
              <div className="state-change-title">
                <CircleCheck size={17} />
                <div><strong>提交前状态预览</strong><span>同一事项只进入一个新状态，不保留重复旧待办。</span></div>
              </div>
              <dl>
                <div><dt>本轮出口</dt><dd>{statusOption?.label || status}</dd></div>
                <div><dt>当前事项</dt><dd>{isClosed ? "提交后退出活动队列" : "本轮完成，等待下一次触发"}</dd></div>
                {!isClosed ? <div><dt>下一次回来</dt><dd>{formatDateTime(deadline)}</dd></div> : null}
                {!isClosed ? <div><dt>飞书承接</dt><dd>{syncFeishu ? "创建任务；约定时间前私聊一次，过期后待重新安排" : "仅保留工作台 Deadline"}</dd></div> : null}
              </dl>
            </section>
          ) : null}
          <div className="form-footer">
            <Button label="确认并记录本轮结果" variant="primary" type="submit" isLoading={submitting} isDisabled={submitting} />
            <span>提交后只进入一个新状态，不复制旧事项。</span>
          </div>
        </form>

        <aside className="context-column" aria-label="客户上下文">
          <details className="workroom-ai-context" open>
            <summary>
              <span><BrainCircuit size={17} /></span>
              <div><strong>已确认的打法与证据</strong><small>从首页连续带入，可折叠</small></div>
            </summary>
            <div className="workroom-ai-body">
              <div className="workroom-ai-insight">
                <span>为什么现在处理</span>
                <p>{actionWhyNow(item)}</p>
              </div>
              <div className="workroom-ai-draft">
                <span>已确认推进草稿</span>
                <p>{nextStep || actionRecommendation(item)}</p>
              </div>
              <div className="workroom-completeness">
                <div><ConfidenceGauge value={completeness.score} /><span><strong>证据完整度 {completeness.passed}/{completeness.total}</strong><small>{completeness.missing.length ? `待补：${completeness.missing.map((check) => check.label).join("、")}` : "关键证据已齐"}</small></span></div>
                <div className="completeness-checks">
                  {completeness.checks.map((check) => <span key={check.id} className={check.ok ? "is-complete" : "is-missing"}>{check.ok ? <CircleCheck size={12} /> : <CircleAlert size={12} />}{check.label}</span>)}
                </div>
              </div>
              {latestReceipt ? (
                <div className="latest-receipt-inline">
                  <span>最近一次回执 · {formatDateTime(latestReceipt.submitted_at, "")}</span>
                  <strong>{latestReceipt.status || "已处理"}</strong>
                  <p>{latestReceipt.resolution || latestReceipt.next_step || "处理结果已记录"}</p>
                </div>
              ) : null}
            </div>
          </details>

          <section>
            <div className="section-heading compact"><div><p>为什么现在处理</p><h2>事项依据</h2></div></div>
            <p className="context-lead">{item.risk || item.evidence || item.next_step || "当前事项没有补充依据。"}</p>
            <dl className="metadata-list">
              <div><dt>来源</dt><dd>{itemSource(item)}</dd></div>
              <div><dt>{isTranscriptCandidate(item) ? "提取时间" : "原时间"}</dt><dd>{formatDateTime(item.deadline || item.review_at)}</dd></div>
              <div><dt>客户阶段</dt><dd>{account ? stageLabel(data.accounts?.stages, account.stage) : deal?.stage || "未进入正式账户"}</dd></div>
              <div><dt>时间状态</dt><dd>{item.countdown_label || account?.time_state?.label || "待判断"}</dd></div>
            </dl>
          </section>

          <section>
            <div className="section-heading compact"><div><p>客户背景</p><h2>本次需要记住</h2></div></div>
            <dl className="metadata-list long">
              <div><dt>当前机会</dt><dd>{account?.opportunity || deal?.note || "暂无正式判断"}</dd></div>
              <div><dt>切入口</dt><dd>{account?.cut_in || deal?.next_action || "待补充"}</dd></div>
              <div><dt>证据缺口</dt><dd>{account?.gaps?.length ? account.gaps.join("、") : "关键证据已齐"}</dd></div>
            </dl>
          </section>

          {knowledge.length ? (
            <section>
              <div className="section-heading compact"><div><p>AI知识库</p><h2>最近沉淀</h2></div></div>
              <div className="context-timeline">
                {knowledge.map((entry) => <div key={`${entry.path}-${entry.updated_at}`}><time>{entry.updated_at}</time><strong>{entry.title}</strong><p>{entry.preview || entry.summary}</p></div>)}
              </div>
            </section>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

function AccountsView({ data, refresh, navigate, setToast, discovery = false }) {
  const accountData = data.accounts || {};
  const prospecting = data.prospecting || {};
  const candidateCount = prospectSurfaceItems(prospecting.leads || [], "candidate").length;
  const watchCount = prospectSurfaceItems(prospecting.leads || [], "watch").length;
  const ignoredCount = prospectSurfaceItems(prospecting.leads || [], "ignored").length;
  const formalAccounts = accountData.accounts || [];
  const attentionAccounts = formalAccounts.filter((account) => ["overdue", "due", "today"].includes(account.time_state?.id));
  const gapAccounts = formalAccounts.filter((account) => account.gaps?.length);
  const noDeadlineAccounts = formalAccounts.filter((account) => !account.time_state?.id || account.time_state.id === "none");
  const [filter, setFilter] = useState(discovery ? "candidates" : "all");
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [selectedLeadId, setSelectedLeadId] = useState("");
  const selectedAccount = (accountData.accounts || []).find((item) => item.id === selectedAccountId);
  const selectedLead = (prospecting.leads || []).find((item) => item.id === selectedLeadId);

  useEffect(() => {
    if(view!=="projects"){document.querySelector(".app-main")?.scrollTo({ top: 0, behavior: "instant" });window.scrollTo({top:0,behavior:"instant"});}
  }, [selectedAccountId, selectedLeadId]);

  if (selectedLead) {
    return (
      <ProspectDetail
        lead={selectedLead}
        mode={selectedLead.decision === "watch" ? "watch" : selectedLead.decision === "ignored" ? "ignored" : "candidate"}
        onBack={() => setSelectedLeadId("")}
        refresh={refresh}
        onAccepted={(accountId) => {
          setSelectedLeadId("");
          setSelectedAccountId(accountId);
          setFilter("qualify");
        }}
        setToast={setToast}
      />
    );
  }

  if (selectedAccount) {
    return (
      <AccountDetail
        account={selectedAccount}
        accountData={accountData}
        onBack={() => setSelectedAccountId("")}
        refresh={refresh}
        navigate={navigate}
        setToast={setToast}
      />
    );
  }

  const accounts = formalAccounts.filter((account) => {
    if (filter === "all") return true;
    if (filter === "attention") return ["overdue", "due", "today"].includes(account.time_state?.id);
    if (filter === "gaps") return Boolean(account.gaps?.length);
    if (filter === "no-deadline") return !account.time_state?.id || account.time_state.id === "none";
    return account.stage === filter;
  });
  const candidates = prospectSurfaceItems(
    prospecting.leads || [],
    filter === "watch" ? "watch" : filter === "ignored" ? "ignored" : "candidate",
  );
  const operatingSlices = [
    { id: "candidates", label: "待准入判断", count: candidateCount, detail: "需要你决定是否进入主账本" },
    { id: "attention", label: "今日 / 超期", count: attentionAccounts.length, detail: "已进入时间触发窗口" },
    { id: "gaps", label: "证据待补客户", count: gapAccounts.length, detail: `${accountData.summary?.gap_count || 0} 个证据缺口` },
    { id: "no-deadline", label: "无触发时间", count: noDeadlineAccounts.length, detail: "不会自动回到今日行动" },
  ];
  const accountFilterMeta = {
    attention: ["今日 / 超期账户", "这些正式账户已经进入时间触发窗口，应先确认本轮是否继续推进。"],
    gaps: ["证据待补客户", "按客户查看证据缺口；补证据本身不会自动生成今日行动。"],
    "no-deadline": ["无触发时间账户", "这些账户不会自动回到今日行动，需要补充下一次明确触发。"],
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="客户主链"
        title={discovery ? "发现机会" : "客户登记与阶段"}
        subtitle={discovery ? "现挂标讯与历史采购分开看。历史采购只提供建联依据，今年是否有需求，需要实际沟通验证。" : "沿用历史登记；公司 CRM 正式接口待接通，不将本地登记视为当前客户归属证明。"}
        actions={<StatusChip tone="success">工作台主账本 · {accountData.summary?.account_count || 0} 个账户</StatusChip>}
      />

      {discovery && <section className="project-judgement"><h2>建联前，先核实主体归属</h2><p>自己名下可推进；其他 K100 同事名下默认不联系；直销、渠道、标品团队先协商联合。未查到不等于无人持有，还需核实保护状态。</p><p>营收 50 亿以上名单需公开证据；其他潜在线索独立保留，不因规模不足直接当成无价值。</p><a href="https://crm.example.invalid/sales-workspace" target="_blank" rel="noreferrer">去公司 CRM 查主体与保护状态 ↗</a></section>}
      {!discovery && <section className="account-operating-slices" aria-label="客户经营切片">
        {operatingSlices.map((slice) => (
          <button key={slice.id} type="button" className={filter === slice.id ? "is-active" : ""} onClick={() => setFilter(slice.id)}>
            <span>{slice.label}</span>
            <strong>{slice.count}</strong>
            <small>{slice.detail}</small>
          </button>
        ))}
      </section>}

      <section className="pipeline-surface">
        <div className="pipeline-tab-groups">
          {discovery && <div className="pipeline-tab-group">
            <span className="pipeline-group-label">准入与旁路</span>
            <div className="pipeline-tabs" role="tablist" aria-label="准入与旁路">
              <button type="button" role="tab" aria-selected={filter === "candidates"} className={filter === "candidates" ? "is-active" : ""} onClick={() => setFilter("candidates")}>
                <Sparkles size={16} /><span>当前候选标讯</span><strong>{candidateCount}</strong>
              </button>
              <button type="button" role="tab" aria-selected={filter === "watch"} className={filter === "watch" ? "is-active" : ""} onClick={() => setFilter("watch")}>
                <Clock3 size={16} /><span>历史采购 / 培育</span><strong>{watchCount}</strong>
              </button>
              <button type="button" role="tab" aria-selected={filter === "ignored"} className={filter === "ignored" ? "is-active" : ""} onClick={() => setFilter("ignored")}>
                <span>已剔除</span><strong>{ignoredCount}</strong>
              </button>
            </div>
          </div>}
          {!discovery && <div className="pipeline-tab-group is-account-flow">
            <span className="pipeline-group-label">正式账户推进</span>
            <div className="pipeline-tabs" role="tablist" aria-label="正式账户推进">
              {(accountData.stages || []).map((stage) => (
                <button key={stage.id} type="button" role="tab" aria-selected={filter === stage.id} className={filter === stage.id ? "is-active" : ""} onClick={() => setFilter(stage.id)}>
                  <span>{stage.label}</span><strong>{stage.count || 0}</strong>
                </button>
              ))}
              <button type="button" role="tab" aria-selected={filter === "all"} className={filter === "all" ? "is-active" : ""} onClick={() => setFilter("all")}>
                <span>全部账户</span><strong>{accountData.summary?.account_count || 0}</strong>
              </button>
            </div>
          </div>}
        </div>

        <div className="pipeline-summary">
          <div>
            <strong>{accountFilterMeta[filter]?.[0] || (filter === "candidates" ? "每天最多 3 个准入判断" : filter === "watch" ? "AI后台维护的升级与替换机会" : filter === "ignored" ? "已剔除，可随时恢复" : filter === "all" ? "正式账户总览" : stageLabel(accountData.stages, filter))}</strong>
            <span>{accountFilterMeta[filter]?.[1] || (filter === "candidates" ? "只展示窗口、业务范围和信源都成立的最高优先级项目。" : filter === "watch" ? "历史采购证明客户有意图；没有新触发前不进入今日行动、提醒或飞书任务。" : filter === "ignored" ? "保留剔除原因和信源，不进入账户或执行链。" : "客户阶段描述业务进程；提醒时间在单独的时间状态里显示。")}</span>
          </div>
          <div>
            <span>{["candidates", "watch", "ignored"].includes(filter) ? "当前数量" : accountFilterMeta[filter] ? "客户数量" : "证据缺口"}</span>
            <strong>{filter === "candidates" ? candidateCount : filter === "watch" ? watchCount : filter === "ignored" ? ignoredCount : accountFilterMeta[filter] ? accounts.length : accountData.summary?.gap_count || 0}</strong>
          </div>
        </div>

        {["candidates", "watch", "ignored"].includes(filter) ? (
          candidates.length ? <div className="account-list">{candidates.map((lead) => <ProspectRow key={lead.id} lead={lead} mode={filter} onClick={() => setSelectedLeadId(lead.id)} />)}</div> : <EmptyMessage title={filter === "watch" ? "暂时没有长期机会" : "候选池已经判断完"} description={filter === "watch" ? "AI会继续检查历史采购、供应商和下一轮升级信号。" : "下一次 AI 扫描发现符合时间窗口的项目后会出现在这里。"} />
        ) : (
          accounts.length ? <div className="account-list">{accounts.map((account) => <AccountRow key={account.id} account={account} stages={accountData.stages} onClick={() => setSelectedAccountId(account.id)} />)}</div> : <EmptyMessage title="这个阶段暂时没有账户" description="账户满足推进门槛后会进入这里。" />
        )}
      </section>
    </div>
  );
}

function ProspectRow({ lead, mode = "candidates", onClick }) {
  const actionable = lead.actionability === "actionable";
  const watchMode = mode === "watch";
  return (
    <button className="account-row" type="button" onClick={onClick}>
      <span className="account-avatar ai">AI</span>
      <span className="account-main">
        <span className="account-title"><strong>{lead.company || "待识别客户"}</strong><StatusChip tone={watchMode ? "info" : actionable ? "success" : lead.decision === "verify" ? "warning" : "neutral"}>{watchMode ? lead.watch_type || "升级与替换" : lead.status || "待判断"}</StatusChip></span>
        <span>{watchMode ? lead.watch_reason || lead.title : lead.title || "暂无公开信号标题"}</span>
        <small>{watchMode ? `下一触发：${lead.next_trigger || "新招采、扩容或供应商替换"}` : `${lead.deadline ? `招采截止 ${lead.deadline}` : "时间窗口待补证"} · ${lead.scale_rule || "规模待核验"}`}</small>
      </span>
      <ChevronRight size={19} />
    </button>
  );
}

function AccountRow({ account, stages, onClick }) {
  const timeTone = account.time_state?.id === "overdue" ? "danger" : account.time_state?.id === "due" ? "warning" : "neutral";
  const stateLabel = ACCOUNT_STATE_OPTIONS.find((item) => item.value === (account.account_state || "active"))?.label || "推进中";
  return (
    <button className="account-row" type="button" onClick={onClick}>
      <span className="account-avatar">{String(account.name || "客").slice(0, 1)}</span>
      <span className="account-main">
        <span className="account-title"><strong>{account.name}</strong><StatusChip tone="info">{stageLabel(stages, account.stage)}</StatusChip>{account.account_state !== "active" ? <StatusChip>{stateLabel}</StatusChip> : null}</span>
        <span>{account.next_action || account.opportunity || "待补下一步"}</span>
        <small>{account.priority || "P?"} · {account.industry || "行业待补"} · {account.record_source === "workbench_ai_admission" ? "工作台准入" : "历史账户"}</small>
      </span>
      <span className="account-end"><StatusChip tone={timeTone}>{account.time_state?.label || "未安排提醒"}</StatusChip><ChevronRight size={19} /></span>
    </button>
  );
}

function ProspectDetail({ lead, mode = "candidate", onBack, refresh, onAccepted, setToast }) {
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");
  const [confirmIgnore, setConfirmIgnore] = useState(false);
  const link = sourceLink(lead.source_url || lead.url || "");
  const admissionMissing = prospectAdmissionMissing(lead);

  async function decide(target) {
    setLoading(target);
    setError("");
    try {
      const payload = await api.post("/api/prospecting/lead", { id: lead.id, target });
      await refresh({ quiet: true });
      if (target === "accept") {
        setToast("客户已进入工作台正式账户");
        onAccepted(payload.lead?.account_id || payload.customer_pool?.account_id || "");
      } else {
        setToast(target === "verify" ? "已交给 AI 继续补证据" : target === "watch" ? "已转入升级与替换，由 AI 后台维护" : "已从候选池剔除");
        onBack();
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading("");
    }
  }

  return (
    <div className="page-stack">
      <button className="back-link" type="button" onClick={onBack}><ChevronLeft size={17} />返回{mode === "watch" ? "升级与替换" : mode === "ignored" ? "已剔除" : "AI 候选"}</button>
      <PageHeader
        eyebrow={mode === "watch" ? "升级与替换 · AI后台维护" : mode === "ignored" ? "已剔除 · 可恢复" : "AI候选 · 等待你的准入判断"}
        title={lead.company || "待识别客户"}
        subtitle={lead.title || "公开信号待补齐"}
        actions={link ? <a className="external-button" href={link} target="_blank" rel="noreferrer">查看信源<ExternalLink size={15} /></a> : null}
      />

      <section className="decision-surface">
        <div className="decision-callout">
          <Sparkles size={22} />
          <div><strong>{mode === "watch" ? "AI维护逻辑" : "AI判断"}</strong><p>{mode === "watch" ? lead.watch_reason || lead.entry_strategy : lead.entry_strategy || lead.why_now || lead.purchase_signal || "当前需要补齐规模、时间窗口和进入路径后再判断。"}</p></div>
        </div>
        {mode === "candidate" ? <div className={`admission-gate ${admissionMissing.length ? "has-gaps" : "is-ready"}`}><strong>{admissionMissing.length ? `准入前还缺：${admissionMissing.join("、")}` : "已满足正式账户最低准入条件"}</strong><span>规模证据可以在账户推进中继续补齐，但真实信源、业务触发、切口和有效窗口必须先成立。</span></div> : null}
        {confirmIgnore ? <p className="form-warning">剔除后不会进入执行链，但会保留信源和判断记录。再次点击“确认剔除”完成操作。</p> : null}
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <div className="decision-actions">
          {mode === "candidate" ? <Button label="准入正式账户" variant="primary" isLoading={loading === "accept"} isDisabled={Boolean(loading) || Boolean(admissionMissing.length)} onClick={() => decide("accept")} /> : null}
          {mode !== "watch" ? <Button label={mode === "candidate" ? "让 AI 补证据" : "恢复到待判断"} variant="secondary" isLoading={loading === "verify"} isDisabled={Boolean(loading)} onClick={() => decide("verify")} /> : null}
          {mode !== "watch" ? <Button label="转入升级与替换" variant="ghost" isLoading={loading === "watch"} isDisabled={Boolean(loading)} onClick={() => decide("watch")} /> : null}
          {mode !== "ignored" ? <Button label={confirmIgnore ? "确认移出" : mode === "watch" ? "移出升级与替换" : "剔除候选"} variant="destructive" isLoading={loading === "ignore"} isDisabled={Boolean(loading)} onClick={() => confirmIgnore ? decide("ignore") : setConfirmIgnore(true)} /> : null}
        </div>
        <dl className="evidence-grid">
          {mode === "watch" ? <><div><dt>机会类型</dt><dd>{lead.watch_type || "升级与替换"}</dd></div><div><dt>下一触发</dt><dd>{lead.next_trigger || "等待新招采、扩容或替换信号"}</dd></div></> : null}
          <div><dt>真实触发</dt><dd>{lead.purchase_signal || lead.title || "待补"}</dd></div>
          <div><dt>{mode === "watch" ? "本轮窗口" : "准备窗口"}</dt><dd>{lead.deadline ? mode === "watch" ? `${lead.deadline} · ${lead.time_window_label || "不作为当前可投"}` : `截至 ${lead.deadline}` : mode === "watch" ? "未核到明确截止，本轮不作为当前可投" : "未核到明确截止时间"}</dd></div>
          {mode === "watch" ? <div><dt>最近检查</dt><dd>{formatDateTime(lead.detail_checked_at || lead.watch_since, "等待下一次 AI 扫描")}</dd></div> : null}
          {mode === "watch" ? <div><dt>触发后去向</dt><dd>回到 AI 候选，等待你重新判断是否准入</dd></div> : null}
          <div><dt>规模证据</dt><dd>{evidenceLabel(lead.revenue_evidence, lead.scale_rule || "待补")}</dd></div>
          <div><dt>供应商路径</dt><dd>{text(lead.supplier_path, "待补")}</dd></div>
          <div><dt>业务平台切口</dt><dd>{lead.entry_strategy || lead.youzan_fit || "待补"}</dd></div>
          <div><dt>{mode === "watch" ? "执行边界" : "可行动性"}</dt><dd>{mode === "watch" ? lead.execution_boundary || "AI后台监控，不生成销售待办" : lead.actionability === "actionable" ? "时间和项目方向可行动" : "仍有关键证据缺口"}</dd></div>
        </dl>
      </section>
    </div>
  );
}

function accountGateMissing(account, targetStage) {
  const verifiedRevenue = (value) => {
    const evidence = text(value).toLowerCase();
    return Boolean(evidence) && !["pending_public_lookup", "待补", "待查", "未核验", "none"].some((marker) => evidence.includes(marker));
  };
  const checks = {
    qualify: [["source", "来源证据"], ["recent_signal", "触发信号"]],
    path: [["revenue_evidence", "规模证据", verifiedRevenue], ["source", "来源链接"], ["cut_in", "业务平台切口"]],
    contact: [["channel_count", "进入渠道"], ["next_action", "明确下一步"]],
    opportunity: [["opportunity", "机会判断"], ["next_action", "明确下一步"]],
  };
  return (checks[targetStage] || [])
    .filter(([key, , validate]) => validate ? !validate(account[key]) : !account[key])
    .map(([, label]) => label);
}

function AccountDetail({ account, accountData, onBack, refresh, navigate, setToast }) {
  const [composerOpen, setComposerOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [stateDraft, setStateDraft] = useState(account.account_state || "active");
  const [stateReason, setStateReason] = useState("");
  const [stateLoading, setStateLoading] = useState(false);
  const [error, setError] = useState("");
  const currentIndex = STAGE_ORDER.indexOf(account.stage);
  const nextStage = currentIndex >= 0 && currentIndex < STAGE_ORDER.length - 1 ? STAGE_ORDER[currentIndex + 1] : "";
  const missing = nextStage ? accountGateMissing(account, nextStage) : [];
  const link = sourceLink(account.source);
  const activeAccount = (account.account_state || "active") === "active";

  useEffect(() => {
    setStateDraft(account.account_state || "active");
  }, [account.account_state]);

  async function advance() {
    if (!nextStage || missing.length || !activeAccount) return;
    setAdvancing(true);
    setError("");
    try {
      const result = await api.post("/api/account-advancement/stage", { id: account.id, target_stage: nextStage });
      setToast(result.message || "客户阶段已更新");
      await refresh({ quiet: true });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setAdvancing(false);
    }
  }

  async function updateState() {
    if (stateDraft === (account.account_state || "active")) return;
    setStateLoading(true);
    setError("");
    try {
      const result = await api.post("/api/account-advancement/state", { id: account.id, account_state: stateDraft, reason: stateReason });
      setToast(result.message || "账户状态已更新");
      setStateReason("");
      await refresh({ quiet: true });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setStateLoading(false);
    }
  }

  return (
    <div className="page-stack account-detail-page">
      <button className="back-link" type="button" onClick={onBack}><ChevronLeft size={17} />返回客户推进</button>
      <PageHeader
        eyebrow={`${account.priority || "P?"} · ${account.industry || "行业待补"}`}
        title={account.name}
        subtitle={account.opportunity || account.status_note || "当前机会判断待补充"}
        actions={<div className="header-chips"><StatusChip tone="info">{stageLabel(accountData.stages, account.stage)}</StatusChip><StatusChip tone={account.time_state?.id === "overdue" ? "danger" : "neutral"}>{account.time_state?.label || "未安排提醒"}</StatusChip></div>}
      />

      <section className="stage-rail" aria-label="客户生命周期">
        {(accountData.stages || []).map((stage, index) => (
          <div key={stage.id} className={index < currentIndex ? "is-complete" : index === currentIndex ? "is-current" : ""}>
            <span>{index < currentIndex ? <CheckCircle2 size={16} /> : index + 1}</span>
            <strong>{stage.label}</strong>
          </div>
        ))}
      </section>

      <section className="account-state-bar">
        <div><p>账户状态</p><span>生命周期阶段描述推进到哪；账户状态负责暂停、成交、流失和归档。</span></div>
        <label className="native-field"><span>当前状态</span><select value={stateDraft} onChange={(event) => setStateDraft(event.target.value)}>{ACCOUNT_STATE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        {["paused", "lost", "archived"].includes(stateDraft) ? <label className="native-field state-reason"><span>原因 <b>必填</b></span><input value={stateReason} onChange={(event) => setStateReason(event.target.value)} placeholder="记录暂停、流失或归档原因" /></label> : null}
        <Button label="更新状态" variant="secondary" isLoading={stateLoading} isDisabled={stateLoading || stateDraft === (account.account_state || "active")} onClick={updateState} />
      </section>

      <div className="account-action-bar">
        <div><p>建议下一步</p><strong>{account.next_action || "补齐证据后确认下一步"}</strong><span>来源：{account.next_action_source || "工作台账户主账本"}</span></div>
        <Button label={composerOpen ? "收起行动" : "采纳为行动"} variant="primary" isDisabled={!activeAccount} onClick={() => setComposerOpen((value) => !value)} />
      </div>

      {composerOpen ? <ActionComposer account={account} refresh={refresh} navigate={navigate} setToast={setToast} /> : null}

      <section className="account-evidence">
        <div className="section-heading"><div><p>账户证据</p><h2>判断、切口和缺口</h2></div><div className="section-actions">{link ? <a href={link} target="_blank" rel="noreferrer">查看来源<ExternalLink size={14} /></a> : null}<Button label={evidenceOpen ? "收起补充" : "补充证据"} variant="secondary" onClick={() => setEvidenceOpen((value) => !value)} /></div></div>
        <dl className="evidence-grid">
          <div><dt>近期触发</dt><dd>{account.recent_signal || "待补"}</dd></div>
          <div><dt>规模证据</dt><dd>{evidenceLabel(account.revenue_evidence)}</dd></div>
          <div><dt>业务平台切口</dt><dd>{account.cut_in || "待补"}</dd></div>
          <div><dt>建议打法</dt><dd>{account.suggested_play || "待补"}</dd></div>
          <div><dt>查重判断</dt><dd>{account.dedupe || "待补"}</dd></div>
          <div><dt>当前缺口</dt><dd>{account.gaps?.length ? account.gaps.join("、") : "关键证据已齐"}</dd></div>
        </dl>
        {evidenceOpen ? <AccountEvidenceEditor account={account} refresh={refresh} setToast={setToast} onSaved={() => setEvidenceOpen(false)} /> : null}
      </section>

      <section className="channel-section">
        <div className="section-heading"><div><p>进入路径</p><h2>供应商与渠道</h2></div><span>{account.channel_count || 0} 条</span></div>
        {account.channels?.length ? (
          <div className="channel-table" role="table">
            {account.channels.map((channel) => (
              <div className="channel-row" role="row" key={channel.id}>
                <div role="cell"><strong>{channel.name}</strong><span>{channel.status || "待验证"}</span></div>
                <div role="cell"><p>{channel.value || channel.signal || "暂无渠道价值说明"}</p><small>{channel.next_action || "待补下一步"}</small></div>
                {sourceLink(channel.source) ? <a href={sourceLink(channel.source)} target="_blank" rel="noreferrer" aria-label={`查看 ${channel.name} 来源`}><ExternalLink size={16} /></a> : <span />}
              </div>
            ))}
          </div>
        ) : <EmptyMessage title="还没有确认进入路径" description="先补供应商、渠道或客户侧负责人，再进入正式接触。" />}
      </section>

      <section className="advance-section">
        <div>
          <p>阶段推进</p>
          <h2>{nextStage ? `下一节点：${stageLabel(accountData.stages, nextStage)}` : "已进入商机推进"}</h2>
          <span>{missing.length ? `还缺：${missing.join("、")}` : nextStage ? "关键门槛已满足，可以推进。" : "继续在行动和回执中推进预算、方案与采购。"}</span>
        </div>
        {nextStage ? <Button label={`推进到${stageLabel(accountData.stages, nextStage)}`} variant="secondary" isDisabled={!activeAccount || Boolean(missing.length) || advancing} isLoading={advancing} onClick={advance} /> : null}
      </section>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
    </div>
  );
}

function AccountEvidenceEditor({ account, refresh, setToast, onSaved }) {
  const [fields, setFields] = useState({
    recent_signal: account.recent_signal || "",
    revenue_evidence: evidenceLabel(account.revenue_evidence, ""),
    source: account.source || "",
    cut_in: account.cut_in || "",
    opportunity: account.opportunity || "",
    next_action: account.next_action || "",
    owner: account.owner || "",
    channel_path: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const set = (key) => (value) => setFields((current) => ({ ...current, [key]: value }));

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await api.post("/api/account-advancement/evidence", { id: account.id, ...fields });
      setToast(result.message || "账户证据已更新");
      await refresh({ quiet: true });
      onSaved?.();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="evidence-editor" onSubmit={submit}>
      <TextArea label="近期触发" value={fields.recent_signal} onChange={set("recent_signal")} rows={2} />
      <TextArea label="规模证据" value={fields.revenue_evidence} onChange={set("revenue_evidence")} rows={2} />
      <label className="native-field"><span>来源链接</span><input value={fields.source} onChange={(event) => set("source")(event.target.value)} placeholder="公开信源 URL" /></label>
      <TextArea label="业务平台切口" value={fields.cut_in} onChange={set("cut_in")} rows={2} />
      <TextArea label="机会判断" value={fields.opportunity} onChange={set("opportunity")} rows={2} />
      <TextArea label="明确下一步" value={fields.next_action} onChange={set("next_action")} rows={2} />
      <label className="native-field"><span>客户侧负责人</span><input value={fields.owner} onChange={(event) => set("owner")(event.target.value)} placeholder="姓名、角色或待确认部门" /></label>
      <label className="native-field"><span>进入路径 / 渠道</span><input value={fields.channel_path} onChange={(event) => set("channel_path")(event.target.value)} placeholder="供应商、渠道、部门或负责人" /></label>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <div className="form-footer"><span>保存后立即重新计算当前证据缺口。</span><Button label="保存账户证据" variant="primary" type="submit" isLoading={loading} isDisabled={loading} /></div>
    </form>
  );
}

function ActionComposer({ account, refresh, navigate, setToast }) {
  const [target, setTarget] = useState("now");
  const [nextStep, setNextStep] = useState(account.next_action || "");
  const [deadline, setDeadline] = useState(defaultDeadline());
  const [syncFeishu, setSyncFeishu] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (!nextStep.trim()) return setError("请先写清下一步动作。");
    setLoading(true);
    try {
      const result = await api.post("/api/manual-todo", {
        account_id: account.id,
        customer: account.name,
        title: nextStep,
        next_step: nextStep,
        evidence: account.opportunity || account.recent_signal || "账户推进建议",
        target,
        priority: account.priority || "P2",
        deadline: target === "scheduled" ? deadline : "",
        reminder_minutes: 10,
        sync_calendar: target === "scheduled" && syncFeishu,
      });
      await refresh({ quiet: true });
      setToast(target === "now" ? "已进入今日行动" : "已安排到下次提醒");
      navigate(target === "now" ? "today" : "reminders", target === "now" ? { focusAction: result.todo } : {});
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="inline-composer" onSubmit={submit}>
      <div className="section-heading compact"><div><p>行动承接</p><h2>确认进入哪里</h2></div></div>
      <div className="binary-choice" role="radiogroup" aria-label="行动进入位置">
        <button type="button" role="radio" aria-checked={target === "now"} className={target === "now" ? "is-selected" : ""} onClick={() => setTarget("now")}><ListTodo size={17} />今天处理</button>
        <button type="button" role="radio" aria-checked={target === "scheduled"} className={target === "scheduled" ? "is-selected" : ""} onClick={() => setTarget("scheduled")}><Clock3 size={17} />安排下次</button>
      </div>
      <TextArea label="明确下一步（必填）" value={nextStep} onChange={setNextStep} rows={3} />
      {target === "scheduled" ? (
        <div className="followup-fields compact-fields">
          <label className="native-field"><span>触发时间 <b>必填</b></span><input type="datetime-local" value={deadline} onChange={(event) => setDeadline(event.target.value)} /></label>
          <label className="check-field"><input type="checkbox" checked={syncFeishu} onChange={(event) => setSyncFeishu(event.target.checked)} /><span><strong>同步飞书任务并启用私聊提醒</strong><small>约定时间前私聊一次，过期后待重新安排；不写入日历。</small></span></label>
        </div>
      ) : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <Button label={target === "now" ? "加入今日行动" : "安排下次提醒"} variant="primary" type="submit" isLoading={loading} isDisabled={loading} />
    </form>
  );
}

function RemindersView({ data, refresh, navigate, setToast, focusAction, onFocusConsumed }) {
  const [selected, setSelected] = useState(null);
  useEffect(() => { if (focusAction) { const current = (data.reminders?.items || []).find(i => i.id === focusAction.id); if (current) setSelected(current); onFocusConsumed?.(); } }, [focusAction]);
  const scheduleArchive = splitScheduleArchive(uniqueItems(data.reminders?.items || []).filter(item => !isTranscriptCandidate(item)));
  const archivedItems=scheduleArchive.current.filter(item=>item.sales_suppressed);
  const items = formalReminderItems(data.reminders?.items || []).filter(item => !item.sales_suppressed&&!splitCurrentActions([item]).history.length);
  const visibleIds = new Set(items.map(itemKey));
  const oldItems = formalReminderItems(data.reminders?.items || []).filter((item) =>
    !item.sales_suppressed && splitCurrentActions([item]).history.length > 0 && !visibleIds.has(itemKey(item))
  );
  const delivery = data.reminders?.delivery || {};
  const deliveryHistory = [...(delivery.history || [])]
    .sort((left, right) => String(right.sent_at || right.updated_at || "").localeCompare(String(left.sent_at || left.updated_at || "")))
    .slice(0, 4);
  const receiptArchive = splitReceiptArchive(data.dashboard?.workflow_state?.receipts || []);
  const recentReceipts = [...receiptArchive.current]
    .sort((left, right) => String(right.submitted_at || "").localeCompare(String(left.submitted_at || "")))
    .slice(0, 3);
  if (selected) return <Workroom item={selected} data={data} onBack={() => setSelected(null)} refresh={refresh} onNavigate={navigate} setToast={setToast} backLabel="返回下次提醒" />;
  const groups = [
    { id: "overdue", label: "已超期", items: items.filter((item) => item.schedule_bucket === "overdue") },
    { id: "today", label: "今天", items: items.filter((item) => item.schedule_bucket === "today") },
    { id: "week", label: "未来 7 天", items: items.filter((item) => item.schedule_bucket === "week") },
    { id: "later", label: "后续", items: items.filter((item) => !["overdue", "today", "week"].includes(item.schedule_bucket)) },
  ].filter((group) => group.items.length);

  return (
    <div className="page-stack">
      <PageHeader eyebrow="时间系统" title="日程 / Deadline" subtitle="逾期超过15天自动归档；原记录保留，可重新安排。" />
      <section className="reminder-surface">
        {archivedItems.length>0&&<section className="reminder-group"><header><strong>已归档项目·待收尾 / 原提醒待核对</strong><span>{archivedItems.length} 条</span></header><p>责任与原期限保留，不自动恢复销售催办。真实会议和外部已建任务不取消。</p>{archivedItems.map(item=><div key={itemKey(item)}><small>{item.archive_label}</small><ActionRow item={item} onClick={()=>item.source_type==="project_round"?navigate("projects",{projectId:item.project_id}):setSelected(item)}/></div>)}</section>}
        {groups.length ? groups.map((group) => (
          <section className="reminder-group" key={group.id}>
            <header><strong>{group.label}</strong><span>{group.items.length} 条</span></header>
            <div className="queue-list">{group.items.map((item) => <ActionRow key={itemKey(item)} item={item} onClick={() => item.source_type === "project_round" ? navigate("projects", { projectId: item.project_id, projectTitle: item.project_title, customer: item.customer }) : setSelected(item)} />)}</div>
          </section>
        )) : (
          <div className="reminder-empty-stack">
            <EmptyMessage title="没有待跟进事项" description="项目中的跟进日期会显示在这里；完成或暂停后自动移出。" />
            {recentReceipts.length ? (
              <section className="reminder-audit-trail">
                <header><div><strong>最近状态记录</strong><span>用于确认系统正常运转，不是待办。</span></div><StatusChip tone="neutral">只读</StatusChip></header>
                {recentReceipts.map((entry) => (
                  <div key={`${entry.submitted_at}-${entry.customer}-${entry.title}`}>
                    <span><strong>{entry.customer || "客户事项"}</strong><small>{entry.status || "已处理"}</small></span>
                    <p>{compactSentence(entry.resolution || entry.next_step || entry.title || "处理结果已记录", 74)}</p>
                    <time>{formatDateTime(entry.submitted_at, "")}</time>
                  </div>
                ))}
              </section>
            ) : null}
          </div>
        )}
        <details className="reminder-system-records" open={delivery.status==='failed'||undefined}><summary>提醒与送达记录 <span>{delivery.status==='failed'?'存在发送失败，需核对':'查看飞书链路与累计回执'}</span></summary>
        <div className="boundary-note"><Bell size={18} /><div><strong>飞书提醒链路</strong><span>工作台决定事项状态；飞书任务承接待办，飞书私聊负责叫回，飞书日历只承接会议。</span></div></div>
        <section className={`reminder-delivery-summary is-${delivery.status || "disabled"}`}>
          <div>
            <strong>飞书私聊送达</strong>
            <span>{delivery.policy?.due || "已确认事项到期前私聊一次"}；{delivery.policy?.overdue || "过期后待重新安排，不整批催办"}</span>
          </div>
          <dl>
            <div><dt>最近发送</dt><dd>{formatDateTime(delivery.last_success_at, "尚未发送")}</dd></div>
            <div><dt>累计成功</dt><dd>{delivery.sent_count || 0} 次</dd></div>
            <div><dt>已确认待提醒</dt><dd>{delivery.eligible_count || 0} 项</dd></div>
          </dl>
          <StatusChip tone={delivery.status === "healthy" ? "success" : delivery.status === "failed" ? "danger" : "neutral"}>
            {delivery.status === "healthy" ? "按确认事项启用" : delivery.status === "failed" ? "存在发送失败记录" : "未启用"}
          </StatusChip>
        </section>
        </details>
        {oldItems.length ? (
          <details className="reminder-group">
            <summary>待重新安排的旧任务 · {oldItems.length}</summary>
            <p>原记录保留，不补发、不每日催办。打开事项核实进展，再决定是否重新安排提醒。</p>
            <div className="queue-list">{oldItems.map((item) => <ActionRow key={itemKey(item)} item={item} onClick={() => item.source_type === "project_round" ? navigate("projects", { projectId: item.project_id, projectTitle: item.project_title, customer: item.customer }) : setSelected(item)} />)}</div>
          </details>
        ) : null}
        {(scheduleArchive.archived.length > 0 || receiptArchive.archived.length > 0) && <details className="reminder-audit-trail schedule-archive">
          <summary>历史归档 · {scheduleArchive.archived.length} 条日程{receiptArchive.archived.length > 0 ? ` · ${receiptArchive.archived.length} 条状态记录` : ''}</summary>
          <header><div><strong>历史记录保留</strong><span>日程逾期超过15天收起；不代表已完成，不取消外部会议或任务。</span></div><StatusChip tone="neutral">已归档</StatusChip></header>
          {scheduleArchive.archived.map(item => <div key={itemKey(item)}><span><strong>{item.customer || '客户事项'}</strong><small>逾期自动归档{item.status ? ` · ${item.status}` : ''}{item.sales_suppressed && item.archive_label ? ` · ${item.archive_label}` : ''}</small></span><p>{compactSentence(item.title || item.action || item.next_step || '原日程',74)}</p><button className="plain-action" onClick={()=>item.source_type==='project_round'?navigate('projects',{projectId:item.project_id,projectTitle:item.project_title,customer:item.customer}):setSelected(item)}>查看 / 重新安排</button><time>{formatDateTime(item.deadline || item.due || item.review_at,'')}</time></div>)}
          {receiptArchive.archived.map((entry,index)=><div key={`${entry.submitted_at}-${entry.customer}-${index}`}><span><strong>{entry.customer || '客户事项'}</strong><small>{entry.status || '状态记录'}</small></span><p>{compactSentence(entry.resolution || entry.next_step || entry.title || '原状态记录',74)}</p><time>{formatDateTime(entry.submitted_at,'')}</time></div>)}
        </details>}
        {deliveryHistory.length ? (
          <details className="reminder-audit-trail"><summary>飞书发送回执 · {deliveryHistory.length} 条</summary>
            <header><div><strong>飞书发送回执</strong><span>任务创建与私聊发送分开记录，以下是真实发送结果。</span></div><StatusChip tone="neutral">只读</StatusChip></header>
            {deliveryHistory.map((entry) => (
              <div key={entry.id}>
                <span><strong>{entry.kind === "overdue_digest" ? "超期汇总" : "到期提醒"}</strong><small>{entry.status === "sent" ? "已发送" : "发送失败"}</small></span>
                <p>{entry.title || entry.last_error || "飞书私聊提醒"}</p>
                <time>{formatDateTime(entry.sent_at || entry.updated_at, "")}</time>
              </div>
            ))}
          </details>
        ) : null}
      </section>
    </div>
  );
}

function KnowledgeView({ dashboard }) {
  const [selectedProject, setSelectedProject] = useState("");
  const groups = useMemo(() => {
    const map = new Map();
    for (const item of dashboard.knowledge_timeline || []) {
      const project = item.project || item.projects?.[0] || item.raw_title || "未归类";
      if (!map.has(project)) map.set(project, []);
      map.get(project).push(item);
    }
    return [...map.entries()].map(([project, items]) => ({ project, items })).sort((a, b) => String(b.items[0]?.updated_at).localeCompare(String(a.items[0]?.updated_at)));
  }, [dashboard.knowledge_timeline]);
  const selected = groups.find((group) => group.project === selectedProject);

  if (selected) {
    return (
      <div className="page-stack reader-page">
        <button className="back-link" type="button" onClick={() => setSelectedProject("")}><ChevronLeft size={17} />返回 AI知识库</button>
        <PageHeader eyebrow={`${selected.items.length} 条历史沉淀`} title={selected.project} subtitle="知识解释为什么行动，不自动改变今日队列。" />
        <div className="reader-timeline">{selected.items.map((item) => (
          <article key={`${item.path}-${item.updated_at}`}>
            <time>{item.updated_at}</time><h2>{item.title || item.raw_title}</h2><p>{item.full_summary || item.summary || item.preview || "暂无摘要"}</p>
          </article>
        ))}</div>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <PageHeader eyebrow="只读背景" title="AI知识库" subtitle="按客户和项目聚合历史沟通、判断和可复用结论；工作进度仍留在行动与回执中。" />
      <section className="reader-index">{groups.map((group) => (
        <button key={group.project} type="button" onClick={() => setSelectedProject(group.project)}><div><strong>{group.project}</strong><span>{group.items[0]?.preview || group.items[0]?.summary || "暂无摘要"}</span></div><div><time>{group.items[0]?.updated_at}</time><StatusChip>{group.items.length} 条</StatusChip><ChevronRight size={18} /></div></button>
      ))}</section>
    </div>
  );
}

function ReportsView({ dashboard, refresh }) {
  const [older, setOlder] = useState([]);
  const [hasMore, setHasMore] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const days = [...new Map([...older, ...(dashboard.message_digest?.days || [])].map(day => [day.date, day])).values()].sort((a,b) => b.date.localeCompare(a.date));
  async function loadOlder() {
    setBusy(true); setError("");
    try { const result = await api.get(`/api/messages/reports?offset=${days.length}&limit=20`); setOlder(current => [...current, ...result.days]); setHasMore(result.has_more); }
    catch(e) { setError(e.message); }
    finally { setBusy(false); }
  }
  const [includeHistory, setIncludeHistory] = useState(false);
  const visibleDays = includeHistory ? days : days.filter(day=>day.date>=cutoffKey());
  const [selectedDate, setSelectedDate] = useState("");
  const selected = visibleDays.find((day) => day.date === selectedDate) || visibleDays[0];
  return (
    <div className="page-stack reader-page">
      <PageHeader eyebrow="持续保留" title="项目群日报" subtitle={`最近一份日报：${dashboard.message_digest?.latest_date || "暂无"}。历史内容保留，不用首页刷新时间冒充群消息更新时间。`} />
      <ReportSync refresh={refresh} />
      <div className="readonly-banner"><BookOpen size={18} /><span>日报是背景信息。需要行动时，由你通过销售捕捉明确创建。</span></div>
      <div className="report-date-tabs" role="tablist" aria-label="日报日期">{visibleDays.map((day) => <button type="button" role="tab" aria-selected={selected?.date === day.date} className={selected?.date === day.date ? "is-active" : ""} key={day.date} onClick={() => setSelectedDate(day.date)}>{day.date}<span>{day.message_count || 0} 条</span></button>)}</div>
      <details onToggle={e=>{if(!e.currentTarget.open)setIncludeHistory(false);}}><summary>历史日报（默认收起，原文保留）</summary><p>默认仅展示近30天日报，旧日报不作为当前进展。</p><button className="plain-action" onClick={()=>setIncludeHistory(true)}>显示已有历史日报</button>{hasMore && <button className="plain-action" disabled={busy} onClick={()=>{setIncludeHistory(true);loadOlder();}}>{busy ? "正在读取历史…" : "加载更早日报"}</button>}</details>{error && <p role="alert">{error}</p>}
      {selected ? (
        <section className="report-reader">
          <header><div><p>{selected.date}</p><h2>{selected.summary || "当日项目群动态"}</h2></div><StatusChip tone={selected.health === "红" ? "warning" : "neutral"}>{selected.message_count || 0} 条有效消息</StatusChip></header>
          {(selected.items || []).map((group) => <article key={group.name}><h3>{group.name}</h3><p>{group.summary}</p>{group.discussion_points?.length ? <ul>{group.discussion_points.map((point) => <li key={point}>{point}</li>)}</ul> : null}</article>)}
        </section>
      ) : <EmptyMessage title="暂无项目群日报" description="同步成功后会在这里按日期显示。" />}
    </div>
  );
}

function PerformanceView({ dashboard, projectId, navigate, refreshKey }) {
  const [crmRevision,setCrmRevision]=useState(0);
  const [candidates, setCandidates] = useState([]);
  const [candidateError, setCandidateError] = useState("");
  useEffect(() => { api.get("/api/project-workspace/overview").then(r => setCandidates(r.projects)).catch(e => setCandidateError(e.message)); }, []);
  const status = dashboard.fxiaoke_status || {};
  const quarter = status.quarter || {};
  const rows = status.pipeline?.signed_order_rows || [];
  const stale = status.mode === "page_snapshot";
  return (
    <div className="page-stack">
      <PageHeader eyebrow="经营概览" title="合同业绩" subtitle="按年、季度、月查看本人业绩及所选订单回款。" />
      <div className="current-performance"><BusinessOverview refreshKey={refreshKey}/></div>
      <details className="performance-support"><summary>旧 CRM 历史业绩（已停用，仅供对照）</summary><CrmConnect refreshKey={refreshKey} onSynced={()=>setCrmRevision(v=>v+1)} /></details>
      <ProjectContractAudit key={projectId} projectId={projectId} refreshKey={crmRevision} navigate={navigate} />
      <details className="performance-support" open={Boolean(projectId)}><summary>回到工作台项目 · 查看依据与下一步</summary>{candidateError && <p role="alert">{candidateError}</p>}
        <section>{(projectId ? candidates.filter(p => p.id === projectId) : candidates.filter(p=>p.is_current).slice(0, 6)).map(p => <article key={p.id}><h3>{p.title}</h3><p>{p.judgement}</p>{!p.is_current && <p>当前项目属于历史待核实，仅保留往返入口，不计作当前候选机会。</p>}<button className="plain-action" onClick={() => navigate("projects", { projectId: p.id })}>查看依据并决定本轮动作</button></article>)}</section>
      </details>
      {status.last_sync && <details className="performance-surface"><summary>查看旧纷享销客快照（仅历史参考）</summary>
        <div className="snapshot-warning"><CircleAlert size={18} /><div><strong>历史口径：{String(quarter.period || "周期待确认").replace("本季度", "原快照季度")}</strong><span>最后读取 {formatDateTime(status.last_sync)}。下列缺口仅属于历史季度，不是当前考核缺口。</span></div></div>
        <div className="metric-strip"><div><span>目标</span><strong>{quarter.target_amount || "-"}</strong></div><div><span>已签约</span><strong>{quarter.achieved_amount || "-"}</strong></div><div><span>完成率</span><strong>{quarter.attainment_rate || "-"}</strong></div><div><span>缺口</span><strong>{quarter.gap_amount || "-"}</strong></div></div>
        <section className="signed-orders"><header><strong>签约明细</strong><span>{rows.length} 笔</span></header>{rows.map((row, index) => <div key={`${row.customer_label}-${row.order_date}-${index}`}><span>{row.customer_label}</span><time>{row.order_date}</time><strong>{formatAmount(row.amount)}</strong></div>)}</section>
      </details>}
    </div>
  );
}

function PricingWorkspace({ focusSection, quoteConflict, onResolveQuote, onNewQuote, quoteSaving, incomingQuote, onTransferQuote, tab, values, setValues, approval, setApproval, resetKey, initialProjectId, onProjectSelected, navigate, registerNavigationGuard, canSwitch }) {
  const choose = value => { if (value !== tab) navigate('pricing', { pricingTab: value }); };
  return <div className="page-stack pricing-workspace"><div className="pricing-toolbar"><div className="pricing-tabs" role="tablist" aria-label="报价工具"><button type="button" role="tab" aria-selected={tab==='calculator'} onClick={()=>choose('calculator')}>报价计算器</button><button type="button" role="tab" aria-selected={tab==='approval'} onClick={()=>choose('approval')}>项目审批材料</button></div>{tab === 'calculator' && <button disabled={quoteSaving} className="plain-action" onClick={onNewQuote}>当前输入另开一笔报价</button>}</div>
    {tab === 'calculator' && quoteConflict && <div>
      {quoteConflict && <section className="performance-surface" role="alert"><h2>这笔报价已有新版 · 输入已保留</h2><p>最新第 {quoteConflict.revision} 版：{quoteConflict.values.customer} · {quoteConflict.values.requirement} · {quoteConflict.values.effort} 人日 · 对客金额 ¥{Number(quoteConflict.calculation.revenue).toLocaleString('zh-CN')}</p><details><summary>查看新版范围与成本</summary><p>范围版本：{quoteConflict.values.version || '未填写'}</p>{COST_FIELDS.map(([key,label]) => <p key={key}>{label}：{quoteConflict.values.costs[key]}</p>)}<p>另计10%自成本：{quoteConflict.values.selfCostEnabled ? '是' : '否'}</p></details><button disabled={quoteSaving} onClick={() => onResolveQuote(true)}>已核对新版，保留当前输入继续修订</button><button disabled={quoteSaving} onClick={() => onResolveQuote(false)}>将当前输入另存为独立报价</button></section>}
    </div>}
    {tab==='calculator'?<fieldset disabled={quoteSaving} style={{border:0,padding:0,margin:0,minWidth:0}}><PricingView onTransferQuote={onTransferQuote} values={values} setValues={setValues} approval={approval} setApproval={setApproval}/></fieldset>:<CommercialWorkspace focusSection={focusSection} incomingQuote={focusSection?null:incomingQuote} initialProjectId={initialProjectId} onProjectSelected={onProjectSelected} navigate={navigate} registerNavigationGuard={registerNavigationGuard}/>}
  </div>;
}

function PricingView({onTransferQuote,values,setValues,approval,setApproval}) {
  const updateApproval = update => {
    const next = typeof update === 'function' ? update(approval) : update;
    if (next.effort !== approval.effort || next.rate !== approval.rate || next.selfCostEnabled !== approval.selfCostEnabled) {
      const quote = { ...values, quotedDays: next.effort, billingRate: next.rate, selfCostEnabled: next.selfCostEnabled };
      next.calculatorFingerprint = JSON.stringify(quote);
      setValues(quote);
    }
    setApproval(next);
  };
  const model=useMemo(()=>calculateQuote(values),[values]);
  const set=key=>event=>setValues(current=>({...current,[key]:event.target.value}));
  const amount=(value,known)=>known?formatAmount(value):'待输入';
  return <div className="page-stack independent-pricing">
    <PageHeader eyebrow="随时试算" title="报价计算器" subtitle="无需关联项目。输入仅保留在当前会话，不生成审批或客户承诺。" />
    <section className="pricing-surface"><form className="pricing-form" onSubmit={event=>event.preventDefault()}>
      <label className="native-field"><span>预计投入人天</span><input type="number" min="0" step="any" value={values.actualDays} onChange={set('actualDays')}/></label>
      <label className="native-field"><span>内部日成本（元／人天）</span><input type="number" min="0" step="any" value={values.internalCost} onChange={set('internalCost')}/></label>
      <label className="native-field"><span>报价人天</span><input type="number" min="0" step="any" value={values.quotedDays} onChange={set('quotedDays')}/></label>
      <label className="native-field"><span>对客单价（元／人天）</span><input type="number" min="0" step="any" value={values.billingRate} onChange={set('billingRate')}/></label>
      <label className="native-field"><span>目标毛利率（%）</span><input type="number" min="0" max="100" step="any" value={values.targetMargin} onChange={set('targetMargin')}/></label>
      <label className="check-field"><input type="checkbox" checked={values.selfCostEnabled} onChange={event=>setValues(current=>({...current,selfCostEnabled:event.target.checked}))}/><span><strong>计入成交额 10% 自成本</strong><small>按本次试算口径选择。</small></span></label>
    </form><div className={`pricing-result ${model.comparisonKnown?(model.passed?'is-passed':'is-warning'):'is-pending'}`} aria-live="polite"><StatusChip tone={!model.comparisonKnown?'neutral':model.passed?'success':'warning'}>{!model.comparisonKnown?'待输入完整试算条件':model.passed?'达到目标毛利率':'未达到目标毛利率'}</StatusChip><h2>{amount(model.revenue,model.revenueKnown)}</h2><p>对客报价金额</p><dl><div><dt>内部成本</dt><dd>{amount(model.internalTotal,model.costKnown)}</dd></div><div><dt>自成本</dt><dd>{amount(model.selfCost,model.revenueKnown)}</dd></div><div><dt>预计毛利</dt><dd>{amount(model.grossProfit,model.revenueKnown&&model.costKnown)}</dd></div><div><dt>毛利率</dt><dd>{model.revenueKnown&&model.costKnown?`${(model.marginRate*100).toFixed(2)}%`:'待输入'}</dd></div></dl><button type="button" className="analysis-adopt" disabled={!model.revenueKnown||!model.costKnown} onClick={()=>setApproval(current=>({...current,open:true}))}>生成审批负责人审批话术</button></div></section>
    {approval.open&&<StandaloneApproval onTransferQuote={onTransferQuote} draft={approval} setDraft={updateApproval}/>}
  </div>;
}


function StandaloneApproval({draft,setDraft,onTransferQuote}) {
  const model=useMemo(()=>formatApproval(draft),[draft]);
  const [notice,setNotice]=useState('');
  const [transferring,setTransferring]=useState(false);
  const edit=patch=>{setDraft(current=>editApproval(current,patch));setNotice('');};
  const field=key=>event=>edit({[key]:event.target.value});
  return <section className="performance-surface standalone-approval" aria-label="独立审批负责人审批话术"><header className="standalone-approval-header"><div><h2>审批负责人审批话术</h2><p>先核对客户版本与内部成本；只生成草稿，不绑定项目、不发送。</p></div><button className="plain-action" onClick={()=>setDraft(current=>({...current,open:false}))}>收起</button></header>
    <div className="pricing-form">{[['customer','客户'],['requirement','本次需求'],['version','本次版本']].map(([key,label])=><label className="native-field" key={key}><span>{label}</span><input value={draft[key]} onChange={field(key)} placeholder="自由输入，无需选择项目"/></label>)}
    <label className="native-field"><span>客户确认／拟确认人日</span><input type="number" min="0" step="any" value={draft.effort} onChange={field('effort')}/></label><label className="native-field"><span>对客单价（元／人日）</span><input type="number" min="0" step="any" value={draft.rate} onChange={field('rate')}/></label><label className="native-field"><span>自有人力预算金额（已带入试算，待核对）</span><input type="number" min="0" step="any" value={draft.costs.own_labor} onChange={event=>edit({costs:{...draft.costs,own_labor:event.target.value}})}/></label></div>
    <details><summary>其余七项成本 · 空白按0，仍需核对</summary><div className="pricing-form">{COST_FIELDS.slice(1).map(([key,label])=><label className="native-field" key={key}><span>{label}（元）</span><input type="number" min="0" step="any" value={draft.costs[key]} onChange={event=>edit({costs:{...draft.costs,[key]:event.target.value}})}/></label>)}</div></details>
    <label className="check-field"><input type="checkbox" checked={draft.selfCostEnabled} onChange={event=>edit({selfCostEnabled:event.target.checked})}/><span>另外计入成交额10%自成本（单独列示，不并入八项预算）</span></label>
    <div className="approval-confirmations"><label className="check-field"><input type="checkbox" checked={draft.customerConfirmed} onChange={event=>setDraft(current=>({...current,customerConfirmed:event.target.checked}))}/><span>客户已确认本次人日及版本</span></label><label className="check-field"><input type="checkbox" checked={draft.costsConfirmed} onChange={event=>setDraft(current=>({...current,costsConfirmed:event.target.checked}))}/><span>内部八项成本及自成本口径已核对</span></label></div>
    <p className={model.ready?'approval-ready':'analysis-meta'}>{model.ready?'已按双方核对结果生成，仍是未提交草稿':'待核实草稿 · '+model.errors.join('；')}</p><label className="native-field"><span>内部审批文本（包含成本与毛利）</span><textarea readOnly rows={14} value={model.text}/></label><button className="analysis-adopt" disabled={!model.valid} onClick={async()=>{try{await navigator.clipboard.writeText(model.text);setNotice('审批草稿已复制；未发送、未提交审批。');}catch{setNotice('请手动选择文本复制。');}}}>复制审批负责人审批话术</button><button className="plain-action" disabled={!model.valid || transferring} onClick={async()=>{if(transferring)return;setTransferring(true);try{await onTransferQuote(draft);}catch(e){setNotice(e.message);}finally{setTransferring(false);}}}>{transferring?'正在保存报价版本…':'带入项目审批材料（可选）'}</button>{notice&&<p role="status">{notice}</p>}
  </section>;
}


function CaptureDialog({ isOpen, onOpenChange }) {
 const [projects,setProjects]=useState([]),[selected,setSelected]=useState(''),[error,setError]=useState('');
 const [dirty,setDirty]=useState(false),[busy,setBusy]=useState(false);
 const askDiscard=useDiscardChanges();
 useEffect(()=>{if(!isOpen)return;setSelected('');setDirty(false);api.get('/api/project-workspace').then(x=>setProjects(x.projects||[])).catch(e=>setError(e.message));},[isOpen]);
 async function close(){if(busy)return;if(dirty&&!await askDiscard('进展尚未保存，是否放弃这段输入？'))return;onOpenChange(false);}
 const project=projects.find(x=>x.id===selected);
 return <Dialog isOpen={isOpen} onOpenChange={open=>open?onOpenChange(true):close()} width="min(680px, calc(100vw - 48px))" maxHeight="88vh" purpose="form"><div className="capture-dialog">
 <header><h2>记录新进展 / 补充纠正</h2><button aria-label="关闭销售捕捉" onClick={close}>×</button></header>
 <label className="native-field"><span>归属项目</span><select aria-label="进展归属项目" value={selected} disabled={dirty||busy} onChange={e=>setSelected(e.target.value)}><option value="">请选择项目，不继承上次对象</option>{projects.filter(x=>!x.archive?.archived).map(x=><option value={x.id} key={x.id}>{x.customer} · {x.title}</option>)}</select></label>
 {error&&<p role="alert">{error}</p>}{project&&<ProgressComposer key={project.id} project={project} markDirty={(_,v)=>setDirty(v)} markSaving={(_,v)=>setBusy(v)}/>}
 </div></Dialog>;
}

export default function WorkbenchRoot() { return <DiscardChangesProvider><App /></DiscardChangesProvider>; }
