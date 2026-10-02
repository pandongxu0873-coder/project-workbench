import copy,unittest
import project_analysis as ai
class CRMRefreshFingerprint(unittest.TestCase):
 def test_read_time_only_is_not_business_change(self):
  before=[{'path':'local://crm-project-records','relation':'crm_snapshot','recorded_at':'18:00','content':'尚未确认','date':''}]
  after=copy.deepcopy(before);after[0]['recorded_at']='18:31'
  self.assertEqual(ai.prepared_fingerprint(before),ai.prepared_fingerprint(after))
  self.assertEqual(before[0]['recorded_at'],'18:00')
  for key,value in [('content','已确认'),('date','2026-09-20'),('relation','customer_statement')]:
   changed=copy.deepcopy(after);changed[0][key]=value
   self.assertNotEqual(ai.prepared_fingerprint(before),ai.prepared_fingerprint(changed))
 def test_local_work_and_other_source_record_times_remain_significant(self):
  for path,relation in [('local://round','local'),('local://other-record','crm_snapshot')]:
   before=[{'path':path,'relation':relation,'recorded_at':'18:00','content':'反馈'}]
   after=copy.deepcopy(before);after[0]['recorded_at']='18:31'
   self.assertNotEqual(ai.prepared_fingerprint(before),ai.prepared_fingerprint(after))
if __name__=='__main__':unittest.main()
