import copy
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
import public_signal_hub as hub
import server
import background_operations as operations

class SignalHubTests(unittest.TestCase):
    def test_empty_new_customer_research_retains_auditable_coverage_and_replays(self):
        with tempfile.TemporaryDirectory() as d,patch.object(server,'PROSPECTING_STATE_FILE',Path(d)/'research.json'):
            payload={'run_id':'public-empty-verified','checked_queries':[{'group':'零售','query':'公开招标'}], 'coverage_notes':[{'group':'零售','gap':'报名准备期不足'}], 'reviewed_exclusions':[{'company':'甲','reason':'不足14天'}], 'source_links':[{'url':'https://example.com/official'}], 'leads':[]}
            first=server.import_prospecting_payload(payload)
            receipt=first['prospecting']['public_receipt']
            self.assertEqual(receipt['status'],'no_change')
            self.assertEqual(receipt['candidate_added_count'],0)
            for key in ('checked_queries','coverage_notes','source_links','reviewed_exclusions'):
                self.assertEqual(receipt[key],payload[key])
            retry=server.import_prospecting_payload(payload)
            self.assertTrue(retry['replayed'])
            self.assertEqual(len(retry['prospecting']['runs']),1)
            self.assertEqual(retry['prospecting']['public_receipt'],receipt)

    def test_tender_receipt_is_separate_from_waiting_scheduler_and_public_research(self):
        state={'task':{'last_run_status':'ok','last_run_at':'2026-09-20T00:54:33+08:00'},'summary':{'candidate_count':0,'watch_count':6},'runs':[
            {'source':'codex_agent_search','at':'later','status':'ok','search_total':999},
            {'source':'zhiliao_tender_search','at':'2026-09-20T00:54:33+08:00','status':'ok','search_total':175,'detail_count':4,'result_count':2}]}
        receipt=hub.tender_receipt(state)
        self.assertEqual(receipt['search_total'],175);self.assertEqual(receipt['detail_count'],4)
        self.assertIsNone(receipt['searched_item_count']);self.assertEqual(receipt['current_candidate_count'],0)
        self.assertEqual(receipt['status'],'ok')

    def test_customer_research_preserves_coverage_and_zero_change_receipt(self):
        with tempfile.TemporaryDirectory() as d,patch.object(server,'CUSTOMER_INTEL_STATE_FILE',Path(d)/'intel.json'),patch.object(server,'customer_intel_target_names',return_value=['甲']):
            payload={'run_id':'coverage-test','checked_customers':['甲'],'checked_queries':[{'customer':'甲','query':'甲官网'}],'coverage_notes':['原文入口暂不可读，未核到新增。'],'customers':[]}
            first=server.import_customer_intel_payload(payload)
            receipt=first['intel']['runs'][0]
            self.assertEqual(receipt['status'],'no_change');self.assertEqual(receipt['new_count'],0)
            self.assertEqual(receipt['checked_queries'],payload['checked_queries']);self.assertEqual(receipt['coverage_notes'],payload['coverage_notes'])
            self.assertTrue(server.import_customer_intel_payload(payload)['replayed'])
    def test_explicit_identity_only(self):
        for a,b in [('松果宠物','松叶宠物（独立体系）'),('示例汽车集团/星海汽车','示例汽车集团汽车'),('示例汽车集团/星海汽车','权益平台'),('示例汽车集团/星海汽车','示例汽车集团金融'),('示例汽车集团/星海汽车','陌生集团/星海汽车'),('甲集团','甲集团成都有限公司')]:
            self.assertFalse(hub.same_customer(a,b,hub.identity_aliases),(a,b))
        self.assertTrue(hub.same_customer('松果宠物','entities/松果宠物宠物',hub.identity_aliases))
        self.assertTrue(hub.same_customer('示例汽车集团/星海汽车','星海汽车商城',hub.identity_aliases))

    def test_explicit_project_edge_keeps_primary_customer_and_project_state_separate(self):
        state={'customers':{'示例汽车集团/星海汽车':{'signals':[{'title':'公开背景','published_at':'2026-09-19','source_url':'https://example.com'}]}}}
        reference={'customer':'星海汽车商城','path':'projects/权益.md','link':'entities/星海汽车商城'}
        projects=[{'id':'rights','title':'星海汽车数字资产中台','customer':'示例汽车集团汽车','source_path':'projects/权益.md','is_current':False,'related_customers':[reference]},
                  {'id':'mall','title':'商城交付','customer':'星海汽车商城','is_current':True},
                  {'id':'unknown','title':'星海汽车财经关键词','customer':'示例汽车集团金融'},
                  {'id':'wrong-path','title':'未核关系','customer':'独立主体','source_path':'projects/其他.md','related_customers':[reference]}]
        original=copy.deepcopy(projects)
        result=hub.build_hub(state,projects,hub.identity_aliases,datetime(2026,9,20,8,tzinfo=hub.TZ))
        related=result['signals'][0]['related_projects']
        self.assertEqual([p['id'] for p in related],['rights','mall'])
        self.assertEqual(related[0]['customer'],'示例汽车集团汽车')
        self.assertEqual(related[0]['relation_scope'],'explicit_project_reference')
        self.assertEqual(related[0]['relation_evidence'],reference)
        self.assertEqual(projects,original)
        self.assertFalse(result['signals'][0]['should_create_todo'])
        self.assertEqual(result['signals'][0]['freshness_label'],'30天内公开资料')

    def test_merge_retains_history_and_first_seen(self):
        old=[{'id':'a','title':'旧事件','url':'https://example.com/a','first_seen_at':'2026-09-17'},{'id':'b','title':'另一条','url':'https://example.com/b'}]
        self.assertEqual(len(hub.merge_signals(old,[], '2026-09-20')),2)
        result=hub.merge_signals(old,[{'title':'已更新','url':'https://example.com/a?utm_source=retry'}],'2026-09-20')
        self.assertEqual(len(result),2)
        a=next(x for x in result if x['id']=='a')
        self.assertEqual(a['first_seen_at'],'2026-09-17');self.assertEqual(a['last_seen_at'],'2026-09-20')

    def test_missed_scan_is_not_no_change_and_event_age_is_not_import_age(self):
        now=datetime(2026,9,20,8,tzinfo=hub.TZ)
        state={'task':{'last_run_at':'2026-09-18T06:03:00+08:00','last_run_status':'ok'},'customers':{'松果宠物':{'updated_at':'2026-09-20','signals':[{'title':'旧事件','published_at':'2026-06-01','url':'https://example.com','should_create_todo':True}]}}}
        result=hub.build_hub(state,[{'id':'wrong','customer':'松叶宠物','title':'独立项目'}],hub.identity_aliases,now)
        self.assertTrue(result['task']['overdue']);self.assertEqual(result['signals'][0]['freshness'],'historical')
        self.assertFalse(result['signals'][0]['related_projects']);self.assertFalse(result['signals'][0]['should_create_todo'])

    def test_earliest_node_and_unresolved_node(self):
        for body,expected in [
            ('招标文件获取时间：2026年9月20日至2026年9月25日。投标截止时间：2026年10月10日。','2026-09-25'),
            ('提问截止时间：2026年9月25日。投标截止时间：2026年10月10日。','2026-09-25'),
            ('投标截止时间：2026年10月10日。保证金2026年9月22日退回。','2026-10-10'),
            ('文件获取时间：另行通知。投标截止时间：2026年10月10日。','')]:
            self.assertEqual(server.prospecting_deadline_from_detail({'source':body}),expected)

    def test_import_does_not_approve_or_trust_pending_revenue(self):
        evidence={'status':'pending_public_lookup','amount_yi':120}
        self.assertNotEqual(server.prospecting_icp_tier('会员系统采购',evidence,'招采/采购触发')['code'],'strategic_attack')
        self.assertNotIn('100亿',server.prospecting_scale_label(evidence))
        self.assertIsNone(server.prospecting_extract_revenue_evidence('2027年销售额目标100亿元'))
        lead=server.prospecting_import_row_to_lead({'company':'隔离客户','title':'会员系统采购','source_url':'https://example.com','decision':'accepted','icp_tier':'strategic_attack'},1)
        self.assertNotEqual(lead['decision'],'accepted');self.assertNotEqual(lead['icp_tier'],'strategic_attack')

    def test_new_signal_does_not_erase_formal_decision(self):
        for decision in ['accepted','ignored']:
            old={'id':'old','company':'隔离客户','decision':decision,'account_id':'account','history':[{'action':'用户决定'}]}
            result=server.merge_prospecting_leads({'leads':[copy.deepcopy(old)]},[{'id':'new','company':'隔离客户','title':'会员系统采购','deadline':'2026-10-10'}])
            retained=next(x for x in result if x['id']=='old')
            self.assertEqual(retained['decision'],decision);self.assertEqual(retained['account_id'],'account');self.assertEqual(retained['history'],old['history'])

    def test_import_empty_receipt_and_retry_preserve_saved_signals(self):
        with tempfile.TemporaryDirectory() as d,patch.object(server,'CUSTOMER_INTEL_STATE_FILE',Path(d)/'signals.json'),patch.object(server,'customer_intel_target_names',return_value=['甲']):
            a=server.import_customer_intel_payload({'run_id':'one','customers':[{'customer':'甲','signals':[{'title':'新闻','source_url':'https://example.com','summary':'事实'}]}]})
            again=server.import_customer_intel_payload({'run_id':'one','customers':[]})
            self.assertTrue(again['replayed']);self.assertEqual(again['signal_count'],1)
            b=server.import_customer_intel_payload({'run_id':'two','customers':[],'checked_customers':['甲']})
            self.assertEqual(b['intel']['task']['last_run_status'],'no_change')
            self.assertEqual(len(b['intel']['customers']['甲']['signals']),1)

    def test_background_failures_are_independent_and_backoff_persists(self):
        class CRM:
            @staticmethod
            def status(root):raise ValueError('sensitive exception must not escape')
        class Communications:
            calls=0
            @classmethod
            def status(cls,*args):return {'job':{'running':False}}
            @classmethod
            def start(cls,*args):cls.calls+=1;cls.actions.append(args[0]['action']);return {'started':True}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);operations.run_once(root,root,clock=lambda:7200,communications=Communications)
            state=operations.read_status(root)
            self.assertNotIn('crm',state['jobs']);self.assertNotIn('sensitive',str(state))
            self.assertEqual(Communications.calls,1)
            operations.run_once(root,root,clock=lambda:7201,communications=Communications)
            self.assertEqual(Communications.calls,1)

    def test_revenue_requires_actual_annual_same_entity_amount(self):
        base={'status':'verified_from_public_report','amount_yi':80,'entity':'甲集团','year':2025,'period':'annual','source_url':'https://example.com/report','source_text':'甲集团2025年营业收入80亿元。集团销售额90亿元。'}
        self.assertTrue(hub.verified_revenue(base,'甲集团'))
        for changes in [{'period':'quarterly'},{'entity':'另一主体'},{'amount_yi':800},{'source_text':'甲集团2025年营业收入目标80亿元'},{'source_text':'甲集团2025年上半年营业收入80亿元'}]:
            self.assertFalse(hub.verified_revenue({**base,**changes},'甲集团'))
        self.assertFalse(hub.verified_revenue(base,'甲集团成都有限公司'))

    def test_optional_scheduler_dates_and_strict_user_deadlines(self):
        self.assertIsNone(server.parse_optional_local_datetime(None))
        self.assertIsNone(server.parse_optional_local_datetime('bad'))
        self.assertIsInstance(server.prospecting_due({'task':{}}),bool)
        with self.assertRaises(ValueError):server.parse_local_datetime('bad')

    def test_formal_lead_keeps_distinct_sources_and_identity(self):
        old={'id':'old','company':'甲集团','decision':'accepted','account_id':'formal','source_url':'https://example.com/old','history':[]}
        incoming=[{'id':str(i),'company':'甲集团','title':'会员采购','source_url':'https://example.com/'+str(i),'deadline':'2026-10-10'} for i in [1,2]]
        result=server.merge_prospecting_leads({'leads':[old]},incoming)
        self.assertEqual(result[0]['id'],'old');self.assertEqual(result[0]['account_id'],'formal');self.assertEqual(len(result[0]['additional_signals']),3)
        again=server.merge_prospecting_leads({'leads':result},incoming)
        self.assertEqual(len(again[0]['additional_signals']),3)
        other=server.merge_prospecting_leads({'leads':again},[{'id':'child','company':'甲集团成都有限公司','title':'会员采购','source_url':'https://example.com/child'}])
        self.assertEqual(len(other),2)

    def test_interrupted_collection_resumes_instead_of_accepting_collected_receipt(self):
        class CRM:
            @staticmethod
            def status(root):return {'configured':False}
        class Communications:
            calls=[]
            @staticmethod
            def status(*args):return {'job':{'state':'interrupted','running':False},'receipt':{'status':'collected','checked_at':'9999','refresh_pending':[]}}
            @classmethod
            def start(cls,payload,*args):cls.calls.append(payload['action']);return {'started':True,'job':{'request_id':'new'}}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);operations.record(root,'communications',awaiting_result=True,dispatched_at='2000',next_epoch=0)
            operations.run_once(root,root,clock=lambda:1000,communications=Communications)
            self.assertEqual(Communications.calls,['resume'])

    def test_same_source_or_id_cannot_merge_different_entities(self):
        old={'id':'same','company':'甲集团','decision':'accepted','account_id':'formal','source_url':'https://example.com/shared','history':[]}
        other={'id':'same','company':'乙公司','title':'会员采购','source_url':'https://example.com/shared'}
        result=server.merge_prospecting_leads({'leads':[old]},[other])
        self.assertEqual(len(result),2);self.assertNotEqual(result[0]['id'],result[1]['id']);self.assertFalse(result[0].get('additional_signals'))
        with patch.object(server,'ACCOUNT_STORE_FILE',Path('/tmp/nonexistent-sales-test-ledger')),patch.object(server,'parse_client_registry',return_value={'active':[{'name':'甲集团'}]}):
            self.assertIsNone(server.prospecting_existing_customer_match('乙公司','甲集团与乙公司联合项目'))
            self.assertIsNone(server.prospecting_existing_customer_match('甲集团成都有限公司','甲集团采购'))
    def test_import_receipt_counts_persisted_evidence_not_candidates(self):
        with tempfile.TemporaryDirectory() as d,patch.object(server,'PROSPECTING_STATE_FILE',Path(d)/'research.json'),patch.object(server,'prospecting_existing_customer_match',return_value=None):
            server.save_prospecting_state({'leads':[{'id':'old','company':'甲集团','decision':'accepted','account_id':'formal','history':[]}],'task':{}})
            payload={'checked_queries':['甲会员采购'],'leads':[{'company':'甲集团','title':'会员采购系统升级','source_url':'https://example.com/new','summary':'新的事实'}]}
            first=server.import_prospecting_payload(payload)
            self.assertEqual(first['candidate_added_count'],0);self.assertEqual(first['evidence_added_count'],1);self.assertEqual(first['imported_count'],1)
            replay=server.import_prospecting_payload(payload)
            self.assertEqual(replay['imported_count'],0)
            payload['leads'][0]['summary']='更新后的事实'
            changed=server.import_prospecting_payload(payload)
            self.assertEqual(changed['evidence_updated_count'],1)
            stored=server.load_prospecting_state()['leads'][0]
            self.assertEqual(stored['decision'],'accepted');self.assertEqual(stored['account_id'],'formal');self.assertEqual(stored['additional_signals'][0]['summary'],'更新后的事实')
    def test_interrupted_recovery_has_a_durable_limit(self):
        class CRM:
            @staticmethod
            def status(root):return {'configured':False}
        class Communications:
            calls=0
            actions=[]
            @staticmethod
            def status(*args):return {'job':{'state':'interrupted','running':False},'receipt':{'status':'collected'}}
            @classmethod
            def start(cls,*args):cls.calls+=1;cls.actions.append(args[0]['action']);return {'started':True}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for clock in [1000,1061,1122,1183,4800]:operations.run_once(root,root,clock=lambda:clock,communications=Communications)
            self.assertEqual(Communications.actions,['resume','resume','resume','collect'])
            self.assertEqual(operations.read_status(root)['jobs']['communications']['recovery_attempts'],3)
            self.assertEqual(operations.read_status(root)['jobs']['communications']['status'],'needs_input')
    def test_same_batch_duplicate_ids_keep_distinct_customers(self):
        result=server.merge_prospecting_leads({'leads':[]},[{'id':'collision','company':name,'title':'会员系统升级','source_url':'https://example.com/shared'} for name in ('甲','乙')])
        self.assertEqual(len(result),2);self.assertEqual(len({x['id'] for x in result}),2)
