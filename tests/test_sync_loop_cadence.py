import unittest
from unittest.mock import patch
import project_analysis as ai

class SyncCadenceTests(unittest.TestCase):
    def run_loop(self, error=None):
        class ClockStop:
            now=0
            def is_set(self): return self.now>315
            def wait(self,seconds): self.now+=seconds
        clock=ClockStop();scans=[];requests=[]
        def scan(*args):
            scans.append(clock.now)
            if error: raise error
        with patch.object(ai.time,'monotonic',side_effect=lambda:clock.now), patch.object(ai,'sync_once',side_effect=scan), patch.object(ai,'dispatch_pending',side_effect=lambda *a:requests.append(clock.now)):
            ai.sync_loop(None,None,clock)
        return scans,requests
    def test_full_scan_throttled_but_manual_requests_still_dispatch(self):
        scans,requests=self.run_loop()
        self.assertEqual(scans,[0,300])
        self.assertIn(15,requests)
        self.assertIn(285,requests)
        self.assertIn(315,requests)
    def test_scan_failure_does_not_create_busy_retry_loop(self):
        scans,requests=self.run_loop(OSError('transient'))
        self.assertEqual(scans,[0,300])
        self.assertIn(15,requests)
    def test_stopped_loop_does_no_work(self):
        import threading
        stop=threading.Event();stop.set()
        with patch.object(ai,'sync_once') as scan,patch.object(ai,'dispatch_pending') as dispatch:
            ai.sync_loop(None,None,stop)
            scan.assert_not_called();dispatch.assert_not_called()
    def test_material_index_failure_keeps_discovery_worker_alive(self):
        from material_library import MaterialError
        scans,requests=self.run_loop(MaterialError('资料索引暂不可用',503))
        self.assertEqual(scans,[0,300])
        self.assertIn(15,requests)
    def test_material_index_failure_keeps_dispatch_worker_alive(self):
        from material_library import MaterialError
        class Stop:
            calls=0
            def is_set(self):return self.calls>=3
            def wait(self,_):self.calls+=1
        with patch.object(ai,'sync_once'),patch.object(ai,'dispatch_pending',side_effect=MaterialError('索引暂不可用',503)) as dispatch:
            ai.sync_loop(None,None,Stop())
        self.assertEqual(dispatch.call_count,2)
