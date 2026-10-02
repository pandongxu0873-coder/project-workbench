import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
import workbench_agent as a

class AgentTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.state=Path(self.temp.name)/'state';self.root=Path(self.temp.name)/'knowledge';self.root.mkdir();self.cid='a'*32;a.ACTIVE.clear()
 def tearDown(self):a.ACTIVE.clear();self.temp.cleanup()
 def value(self,status='idle'):
  v={'id':self.cid,'title':'合同核对','created_at':a.now(),'updated_at':a.now(),'status':status,'archived':False,'phase':'','messages':[]};a.write(self.state,v);return v
 def test_draft_input_survives_process_reload(self):
  a.save_input(self.state,self.cid,'未发出的客户问题');self.assertEqual(a.read(self.state,self.cid)['input'],'未发出的客户问题')
 def test_submission_retry_does_not_duplicate_or_spawn(self):
  self.value()
  with patch('workbench_agent.threading.Thread') as thread:
   v=a.submit(self.state,self.root,self.cid,'找合同','request-123');other=a.submit(self.state,self.root,self.cid,'找合同','request-123')
  self.assertEqual(len(other['messages']),1);self.assertEqual(thread.call_count,1);self.assertEqual(v['input'],'')
 def test_creation_retry_reuses_original_id(self):
  with patch('workbench_agent.threading.Thread') as thread:
   v=a.submit(self.state,self.root,None,'找合同','request-create-123');other=a.submit(self.state,self.root,None,'找合同','request-create-123')
  self.assertEqual(v['id'],other['id']);self.assertEqual(thread.call_count,1)
 def test_changed_retry_content_rejected(self):
  self.value()
  with patch('workbench_agent.threading.Thread'):
   a.submit(self.state,self.root,self.cid,'找合同','request-123')
   with self.assertRaises(ValueError):a.submit(self.state,self.root,self.cid,'改合同','request-123')
 def test_restart_marks_interruption_never_reruns(self):
  self.value('running')
  with patch('workbench_agent.subprocess.Popen') as process:
   self.assertEqual(a.read(self.state,self.cid)['status'],'interrupted');process.assert_not_called()
 def test_cancel_preserves_messages(self):
  v=self.value('running');v['messages']=[{'id':'u','role':'user','content':'问题'}];a.write(self.state,v);a.ACTIVE.add(self.cid)
  v=a.cancel(self.state,self.cid);self.assertEqual(v['status'],'cancelled');self.assertEqual(v['messages'][0]['content'],'问题')
 def test_archive_does_not_change_business_or_drafts(self):
  self.value();business=self.state/'risk_todos.json';business.write_text('{"status":"待客户反馈"}');before=business.read_bytes()
  a.archive(self.state,self.cid,True);self.assertEqual(business.read_bytes(),before);self.assertTrue(a.read(self.state,self.cid)['archived']);a.archive(self.state,self.cid,False);self.assertFalse(a.read(self.state,self.cid)['archived'])
 def test_running_archive_rejected(self):
  self.value('running');a.ACTIVE.add(self.cid)
  with self.assertRaises(ValueError):a.archive(self.state,self.cid,True)
 def test_source_symlink_escape_rejected(self):
  outside=Path(self.temp.name)/'outside.txt';outside.write_text('private');(self.root/'link.txt').symlink_to(outside)
  with self.assertRaises(ValueError):a.source_path(self.root,self.state,str(self.root/'link.txt'))
 def test_traversal_identifier_rejected(self):
  with self.assertRaises(ValueError):a.read(self.state,'../../outside')
 def test_save_draft_idempotent_and_read_back(self):
  v=self.value();v['messages']=[{'id':'answer-1','role':'assistant','content':'内部提纲','sources':[]}];a.write(self.state,v)
  r=a.draft(self.state,self.cid,'answer-1');before=Path(r['path']).stat().st_mtime_ns;r2=a.draft(self.state,self.cid,'answer-1');self.assertEqual(r,r2);self.assertEqual(Path(r['path']).stat().st_mtime_ns,before);self.assertIn('未确认、未发送',Path(r['path']).read_text())
 def test_old_input_cannot_overwrite_new_revision(self):
  a.save_input(self.state,self.cid,'新输入',0)
  with self.assertRaises(ValueError):a.save_input(self.state,self.cid,'旧输入',0)
  self.assertEqual(a.read(self.state,self.cid)['input'],'新输入')
 def test_cancelled_process_must_exit_before_same_chat_resubmit(self):
  self.value('cancelled');a.ACTIVE.add(self.cid)
  with self.assertRaises(ValueError):a.submit(self.state,self.root,self.cid,'新问题','request-new-123')
 def test_send_invalidates_delayed_input_save(self):
  a.save_input(self.state,self.cid,'发送的问题',0)
  with patch('workbench_agent.threading.Thread'):a.submit(self.state,self.root,self.cid,'发送的问题','request-send-123')
  with self.assertRaises(ValueError):a.save_input(self.state,self.cid,'旧文本',1)
  self.assertEqual(a.read(self.state,self.cid)['input'],'')
 def test_deferred_suggestion_persists_without_changing_deadlines(self):
  self.state.mkdir(parents=True);deadline=self.state/'risk_todos.json';deadline.write_text('original')
  a.preferences(self.state,'action-1',True)
  self.assertEqual(a.preferences(self.state)['deferred'],['action-1']);self.assertEqual(deadline.read_text(),'original')
  self.assertEqual(a.preferences(self.state,'action-1',False)['deferred'],[])
 def test_history_search_includes_archived_content(self):
  v=self.value();v['messages']=[{'role':'user','content':'星海汽车报价版本'}];a.write(self.state,v);a.archive(self.state,self.cid,True);self.assertEqual(a.listing(self.state,'星海汽车')[0]['id'],self.cid)
