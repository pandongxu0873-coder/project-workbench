import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from commercial import BUDGET_FIELDS, DraftConflict, get_draft, preview_draft, save_draft
from project_workspace import build_projects


class CommercialTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.knowledge = self.root / "knowledge"
        self.state = self.root / "state"
        (self.knowledge / "projects").mkdir(parents=True)
        (self.knowledge / "raw").mkdir()
        (self.knowledge / "raw" / "reply.md").write_text("真实测试夹具：确认本版本36.5人日。")
        self.source = self.knowledge / "projects" / "星海汽车.md"
        self.source.write_text("---\nsources:\n  - raw/reply.md\n---\n# 星海汽车定制\n\n**客户**：[[星海汽车商城]]\n")
        self.project = build_projects(self.knowledge, self.state)[0]
        self.payload = {"project_id": self.project["id"], "revision": 0, "requirement": "代客下单改价叠加积分及优惠选择",
                        "effort": "36.5", "rate": "2000", "budget": {"own_labor": "45000"},
                        "customer_confirmed": True, "budget_verified": True, "confirmation_source": "raw/reply.md",
                        "confirmation_excerpt": "确认本版本36.5人日", "version": "复核确认版"}

    def tearDown(self):
        self.temp.cleanup()

    def test_no_contact_suppresses_customer_email_across_read_preview_save(self):
        from project_rounds import save_round
        save_round(dict(project_id=self.project['id'], revision=0, scenario='relationship', relationship='no_contact', status='暂停跟进', facts='客户明确暂勿联系'), self.knowledge, self.state)
        for result in (get_draft(self.project['id'], self.knowledge, self.state), preview_draft(self.payload,self.knowledge,self.state), save_draft(self.payload,self.knowledge,self.state)):
            self.assertTrue(result['contact_blocked'])
            self.assertIsNone(result['customer_email'])
            self.assertTrue(result['internal_approval'])

    def test_exact_template_and_external_separation(self):
        result = preview_draft(self.payload, self.knowledge, self.state)
        self.assertEqual(result["calculation"], {"revenue": "73000", "budget_total": "45000", "gross_profit": "28000", "margin_percent": "38.36"})
        self.assertTrue(result["approval_ready"])
        self.assertIn("@审批负责人，星海汽车新增定制需求", result["internal_approval"])
        self.assertIn("客户已确认人天，辛苦审批负责人审批报价申请、合同工单及提前启动工单～", result["internal_approval"])
        for key, label in BUDGET_FIELDS:
            self.assertIn(f"{label}：{'45,000' if key == 'own_labor' else '0'}元", result["internal_approval"])
            self.assertNotIn(label, result["customer_email"]["body"])
        for private in ("45,000", "28,000", "38.36", "毛利", "预算", "自成本", "PCO", "Token"):
            self.assertNotIn(private, result["customer_email"]["body"])
        self.assertFalse((self.state / "commercial_drafts").exists())

    def test_missing_evidence_unknown_cost_and_sample_stay_drafts(self):
        for changes in ({"confirmation_source": "projects/星海汽车.md"}, {"confirmation_source": "raw/missing.md"},
                        {"confirmation_excerpt": ""}, {"version": ""}, {"customer_confirmed": False},
                        {"budget_verified": False}, {"sample": True}):
            with self.subTest(changes=changes):
                result = preview_draft({**self.payload, **changes}, self.knowledge, self.state)
                self.assertFalse(result["approval_ready"])
                self.assertNotIn("客户已完成工作量复核确认", result["internal_approval"])
                self.assertNotIn("客户已确认人天，辛苦", result["internal_approval"])

    def test_save_reload_revision_and_project_identity(self):
        source_before = self.source.read_text()
        saved = save_draft(self.payload, self.knowledge, self.state)
        restored = get_draft(self.project["id"], self.knowledge, self.state)
        self.assertEqual(saved, restored)
        self.assertEqual(restored["draft"]["revision"], 1)
        self.assertEqual(restored["draft"]["project_source"], "projects/星海汽车.md")
        self.assertEqual(self.source.read_text(), source_before)
        with self.assertRaises(DraftConflict):
            save_draft(self.payload, self.knowledge, self.state)
        self.assertEqual(get_draft(self.project["id"], self.knowledge, self.state)["draft"]["revision"], 1)
        with self.assertRaises(ValueError):
            save_draft({**self.payload, "project_id": "../../outside"}, self.knowledge, self.state)

    def test_atomic_failure_preserves_previous(self):
        save_draft(self.payload, self.knowledge, self.state)
        before = get_draft(self.project["id"], self.knowledge, self.state)
        with patch("commercial.os.replace", side_effect=OSError("isolated simulated disk failure")):
            with self.assertRaises(OSError):
                save_draft({**self.payload, "revision": 1, "rate": "2500"}, self.knowledge, self.state)
        self.assertEqual(before, get_draft(self.project["id"], self.knowledge, self.state))
        self.assertFalse(list((self.state / "commercial_drafts").glob("*.tmp")))

    def test_strict_decimals_and_blank_zero(self):
        for value in ("-1", "NaN", "Infinity", True, "1.0000001", "100000000001", [], None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                preview_draft({**self.payload, "effort": value}, self.knowledge, self.state)
        result = preview_draft({**self.payload, "effort": "", "budget": {"own_labor": ""}}, self.knowledge, self.state)
        self.assertEqual(result["calculation"]["budget_total"], "0")
        self.assertIsNone(result["calculation"]["margin_percent"])
        self.assertFalse(result["approval_ready"])

    def test_unknown_fields_and_removed_source(self):
        with self.assertRaises(ValueError):
            preview_draft({**self.payload, "budget": {"auto_ten_percent": "7300"}}, self.knowledge, self.state)
        save_draft(self.payload, self.knowledge, self.state)
        (self.knowledge / "raw" / "reply.md").unlink()
        self.assertFalse(get_draft(self.project["id"], self.knowledge, self.state)["approval_ready"])
        self.source.unlink()
        with self.assertRaises(ValueError):
            get_draft(self.project["id"], self.knowledge, self.state)

    def test_changed_evidence_revokes_confirmation_and_versions_are_kept(self):
        first = save_draft(self.payload, self.knowledge, self.state)
        self.assertTrue(first["draft"]["confirmation_fingerprint"])
        (self.knowledge / "raw" / "reply.md").write_text("修订版本：人日尚未确认")
        changed = get_draft(self.project["id"], self.knowledge, self.state)
        self.assertFalse(changed["approval_ready"])
        self.assertFalse(changed["draft"]["customer_confirmed"])
        self.assertIn("确认来源内容已变化", "；".join(changed["blocking_reasons"]))
        save_draft(changed["draft"], self.knowledge, self.state)
        histories = list((self.state / "commercial_drafts").glob("*.r1.json"))
        self.assertEqual(len(histories), 1)
        self.assertTrue(json.loads(histories[0].read_text())["customer_confirmed"])

    def test_open_draft_recheck_detects_newer_saved_quote_without_overwriting(self):
        first = save_draft(self.payload, self.knowledge, self.state)
        second = save_draft({**first['draft'], 'effort': '40', 'customer_confirmed': False}, self.knowledge, self.state)
        with self.assertRaises(DraftConflict):
            preview_draft(first['draft'], self.knowledge, self.state)
        self.assertEqual(get_draft(self.project['id'], self.knowledge, self.state)['draft'], second['draft'])

    def test_open_draft_preview_downgrades_changed_evidence_and_no_contact(self):
        from project_rounds import save_round
        first = save_draft(self.payload, self.knowledge, self.state)
        (self.knowledge / 'raw' / 'reply.md').write_text('范围已调整，旧人日待重新确认')
        checked = preview_draft(first['draft'], self.knowledge, self.state)
        self.assertFalse(checked['approval_ready'])
        self.assertEqual(checked['draft']['effort'], first['draft']['effort'])
        self.assertNotIn('客户已完成工作量复核确认', checked['internal_approval'])
        save_round(dict(project_id=self.project['id'], revision=0, scenario='relationship', relationship='no_contact', status='暂停跟进', facts='客户明确暂勿联系'), self.knowledge, self.state)
        checked = preview_draft(first['draft'], self.knowledge, self.state)
        self.assertIsNone(checked['customer_email'])
        self.assertEqual(get_draft(self.project['id'], self.knowledge, self.state)['draft']['revision'], 1)


if __name__ == "__main__":
    unittest.main()
