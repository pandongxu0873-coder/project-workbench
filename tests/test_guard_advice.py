import unittest,copy
import project_analysis as ai
class GuardAdviceTests(unittest.TestCase):
 def test_pause_and_no_contact_preserve_advice_without_releasing_action(self):
  for local in [{'status':'暂停跟进'},{'relationship':'no_contact'}]:
   value={'next_action':'让售前先核对已收规划','draft':'对外消息','role':'售前',
    'brief':{'attention':'可推进'},'understanding':{'interventions':[{'action':'先恢复已有审阅结论，再补必要初评','owner':'售前','success_signal':'取得内部初评'}],
      'scope_comparisons':[{'recommendation':'根据规划核对旧范围，不追加开发'}]}}
   before=copy.deepcopy(value);result=ai.guarded(value,local)
   self.assertEqual(result['draft'],'');self.assertEqual(result['brief']['attention'],'暂缓')
   self.assertEqual(result['understanding']['interventions'][0]['prior_advice'],value['understanding']['interventions'][0]['action'])
   self.assertIn('仅内部复核',result['understanding']['interventions'][0]['action'])
   self.assertEqual(result['understanding']['scope_comparisons'][0]['prior_advice'],value['understanding']['scope_comparisons'][0]['recommendation'])
   self.assertEqual(value,before)

   repeated=ai.guarded(result,local)
   self.assertEqual(repeated['understanding']['interventions'][0]['prior_advice'],value['understanding']['interventions'][0]['action'])
   self.assertEqual(repeated['understanding']['scope_comparisons'][0]['prior_advice'],value['understanding']['scope_comparisons'][0]['recommendation'])
