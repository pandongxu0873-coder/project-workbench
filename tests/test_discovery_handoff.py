import json
import tempfile
import unittest
from contextlib import ExitStack
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
import server
import discovery_handoff as handoff
import discovery_workspace as notes
import project_rounds
from project_workspace import build_projects

class DiscoveryHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.k=self.root/'kb';self.s=self.root/'state';self.s.mkdir();(self.k/'projects').mkdir(parents=True)
        for name,customer in [('甲','隔离客户甲'),('甲二期','隔离客户甲'),('乙','隔离客户乙')]:
            (self.k/'projects'/f'{name}.md').write_text(f'# 项目{name}\n**客户**：[[{customer}]]\n')
        self.projects=build_projects(self.k,self.s);self.pa=next(p for p in self.projects if p['title']=='项目甲');self.pb=next(p for p in self.projects if p['title']=='项目乙')
        self.accounts=[dict(id='a1',name='隔离客户甲',stage='path',account_state='active'),dict(id='b1',name='隔离客户乙',stage='qualify',account_state='active')]
        self.lead=dict(id='l1',company='隔离客户甲',account_id='a1',decision='accepted',title='客户系统采购',entry_strategy='核对采购要求',source_url='https://example.com/source',deadline=(date.today()+timedelta(days=20)).isoformat())
        self.leads=[self.lead]
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for k,v in {'SALES_WORKBENCH_KNOWLEDGE_ROOT':self.k,'WORKBENCH_DATA_ROOT':self.s,'RISK_TODO_FILE':self.s/'risk_todos.json','ACCOUNT_STORE_FILE':self.s/'accounts.sqlite','ACCOUNT_STORE_INITIALIZED':False}.items():self.stack.enter_context(patch.object(server,k,v))
        self.stack.enter_context(patch.object(server,'account_store_rows',return_value=self.accounts))
        self.stack.enter_context(patch.object(server,'load_prospecting_state',side_effect=lambda:dict(leads=[dict(x) for x in self.leads])))
        self.stack.enter_context(patch.object(server,'load_workflow_state',side_effect=lambda:json.loads((self.s/'workflow_state.json').read_text()) if (self.s/'workflow_state.json').exists() else {}))
        self.stack.enter_context(patch.object(server,'load_feishu_reminder_delivery_state',return_value={}))
    def prep(self):return server.discovery_preparation(dict(kind='lead',source_id='l1'))
    def transfer(self,project=''):
        p=self.prep();return server.save_discovery_handoff(dict(kind='lead',source_id='l1',revision=p['revision'],source_version=p['source_version'],project_id=project))
    def note(self,**extra):
        n=notes.load_notes(self.s)
        return notes.save_note(dict(kind='lead',source_id='l1',revision=n['revision'],entity_version=handoff.signature(self.lead),owner_scope='mine',protection='mine',checked_at=date.today().isoformat(),ownership_evidence='隔离 CRM 只读查询',demand='confirmed',contact_result='已沟通需求；范围待评估',next_date=(date.today()+timedelta(days=3)).isoformat(),**extra),self.s,self.leads,self.accounts)
    def test_default_internal_action_without_manual_form_or_invented_date(self):
        p=self.prep();self.assertTrue(p['internal_only']);self.assertTrue(p['ready']);self.assertEqual(len(p['projects']),2)
        r=self.transfer();self.assertEqual(r['todo']['deadline'],'');self.assertEqual(r['todo']['status'],'待处理');self.assertFalse(r['todo']['reminder_consent']['enabled']);self.assertEqual(r['todo']['calendar'],{})
    def test_owned_note_carries_date_and_explicit_project_once(self):
        self.note();before={p:p.read_bytes() for p in self.k.rglob('*') if p.is_file()}
        first=self.transfer(self.pa['id']);second=self.transfer(self.pa['id'])
        self.assertEqual(first['todo']['id'],second['todo']['id']);self.assertTrue(second['existing']);self.assertEqual(len(server.load_risk_todos()),1)
        self.assertFalse(first['todo']['internal_only']);self.assertEqual(first['todo']['deadline'],(date.today()+timedelta(days=3)).isoformat())
        self.assertIn('已沟通需求',first['todo']['evidence']);self.assertEqual(first['todo']['project_id'],self.pa['id'])
        self.assertEqual(before,{p:p.read_bytes() for p in before})
    def test_cross_project_and_stale_note_are_rejected_without_writes(self):
        with self.assertRaisesRegex(ValueError,'项目与来源'):self.transfer(self.pb['id'])
        p=self.prep();self.note()
        with self.assertRaisesRegex(ValueError,'记录已更新'):server.save_discovery_handoff(dict(kind='lead',source_id='l1',revision=p['revision'],source_version=p['source_version']))
        self.assertFalse((self.s/'risk_todos.json').exists())
    def test_completion_does_not_resurrect_and_new_note_can_start_next_round(self):
        r=self.transfer();aid=r['todo']['id'];server.save_risk_todos([])
        (self.s/'workflow_state.json').write_text(json.dumps({'schedule_status':{aid:{'hidden':True,'status':'已处理'}}}))
        self.assertTrue(self.transfer()['handled']);self.assertEqual(server.load_risk_todos(),[])
        self.note();new=self.transfer();self.assertNotEqual(new['todo']['id'],aid)
    def test_adopted_round_keeps_original_id_and_date_on_reentry(self):
        self.note();first=self.transfer(self.pa['id']);aid=first['todo']['id']
        project_rounds.save_round(dict(project_id=self.pa['id'],revision=0,scenario='first',relationship='unknown',status='准备中',facts='已有来源',action='核对范围',due=(date.today()+timedelta(days=8)).isoformat(),origin_action_id=aid),self.k,self.s)
        r=self.transfer(self.pa['id']);self.assertEqual(r['todo']['id'],'round:'+self.pa['id'])
        self.assertEqual(project_rounds.read_round(self.pa['id'],self.k,self.s)['record']['due'],(date.today()+timedelta(days=8)).isoformat())
    def test_historical_window_and_paused_account_never_create_tasks(self):
        self.lead['deadline']=(date.today()-timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(ValueError,'历史'):self.transfer()
        self.lead['deadline']=(date.today()+timedelta(days=20)).isoformat();self.accounts[0]['account_state']='paused'
        with self.assertRaisesRegex(ValueError,'暂停'):self.transfer()
        self.assertFalse((self.s/'risk_todos.json').exists())
    def test_duplicate_admission_does_not_write_registry_or_reset_formal_state(self):
        with patch.object(server,'append_prospect_to_client_registry') as registry,patch.object(server,'upsert_account_store') as store:
            result=server.update_prospecting_lead(dict(id='l1',target='accept'))
        self.assertEqual(result['customer_pool']['status'],'already_admitted');registry.assert_not_called();store.assert_not_called()
        original=dict(id='account1',name='固定主体',stage='path',account_state='paused',next_action='保留实际工作')
        server.upsert_account_store(original,source_kind='workbench_manual')
        result=server.upsert_account_store(dict(id='new1',name='固定主体',stage='qualify',account_state='active',next_action='新AI建议'),source_kind='workbench_ai_admission')
        self.assertEqual(result['stage'],'path');self.assertEqual(result['account_state'],'paused');self.assertEqual(result['next_action'],'保留实际工作');self.assertEqual(result['id'],'account1')
    def test_protection_and_corruption_fail_closed(self):
        n=notes.save_note(dict(kind='lead',source_id='l1',revision=0,entity_version=handoff.signature(self.lead),owner_scope='other_k100',protection='other',checked_at=date.today().isoformat(),ownership_evidence='同事保护记录',demand='unknown'),self.s,self.leads,self.accounts)
        self.assertTrue(self.prep()['internal_only'])
        (self.s/'qualification_notes.json').write_text(json.dumps({'revision':n['revision'],'items':{'lead:l1':{}}}))
        with self.assertRaises(ValueError):self.transfer()

    def test_explicit_account_mismatch_rejected(self):
        self.lead['account_id']='b1'
        with self.assertRaisesRegex(ValueError,'主体不一致'):self.transfer(self.pb['id'])
        self.assertFalse((self.s/'risk_todos.json').exists())
    def test_stale_source_cannot_relabel_communication(self):
        old=handoff.signature(self.lead);self.lead['company']='隔离客户乙'
        with self.assertRaisesRegex(ValueError,'来源主体'):
            notes.save_note(dict(kind='lead',source_id='l1',revision=0,entity_version=old,owner_scope='unknown',protection='unknown',demand='unknown',contact_result='客户甲原有沟通'),self.s,self.leads,self.accounts)
        self.assertFalse((self.s/'qualification_notes.json').exists())
    def test_real_feedback_keeps_lineage_and_internal_boundary(self):
        original=self.transfer()['todo']
        for key,value in {'WORKFLOW_RECEIPT_ROOT':self.s/'workflow_receipts','WORKFLOW_RECEIPT_LOG':self.s/'receipt-log.md','WORKFLOW_EVIDENCE_ASSET_ROOT':self.s/'evidence','WORKFLOW_STATE_FILE':self.s/'workflow_state.json','RISK_TODO_LOG':self.s/'todo.md'}.items():self.stack.enter_context(patch.object(server,key,value))
        self.stack.enter_context(patch.object(server,'apply_receipt_to_account',return_value='a1'))
        result=server.submit_risk_evidence_impl(dict(todo_id=original['id'],customer='隔离客户甲',account_id='a1',title='内部核实',status='待客户反馈',resolution='正在内部核对',next_step='内部核对负责人',deadline=(date.today()+timedelta(days=5)).isoformat()+'T12:00',sync_calendar=False))
        self.assertEqual(result['todo']['discovery_source_key'],original['discovery_source_key']);self.assertTrue(result['todo']['internal_only'])
        self.assertIn('内部核实',(self.s/'receipt-log.md').read_text())
        self.assertEqual(self.prep()['existing']['id'],original['id'])
        self.note();self.transfer()
        self.assertEqual(len(server.load_risk_todos()),1)
        self.assertEqual(server.load_risk_todos()[0]['deadline'],result['todo']['deadline'])

    def account_prep(self):
        return server.discovery_preparation(dict(kind='account',source_id='a1'))

    def account_transfer(self):
        p=self.account_prep()
        return server.save_discovery_handoff(dict(kind='account',source_id='a1',revision=p['revision'],source_version=p['source_version']))

    def legacy_note(self):
        # Pre-admission qualification remains append-only when the account opens.
        self.lead['decision']='watch'
        self.note()
        self.lead['decision']='accepted'

    def test_expired_admitted_signal_can_open_account_without_reopening_bid(self):
        self.lead['deadline']=(date.today()-timedelta(days=1)).isoformat()
        self.assertFalse(self.prep()['ready'])
        p=self.account_prep()
        self.assertTrue(p['ready']);self.assertTrue(p['internal_only']);self.assertEqual(p['due'],'')
        self.assertEqual(p['account_id'],'a1')
        self.assertFalse((self.s/'risk_todos.json').exists())
        self.accounts[0]['account_state']='paused'
        self.assertFalse(self.account_prep()['ready'])

    def test_legacy_qualification_and_active_followup_survive_account_entry(self):
        self.legacy_note();first=self.transfer();prior=notes.load_notes(self.s)
        self.lead['deadline']=(date.today()-timedelta(days=1)).isoformat()
        p=self.account_prep()
        self.assertEqual(p['note'],prior['items']['lead:l1'])
        self.assertEqual(p['existing']['id'],first['todo']['id'])
        self.assertEqual(self.account_transfer()['todo']['id'],first['todo']['id'])
        self.assertEqual(len(server.load_risk_todos()),1)
        self.assertEqual(notes.load_notes(self.s),prior)

    def test_completed_legacy_followup_not_resurrected_when_opening_account(self):
        self.legacy_note();first=self.transfer();server.save_risk_todos([])
        (self.s/'workflow_state.json').write_text(json.dumps({'schedule_status':{first['todo']['id']:{'hidden':True,'status':'已处理'}}}))
        self.assertTrue(self.account_prep()['handled'])
        self.assertTrue(self.account_transfer()['handled'])
        self.assertEqual(server.load_risk_todos(),[])
        p=self.account_prep()
        notes.save_note(dict(**{k:v for k,v in p['note'].items() if k in notes.FIELDS},kind='account',source_id='a1',revision=p['revision'],entity_version=p['entity_version']),self.s,self.leads,self.accounts)
        # Saving an identical inherited note must not create a new business round.
        self.assertTrue(self.account_prep()['handled'])
        changed={k:v for k,v in p['note'].items() if k in notes.FIELDS}
        changed['contact_result']='之后取得新的需求回复'
        notes.save_note(dict(**changed,kind='account',source_id='a1',revision=p['revision'],entity_version=p['entity_version']),self.s,self.leads,self.accounts)
        new=self.account_transfer()
        self.assertNotEqual(new['todo']['id'],first['todo']['id'])
        self.assertEqual(self.prep()['existing']['id'],new['todo']['id'])
        self.assertEqual(len(server.load_risk_todos()),1)

    def test_account_and_lead_edits_share_revision_and_keep_legacy_evidence(self):
        self.legacy_note();p=self.account_prep();old=dict(p['note'])
        fields={k:v for k,v in old.items() if k in notes.FIELDS};fields['contact_result']='正式账户中新增的实际沟通'
        notes.save_note(dict(**fields,kind='account',source_id='a1',revision=p['revision'],entity_version=p['entity_version']),self.s,self.leads,self.accounts)
        current=notes.load_notes(self.s)
        self.assertEqual(current['items']['lead:l1'],old)
        self.assertEqual(self.prep()['note']['contact_result'],fields['contact_result'])
        with self.assertRaisesRegex(ValueError,'已更新'):
            notes.save_note(dict(**fields,kind='lead',source_id='l1',revision=p['revision'],entity_version=handoff.signature(self.lead)),self.s,self.leads,self.accounts)

    def test_multiple_legacy_notes_not_silently_merged(self):
        self.legacy_note();other=dict(self.lead,id='l2');self.leads.append(other)
        state=notes.load_notes(self.s);state['items']['lead:l2']={**state['items']['lead:l1'],'source_id':'l2','contact_result':'另一事项'}
        (self.s/'qualification_notes.json').write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError,'多份旧沟通'):self.account_prep()
        self.assertFalse((self.s/'risk_todos.json').exists())
