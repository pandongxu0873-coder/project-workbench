import copy, unittest
from project_analysis import guarded
class OutcomeTest(unittest.TestCase):
 def setUp(self):
  self.a={'next_action':'再次确认老板目标','draft':'联系话术','brief':{'attention':'可推进','next_action':'再次确认'},'story':{'conversation':{}},'understanding':{'evolution':[{'title':'历史事实'}],'interventions':[{'action':'制作小样'}],'scope_comparisons':[{'recommendation':'有限投入'}]}}
 def test_done_does_not_prove_customer_silence(self):
  before=copy.deepcopy(self.a)
  r=guarded(self.a,{'status':'本轮完成'},'done_waiting')
  self.assertEqual(r['brief']['attention'],'需核实')
  self.assertIn('不等于客户未回复',r['next_action'])
  self.assertEqual(r['draft'],'')
  self.assertEqual(self.a,before)
  self.assertEqual(r['understanding']['evolution'],before['understanding']['evolution'])
 def test_actual_wait_remains_wait(self):
  r=guarded(self.a,{'status':'已发出等待反馈'},'done_waiting')
  self.assertEqual(r['brief']['attention'],'等反馈')
 def test_no_contact_and_pause_are_not_reopened(self):
  for local in ({'relationship':'no_contact'},{'status':'暂停跟进'}):
   r=guarded(self.a,local,'done_waiting')
   self.assertEqual(r['brief']['attention'],'暂缓')
   self.assertEqual(r['draft'],'')
 def test_wait_does_not_erase_another_obligation(self):
  before=copy.deepcopy(self.a)
  self.a['understanding']['interventions'][0].update(action='补齐已承诺的盖章收费说明',owner='商务经办',success_signal='客户经办已取得适用说明')
  r=guarded(self.a,{'status':'已发出等待反馈'},'done_waiting')
  self.assertIn('不自动暂停其他原有责任',r['guard'])
  row=r['understanding']['interventions'][0]
  self.assertIn('补齐已承诺的盖章收费说明',row['action'])
  self.assertEqual(row['owner'],'商务经办')
  self.assertIn('不代表其他责任的共同前置',row['success_signal'])
  self.assertEqual(r['draft'],'')
  restricted=guarded(self.a,{'relationship':'no_contact'},'done_waiting')
  self.assertNotIn('本项原建议',restricted['understanding']['interventions'][0]['action'])
  self.assertEqual(r['understanding']['evolution'],before['understanding']['evolution'])
 def test_new_evidence_is_not_external_wait(self):
  r=guarded(self.a,{},'new_evidence_review')
  self.assertEqual(r['brief']['attention'],'需核实')
if __name__=='__main__':unittest.main()
