import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from ai_hot import Client, FeedError, endpoint, retry_delay


class AIHotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 1000
        self.calls = []
        self.responses = []
        def transport(path, etag):
            self.calls.append((path, etag))
            value = self.responses.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        self.client = Client(self.tmp.name, transport, lambda: self.now)

    def feed(self, items=None, **extra):
        return {'schemaVersion': 1, 'items': items or [], **extra}

    def test_reset_snapshot_replaces_retractions_and_keeps_source_watermark(self):
        first = {'schemaVersion': 1, 'checkedAt': '2026-09-17T10:00:00+08:00', 'events': [{'id': 'a'}, {'id': 'b'}]}
        second = {**first, 'events': [{'id': 'b', 'status': 'confirmed'}]}
        self.responses = [(first, 'a'), (second, 'b'), FeedError('暂不可用')]
        self.assertEqual(endpoint({'view': 'resets'}), 'codex-resets')
        self.client.read({'view': 'resets'})
        self.now += 61
        self.client.read({'view': 'resets', 'refresh': '1'})
        self.assertEqual(len(self.calls), 1)
        self.now += 300
        result = self.client.read({'view': 'resets'})
        self.assertEqual(result['data'], second)
        self.assertEqual(self.calls[1][1], 'a')
        self.now += 300
        result = self.client.read({'view': 'resets'})
        self.assertTrue(result['stale'])
        self.assertEqual(result['data'], second)

    def test_warm_cache_and_conditional_request_keep_original_fetch_date(self):
        self.responses = [(self.feed([{'id': 'a'}]), 'W/"one"'), (None, 'W/"one"')]
        first = self.client.read({})
        self.now += 30
        self.assertEqual(self.client.read({'refresh': '1'})['data'], first['data'])
        self.assertEqual(len(self.calls), 1)
        self.now += 400
        second = self.client.read({})
        self.assertEqual(self.calls[1][1], 'W/"one"')
        self.assertEqual(second['fetched_at'], first['fetched_at'])
        self.assertNotEqual(second['checked_at'], first['checked_at'])
        self.assertFalse(second['stale'])

    def test_failed_refresh_preserves_cached_data_and_marks_stale(self):
        self.responses = [(self.feed([{'id': 'a'}]), 'x'), FeedError('连接失败')]
        first = self.client.read({})
        self.now += 400
        result = self.client.read({})
        self.assertTrue(result['stale'])
        self.assertEqual(result['data'], first['data'])
        self.assertEqual(result['checked_at'], first['checked_at'])
        self.now += 1
        self.assertTrue(self.client.read({'refresh': '1'})['stale'])
        self.assertEqual(len(self.calls), 2)

    def test_search_fallback_preserves_all_filters_and_cursor_mode(self):
        self.responses = [(self.feed(), ''), (self.feed([{'id': 'b', 'selected': False}]), '')]
        result = self.client.read({'q': '营销', 'window': '7d', 'category': 'ai-products'})
        self.assertTrue(result['unselected_search'])
        query = parse_qs(urlparse(self.calls[1][0]).query)
        self.assertEqual(query['q'], ['营销'])
        self.assertEqual(query['category'], ['ai-products'])
        self.assertEqual(query['window'], ['7d'])
        self.assertEqual(query['mode'], ['all'])
        path = endpoint({'q': '营销', 'window': '7d', 'mode': 'all', 'cursor': 'abc/+=='})
        self.assertEqual(parse_qs(urlparse(path).query)['cursor'], ['abc/+=='])

    def test_empty_broad_query_does_not_expand_pool(self):
        self.responses = [(self.feed(), '')]
        self.assertFalse(self.client.read({})['unselected_search'])
        self.assertEqual(len(self.calls), 1)

    def test_daily_uses_actual_index_date_and_keeps_report_structure(self):
        report = {'date': '2026-09-11', 'lead': None, 'sections': [], 'flashes': []}
        self.responses = [(self.feed([{'date': '2026-09-11'}]), ''), ({'schemaVersion': 1, 'report': report}, '')]
        result = self.client.read({'view': 'daily'})
        self.assertEqual(self.calls[1][0], 'dailies/2026-09-11')
        self.assertEqual(result['data']['report'], report)
        self.assertEqual(result['dates'], ['2026-09-11'])

    def test_missing_explicit_daily_does_not_substitute_another_date(self):
        self.responses = [FeedError('该日期尚无日报', status=404)]
        with self.assertRaises(FeedError):
            self.client.read({'view': 'daily', 'date': '2026-01-01'})
        self.assertEqual(len(self.calls), 1)

    def test_rate_limit_blocks_other_queries_without_bypassing(self):
        self.responses = [FeedError('稍后再试', status=429, retry_after=120)]
        with self.assertRaises(FeedError): self.client.read({})
        with self.assertRaises(FeedError): self.client.read({'q': 'Agent'})
        self.assertEqual(len(self.calls), 1)

    def test_invalid_queries_and_untrusted_urls_do_not_become_endpoints(self):
        for params in [{'view': 'https://evil.test'}, {'window': '30d'}, {'category': 'unknown'},
                       {'q': 'a'}, {'view': 'daily', 'date': '../../secrets'}, {'mode': 'all'}]:
            with self.assertRaises(ValueError): endpoint(params)
        path = endpoint({'q': 'hello&cursor=evil'})
        self.assertEqual(parse_qs(urlparse(path).query)['q'], ['hello&cursor=evil'])
        self.assertNotIn('cursor', parse_qs(urlparse(path).query))

    def test_caches_do_not_mix_searches_or_windows(self):
        self.responses = [(self.feed([{'id': 'today'}]), 'a'), (self.feed([{'id': 'week'}]), 'b')]
        self.client.read({'window': '24h'})
        week = self.client.read({'window': '7d'})
        today = self.client.read({'window': '24h'})
        self.assertEqual(week['data']['items'][0]['id'], 'week')
        self.assertEqual(today['data']['items'][0]['id'], 'today')

    def test_corrupt_cache_does_not_claim_read_success(self):
        self.responses = [(self.feed([{'id': 'a'}]), '')]
        self.client.read({})
        file = next(Path(self.tmp.name).glob('*.json'))
        file.write_text('{broken')
        self.responses = [FeedError('网络不可用')]
        with self.assertRaises(FeedError): self.client.read({})

    def test_stale_index_propagates_to_daily(self):
        report = {'schemaVersion': 1, 'report': {'date': '2026-09-11'}}
        self.responses = [(self.feed([{'date': '2026-09-11'}]), 'a'), (report, 'b')]
        self.client.read({'view': 'daily'})
        self.now += 400
        self.responses = [FeedError('索引暂不可读'), (None, 'b')]
        self.assertTrue(self.client.read({'view': 'daily'})['stale'])


if __name__ == '__main__': unittest.main()
