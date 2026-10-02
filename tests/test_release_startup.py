import json,tempfile,unittest,threading
from pathlib import Path
from release_startup import grace_seconds,start_worker
class ReleaseStartupTests(unittest.TestCase):
 def test_finite_expiring_grace(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);self.assertEqual(grace_seconds(r,100),0)
   f=r/'release_startup_grace.json';f.write_text(json.dumps({'resume_at':200}))
   self.assertEqual(grace_seconds(r,100),100);self.assertEqual(grace_seconds(r,201),0)
   self.assertEqual(grace_seconds(r,-1000),300)
   f.write_text('bad');self.assertEqual(grace_seconds(r,100),0)
 def test_wait_and_stop_do_not_run_jobs(self):
  stop=threading.Event();ran=threading.Event();t=start_worker(ran.set,(),stop,30)
  self.assertFalse(ran.is_set());stop.set();t.join(1);self.assertFalse(ran.is_set())
 def test_expired_grace_preserves_normal_start(self):
  ran=threading.Event();t=start_worker(ran.set,(),threading.Event(),0);t.join(1);self.assertTrue(ran.is_set())
