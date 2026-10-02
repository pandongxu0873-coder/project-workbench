import test from "node:test";
import assert from "node:assert/strict";
import { discoveryLane, revenueRecord, outreachRoute, publicUrl } from "../src/discovery-model.js";

test("historical procurement does not become a live bid; watch alone does not mean historical", () => {
  assert.equal(discoveryLane({ title: "采购中标公告", deadline: "2026-09-20" }, "2026-09-06"), "history");
  assert.equal(discoveryLane({ title: "采购公告", deadline: "2026-09-20", decision: "watch" }, "2026-09-06"), "current");
  assert.equal(discoveryLane({ title: "采购线索", decision: "watch" }, "2026-09-06"), "potential");
  assert.equal(discoveryLane({ deadline: "2026-08-01" }, "2026-09-06"), "history");
  assert.equal(discoveryLane({ deadline: "待核实" }, "2026-09-06"), "potential");
});
test("revenue threshold requires revenue language, year and public evidence, not contract value", () => {
  assert.equal(revenueRecord({ revenue_evidence: "2025年合同额82亿元", source: "https://example.com/report" }).amount, null);
  assert.equal(revenueRecord({ revenue_evidence: "营收82亿元", source: "https://example.com/report" }).amount, null);
  assert.equal(revenueRecord({ revenue_evidence: "2025年营收82亿元", source: "https://example.com/report" }).amount, null);
  assert.equal(revenueRecord({ revenue_evidence: {status: "pending", amount_yi: 100, source_url: "https://example.com"}}).amount, null);
  assert.equal(publicUrl("javascript:alert(1)"), "");
});
test("ownership and protection gate outreach, historical supplier is not assumed replaceable", () => {
  const checked = { checked_at: "2026-09-06", ownership_evidence: "isolated fixture", owner_scope: "mine", protection: "none" };
  assert.match(outreachRoute(), /未查到不等于/);
  assert.match(outreachRoute({...checked, protection: "other"}), /暂停对外/);
  assert.match(outreachRoute({...checked, owner_scope: "other_k100"}), /默认不对外/);
  assert.match(outreachRoute({...checked, owner_scope: "channel"}), /协商联合/);
  assert.match(outreachRoute({...checked, owner_scope: "unowned"}), /认领/);
  assert.match(outreachRoute({...checked, demand: "later"}), /不预设会替换/);
});
