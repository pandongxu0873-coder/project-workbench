"""Exact-content reuse must not hide new evidence or share mutable state."""
import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import project_analysis as ai
import project_source_context as sources
import project_rounds as rounds
import server

class ReadReuseTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.pid='a'*20
  (self.root/'raw/assets').mkdir(parents=True);(self.root/'projects').mkdir()
  ai._validated_cache.cache_clear()
 def test_current_bytes_and_caller_isolation(self):
  ai.write_cache(self.root,self.pid,{'project_id':self.pid,'correction':'first','result':None})
  p=ai.cache_path(self.root,self.pid);stamp=p.stat()
  a=ai.read_cache(self.root,self.pid);a['correction_history'].append({'bad':'mutated'})
  self.assertEqual(ai.read_cache(self.root,self.pid)['correction_history'],[])
  self.assertGreater(ai._validated_cache.cache_info().hits,0)
  p.write_text(p.read_text().replace('first','other'));os.utime(p,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
  self.assertEqual(ai.read_cache(self.root,self.pid)['correction'],'other')
  p.write_text('{broken')
  with self.assertRaises(ValueError):ai.read_cache(self.root,self.pid)
  ai.write_cache(self.root,self.pid,{'project_id':'b'*20,'correction':'other','result':None})
  with self.assertRaises(ValueError):ai.read_cache(self.root,self.pid)
 def test_new_duplicate_attachment_seen_on_next_request(self):
  (self.root/'raw/assets/报价.xlsx').write_bytes(b'one')
  main=self.root/'projects/main.md';main.write_text('附件：报价.xlsx')
  p={'customer':'甲','sources':[{'path':'projects/main.md','exists':True,'readable':True}]}
  snap=sources.discovery_snapshot(self.root)
  self.assertTrue(any(s['path']=='raw/assets/报价.xlsx' for s in sources.supplement_sources(p,self.root,discovery=snap)))
  (self.root/'raw/assets/other').mkdir();(self.root/'raw/assets/other/报价.xlsx').write_bytes(b'two')
  self.assertFalse(any(s['path'].endswith('报价.xlsx') for s in sources.supplement_sources(p,self.root)))
 def test_followups_reuses_supplied_empty_snapshot(self):
  with patch.object(rounds,'build_projects',side_effect=AssertionError('extra scan')):
   self.assertEqual(rounds.followups(self.root,self.root,projects=[])['items'],[])
 def test_calendar_reuses_snapshot_and_rounds_without_scan(self):
  with patch.object(server,'build_projects',side_effect=AssertionError('extra scan')),patch.object(server.project_rounds,'followups',side_effect=AssertionError('extra rounds')),patch.object(server,'fetch_feishu_calendar_instances',return_value={'ok':True,'items':[]}),patch.object(server,'load_risk_todos',return_value=[]),patch.object(server,'load_workflow_state',return_value={}),patch.object(server,'WORKBENCH_DATA_ROOT',self.root):
   value=server.calendar_schedule_payload([],[],projects=[],rounds={'claimed_actions':{}})
  self.assertEqual(value['items'],[])

if __name__=='__main__':unittest.main()


class DisconnectedResponseTests(unittest.TestCase):
    def test_disconnected_browser_does_not_trigger_second_response(self):
        from unittest.mock import Mock
        handler = Mock()
        handler.wfile.write.side_effect = BrokenPipeError()
        server.WorkbenchHandler._send_json(handler, {'saved': True})
        self.assertTrue(handler.close_connection)
        self.assertEqual(handler.send_response.call_count, 1)

    def test_unrelated_write_error_is_not_hidden(self):
        from unittest.mock import Mock
        handler = Mock()
        handler.wfile.write.side_effect = OSError('unrelated disk failure')
        with self.assertRaises(OSError):
            server.WorkbenchHandler._send_json(handler, {'saved': True})
