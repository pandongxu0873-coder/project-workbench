import unittest
from project_local_history import historical_sources
class History(unittest.TestCase):
 def test_more_than_six_rounds_preserve_changes_even_when_feedback_repeated(self):
  history=[{'revision':i,'record':{'feedback':'同一反馈','action':f'动作{i}','due':f'2026-09-{i:02d}','saved_at':f'2026-09-{i:02d}T10:00:00+08:00'}} for i in range(1,10)]
  rows=historical_sources({'revision':9,'history':history},[],lambda *_:'')
  self.assertEqual(len(rows),8)
  self.assertEqual(rows[0]['path'],'local://round/history/1')
  self.assertIn('动作1',rows[0]['content']);self.assertIn('2026-09-01',rows[0]['content'])
  self.assertEqual(rows[0]['date'],'');self.assertTrue(rows[0]['recorded_at'])
 def test_early_correction_and_repeated_values_keep_their_versions(self):
  corrections=[{'revision':i,'text':'最早范围' if i in (1,7) else f'变更{i}','date':f'2026-09-{i:02d}'} for i in range(1,10)]
  rows=historical_sources({'revision':0,'history':[]},corrections,lambda *_:'')
  self.assertEqual(len(rows),8);self.assertEqual(rows[0]['content'],'最早范围');self.assertEqual(rows[6]['content'],'最早范围')
 def test_current_only_does_not_change_inputs(self):
  self.assertEqual(historical_sources({'revision':1,'history':[{'revision':1,'record':{}}]},[],lambda *_:''),[])
if __name__=='__main__':unittest.main()
