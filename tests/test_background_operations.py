import fcntl
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import background_operations as operations


class LiveOperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.folder=self.root/'communication_pipeline';self.folder.mkdir()
        self.saved={'jobs':{'communications':{'status':'partial','error':'旧缺口','next_epoch':99999999999,'recovery_attempts':2,'awaiting_result':False,'request_id':'scheduled-request','run_id':'scheduled-run','dispatched_at':'2026-09-20T00:39:04+08:00','last_attempt_at':'2026-09-20T01:24:32+08:00','last_success_at':'2026-09-19T20:00:00+08:00'},'crm':{'status':'ready','next_epoch':99999999999}}}
        self.write(self.root/'background_operations.json',self.saved)
        self.active={'state':'running','action':'retry','request_id':'retry-request','run_id':'retry-run','pid':os.getpid(),'started_at':'2026-09-20T01:39:23+08:00','phase':'analyzing','analysis_done':1,'analysis_total':4}
        self.write(self.folder/'active_run.json',self.active)
        self.lock=(self.folder/'pipeline.lock').open('wb');fcntl.flock(self.lock,fcntl.LOCK_EX)

    def tearDown(self):
        self.lock.close();self.tmp.cleanup()

    def write(self,path,value):path.write_text(json.dumps(value,ensure_ascii=False))

    def files(self):return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_live_retry_is_visible_before_schedule_without_changing_accounting(self):
        before=self.files();job=operations.read_status(self.root)['jobs']['communications']
        self.assertEqual(job['status'],'running');self.assertEqual(job['current_started_at'],self.active['started_at']);self.assertEqual(job['live_run_id'],'retry-run')
        self.assertEqual(job['analysis_done'],1);self.assertEqual(job['error'],'')
        for key in ('request_id','run_id','next_epoch','recovery_attempts','awaiting_result','last_attempt_at','last_success_at'):
            self.assertEqual(job[key],self.saved['jobs']['communications'][key])
        self.assertEqual(self.files(),before)
        crm=Mock();communications=Mock()
        operations.run_once(self.root,self.root,clock=lambda:1000,communications=communications)
        crm.status.assert_not_called();communications.status.assert_not_called();communications.start.assert_not_called()
        self.assertEqual(self.files(),before)

    def test_scheduler_record_does_not_persist_live_projection(self):
        operations.record(self.root,'crm',error='test')
        saved=json.loads((self.root/'background_operations.json').read_text())
        self.assertEqual(saved['jobs']['communications'],self.saved['jobs']['communications'])
        self.assertNotIn('live_run_id',saved['jobs']['communications'])

    def test_dead_pid_or_released_lock_never_claims_running(self):
        with patch.object(operations.os,'kill',side_effect=ProcessLookupError):
            self.assertEqual(operations.read_status(self.root)['jobs']['communications']['status'],'needs_input')
        fcntl.flock(self.lock,fcntl.LOCK_UN)
        self.assertEqual(operations.read_status(self.root)['jobs']['communications']['status'],'needs_input')

    def test_latest_terminal_receipt_wins_over_stale_running_state(self):
        latest={'run_id':'newer-import','status':'completed','checked_at':'2026-09-20T01:45:00+08:00','unresolved':{},'refresh_pending':[],'gaps':[]}
        self.write(self.folder/'latest.json',latest);before=self.files()
        job=operations.read_status(self.root)['jobs']['communications']
        self.assertEqual(job['status'],'ready');self.assertEqual(job['current_finished_at'],latest['checked_at']);self.assertEqual(job['live_run_id'],'newer-import')
        self.assertEqual(job['last_success_at'],self.saved['jobs']['communications']['last_success_at'])
        self.assertEqual(self.files(),before)

    def test_completed_label_with_unresolved_material_is_still_partial(self):
        self.write(self.folder/'latest.json',{'run_id':'retry-run','status':'completed','checked_at':'2026-09-20T01:45:00+08:00','unresolved':{'extraction_pending':2}})
        job=operations.read_status(self.root)['jobs']['communications']
        self.assertEqual(job['status'],'partial');self.assertIn('部分材料',job['error'])

    def test_foreign_embedded_receipt_and_missing_run_identity_are_not_trusted(self):
        active={**self.active,'receipt':{'run_id':'foreign-run','status':'completed','checked_at':'2026-09-20T01:45:00+08:00'}}
        self.write(self.folder/'active_run.json',active)
        self.assertEqual(operations.read_status(self.root)['jobs']['communications']['status'],'running')
        active.pop('run_id');self.write(self.folder/'active_run.json',active)
        self.assertEqual(operations.read_status(self.root)['jobs']['communications'],self.saved['jobs']['communications'])

    def test_older_runtime_files_do_not_replace_newer_saved_completion(self):
        saved=self.saved['jobs']['communications'];saved.update(status='ready',last_success_at='2026-09-20T02:00:00+08:00')
        self.write(self.root/'background_operations.json',self.saved)
        self.write(self.folder/'latest.json',{'run_id':'old-run','status':'partial','checked_at':'2026-09-20T01:45:00+08:00'})
        self.assertEqual(operations.read_status(self.root)['jobs']['communications'],saved)


if __name__=='__main__':unittest.main()
