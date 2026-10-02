import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
import server

class ManualTimingTests(unittest.TestCase):
    def run_at(self, instant, **payload):
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            stack.enter_context(patch.object(server,'datetime',Clock))
            stack.enter_context(patch.object(server,'RISK_TODO_LOG',Path(folder)/'todo.md'))
            stack.enter_context(patch.object(server,'append_risk_todo'))
            stack.enter_context(patch.object(server,'load_workflow_state',return_value={'schedule_status':{}}))
            stack.enter_context(patch.object(server,'save_workflow_state'))
            stack.enter_context(patch.object(server,'get_dashboard_payload',return_value={}))
            stack.enter_context(patch.object(server,'project_line_for_customer',return_value=''))
            return server.create_manual_todo_impl(dict(account_id='isolated-account',customer='隔离客户',title='当天跟进',sync_calendar=False,**payload))

    def test_now_never_moves_to_tomorrow_at_midnight(self):
        for time,expected in [('23:55:00','23:59'),('23:59:50','23:59'),('12:00:00','12:15')]:
            result=self.run_at(datetime.fromisoformat('2026-09-07T'+time+'+08:00'),target='now')
            self.assertEqual(result['todo']['deadline'],'2026-09-07T'+expected+'+08:00')
            self.assertEqual(result['workflow_state']['schedule_status'][result['todo']['id']]['deadline'],result['todo']['deadline'])

    def test_explicit_tomorrow_keeps_its_confirmed_date(self):
        result=self.run_at(datetime.fromisoformat('2026-09-07T23:55:00+08:00'),target='scheduled',deadline='2026-09-08T10:00+08:00')
        self.assertEqual(result['todo']['deadline'],'2026-09-08T10:00+08:00')
