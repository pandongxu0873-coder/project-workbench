import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import legacy_crm_snapshot as legacy
import background_operations as ops
import k100_sync as sync
import project_analysis as ai
import test_execution_v2 as fixture_module

class RetirementTests(unittest.TestCase):
 def test_snapshot_is_read_only_and_never_reads_keychain_or_network(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'ka_sales_snapshot.json';p.write_text(json.dumps({'resources':{'orders':{'data':{'list':[{'id':'old'}]}}}}));before=p.read_bytes()
   with patch('urllib.request.urlopen',side_effect=AssertionError('network')),patch.object(sync,'keychain',side_effect=AssertionError('credential')):
    result=legacy.status(root)
   self.assertTrue(result['retired']);self.assertEqual(p.read_bytes(),before);self.assertFalse(result['configured'])
 def test_retired_schedule_is_not_run_or_advertised(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);ops.record(root,'crm',status='running',next_epoch=0);ops.record(root,'communications',next_epoch=99999999999)
   with patch('urllib.request.urlopen',side_effect=AssertionError('network')):
    ops.run_once(root,root,communications=Mock())
   self.assertNotIn('crm',ops.INTERVALS);self.assertNotIn('crm',ops.read_status(root)['jobs'])
 def test_transport_deleted_k100_has_independent_bindings(self):
  root=Path(__file__).resolve().parents[1]
  self.assertFalse((root/'crm_adapter.py').exists());self.assertNotIn('crm_adapter', (root/'k100_sync.py').read_text())

class WorkbenchSyncTests(unittest.TestCase):
 def setUp(self):
  self.f=fixture_module.IncrementalV2Tests();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.body={'project_id':self.f.p,'request_id':'qa-progress-record-00001','text':'合成记录：一期范围已提交，等待客户核对。'}
 def link(self):
  with sync.locked(self.f.s) as folder:
   state=sync.read_state(folder);state['links'][self.f.p]={'user_id':'qa-user','enabled':True,'customer_id':'qa','customer_name':'合成'};sync.write_state(folder,state)
 def test_body_only_is_one_original_one_outbox_and_defaults_non_effective(self):
  self.link()
  with patch.object(sync,'target',return_value=('qa-user',{'id':'qa','legalName':'合成'})),patch.object(sync,'request',return_value={}) as send,patch.object(sync,'audit_records',return_value=[]),patch.object(ai,'run_model',side_effect=AssertionError('model')):
   a=sync.save_workbench_progress(self.body,self.f.k,self.f.s);b=sync.save_workbench_progress(self.body,self.f.k,self.f.s)
   self.assertEqual(send.call_count,1);self.assertEqual(a['record_id'],b['record_id']);self.assertEqual(len(ai.progress_records(self.f.p,self.f.k,self.f.s)['items']),1)
  with sync.locked(self.f.s) as folder:
   events=sync.read_state(folder)['events'];self.assertEqual(len(events),1);self.assertEqual(next(iter(events.values()))['type'],'GENERAL_NOTE')
 def test_unlinked_local_save_retained_and_recoverable_after_link(self):
  result=sync.save_workbench_progress(self.body,self.f.k,self.f.s);self.assertEqual(result['k100']['state'],'needs_link');self.link()
  with patch.object(sync,'target',return_value=('qa-user',{'id':'qa','legalName':'合成'})),patch.object(sync,'request',return_value={}) as send,patch.object(sync,'audit_records',return_value=[]):
   sync.recover_progress(self.f.s,{'project_id':self.f.p,'record_id':self.body['request_id']},self.f.k);self.assertEqual(send.call_count,1)
 def test_changed_metadata_same_id_rejected_and_failure_retains_original(self):
  with patch.object(sync,'progress',side_effect=RuntimeError('offline')):
   result=sync.save_workbench_progress(self.body,self.f.k,self.f.s)
  self.assertEqual(result['k100']['state'],'failed');self.assertEqual(ai.progress_records(self.f.p,self.f.k,self.f.s)['items'][0]['text'],self.body['text'])
  with self.assertRaises(ValueError):sync.save_workbench_progress({**self.body,'k100':{'type':'WECHAT','occurredAt':'2026-01-01T00:00:00Z'}},self.f.k,self.f.s)
 def test_recovery_rejects_path_and_archive(self):
  with self.assertRaises(sync.SyncError):sync.recover_progress(self.f.s,{'project_id':'../bad','record_id':'x'},self.f.k)
  sync.save_workbench_progress(self.body,self.f.k,self.f.s)
  with patch('project_archive.state',return_value={'archived':True}),patch.object(sync,'progress') as send:
   with self.assertRaises(sync.SyncError):sync.recover_progress(self.f.s,{'project_id':self.f.p,'record_id':self.body['request_id']},self.f.k)
   send.assert_not_called()
