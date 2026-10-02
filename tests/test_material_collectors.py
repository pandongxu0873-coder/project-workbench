import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import material_collectors as collectors
import material_coverage as coverage
class DesktopCollectorTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.desktop=self.root/'desktop';self.desktop.mkdir();self.s=self.root/'state';self.s.mkdir();(self.desktop/'客户').mkdir();self.doc=self.desktop/'客户/范围.txt';self.doc.write_text('原范围');self.config={'desktop_root':str(self.desktop),'directories':['客户'],'files':{'客户/范围.txt':hashlib.sha256(self.doc.read_bytes()).hexdigest()},'scope':'隔离客户目录及根目录散落文件'}
 def test_background_inventory_uses_authorized_interpreter_without_shell(self):
  from types import SimpleNamespace
  (self.s/'material_collectors.json').write_text(json.dumps(self.config))
  thread=lambda target,**kw:SimpleNamespace(start=target)
  with patch.object(collectors.threading,'Thread',side_effect=thread),patch.object(collectors.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
   collectors.start_due(self.s)
  self.assertTrue(run.call_args.args[0][0].endswith('/tools/.communication-venv/bin/python'))
  self.assertNotIn('shell',run.call_args.kwargs);self.assertEqual(run.call_args.kwargs['timeout'],120)
 def test_delta_keeps_pending_until_processed_and_unchanged_files_use_cache(self):
  r=collectors.scan_desktop(self.s,self.config);self.assertEqual((r['new_count'],r['changed_count']),(0,0))
  with patch('material_collectors.fingerprint',side_effect=AssertionError('unchanged file rehashed')):collectors.scan_desktop(self.s,self.config)
  self.doc.write_text('新范围');(self.desktop/'新需求.txt').write_text('新材料')
  for _ in range(2):
   r=collectors.scan_desktop(self.s,self.config);self.assertEqual((r['new_count'],r['changed_count']),(1,1));self.assertEqual(r['status'],'ok')
  self.assertIn('仍需提取',r['note'])
 def test_missing_directory_fails_without_erasing_previous_receipt(self):
  before=collectors.scan_desktop(self.s,self.config);self.doc.unlink();(self.desktop/'客户').rmdir()
  with self.assertRaises(OSError):collectors.scan_desktop(self.s,self.config)
  self.assertEqual(coverage.read(self.s)['channels']['desktop']['checked_at'],before['checked_at'])
 def test_secret_and_symlink_are_not_read_or_misreported_as_missing(self):
  (self.desktop/'secret.txt').write_text('secret');self.config['files']['secret.txt']='unknown';(self.desktop/'linked.txt').symlink_to(self.doc)
  r=collectors.scan_desktop(self.s,self.config);self.assertEqual(r['observed'],1);self.assertEqual(r['failed_files'],[]);self.assertEqual(r['excluded'],1)
 def test_failed_file_is_retried_without_losing_old_success_boundary(self):
  collectors.scan_desktop(self.s,self.config);self.doc.write_text('变化')
  with patch('material_collectors.fingerprint',side_effect=OSError('read failed')):
   r=collectors.scan_desktop(self.s,self.config)
  self.assertEqual(r['status'],'partial');self.assertTrue(coverage.read(self.s)['channels']['desktop'].get('last_complete_scan'))
  r=collectors.scan_desktop(self.s,self.config);self.assertEqual(r['status'],'ok');self.assertEqual(r['changed_count'],1)

 def test_nested_directory_error_is_partial(self):
  def broken(directory, followlinks, onerror):
   onerror(PermissionError(13,'denied',str(self.desktop/'客户/新目录')))
   return iter([])
  with patch('material_collectors.os.walk',side_effect=broken):r=collectors.scan_desktop(self.s,self.config)
  self.assertEqual(r['status'],'partial');self.assertFalse(r['complete_scope']);self.assertTrue(any(x['title']=='客户/新目录' for x in r['failed_files']))

 def test_concurrent_collectors_preserve_snapshot_and_receipts(self):
  from concurrent.futures import ThreadPoolExecutor
  import time
  original=collectors.fingerprint
  def slow(path):time.sleep(.03);return original(path)
  with patch('material_collectors.fingerprint',side_effect=slow),ThreadPoolExecutor(max_workers=4) as pool:
   rows=list(pool.map(lambda _:collectors.scan_desktop(self.s,self.config),range(4)))
  self.assertTrue(all(r['status']=='ok' and r['observed']==1 for r in rows))
  snapshot=json.loads((self.s/'desktop_scan_snapshot.json').read_text())
  self.assertEqual(snapshot['files']['客户/范围.txt']['sha256'],self.config['files']['客户/范围.txt'])
