import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import k100_sync as sync
import project_rounds
from project_workspace import build_projects

class K100Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.kb=self.root/'knowledge';(self.kb/'projects').mkdir(parents=True)
        (self.kb/'projects'/'one.md').write_text('# one\n客户 项目\n')
        self.pid=build_projects(self.kb,self.root)[0]['id']
        self.body=dict(test=True,customer_id='customer-test',source_id='test-1',type='GENERAL_NOTE',occurredAt='2026-01-01T00:00:00Z',content='技术接入测试')
        self.customer=dict(id='customer-test',legalName='测试主体',isMine=True,availableActions=['ADD_FOLLOW_UP'])
    def test_duplicate_and_changed_content(self):
        with patch.object(sync,'target',return_value=('user',self.customer)),patch.object(sync,'audit_records',return_value=[]),patch.object(sync,'request',return_value={}) as post:
            a=sync.progress(self.root,self.body);b=sync.progress(self.root,self.body)
            self.assertEqual(a,b);self.assertEqual(post.call_count,1)
            with self.assertRaises(sync.SyncError):sync.progress(self.root,{**self.body,'content':'技术接入测试changed'})
    def test_uncertain_never_resends_or_claims_accepted(self):
        with patch.object(sync,'target',return_value=('user',self.customer)),patch.object(sync,'audit_records',return_value=[]),patch.object(sync,'request',side_effect=sync.SyncError('timeout','uncertain')) as post,patch.object(sync,'identity',return_value='user'):
            e=sync.progress(self.root,self.body)['event'];self.assertEqual(e['state'],'uncertain')
            sync.deliver(self.root,e['id']);r=sync.reconcile(self.root,e['id'])['event']
            self.assertEqual(post.call_count,1);self.assertEqual(r['state'],'uncertain');self.assertNotIn('已接受',r['message'])
    def test_test_note_cannot_be_effective(self):
        with self.assertRaises(sync.SyncError):sync.progress(self.root,{**self.body,'type':'WECHAT'})
    def test_ownership_and_action_are_checked(self):
        for customer in [{**self.customer,'isMine':False},{**self.customer,'availableActions':[]}]:
            with patch.object(sync,'identity',return_value='user'),patch.object(sync,'customer_detail',return_value={'customer':customer}),self.assertRaises(sync.SyncError):sync.target('customer-test')
    def test_local_save_survives_sync_failure_and_history_unchanged_does_not_repeat(self):
        payload=dict(project_id=self.pid,revision=0,scenario='return',relationship='unknown',status='准备中',facts='真实反馈',k100={'type':'PHONE_CALL','occurredAt':'2026-01-01T00:00:00Z'})
        with patch.object(sync,'progress',side_effect=RuntimeError('disk fail')):
            result=sync.save_round(payload,self.kb,self.root)
        self.assertEqual(result['revision'],1);self.assertEqual(result['k100']['state'],'failed')
        self.assertEqual(project_rounds.read_round(self.pid,self.kb,self.root)['record']['facts'],'真实反馈')
        with patch.object(sync,'progress') as call:
            again=sync.save_round({**payload,'revision':1},self.kb,self.root)
            call.assert_not_called();self.assertEqual(again['k100']['state'],'unchanged')
    def test_linked_save_defaults_note_and_does_not_reuse_effective_type(self):
        with sync.locked(self.root) as folder:
            state=sync.read_state(folder);state['links'][self.pid]={'enabled':True};sync.write_state(folder,state)
        payload=dict(project_id=self.pid,revision=0,scenario='return',relationship='unknown',status='准备中',facts='新事实',k100_type='PHONE_CALL',k100_occurred_at='old')
        with patch.object(sync,'progress',return_value={'event':{'state':'confirmed'}}) as call:
            result=sync.save_round(payload,self.kb,self.root)
            self.assertEqual(call.call_args.args[1]['type'],'GENERAL_NOTE')
            self.assertEqual(result['record']['k100_type'],'GENERAL_NOTE')
    def test_audit_readback_and_non_effective_protection(self):
        row={'id':'audit-1','action':'CUSTOMER_FOLLOW_UP_CREATED','actorId':'user','changes':[{'field':'跟进类型','after':'普通备注'},{'field':'有效跟进','after':'否'},{'field':'刷新保护计时','after':'否'}]}
        with patch.object(sync,'target',return_value=('user',self.customer)),patch.object(sync,'audit_records',side_effect=[[],[row]]),patch.object(sync,'request',return_value={}),patch.object(sync,'customer_detail',return_value={'customer':self.customer}):
            e=sync.progress(self.root,self.body)['event'];self.assertEqual(e['state'],'confirmed');self.assertFalse(e['effective']);self.assertFalse(e['protection_refreshed'])
    def test_archived_project_blocks_queued_delivery(self):
        with sync.locked(self.root) as folder:
            state=sync.read_state(folder);state['events']['event']={'id':'event','project_id':self.pid,'state':'pending','customer_id':'customer-test'};sync.write_state(folder,state)
        with patch('project_archive.state',return_value={'archived':True}),patch.object(sync,'target') as target:
            result=sync.deliver(self.root,'event')['event'];self.assertEqual(result['state'],'blocked');target.assert_not_called()
    def test_missing_login_retains_local_outbox(self):
        with patch.object(sync,'target',side_effect=sync.SyncError('会话失效','needs_login')):
            result=sync.progress(self.root,self.body)['event'];self.assertEqual(result['state'],'needs_login')
        with sync.locked(self.root) as folder:
            self.assertEqual(sync.read_state(folder)['events'][result['id']]['content'],self.body['content'])
