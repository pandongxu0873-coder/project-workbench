import tempfile, unittest
from pathlib import Path
from calendar_project_links import link_project_calendar_items

class CalendarProjectLinksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); (self.root/'raw').mkdir()
        (self.root/'raw/event.md').write_text('- 事件 ID：event-1_0\n')
        self.project = {'id':'project-1', 'customer':'示例餐饮', 'title':'商城POC', 'source_path':'projects/商城.md',
                        'sources':[{'path':'raw/event.md','relation':'explicit_evidence','readable':True}]}
        self.item = {'source_type':'feishu_calendar','calendar':{'event_id':'event-1_0'},'customer':'待匹配日程', 'matched_customer':False, 'account_id':''}
    def test_exact_citation_links_without_mutating_original_or_formal_account(self):
        linked = link_project_calendar_items([self.item],[self.project],self.root)[0]
        self.assertEqual(linked['customer'],'示例餐饮'); self.assertEqual(linked['project_id'],'project-1')
        self.assertEqual(linked['account_id'],''); self.assertFalse(self.item['matched_customer'])
    def test_ambiguous_project_or_existing_customer_disagreement_stays_unchanged(self):
        other = dict(self.project,id='project-2')
        self.assertEqual(link_project_calendar_items([self.item],[self.project,other],self.root),[self.item])
        existing = dict(self.item,customer='其他客户',matched_customer=True)
        self.assertEqual(link_project_calendar_items([existing],[self.project],self.root),[existing])
    def test_missing_background_wrong_id_or_non_calendar_never_links(self):
        for source in [dict(self.project['sources'][0],path='raw/missing.md'),dict(self.project['sources'][0],relation='background_reference')]:
            self.assertEqual(link_project_calendar_items([self.item],[dict(self.project,sources=[source])],self.root),[self.item])
        for item in [dict(self.item,calendar={'event_id':'event-1'}),dict(self.item,source_type='manual')]:
            self.assertEqual(link_project_calendar_items([item],[self.project],self.root),[item])

if __name__ == '__main__': unittest.main()
