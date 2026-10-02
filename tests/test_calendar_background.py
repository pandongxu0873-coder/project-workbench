"""Calendar cache concurrency; real CLI/network and production writes are mocked."""
from contextlib import ExitStack
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import server


class CalendarBackgroundTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stack = ExitStack()
        self.path = Path(self.tmp.name)/'calendar.json'
        self.jobs = {}
        self.stack.enter_context(patch.object(server, 'FEISHU_CALENDAR_CACHE', self.path))
        self.stack.enter_context(patch.object(server, 'FEISHU_CALENDAR_READ_JOBS', self.jobs))
        self.start = datetime(2026, 9, 20, tzinfo=server.LOCAL_TZ)
        self.end = self.start+timedelta(days=7)
        self.key = f'{int(self.start.timestamp())}:{int(self.end.timestamp())}'
        self.entered = threading.Event(); self.release = threading.Event()

    def tearDown(self):
        self.release.set()
        for job in list(self.jobs.values()):
            self.assertTrue(job['done'].wait(2), 'test worker did not complete')
        self.stack.close(); self.tmp.cleanup()

    def cache(self, age=300, items=None, key=None):
        value = {'ok': True, 'range_key': key or self.key, 'fetched_at': 'old-time',
                 'fetched_at_ts': int(time.time())-age, 'items': [{'event_id': 'existing'}] if items is None else items, 'error': ''}
        self.path.write_text(json.dumps(value)); return value

    def blocked_cli(self, *args, **kwargs):
        self.entered.set()
        if not self.release.wait(2): raise RuntimeError('test barrier timeout')
        return {'data': {'items': [{'event_id': 'new'}]}}

    def fetch(self, refresh=False):
        return server.fetch_feishu_calendar_instances(self.start, self.end, refresh)

    def complete(self):
        self.release.set()
        self.assertTrue(next(iter(self.jobs.values()))['done'].wait(2))

    def test_stale_get_returns_cache_and_ten_readers_share_one_background_cli(self):
        self.cache()
        cli = self.stack.enter_context(patch.object(server, 'run_json_command', side_effect=self.blocked_cli))
        first = self.fetch()
        self.assertTrue(self.entered.wait(1))
        rows = [self.fetch() for _ in range(10)]
        self.assertEqual(cli.call_count, 1)
        self.assertTrue(first['ok'] and first['stale'] and first['refreshing'])
        self.assertTrue(all(r['items'][0]['event_id']=='existing' and r['fetched_at']=='old-time' for r in rows))
        self.complete()
        fresh = self.fetch()
        self.assertFalse(fresh['stale'] or fresh['refreshing']); self.assertEqual(fresh['items'][0]['event_id'], 'new')

    def test_cold_get_is_unread_until_success_even_when_valid_result_is_empty(self):
        def empty(*args, **kwargs):
            self.blocked_cli(); return {'data': {'items': []}}
        self.stack.enter_context(patch.object(server, 'run_json_command', side_effect=empty))
        cold = self.fetch()
        self.assertFalse(cold['ok'] or cold['cache_available']); self.assertTrue(cold['refreshing'])
        self.assertIn('尚不能确认', cold['error'])
        self.complete()
        complete = self.fetch()
        self.assertTrue(complete['ok'] and complete['cache_available']); self.assertEqual(complete['items'], [])
        self.assertEqual(complete['read_state'], 'ready')

    def test_failure_keeps_old_file_and_backs_off_but_force_retries(self):
        self.cache(items=[]); previous = self.path.read_bytes()
        cli = self.stack.enter_context(patch.object(server, 'run_json_command', side_effect=[TimeoutError('timeout'), {'data': {'items': []}}]))
        self.fetch(); self.assertTrue(next(iter(self.jobs.values()))['done'].wait(1))
        rows = [self.fetch() for _ in range(10)]
        self.assertEqual(cli.call_count, 1); self.assertEqual(self.path.read_bytes(), previous)
        self.assertTrue(rows[0]['ok'] and rows[0]['stale']); self.assertEqual(rows[0]['read_state'], 'error')
        self.assertIn('日程读取超时', rows[0]['error'])
        forced = self.fetch(True)
        self.assertEqual(cli.call_count, 2); self.assertTrue(forced['ok']); self.assertFalse(forced['from_cache'])

    def test_force_joins_inflight_and_returns_completion_not_refreshing_receipt(self):
        self.cache()
        cli = self.stack.enter_context(patch.object(server, 'run_json_command', side_effect=self.blocked_cli))
        self.fetch(); self.assertTrue(self.entered.wait(1))
        result = {}; done = threading.Event()
        def force(): result.update(self.fetch(True)); done.set()
        caller = threading.Thread(target=force); caller.start()
        self.assertFalse(done.wait(.03)); self.assertEqual(cli.call_count, 1)
        self.complete(); caller.join(2)
        self.assertTrue(done.is_set()); self.assertTrue(result['ok'])
        self.assertFalse(result['refreshing'] or result['from_cache']); self.assertEqual(result['items'][0]['event_id'], 'new')

    def test_explicit_force_failure_is_failure_even_with_cached_items(self):
        self.cache(age=1)
        self.stack.enter_context(patch.object(server, 'run_json_command', side_effect=RuntimeError('network unavailable')))
        result = self.fetch(True)
        self.assertFalse(result['ok']); self.assertTrue(result['cache_available'] and result['stale'])
        self.assertEqual(result['items'][0]['event_id'], 'existing'); self.assertIn('network unavailable', result['error'])

    def test_other_window_does_not_show_old_events_and_serializes_force(self):
        self.cache()
        cli = self.stack.enter_context(patch.object(server, 'run_json_command', side_effect=self.blocked_cli))
        self.fetch(); self.assertTrue(self.entered.wait(1))
        other_start=self.start+timedelta(days=1); other_end=self.end+timedelta(days=1)
        other = server.fetch_feishu_calendar_instances(other_start, other_end)
        self.assertFalse(other['ok'] or other['cache_available']); self.assertEqual(other['items'], [])
        self.assertEqual(cli.call_count, 1)
        result = {}; done = threading.Event()
        def force(): result.update(server.fetch_feishu_calendar_instances(other_start, other_end, True)); done.set()
        caller = threading.Thread(target=force); caller.start()
        self.assertFalse(done.wait(.03)); self.release.set(); caller.join(2)
        self.assertTrue(done.is_set()); self.assertEqual(cli.call_count, 2)
        self.assertTrue(result['ok']); self.assertNotEqual(result['range_key'], self.key)

    def test_malformed_result_never_replaces_cache_with_empty_success(self):
        self.cache(); previous=self.path.read_bytes()
        self.stack.enter_context(patch.object(server, 'run_json_command', return_value={'data': {}}))
        result=self.fetch(True)
        self.assertFalse(result['ok']); self.assertIn('不能认定没有日程', result['error'])
        self.assertEqual(self.path.read_bytes(), previous)

    def test_routine_meeting_only_survives_in_display_background(self):
        now = server.datetime.now(server.LOCAL_TZ)
        event = {'event_id':'isolated-weekly', 'summary':'内部周会', 'start_time':{'timestamp':str(int(now.timestamp())+3600)}, 'end_time':{'timestamp':str(int(now.timestamp())+7200)}}
        self.assertIsNone(server.normalize_calendar_event(event, [], now))
        item = server.normalize_calendar_event(event, [], now, include_background=True)
        self.assertIsNotNone(item)
        self.assertEqual(server.merge_schedule_items([], [item], {}), [])

    def test_unmatched_nonroutine_is_only_calendar_background(self):
        now = server.datetime.now(server.LOCAL_TZ)
        event = {'event_id':'isolated-unmatched', 'summary':'待确认事项', 'start_time':{'timestamp':str(int(now.timestamp())+3600)}, 'end_time':{'timestamp':str(int(now.timestamp())+7200)}}
        fetched = {'ok':True,'items':[event]}
        with patch.object(server, 'fetch_feishu_calendar_instances', return_value=fetched), patch.object(server, 'build_projects', return_value=[]), patch.object(server.project_rounds, 'followups', return_value={'claimed_actions': {}}), patch.object(server, 'load_risk_todos', return_value=[]), patch.object(server, 'load_workflow_state', return_value={}):
            result = server.calendar_schedule_payload([], [])
        self.assertEqual(len(result['background_items']),1)
        self.assertEqual(result['items'],[])

    def test_schedule_payload_propagates_cached_refresh_state(self):
        fetched = {'ok': True, 'items': [], 'from_cache': True, 'fetched_at': 'old-time', 'error': '更新中，显示上次结果',
                   'cache_available': True, 'stale': True, 'refreshing': True, 'refresh_error': '', 'read_state': 'refreshing'}
        with patch.object(server, 'fetch_feishu_calendar_instances', return_value=fetched), patch.object(server, 'build_projects', return_value=[]), patch.object(server.project_rounds, 'followups', return_value={'claimed_actions': {}}), patch.object(server, 'load_risk_todos', return_value=[]), patch.object(server, 'load_workflow_state', return_value={}):
            result=server.calendar_schedule_payload([], [])
        self.assertEqual(result['label'], '飞书日程更新中'); self.assertEqual(result['fetched_at'], 'old-time')
        self.assertTrue(result['stale'] and result['refreshing']); self.assertEqual(result['read_state'], 'refreshing')


if __name__ == '__main__': unittest.main()
