import unittest
import project_history_synthesis as h
class Dates(unittest.TestCase):
 def dates(self,text):
  ledger=h.evidence_ledger([{'path':'project.md','content':text,'date':'2026-09-20'}])
  return next(iter(ledger['references'].values()))['supported_dates']
 def test_chinese_adjacent(self):
  self.assertEqual(self.dates('于2026-09-04已现场沟通；2026-09-05再次确认。'),['2026-09-04','2026-09-05','2026-09-20'])
 def test_partial_numeric_identifier_not_a_date(self):
  self.assertEqual(self.dates('编号12026-09-041，仅在2026-09-06沟通。'),['2026-09-06','2026-09-20'])
if __name__=='__main__':unittest.main()
