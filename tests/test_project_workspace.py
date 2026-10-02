import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_workspace import build_projects, save_plan, read_source
from unittest.mock import patch
from datetime import date
import project_workspace


class ProjectWorkspaceTest(unittest.TestCase):
    def test_date_cache_tracks_content_and_calendar_day(self):
        body='occurred_at: 2026-09-15\nreviewed_at: 2026-09-15'
        with patch('project_workspace.date',wraps=date) as calendar:
            calendar.today.return_value=date(2026,9,14)
            self.assertEqual(project_workspace.source_dates('',body),'')
            self.assertEqual(project_workspace.review_dates('',body),'')
            calendar.today.return_value=date(2026,9,15)
            self.assertEqual(project_workspace.source_dates('',body),'2026-09-15')
            self.assertEqual(project_workspace.review_dates('',body),'2026-09-15')
            self.assertEqual(project_workspace.source_dates('',body.replace('09-15','09-13')),'2026-09-13')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "projects").mkdir()
        self.state = self.root / "state"
        (self.root / "projects" / "示例酒品牌.md").write_text("---\nupdated: 2026-09-02\nsources:\n  - raw/transcripts/示例酒品牌.md\n---\n# 示例酒品牌会员小程序\n\n**客户**：[[示例酒品牌]]\n\n## 一句话判断\n会员权益需要先澄清。\n\n## 当前待办\n- [ ] 研发确认接口人天\n- [x] 已完成动作\n- [ ] 梳理迁移验收方案\n")

    def tearDown(self):
        self.temp.cleanup()

    def test_explicit_source_and_customer(self):
        project = build_projects(self.root, self.state)[0]
        self.assertEqual(project["customer"], "示例酒品牌")
        self.assertEqual(len(project["actions"]), 2)
        self.assertEqual(project["actions"][0]["suggested_role"], "技术 TO")
        self.assertEqual(project["actions"][1]["suggested_role"], "交付")
        self.assertFalse(project["sources"][1]["exists"])
        self.assertEqual(project["id"], build_projects(self.root, self.state)[0]["id"])

    def test_customer_short_link_and_related_link_require_known_unique_identity(self):
        (self.root/'tracking').mkdir()
        (self.root/'tracking/client_registry.md').write_text('| 客户 | 状态 |\n|---|---|\n| 松果宠物 | 跟进 |\n|| 示例汽车集团/星海汽车 | 合作 |\n')
        cases={
            'short':'# AI项目\n[[松果宠物]]客户项目。\n## 关联\n- [[业务平台]]',
            'related':'# 压测项目\n客户技术诉求。\n## 关联\n- [[entities/示例采购代表]]\n- [[entities/星海汽车商城]]\n- [[projects/另一个项目]]',
            'ambiguous':'# 联合项目\n客户项目。\n## 关联\n- [[松果宠物]]\n- [[entities/星海汽车商城]]',
            'title_only':'# 松果宠物项目\n客户主体待核。\n## 沟通\n[[松果宠物]]只是参考案例。',
            'person':'# 项目\n客户项目。\n## 关联\n- [[entities/示例采购代表]]',
            'wrong_alias':'# 历史项目\n[[松叶宠物（独立体系）]]客户项目。'}
        for name,body in cases.items():(self.root/'projects'/f'{name}.md').write_text(body)
        rows={Path(p['source_path']).stem:p for p in build_projects(self.root,self.state)}
        self.assertEqual(rows['short']['customer'],'松果宠物');self.assertEqual(rows['related']['customer'],'星海汽车商城')
        self.assertEqual(rows['related']['customer_link_evidence']['link'],'entities/星海汽车商城')
        for name in ('ambiguous','title_only','person','wrong_alias'):self.assertEqual(rows[name]['customer'],'客户关联待核实',name)

    def test_related_customer_edges_require_known_links_in_declared_relation_section(self):
        (self.root/'tracking').mkdir()
        (self.root/'tracking/client_registry.md').write_text('| 客户 | 状态 |\n|---|---|\n| 星海汽车商城 | 合作 |\n| 松果宠物 | 跟进 |\n')
        body='# 权益项目\n权益项目由[[entities/示例汽车集团汽车]]财经侧牵引。\n\n## 项目说明\n正文提及[[松果宠物]]，仅作例子。\n\n## 关联\n- [[entities/示例汽车集团汽车]]\n- [[entities/星海汽车商城]]\n- [[entities/星海汽车商城#情况|另一个显示名]]\n- [[entities/示例协调人]]\n- [[entities/未知公司]]\n- [[entities/松叶宠物|松果宠物]]\n- [[contacts/松果宠物]]\n- [[projects/松果宠物]]\n\n## 不关联\n- [[松果宠物]]\n'
        (self.root/'projects/权益.md').write_text(body)
        (self.root/'projects/行业参考.md').write_text('# 行业参考项目\n客户：[[远航汽车]]\n\n## 销售动作\n可用星海汽车作为行业对照。\n\n## 关联\n- [[entities/远航汽车科技]]\n- [[entities/星海汽车商城]]\n')
        (self.root/'projects/同段对照.md').write_text('# 同段对照项目\n客户：[[远航汽车]]\n\n## 销售动作\n可用[[entities/星海汽车商城]]作为汽车行业对照，不能直接复制。\n\n## 关联\n- [[entities/远航汽车]]\n- [[entities/星海汽车商城]]\n')
        projects=build_projects(self.root,self.state)
        project=next(p for p in projects if p['title']=='权益项目')
        self.assertEqual(project['customer'],'示例汽车集团汽车')
        self.assertEqual(project['related_customers'],[{'customer':'星海汽车商城','path':'projects/权益.md','link':'entities/星海汽车商城'}])
        self.assertFalse(project['is_current'])
        self.assertEqual(project['actions'],[])
        self.assertEqual(next(p for p in projects if p['title']=='行业参考项目')['related_customers'],[])
        self.assertEqual(next(p for p in projects if p['title']=='同段对照项目')['related_customers'],[])

    def test_related_customer_display_metadata_does_not_change_analysis_fingerprint(self):
        import project_analysis
        project=build_projects(self.root,self.state)[0]
        before=project_analysis.packet(project['id'],'',self.root,self.state,project_snapshot=project)
        related={**project,'related_customers':[{'customer':'独立客户','path':project['source_path'],'link':'entities/独立客户'}]}
        after=project_analysis.packet(project['id'],'',self.root,self.state,project_snapshot=related)
        self.assertEqual(before['fingerprint'],after['fingerprint'])
        self.assertEqual(before['stable_fingerprint'],after['stable_fingerprint'])
        self.assertEqual(before['sources'],after['sources'])

    def test_result_persists_without_changing_source(self):
        project = build_projects(self.root, self.state)[0]
        source_before = (self.root / project["source_path"]).read_text()
        payload = {"project_id": project["id"], "action_id": project["actions"][0]["id"], "revision": 0, "owner": "技术同事", "status": "等待反馈", "result": "已发出评估请求，未确认接受", "due": "2026-09-08"}
        self.assertTrue(save_plan(payload, self.root, self.state)["ok"])
        restored = build_projects(self.root, self.state)[0]
        self.assertEqual(restored["actions"][0]["record"]["status"], "等待反馈")
        self.assertEqual(restored["plan_revision"], 1)
        self.assertEqual((self.root / project["source_path"]).read_text(), source_before)
        with self.assertRaises(ValueError):
            save_plan(payload, self.root, self.state)

    def test_completion_requires_evidence_and_valid_id(self):
        project = build_projects(self.root, self.state)[0]
        payload = {"project_id": project["id"], "action_id": project["actions"][0]["id"], "revision": 0, "status": "已完成"}
        with self.assertRaises(ValueError):
            save_plan(payload, self.root, self.state)
        payload.update(project_id="../../bad", result="测试")
        with self.assertRaises(ValueError):
            save_plan(payload, self.root, self.state)

    def test_inline_sources_are_readable_only_for_the_linked_project(self):
        (self.root / "raw").mkdir()
        (self.root / "raw" / "fixture.md").write_text("isolated evidence")
        (self.root / "raw" / "unlinked.md").write_text("not linked")
        (self.root / "projects" / "星海汽车.md").write_text('---\nsources: ["raw/fixture.md"]\n---\n# 星海汽车项目\n\n客户项目说明。\n')
        project = next(p for p in build_projects(self.root, self.state) if p["title"] == "星海汽车项目")
        self.assertEqual(read_source(project["id"], "raw/fixture.md", self.root, self.state)["content"], "isolated evidence")
        for wrong in ("raw/unlinked.md", "../outside", "projects/示例酒品牌.md"):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                read_source(project["id"], wrong, self.root, self.state)

if __name__ == "__main__":
    unittest.main()

class EvidenceFreshnessTest(unittest.TestCase):
    def test_occurrence_label_does_not_absorb_same_line_promised_dates(self):
        promise='客户回邮：双方于2026年8月31日前完成正式合同签署，我司于2026年9月30日前支付全部合同款项。'
        with patch('project_workspace.date',wraps=date) as calendar:
            for today in (date(2026,9,20),date(2026,10,1)):
                calendar.today.return_value=today
                for label in ('occurred_at','event_date','沟通日期','录音日期','会议日期','业务日期','发生日期','date','日期'):
                    with self.subTest(today=today,label=label):
                        self.assertEqual(project_workspace.source_dates('',label+'：2026-08-21 '+promise),'2026-08-21')
                self.assertEqual(project_workspace.source_dates('','沟通日期：待确认。'+promise),'')
                self.assertEqual(project_workspace.source_dates('','沟通日期：8月21日。'+promise),'')
                self.assertEqual(project_workspace.source_dates('','沟通日期：2026-02-30。'+promise),'')
    def test_occurrence_date_range_and_recording_metadata_preserve_original_dates(self):
        cases=[
            ('业务日期：2026-08-20至2026-08-21。客户承诺2026-09-01付款。','2026-08-21'),
            ('沟通日期：2026年8月20日—2026年8月21日，签约约定2026年8月31日。','2026-08-21'),
            ('event_date: "2026-08-21T10:30:00+08:00"；付款约定2026-09-01。','2026-08-21'),
            ('发生日期：20260821，20260901前付款。','2026-08-21'),
            ('录音：PHONE-003，2026-08-21 09:44:58，20分07秒。付款约定2026-09-01。','2026-08-21'),
            ('沟通日期：2026-08-21（转写文件导出时间为2026-09-01）','2026-08-21'),
        ]
        with patch('project_workspace.date',wraps=date) as calendar:
            calendar.today.return_value=date(2026,9,20)
            for body,expected in cases:
                with self.subTest(body=body):self.assertEqual(project_workspace.source_dates('',body),expected)
    def test_recording_occurrence_is_separate_from_review_on_same_line(self):
        from project_workspace import source_dates, review_dates
        text = '发生日期：2026-09-03。来源编号：PHONE-050。复核日期：2026-09-07。'
        self.assertEqual(source_dates('raw/录音复核_20260907/PHONE-050.md', text), '2026-09-03')
        self.assertEqual(review_dates('raw/录音复核_20260907/PHONE-050.md', text), '2026-09-07')
        self.assertEqual(source_dates('raw/20260904_PHONE-003_报价复核_20260907.md', ''), '2026-09-04')
        self.assertEqual(source_dates('raw/20260907_复核.md', '## 2026-09-07 录音二次复核'), '')
        self.assertEqual(source_dates('projects/a.md', '## 2026-09-07 客户沟通\n新沟通'), '2026-09-07')
        self.assertEqual(source_dates('projects/a.md', '## 2026-09-07 客户回复：已复核工作量'), '2026-09-07')
        self.assertEqual(source_dates('projects/a.md', 'date: 2026-08-01\n## 2026-09-07 客户回复'), '2026-09-07')

    def test_archive_readback_date_does_not_refresh_business_event(self):
        from project_workspace import source_dates, review_dates
        text='业务日期：2026-08-27至2026-08-28。资料回读日：2026-09-07。'
        self.assertEqual(source_dates('raw/交叉核验_20260907/20260828_附件核验.md',text),'2026-08-28')
        self.assertEqual(review_dates('raw/附件.md',text),'2026-09-07')
        self.assertEqual(source_dates('raw/20260907_回读.md','## 2026-09-07 会议回读'),'')

    def test_recording_old_feedback_today_does_not_revive_old_project(self):
        import json
        from datetime import date
        from project_rounds import save_round
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root/'projects').mkdir(); (root/'raw').mkdir()
            (root/'raw'/'20200102_客户回复.txt').write_text('旧业务')
            (root/'projects'/'old.md').write_text('# 客户旧项目\n[[raw/20200102_客户回复.txt]]')
            state = root/'state'; project = build_projects(root, state)[0]
            save_round(dict(project_id=project['id'], revision=0, scenario='return', relationship='unknown', status='已收到反馈', feedback='补录旧反馈，不能认作今天沟通'), root, state)
            current = build_projects(root, state)[0]
            self.assertEqual(current['latest_evidence_date'], '2020-01-02')
            self.assertFalse(current['is_current'])
            self.assertEqual(current['latest_recorded_at'][:10], date.today().isoformat())

    def test_unique_txt_wikilink_and_other_project_date_not_current(self):
        from datetime import date
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'projects').mkdir();(root/'raw').mkdir()
            (root/'raw'/'2020-01-02_旧沟通.txt').write_text('旧沟通原话')
            (root/'projects'/'old.md').write_text('# 旧项目\n客户 项目\n[[2020-01-02_旧沟通.txt]]\n[[projects/new]]\n')
            (root/'projects'/'new.md').write_text('# 新项目\n客户 项目\n## 会议反馈 '+date.today().isoformat()+'\n新事实')
            projects=build_projects(root,root/'state');old=next(p for p in projects if p['title']=='旧项目')
            self.assertEqual(old['latest_evidence_date'],'2020-01-02');self.assertFalse(old['is_current'])
            self.assertTrue(any(s['path']=='raw/2020-01-02_旧沟通.txt' for s in old['sources']))
            self.assertEqual(next(s for s in old['sources'] if s['path']=='projects/new.md')['relation'],'background_reference')
    def test_plan_and_archive_dates_are_not_new_communication(self):
        from project_workspace import source_dates
        self.assertEqual(source_dates('projects/old.md','# 计划2026-09-01会议\nupdated: 2026-09-06\n## 2026-09-06归档'), '')

    def test_archive_parent_dates_do_not_refresh_old_business(self):
        from project_workspace import source_dates
        self.assertEqual(source_dates('raw/articles/交叉核验_20260907/20200102_客户回复.txt',''), '2020-01-02')
        self.assertEqual(source_dates('raw/articles/交叉核验_20260907/无日期.txt','## 2026-09-07 客户回复核验'), '')
        self.assertEqual(source_dates('raw/transcripts/业务沟通录音_20200102/原文.txt',''), '2020-01-02')

    def test_linked_review_is_readable_without_becoming_new_business(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'projects').mkdir();(root/'raw').mkdir();(root/'moc').mkdir()
            (root/'raw'/'20200102_客户回复.txt').write_text('旧业务')
            (root/'moc'/'20260907_复核.md').write_text('归档日不表示业务进展')
            (root/'projects'/'sample.md').write_text('# 客户项目\n[[raw/20200102_客户回复.txt]]\n[[moc/20260907_复核.md]]')
            project=build_projects(root,root/'state')[0]
            self.assertEqual(project['latest_evidence_date'],'2020-01-02')
            self.assertEqual(read_source(project['id'],'moc/20260907_复核.md',root,root/'state')['content'],'归档日不表示业务进展')
