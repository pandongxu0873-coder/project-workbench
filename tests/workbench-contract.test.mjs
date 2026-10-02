import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";

const HOST = "127.0.0.1";
let processHandle;
let baseUrl;
let testStateRoot;
const projectRoot = fileURLToPath(new URL("..", import.meta.url));

async function reservePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, HOST, () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

async function waitForServer(url) {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${url}/api/dashboard`);
      if (response.ok) return;
    } catch {
      // The child process may still be starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error("Timed out waiting for the workbench test server");
}

async function getJson(path) {
  const response = await fetch(`${baseUrl}${path}`);
  assert.equal(response.status, 200, `${path} should return 200`);
  return response.json();
}

async function postJson(pathname, body) {
  const response = await fetch(`${baseUrl}${pathname}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `${pathname} returned ${response.status}`);
  return payload;
}

function dateOffset(days) {
  const value = new Date();
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

before(async () => {
  const port = await reservePort();
  baseUrl = `http://${HOST}:${port}`;
  testStateRoot = await mkdtemp(path.join(os.tmpdir(), "sales-workbench-test-"));
  const testDataRoot = path.join(testStateRoot, "workbench_data");
  await mkdir(testDataRoot, { recursive: true });
  await writeFile(path.join(testDataRoot, "feishu_calendar_cache.json"), JSON.stringify({
    ok: true,
    range_key: "stale-window",
    fetched_at_ts: 1,
    items: [{ event_id: "stale-event", summary: "STALE-CALENDAR-EVENT" }],
  }));
  await writeFile(path.join(testDataRoot, "workflow_state.json"), JSON.stringify({
    version: 1,
    action_status: {},
    risk_status: {},
    schedule_status: {},
    pm_item_status: {},
    generated_actions: {},
    generated_risks: {},
    receipts: [{
      customer: "云杉百货",
      title: "历史回执迁移验收",
      status: "已闭环",
      relative_path: "",
      submitted_at: "2026-06-01T10:00:00+08:00",
      resolution: "历史回执",
    }],
    updated_at: "",
  }));
  processHandle = spawn("python3", ["tests/run_contract_server.py", "--host", HOST, "--port", String(port)], {
    cwd: projectRoot,
    env: {
      ...process.env,
      SALES_WORKBENCH_WORKBENCH_STATE_ROOT: testStateRoot,
      LARK_CLI_BIN: "/usr/bin/false",
      FEISHU_REMINDER_ENABLED: "0",
      SALES_WORKBENCH_PROJECT_AUTO_SYNC: "0",
      SALES_WORKBENCH_BACKGROUND_UPKEEP: "0",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  await waitForServer(baseUrl);
});

after(async () => {
  if (processHandle && processHandle.exitCode === null) {
    processHandle.kill("SIGTERM");
    await once(processHandle, "exit");
  }
  await rm(testStateRoot, { recursive: true, force: true });
});

test("workbench is the canonical account ledger", async () => {
  const payload = await getJson("/api/account-advancement");

  assert.equal(payload.ok, true);
  assert.equal(payload.source.status, "local_canonical");
  assert.equal(payload.source.label, "工作台账户主账本");
  assert.match(payload.source.write_policy, /唯一状态源/);
  assert.ok(payload.summary.account_count >= 1);
  assert.ok(payload.summary.local_admission_count >= 1);
  assert.ok(payload.accounts.some((account) => account.record_source === "workbench_ai_admission"));
});

test("reminder delivery status is explicit when private-chat delivery is disabled", async () => {
  const payload = await getJson("/api/reminder-delivery");

  assert.equal(payload.ok, true);
  assert.equal(payload.delivery.enabled, false);
  assert.equal(payload.delivery.status, "disabled");
  assert.match(payload.delivery.policy.due, /飞书私聊/);
  assert.match(payload.delivery.policy.overdue, /汇总/);
});

test("customer lifecycle and time state remain separate", async () => {
  const payload = await getJson("/api/account-advancement");
  const stageIds = payload.stages.map((stage) => stage.id);

  assert.deepEqual(stageIds, ["qualify", "path", "contact", "opportunity"]);
  assert.ok(!stageIds.includes("next"));
  for (const account of payload.accounts) {
    assert.ok(stageIds.includes(account.stage));
    assert.ok(account.time_state && typeof account.time_state.id === "string");
  }
});

test("prospecting GET is read-only and keeps result announcements out of active admission", async () => {
  const first = await getJson("/api/prospecting");
  const second = await getJson("/api/prospecting");

  assert.equal(second.task.last_run_at, first.task.last_run_at);
  assert.equal(second.task.scan_in_progress, false);

  const resultPattern = /(中标结果|成交结果|采购结果|终止|废标)/;
  const invalidActive = second.leads.filter(
    (lead) => ["pending", "verify"].includes(lead.decision) && resultPattern.test(lead.title || ""),
  );
  assert.deepEqual(invalidActive, []);
});

test("transcript candidates stay in review and never masquerade as deadlines", async () => {
  const first = await getJson("/api/risk-todos");
  const second = await getJson("/api/risk-todos");
  const selectTranscript = (payload) => payload.items
    .filter((item) => item.source_scope === "transcript_intake")
    .map(({ id, deadline, review_at, schedule_bucket, customer, title }) => ({ id, deadline, review_at, schedule_bucket, customer, title }));

  const firstItems = selectTranscript(first);
  const secondItems = selectTranscript(second);
  assert.deepEqual(secondItems, firstItems);
  assert.equal(new Set(firstItems.map((item) => item.id)).size, firstItems.length);
  assert.ok(firstItems.every((item) => !item.deadline));
  assert.ok(firstItems.every((item) => item.review_at && item.schedule_bucket === "review"));
});

test("today actions carry stable account relationships", async () => {
  const created = await postJson("/api/manual-todo", { customer: "云杉百货", title: "隔离验收：真实创建的行动", next_step: "核对范围", target: "now", sync_calendar: false });
  const dashboard = await getJson("/api/dashboard");
  assert.ok(dashboard.battle_actions.some(item => (item.id || item.todo_id) === created.todo.id), JSON.stringify({created: {id: created.todo.id, deadline: created.todo.deadline, status: created.todo.status}, visible: dashboard.battle_actions.map(item => ({id: item.id || item.todo_id, deadline: item.deadline}))}));
  assert.ok(dashboard.battle_actions.every(item => item.id || item.todo_id));
  const formalActions = dashboard.battle_actions.filter((item) => item.source_scope !== "transcript_intake" && item.source_type !== "transcript_intake");
  const transcriptCandidates = dashboard.battle_actions.filter((item) => item.source_scope === "transcript_intake" || item.source_type === "transcript_intake");
  assert.ok(
    formalActions.every((item) => item.account_id),
    JSON.stringify(formalActions.filter((item) => !item.account_id).map(({ customer, title, source_scope, source_type, schedule_bucket }) => ({ customer, title, source_scope, source_type, schedule_bucket }))),
  );
  assert.ok(transcriptCandidates.every((item) => !item.deadline && item.schedule_bucket === "review"));
  assert.ok(!dashboard.calendar_status.items.some((item) => item.title === "STALE-CALENDAR-EVENT"));
  const legacyReceipt = dashboard.workflow_state.receipts.find((item) => item.title === "历史回执迁移验收");
  assert.match(legacyReceipt.id, /^legacy-receipt-/);
  assert.ok(legacyReceipt.account_id);
});

test("account evidence can unlock the next lifecycle gate", async () => {
  const beforePayload = await getJson("/api/account-advancement");
  const account = beforePayload.accounts.find((item) => item.record_source === "workbench_ai_admission");
  assert.ok(account);

  await postJson("/api/account-advancement/evidence", {
    id: account.id,
    revenue_evidence: "示例食品集团控股公开年报已核验，规模满足目标账户要求",
    source: account.source || "https://www.masterkong.com.cn/",
    cut_in: account.cut_in || "即时零售智慧分销与门店会员运营",
  });
  const advanced = await postJson("/api/account-advancement/stage", {
    id: account.id,
    target_stage: "path",
  });
  assert.equal(advanced.account.stage, "path");

  const paused = await postJson("/api/account-advancement/state", {
    id: account.id,
    account_state: "paused",
    reason: "隔离测试暂停",
  });
  assert.equal(paused.account.account_state, "paused");
  const resumed = await postJson("/api/account-advancement/state", {
    id: account.id,
    account_state: "active",
  });
  assert.equal(resumed.account.account_state, "active");
});

test("candidate admission rejects a missing time window", async () => {
  const prospecting = await getJson("/api/prospecting");
  const lead = prospecting.leads.find((item) => item.actionability === "needs_time_evidence");
  assert.ok(lead);
  const response = await fetch(`${baseUrl}/api/prospecting/lead`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: lead.id, target: "accept" }),
  });
  const payload = await response.json();
  assert.equal(response.status, 400);
  assert.match(payload.error, /有效时间窗口/);
});

test("accepted prospects can only be managed through the formal account ledger", async () => {
  const prospecting = await getJson("/api/prospecting");
  const accepted = prospecting.leads.find((lead) => lead.decision === "accepted");
  assert.ok(accepted);
  const response = await fetch(`${baseUrl}/api/prospecting/lead`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: accepted.id, target: "watch" }),
  });
  const payload = await response.json();
  assert.equal(response.status, 400);
  assert.match(payload.error, /正式账户/);
});

test("user candidate pool requires an explicit deadline and at least 14 preparation days", async () => {
  const dynamicLeadId = `valid-window-${Date.now()}`;
  await postJson("/api/prospecting/import", {
    source: "valid_window_test",
    leads: [{
      id: dynamicLeadId,
      company: "隔离测试有效窗口客户",
      title: "会员系统与私域运营采购招标公告",
      source_url: `https://example.com/valid-window/${dynamicLeadId}`,
      published_at: dateOffset(0),
      deadline: dateOffset(15),
      purchase_signal: "招采/采购触发",
      entry_strategy: "从会员系统和私域运营升级切入",
      force_include: true,
    }],
  });
  const prospecting = await getJson("/api/prospecting");
  const surfaced = prospecting.leads.filter((lead) => lead.user_surface === "candidate");
  assert.ok(surfaced.length >= 1);
  assert.ok(surfaced.every((lead) => lead.deadline));
  assert.ok(surfaced.every((lead) => lead.actionability === "actionable"));
  assert.ok(surfaced.every((lead) => Number(lead.time_window?.prep_days) >= 14));

  const reportedSample = prospecting.leads.find((lead) => lead.company === "中免集团三亚市内免税店有限公司");
  assert.equal(reportedSample.deadline, "2026-07-07");
  assert.equal(reportedSample.actionability, "stale");
  assert.equal(reportedSample.decision, "watch");
  assert.equal(reportedSample.user_surface, "watch");
  assert.match(reportedSample.execution_boundary, /不进入今日行动、下次提醒或飞书任务/);
});

test("candidate and upgrade surfaces stay capped and outside execution planning", async () => {
  const marker = Date.now();
  const leads = Array.from({ length: 4 }, (_, index) => ({
    id: `surface-cap-${marker}-${index}`,
    company: `隔离测试候选客户${index}`,
    title: `会员系统与私域运营采购招标公告${index}`,
    source_url: `https://example.com/tender/${marker}/${index}`,
    published_at: dateOffset(0),
    deadline: dateOffset(15 + index),
    purchase_signal: "招采/采购触发",
    entry_strategy: "从会员系统和私域运营升级切入",
    force_include: true,
  }));
  const imported = await postJson("/api/prospecting/import", { source: "surface_cap_test", leads });
  assert.equal(imported.imported_count, 4);

  const historicalLeads = Array.from({ length: 21 }, (_, index) => ({
    id: `watch-cap-${marker}-${index}`,
    company: `隔离测试长期客户${index}`,
    title: `会员与私域运营采购中标结果公告${index}`,
    source_url: `https://example.com/result/${marker}/${index}`,
    published_at: dateOffset(-20),
    purchase_signal: "已成交背景",
    supplier_path: "中标供应商待核验",
    entry_strategy: "等待续约、扩容或供应商替换触发",
    background_only: true,
    notice_state: "closed_result",
    force_include: true,
  }));
  const historicalImport = await postJson("/api/prospecting/import", { source: "watch_cap_test", leads: historicalLeads });
  assert.equal(historicalImport.imported_count, 21);

  let prospecting = await getJson("/api/prospecting");
  assert.equal(prospecting.surface_limits.daily_candidate_limit, 3);
  assert.equal(prospecting.surface_limits.long_term_limit, 20);
  assert.equal(prospecting.leads.filter((lead) => lead.user_surface === "candidate").length, 3);
  assert.ok(prospecting.leads.some((lead) => lead.user_surface === "candidate_backlog"));
  assert.equal(prospecting.leads.filter((lead) => lead.user_surface === "watch").length, 20);
  assert.ok(prospecting.leads.some((lead) => lead.user_surface === "watch_backlog"));
  assert.ok(historicalLeads.every((expected) => prospecting.leads.some((lead) => lead.id === expected.id)));

  const previousWatchId = historicalLeads[0].id;
  const reactivatedId = `${previousWatchId}-new-trigger`;
  const reactivatedImport = await postJson("/api/prospecting/import", {
    source: "watch_reactivation_test",
    leads: [{
      ...historicalLeads[0],
      id: reactivatedId,
      title: "会员与私域运营系统新一轮采购招标公告",
      deadline: dateOffset(16),
      purchase_signal: "招采/采购触发",
      background_only: false,
      notice_state: "",
    }],
  });
  assert.equal(reactivatedImport.imported_count, 1);
  prospecting = await getJson("/api/prospecting");
  const reactivated = prospecting.leads.find((lead) => lead.id === reactivatedId);
  assert.equal(reactivated.decision, "pending");
  assert.equal(reactivated.actionability, "actionable");
  assert.ok(["candidate", "candidate_backlog"].includes(reactivated.user_surface));
  assert.ok(reactivated.history.some((entry) => entry.action === "新触发回到准入判断"));
  assert.equal(reactivated.previous_watch_lead_id, previousWatchId);
  assert.equal(reactivated.watch_origin.lead_id, previousWatchId);
  assert.match(reactivated.watch_origin.title, /中标结果公告/);

  const dashboard = await getJson("/api/dashboard");
  const reminders = await getJson("/api/risk-todos");
  const workflow = await getJson("/api/workflow/status");
  const planningText = JSON.stringify([
    dashboard.battle_actions,
    dashboard.sales_brain?.today_queue,
    dashboard.sales_brain?.tomorrow_plan,
    dashboard.calendar_status?.items,
    reminders.items,
    workflow.external_sync_outbox,
  ]);
  for (const lead of prospecting.leads.filter((item) => ["watch", "watch_backlog"].includes(item.user_surface))) {
    assert.ok(!planningText.includes(lead.company));
  }
});

test("tender imports without a verified deadline stay out of the workbench", async () => {
  const leadId = `missing-window-${Date.now()}`;
  const imported = await postJson("/api/prospecting/import", {
    source: "contract_test",
    leads: [{
      id: leadId,
      company: "隔离测试采购单位",
      title: "会员系统采购招标公告",
      source_url: "https://example.com/tender",
      published_at: new Date().toISOString().slice(0, 10),
      purchase_signal: "招采/采购触发",
      entry_strategy: "隔离测试切口",
    }],
  });
  assert.equal(imported.imported_count, 0);
  const prospecting = await getJson("/api/prospecting");
  assert.ok(!prospecting.leads.some((lead) => lead.id === leadId));
});

test("concurrent manual actions are not lost", async () => {
  const marker = `并发验收-${Date.now()}`;
  const created = await Promise.all(Array.from({ length: 8 }, (_, index) => postJson("/api/manual-todo", {
    customer: "云杉百货",
    title: `${marker}-${index}`,
    next_step: `完成第 ${index} 条隔离测试动作`,
    target: "now",
    priority: "P2",
    sync_calendar: false,
  })));
  assert.equal(new Set(created.map((item) => item.todo.id)).size, 8);

  const reminders = await getJson("/api/risk-todos");
  const matching = reminders.items.filter((item) => item.title?.startsWith(marker));
  assert.equal(matching.length, 8);
});

test("evidence submission is idempotent across retries", async () => {
  const created = await postJson("/api/manual-todo", {
    customer: "云杉百货",
    title: `幂等验收-${Date.now()}`,
    next_step: "完成隔离幂等验收",
    target: "now",
    priority: "P2",
    sync_calendar: false,
  });
  const requestId = crypto.randomUUID();
  const body = {
    request_id: requestId,
    account_id: created.todo.account_id,
    customer: created.todo.customer,
    title: created.todo.title,
    action: created.todo.next_step,
    resolution: "隔离测试已经完成，没有写入真实客户状态。",
    status: "已处理",
    source_view: "自动验收",
    workflow_key: created.todo.id,
    object_type: "schedule",
    todo_id: created.todo.id,
    sync_calendar: false,
  };
  const first = await postJson("/api/risk-evidence", body);
  const replay = await postJson("/api/risk-evidence", body);
  assert.equal(replay.idempotent_replay, true);
  assert.equal(replay.receipt.id, first.receipt.id);

  const dashboard = await getJson("/api/dashboard");
  assert.equal(dashboard.workflow_state.receipts.filter((receipt) => receipt.id === first.receipt.id).length, 1);
  const accounts = await getJson("/api/account-advancement");
  const linked = accounts.accounts.find((account) => account.id === created.todo.account_id);
  assert.ok(linked.interaction_history.some((entry) => entry.receipt_id === first.receipt.id));
});

test("workroom request identity survives deadline changes and rotates only after a receipt", async () => {
  const created = await postJson("/api/manual-todo", {
    customer: "云杉百货",
    title: `跨刷新幂等验收-${Date.now()}`,
    next_step: "完成跨刷新幂等验收",
    target: "now",
    priority: "P2",
    sync_calendar: false,
  });
  const requestId = created.todo.workroom_request_id;
  assert.equal(requestId, `workroom:${created.todo.id}`);

  const todoFile = path.join(testStateRoot, "workbench_data", "risk_todos.json");
  const todos = JSON.parse(await readFile(todoFile, "utf8"));
  const pendingTodo = todos.find((item) => item.id === created.todo.id);
  pendingTodo.deadline = "2026-07-20T10:00+08:00";
  pendingTodo.created_at = "2026-07-10T18:00:00+08:00";
  await writeFile(todoFile, JSON.stringify(todos, null, 2));

  const result = await postJson("/api/risk-evidence", {
    request_id: requestId,
    account_id: created.todo.account_id,
    customer: created.todo.customer,
    title: created.todo.title,
    action: created.todo.next_step,
    resolution: "本轮已推进，下一轮继续跟进。",
    next_step: "确认下一轮评审时间",
    status: "推进中",
    deadline: "2026-07-20T10:00+08:00",
    source_view: "自动验收",
    workflow_key: created.todo.id,
    object_type: "schedule",
    todo_id: created.todo.id,
    sync_calendar: false,
  });
  assert.notEqual(result.todo.workroom_request_id, requestId);
  assert.match(result.todo.workroom_request_id, new RegExp(`^workroom:${created.todo.id}:cycle:`));

  const reminders = await getJson("/api/risk-todos");
  const persisted = reminders.items.find((item) => item.id === created.todo.id);
  assert.equal(persisted.workroom_request_id, result.todo.workroom_request_id);

  const replay = await postJson("/api/risk-evidence", {
    request_id: requestId,
    account_id: created.todo.account_id,
    customer: created.todo.customer,
    title: created.todo.title,
    action: created.todo.next_step,
    resolution: "本轮已推进，下一轮继续跟进。",
    next_step: "确认下一轮评审时间",
    status: "推进中",
    deadline: "2026-07-20T10:00+08:00",
    source_view: "自动验收",
    workflow_key: created.todo.id,
    object_type: "schedule",
    todo_id: created.todo.id,
    sync_calendar: false,
  });
  assert.equal(replay.idempotent_replay, true);
  assert.equal(replay.todo.workroom_request_id, result.todo.workroom_request_id);
});

test("failed Feishu completion keeps a retryable outbox record", async () => {
  const created = await postJson("/api/manual-todo", {
    customer: "云杉百货",
    title: `飞书补偿验收-${Date.now()}`,
    next_step: "完成隔离飞书补偿验收",
    target: "now",
    priority: "P2",
    sync_calendar: false,
  });
  const todoFile = path.join(testStateRoot, "workbench_data", "risk_todos.json");
  const todos = JSON.parse(await readFile(todoFile, "utf8"));
  const todo = todos.find((item) => item.id === created.todo.id);
  todo.calendar = { ok: true, status: "synced", task_guid: "fake-task-guid" };
  await writeFile(todoFile, JSON.stringify(todos, null, 2));

  const result = await postJson("/api/risk-evidence", {
    request_id: `workroom:${created.todo.id}|${created.todo.created_at}|${created.todo.deadline}|${created.todo.status}`,
    account_id: created.todo.account_id,
    customer: created.todo.customer,
    title: created.todo.title,
    action: created.todo.next_step,
    resolution: "隔离测试本地已闭环，飞书故意失败。",
    status: "已处理",
    source_view: "自动验收",
    workflow_key: created.todo.id,
    object_type: "schedule",
    todo_id: created.todo.id,
    sync_calendar: false,
  });
  assert.equal(result.calendar.status, "failed");
  assert.ok(result.calendar.outbox_id);

  const reminders = await getJson("/api/risk-todos");
  assert.ok(!reminders.items.some((item) => item.id === created.todo.id));
  const workflow = await getJson("/api/workflow/status");
  assert.ok(workflow.external_sync_outbox.some((item) => item.id === result.calendar.outbox_id && item.task_id === "fake-task-guid"));
});

test("static server exposes the app but not local credentials or source files", async () => {
  const page = await fetch(`${baseUrl}/`);
  assert.equal(page.status, 200);
  assert.match(page.headers.get("content-type") || "", /text\/html/);
  assert.match(page.headers.get("content-security-policy") || "", /default-src 'self'/);

  for (const path of ["/server.py", "/lark_auth_state.json", "/auth/lark-auth-20260612-172214.png"]) {
    const response = await fetch(`${baseUrl}${path}`);
    assert.equal(response.status, 404, `${path} should not be public`);
  }
});

test("cross-origin writes are rejected", async () => {
  const rejected = await fetch(`${baseUrl}/api/dashboard`, {
    method: "OPTIONS",
    headers: { Origin: "https://example.com" },
  });
  assert.equal(rejected.status, 403);

  const allowed = await fetch(`${baseUrl}/api/dashboard`, {
    method: "OPTIONS",
    headers: { Origin: baseUrl },
  });
  assert.equal(allowed.status, 204);
  assert.equal(allowed.headers.get("access-control-allow-origin"), baseUrl);
});
