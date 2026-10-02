import copy
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import server


class ReminderConsentTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(server.LOCAL_TZ).replace(second=0, microsecond=0)
        deadline = (self.now + timedelta(minutes=5)).isoformat(timespec="minutes")
        self.item = {"id": "isolated-fixture", "customer": "隔离测试", "title": "确认的回访", "source_scope": "manual", "status": "推进中", "deadline": deadline, "reminder_minutes": 10,
                     "reminder_consent": {"enabled": True, "deadline": deadline, "confirmed_at": (self.now - timedelta(minutes=1)).isoformat()}}

    def test_only_explicit_opt_in_for_current_deadline_is_eligible(self):
        self.assertTrue(server.feishu_reminder_gate(self.item, self.now)["eligible"])
        for changes in ({"source_scope": "transcript_intake"}, {"source_scope": "workflow"}, {"status": "已完成"},
                        {"deadline": ""}, {"reminder_consent": {}}, {"deadline": (self.now + timedelta(hours=1)).isoformat()}):
            with self.subTest(changes=changes):
                self.assertFalse(server.feishu_reminder_gate({**self.item, **changes}, self.now)["eligible"])
        old = {**self.item, "deadline": (self.now - timedelta(days=55)).isoformat(), "source_scope": "workflow_receipt", "resolution_path": "workflow_receipts/fixture.md", "calendar": {"type": "feishu_task", "task_guid": "fixture-guid"}}
        old.pop("reminder_consent")
        self.assertFalse(server.feishu_reminder_gate(old, self.now)["eligible"])
        self.assertTrue(server.feishu_reminder_gate({**old, "deadline": self.item["deadline"]}, self.now)["eligible"])

    def test_once_only_and_no_overdue_replay_even_force(self):
        state = {"version": 1, "deliveries": []}
        rows = [copy.deepcopy(self.item)]
        with patch.object(server, "FEISHU_REMINDER_ENABLED", True), patch.object(server, "load_feishu_reminder_delivery_state", return_value=state), patch.object(server, "save_feishu_reminder_delivery_state"), patch.object(server, "risk_todos_payload", side_effect=lambda: {"items": rows}), patch.object(server, "send_feishu_reminder_message", return_value={"ok": True, "message_id": "fixture-only"}) as send:
            self.assertEqual(server.process_feishu_reminder_deliveries()["sent"], 1)
            self.assertEqual(server.process_feishu_reminder_deliveries()["sent"], 0)
            rows[0]["deadline"] = (self.now - timedelta(days=55)).isoformat()
            self.assertEqual(server.process_feishu_reminder_deliveries(force_overdue=True)["sent"], 0)
            self.assertEqual(send.call_count, 1)

    def test_failed_retry_is_not_replayed_after_expiry(self):
        state = {"version": 1, "deliveries": []}
        rows = [copy.deepcopy(self.item)]
        with patch.object(server, "FEISHU_REMINDER_ENABLED", True), patch.object(server, "load_feishu_reminder_delivery_state", return_value=state), patch.object(server, "save_feishu_reminder_delivery_state"), patch.object(server, "risk_todos_payload", side_effect=lambda: {"items": rows}), patch.object(server, "send_feishu_reminder_message", side_effect=RuntimeError("isolated failure")) as send:
            self.assertEqual(server.process_feishu_reminder_deliveries()["failed"], 1)
            rows[0]["deadline"] = (self.now - timedelta(minutes=1)).isoformat()
            self.assertEqual(server.process_feishu_reminder_deliveries(force_overdue=True)["sent"], 0)
            self.assertEqual(send.call_count, 1)

    def test_auth_start_returns_link_without_qr_json_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "auth.json"
            fixture = {"verification_url": "https://accounts.feishu.cn/fixture", "device_code": "isolated-placeholder", "expires_in": 600}
            with patch.object(server, "LARK_AUTH_STATE_FILE", state_file), patch.object(server, "run_json_command", return_value=fixture) as command:
                result = server.start_lark_auth()
            self.assertEqual(command.call_count, 1)
            self.assertIn("--scope", command.call_args.args[0])
            self.assertNotIn("--recommend", command.call_args.args[0])
            self.assertTrue(result["verification_url"])
            self.assertNotIn("device_code", result)
            self.assertFalse(result["expired"])
            self.assertEqual(state_file.stat().st_mode & 0o777, 0o600)

    def test_repeated_auth_start_reuses_active_request(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "auth.json"
            fixture = {"verification_url": "https://accounts.feishu.cn/fixture", "device_code": "isolated-placeholder", "expires_in": 600}
            with patch.object(server, "LARK_AUTH_STATE_FILE", state_file), patch.object(server, "run_json_command", return_value=fixture) as command:
                first = server.start_lark_auth()
                second = server.start_lark_auth()
                self.assertEqual(command.call_count, 1)
                self.assertTrue(second["reused"])
                self.assertEqual(first["verification_url"], second["verification_url"])
                self.assertNotIn("device_code", second)

    def test_complete_is_idempotent_after_read_verified(self):
        with patch.object(server, "get_message_sync_status", return_value={"action_required": False}), patch.object(server, "run_json_command") as command:
            self.assertTrue(server.complete_lark_auth()["ready"])
            command.assert_not_called()

    def test_complete_does_not_claim_read_success_from_login_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(server, "LARK_AUTH_STATE_FILE", Path(directory) / "auth.json"), patch.object(server, "get_lark_auth_state", return_value={"exists": True, "expired": False, "device_code": "isolated-placeholder"}), patch.object(server, "get_message_sync_status", return_value={"action_required": True, "detail": "missing read scope"}), patch.object(server, "run_json_command", return_value={"event": "authorized"}):
                result = server.complete_lark_auth()
                self.assertFalse(result["ready"])
                self.assertIn("读取尚未通过", result["message"])
