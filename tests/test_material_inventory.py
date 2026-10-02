import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import material_collectors as collectors
from material_inventory import reconcile


class DesktopInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.desktop = self.root / 'desktop'
        self.desktop.mkdir()
        self.state = self.root / 'state'
        self.state.mkdir()
        self.a = self.desktop / '报价.txt'
        self.a.write_text('我方报价，客户未确认')
        self.sha = hashlib.sha256(self.a.read_bytes()).hexdigest()
        self.config = {'desktop_root': str(self.desktop), 'directories': [],
                       'files': {'报价.txt': self.sha}, 'scope': '隔离桌面散落文件'}
        self.index = {'files': [], 'recordings': []}

    def scan(self):
        return collectors.scan_desktop(self.state, self.config)

    def test_unchanged_baseline_is_not_already_indexed_or_reviewed(self):
        receipt = self.scan()
        self.assertEqual(receipt['new_count'], 0)
        result = reconcile(self.state, self.index, receipt)
        self.assertEqual((result['unique_count'], result['indexed_count'], result['unindexed_count']), (1, 0, 1))
        self.assertEqual(result['unindexed_files'][0]['paths'], ['报价.txt'])

    def test_same_bytes_dedupe_across_names_and_index_import_clears_gap(self):
        (self.desktop / '报价副本.txt').write_bytes(self.a.read_bytes())
        receipt = self.scan()
        before = (self.state / 'desktop_scan_snapshot.json').read_bytes()
        result = reconcile(self.state, self.index, receipt)
        self.assertEqual((result['file_count'], result['unique_count'], result['duplicate_count']), (2, 1, 1))
        self.assertEqual(result['unindexed_files'][0]['copy_count'], 2)
        self.index['files'].append({'id': 'f1', 'sha256': self.sha, 'processing': 'pending'})
        result = reconcile(self.state, self.index, receipt)
        self.assertEqual((result['indexed_count'], result['unindexed_count']), (1, 0))
        self.assertEqual(self.index['files'][0]['processing'], 'pending')
        self.assertNotIn('classified', result)
        self.assertEqual((self.state / 'desktop_scan_snapshot.json').read_bytes(), before)

    def test_same_name_changed_content_needs_new_index_version(self):
        self.index['files'].append({'id': 'f1', 'title': '报价.txt', 'sha256': self.sha})
        self.scan()
        self.a.write_text('客户回传新范围，新报价待出')
        receipt = self.scan()
        result = reconcile(self.state, self.index, receipt)
        self.assertEqual(receipt['changed_count'], 1)
        self.assertEqual(result['unindexed_count'], 1)

    def test_recording_index_and_non_business_classification_remain_separate(self):
        self.index['recordings'].append({'id': 'r1', 'sha256': self.sha, 'category': '非业务或测试'})
        result = reconcile(self.state, self.index, self.scan())
        self.assertEqual(result['unindexed_count'], 0)
        self.assertEqual(self.index['recordings'][0]['category'], '非业务或测试')
        self.assertNotIn('project_id', result)

    def test_failed_and_missing_cache_entries_do_not_inflate_current_scan(self):
        self.scan()
        self.a.write_text('正在更新的文件')
        with patch('material_collectors.fingerprint', side_effect=OSError('读取失败')):
            receipt = self.scan()
        cached = json.loads((self.state / 'desktop_scan_snapshot.json').read_text())
        self.assertIn('报价.txt', cached['files'])
        self.assertEqual(cached['observed_paths'], [])
        result = reconcile(self.state, self.index, receipt)
        self.assertTrue(result['partial_scan'])
        self.assertEqual(result['file_count'], 0)
        self.a.unlink()
        self.assertEqual(reconcile(self.state, self.index, self.scan())['file_count'], 0)
        self.a.write_text('恢复成功')
        self.assertEqual(reconcile(self.state, self.index, self.scan())['file_count'], 1)

    def test_mismatched_scope_time_and_unavailable_receipt_do_not_claim_coverage(self):
        receipt = self.scan()
        for changed in ({'scope': '别的目录'}, {'checked_at': '2000-01-01'}):
            self.assertEqual(reconcile(self.state, self.index, {**receipt, **changed})['status'], 'awaiting_scan')

    def test_access_failure_keeps_last_readable_scope_without_claiming_new_scan(self):
        receipt = self.scan()
        failed = {'status': 'unavailable', 'scope': receipt['scope'], 'checked_at': '2099-01-01'}
        result = reconcile(self.state, self.index, failed)
        self.assertTrue(result['retained_scan'])
        self.assertEqual(result['checked_at'], receipt['checked_at'])
        self.assertEqual(result['unindexed_count'], 1)
        self.assertEqual(reconcile(self.state, self.index, {**failed, 'scope': '其他目录'})['status'], 'awaiting_scan')

    def test_legacy_or_corrupt_snapshot_waits_for_scan_and_preserves_data(self):
        receipt = self.scan()
        snapshot_path = self.state / 'desktop_scan_snapshot.json'
        original = json.loads(snapshot_path.read_text())
        for snapshot in ({'files': original['files']}, {**original, 'observed_paths': ['../private.txt']}, {**original, 'observed_paths': ['报价.txt', '报价.txt']}):
            snapshot_path.write_text(json.dumps(snapshot))
            before = snapshot_path.read_bytes()
            self.assertEqual(reconcile(self.state, self.index, receipt)['status'], 'awaiting_scan')
            self.assertEqual(snapshot_path.read_bytes(), before)
