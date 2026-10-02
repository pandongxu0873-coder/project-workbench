import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class SyncIntegrityTest(unittest.TestCase):
    def test_disabled_bot_reminders_never_load_tasks_or_send_even_if_forced(self):
        with patch.object(server, "FEISHU_REMINDER_ENABLED", False), patch.object(server, "risk_todos_payload") as tasks, patch.object(server, "send_feishu_reminder_message") as send:
            result = server.process_feishu_reminder_deliveries(force_overdue=True)
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["sent"], 0)
        tasks.assert_not_called()
        send.assert_not_called()
        with patch.object(server, "FEISHU_REMINDER_ENABLED", False):
            view = server.feishu_reminder_delivery_payload(state={"deliveries": [{"status": "failed", "last_error": "old failure"}]})
        self.assertEqual(view["status"], "disabled")
        self.assertIn("已关闭", view["policy"]["overdue"])

    def test_report_merge_preserves_groups_and_is_replay_safe(self):
        old = {"date": "2026-09-06", "items": [{"name": "A", "message_count": 10}, {"name": "B", "message_count": 5}], "message_count": 15}
        new = {"date": "2026-09-06", "items": [{"name": "A", "message_count": 20}], "message_count": 20}
        merged = server.merge_pm_daily_reports(old, new)
        self.assertEqual({i["name"] for i in merged["items"]}, {"A", "B"})
        self.assertEqual(merged["message_count"], 25)
        self.assertEqual(server.merge_pm_daily_reports(merged, new)["message_count"], 25)

    def test_messages_read_second_page_and_stop_at_today(self):
        pages = [{"data": {"items": [{"create_time": "200"}] * 50, "has_more": True, "page_token": "next"}},
                 {"data": {"items": [{"create_time": "150"}, {"create_time": "90"}], "has_more": True, "page_token": "older"}}]
        reader = lambda params: pages.pop(0)
        self.assertEqual(len(server.collect_today_lark_messages("fixture", 100, reader)), 51)
        self.assertFalse(pages)

    def test_incomplete_paging_is_not_success(self):
        for data in ({"items": [], "has_more": True}, {"items": [{"create_time": "200"}], "has_more": True}):
            with self.subTest(data=data), self.assertRaises(RuntimeError):
                server.collect_today_lark_messages("fixture", 100, lambda params: {"data": data})
        def endless(params):
            token = str(int(params.get("page_token", "0")) + 1)
            return {"data": {"items": [{"create_time": "200"}] * 50, "has_more": True, "page_token": token}}
        with self.assertRaises(RuntimeError):
            server.collect_today_lark_messages("fixture", 100, endless)

    def test_legacy_report_read_is_non_destructive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy, current = root / "legacy", root / "current"
            legacy.mkdir(); current.mkdir()
            source = legacy / "2026-09-01_PM日报.md"
            source.write_text("preserved fixture")
            with patch.object(server, "LEGACY_PM_DAILY_ROOT", legacy), patch.object(server, "PM_DAILY_ROOT", current), patch.object(server, "parse_pm_report_file", return_value={"date": "2026-09-01"}):
                self.assertEqual(len(server.load_persisted_pm_reports(20)), 1)
            self.assertEqual(source.read_text(), "preserved fixture")

