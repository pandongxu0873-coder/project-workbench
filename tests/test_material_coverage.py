import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import material_library as library
import material_coverage as coverage

class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.k = Path(self.tmp.name)/'kb'; self.s = Path(self.tmp.name)/'state'
        (self.k/'tracking').mkdir(parents=True); (self.k/'raw/transcripts').mkdir(parents=True)
        (self.k/'raw/transcripts/a.txt').write_text('我方报价，客户未确认。')
        self.idx = {'assets': {'a': {'path':'raw/transcripts/a.txt','readable':True,'label':'转写'}, 'secret': {'path':'raw/private.m4a','sensitive':True}}, 'recordings': [{'id':'r1','processing':'reviewed','sources':['a','secret'],'project_id':'p1','category':'有业务增量'}], 'files':[], 'conflicts':[]}
        self.save()
    def save(self): (self.k/'tracking/material_library.json').write_text(json.dumps(self.idx))
    def load(self): return library.library(self.k, self.s)
    def test_stages_are_not_business_confirmation_and_private_is_not_failure(self):
        x=self.load(); p=x['recordings'][0]['pipeline']
        self.assertTrue(p['text_ready']); self.assertTrue(p['classified']); self.assertTrue(p['linked'])
        self.assertEqual(p['confirmation'],'claim_specific'); self.assertEqual(p['restricted_count'],1)
        self.assertEqual(x['coverage']['exceptions'],[])
    def test_changed_source_stays_stale_after_repeated_refresh_and_restart(self):
        x=self.load(); before=coverage.read(self.s)
        self.load(); self.assertEqual(coverage.read(self.s),before)
        (self.k/'raw/transcripts/a.txt').write_text('新范围；原报价尚不适用。')
        for i in range(3):
            x=self.load(); self.assertTrue(x['recordings'][0]['pipeline']['stale']); self.assertFalse(x['recordings'][0]['pipeline']['classified'])
        self.assertEqual(len(x['coverage']['exceptions']),1)
    def test_missing_only_fails_corresponding_source_and_recovers_on_readback(self):
        self.idx['assets']['b']={'path':'raw/transcripts/b.txt','readable':True};self.idx['recordings'].append({'id':'r2','sources':['b']});self.save()
        x=self.load();self.assertTrue(x['recordings'][0]['pipeline']['classified'])
        self.assertEqual(x['recordings'][1]['pipeline']['missing_asset_ids'],['b'])
        (self.k/'raw/transcripts/b.txt').write_text('补回原文')
        x=self.load();self.assertEqual(x['recordings'][1]['pipeline']['missing_asset_ids'],[])
        self.assertFalse(x['recordings'][1]['pipeline']['classified'])
    def test_scan_failure_keeps_last_complete_boundary(self):
        good=dict(status='ok',checked_at='2026-09-07T09:00:00+08:00',scope='2026年8月起',receipt='local scan',complete_scope=True,observed=51)
        coverage.record_scan(self.s,'phone',good)
        coverage.record_scan(self.s,'phone',{**good,'status':'unavailable','checked_at':'2026-09-07T10:00:00+08:00','complete_scope':False,'observed':0})
        x=coverage.read(self.s)['channels']['phone'];self.assertEqual(x['last_complete_scan'],good['checked_at']);self.assertEqual(x['status'],'unavailable')
        self.assertEqual(len(list((self.s/'material_scan_history').glob('*.json'))),2)
    def test_excluded_phone_is_not_shown_as_a_sync_failure(self):
        self.s.mkdir(exist_ok=True)
        (self.s/'material_collectors.json').write_text(json.dumps({'excluded_channels':['phone']}))
        with patch('material_collectors.start_due'):
            x=self.load()
        phone=next(c for c in x['coverage']['channels'] if c['id']=='phone')
        self.assertEqual(phone['status'],'excluded');self.assertEqual(phone['failed_files'],[])

    def test_authorized_manual_phone_import_does_not_enable_continuous_collection(self):
        self.s.mkdir(exist_ok=True)
        (self.s/'material_collectors.json').write_text(json.dumps({'excluded_channels':['phone']}))
        coverage.record_scan(self.s,'phone',dict(status='ok',mode='manual_import',checked_at='2026-10-02T15:00:00+08:00',scope='9月26日至10月2日，指定USB设备',receipt='real-import',observed=9,new_count=5,excluded=4,complete_scope=True))
        x=self.load();phone=next(c for c in x['coverage']['channels'] if c['id']=='phone')
        self.assertEqual(phone['status'],'ok');self.assertFalse(phone['auto_sync']);self.assertIn('手动导入',phone['note'])
        self.assertEqual(json.loads((self.s/'material_collectors.json').read_text())['excluded_channels'],['phone'])

    def test_tencent_access_without_a_scan_is_not_full_transcript_coverage(self):
        x=self.load();source=next(c for c in x['coverage']['channels'] if c['id']=='tencent_meeting')
        self.assertEqual(source['status'],'unknown');self.assertNotIn('last_complete_scan',source)
    def test_corrupt_state_and_failed_write_never_replace_good_receipt(self):
        self.load();before=(self.s/'material_coverage.json').read_bytes()
        with patch('material_coverage.os.replace',side_effect=OSError('disk')):
            with self.assertRaises(OSError): coverage.record_scan(self.s,'phone',dict(status='unavailable',checked_at='2026-09-07',scope='specified range',receipt='adb'))
        self.assertEqual((self.s/'material_coverage.json').read_bytes(),before)
        (self.s/'material_coverage.json').write_text('{}')
        with self.assertRaises(ValueError): self.load()
    def test_unindexed_or_unsafe_sources_never_become_available(self):
        self.idx['assets']['escape']={'path':'../private.txt','readable':True}
        self.idx['recordings'][0]['sources']=['escape','unknown'];self.save()
        p=self.load()['recordings'][0]['pipeline'];self.assertFalse(p['acquired']);self.assertEqual(p['missing_asset_ids'],['escape','unknown'])
    def test_broken_item_cannot_establish_new_classification_baseline(self):
        self.load(); state=coverage.read(self.s); state['items']['r1']={};coverage.write(self.s,state)
        (self.k/'raw/transcripts/a.txt').write_text('来源已更新')
        with self.assertRaises(ValueError): self.load()
    def test_transcript_does_not_mean_original_audio_exists(self):
        p=self.load()['recordings'][0]['pipeline'];self.assertTrue(p['acquired']);self.assertFalse(p['original_available'])
    def test_supporting_note_does_not_replace_missing_original_attachment(self):
        original=self.k/'raw/quote.xlsx'
        self.idx['assets']['quote']={'path':'raw/quote.xlsx','kind':'document'}
        self.idx['files']=[{'id':'f1','title':'quote.xlsx','archive_paths':[str(original)],'sources':['a','quote']}]
        self.save()
        p=self.load()['files'][0]['pipeline']
        self.assertTrue(p['acquired']);self.assertFalse(p['original_available'])
        self.assertEqual(p['missing_asset_ids'],['quote'])
        original.write_bytes(b'restored original')
        p=self.load()['files'][0]['pipeline']
        self.assertTrue(p['original_available']);self.assertEqual(p['missing_asset_ids'],[])
        self.assertTrue(p['stale']);self.assertFalse(p['classified'])
    def test_empty_or_external_archive_does_not_promote_supporting_note(self):
        for paths in ([], ['/elsewhere/raw/transcripts/a.txt'], ['../raw/transcripts/a.txt']):
            self.idx['files']=[{'id':'f2','title':'a.txt','archive_paths':paths,'sources':['a']}]
            self.save();self.assertFalse(self.load()['files'][0]['pipeline']['original_available'])
    def test_legacy_original_requires_matching_filename(self):
        self.idx['files']=[{'id':'f3','title':'quote.xlsx','sources':['a']}]
        self.save();self.assertFalse(self.load()['files'][0]['pipeline']['original_available'])
        self.idx['files'][0]['title']='a.txt'
        self.save();self.assertTrue(self.load()['files'][0]['pipeline']['original_available'])
    def test_scope_change_does_not_inherit_complete_scan(self):
        record=dict(status='ok',checked_at='2026-09-07',scope='A',receipt='scan A',complete_scope=True)
        coverage.record_scan(self.s,'desktop',record)
        coverage.record_scan(self.s,'desktop',{**record,'status':'partial','scope':'B','complete_scope':False})
        self.assertNotIn('last_complete_scan',coverage.read(self.s)['channels']['desktop'])
    def test_retry_after_failed_commit_keeps_both_scan_attempts(self):
        self.load();record=dict(status='partial',checked_at='2026-09-07',scope='A',receipt='first')
        with patch('material_coverage.os.replace',side_effect=OSError('disk')):
            with self.assertRaises(OSError):coverage.record_scan(self.s,'desktop',record)
        coverage.record_scan(self.s,'desktop',{**record,'receipt':'second'})
        attempts=[json.loads(p.read_text())['receipt'] for p in (self.s/'material_scan_history').glob('*.json')]
        self.assertEqual(sorted(attempts),['first','second'])
