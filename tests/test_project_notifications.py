import copy,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import project_notifications as inbox
import project_workspace

class InboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.p={'id':'a'*20,'title':'独立项目A','customer':'同客户','sources':[{'path':'raw/a.md','title':'原沟通','relation':'explicit_evidence','content_sha256':'one'}], 'notification_state':{'plan':'one','round':'one','correction':'one'}, 'archive':{'archived':False,'revision':0}}
        self.q={**copy.deepcopy(self.p),'id':'b'*20,'title':'独立项目B'}
        inbox.observe([self.p,self.q],self.root,1)
    def tearDown(self):self.tmp.cleanup()
    def feed(self):return inbox.listing(self.root)
    def change(self,n=2):
        self.p['sources'][0]['content_sha256']=str(n);inbox.observe([self.p,self.q],self.root,n)
    def test_first_baseline_quiet_and_no_repeated_alert(self):
        self.assertEqual(self.feed()['unread_count'],0);inbox.observe([self.p,self.q],self.root,2);self.assertEqual(self.feed()['items'],[])
    def test_merge_identity_persistence_and_next_change(self):
        self.change();self.p['notification_state']['plan']='two';inbox.observe([self.p,self.q],self.root,3)
        feed=self.feed();self.assertEqual(feed['unread_count'],1);self.assertEqual(len(feed['items'][0]['changes']),2)
        self.assertEqual(feed['items'][0]['project_id'],self.p['id'])
        inbox.acknowledge(self.root,{'items':[{'project_id':self.p['id'],'revision':2}]});self.assertEqual(self.feed()['unread_count'],0)
        raw=subprocess.check_output([sys.executable,'-c','import project_notifications as n,json,sys;print(json.dumps(n.listing(sys.argv[1])))',str(self.root)])
        self.assertEqual(json.loads(raw)['unread_count'],0)
        self.change(4);self.assertEqual(self.feed()['unread_count'],1);self.assertEqual(len(self.feed()['items'][0]['changes']),1)
    def test_old_read_ack_cannot_swallow_new_event_or_repeat(self):
        self.change(2);old={'items':[{'project_id':self.p['id'],'revision':1}]};self.change(3)
        inbox.acknowledge(self.root,old);inbox.acknowledge(self.root,old)
        self.assertEqual(self.feed()['unread_count'],1)
    def test_old_observation_cannot_revert_current(self):
        old=copy.deepcopy(self.p);self.change(3);inbox.observe([old],self.root,2)
        inbox.observe([self.p],self.root,4);self.assertEqual(self.feed()['items'][0]['revision'],1)
    def test_missing_material_reappears_without_false_alert(self):
        saved=self.p['sources'];self.p['sources']=[];inbox.observe([self.p],self.root,2)
        self.p['sources']=saved;inbox.observe([self.p],self.root,3);self.assertEqual(self.feed()['items'],[])
    def test_background_reference_and_read_failure_ignore(self):
        self.p['sources'].append({'path':'projects/other.md','relation':'background_reference','content_sha256':'new'})
        self.p['notification_state']['round']=None;inbox.observe([self.p],self.root,2);self.assertEqual(self.feed()['items'],[])
    def test_archive_change_and_material_no_restore(self):
        self.p['archive']={'revision':1,'archived':True};inbox.observe([self.p],self.root,2);self.change(3)
        self.assertTrue(self.feed()['items'][0]['archived']);self.assertEqual(self.p['archive']['revision'],1)
        self.assertFalse((self.root/'project_archive').exists())
    def test_validation_atomic_and_no_future_ack(self):
        self.change()
        for payload in [{'items':[{'project_id':self.p['id'],'revision':True}]},{'items':[{'project_id':self.p['id'],'revision':1},{'project_id':self.q['id'],'revision':99}]}]:
            with self.assertRaises(ValueError):inbox.acknowledge(self.root,payload)
        self.assertEqual(self.feed()['unread_count'],1)
    def test_new_project_after_baseline(self):
        p={**self.p,'id':'c'*20};inbox.observe([p],self.root,2);self.assertEqual(self.feed()['items'][0]['changes'][0]['kind'],'project')
    def test_observer_failure_does_not_mutate_projects(self):
        original=copy.deepcopy(self.p)
        with patch.object(inbox,'observe',side_effect=OSError('fixture')):inbox.observe_safely([self.p],self.root,3)
        self.assertEqual(self.p,original);self.assertTrue(self.feed()['observation_error'])
    def test_nontext_attachment_new_path_is_not_lost(self):
        self.p['sources'].append({'path':'raw/invoice.pdf','relation':'explicit_evidence','exists':True,'readable':False})
        inbox.observe([self.p],self.root,2)
        item=self.feed()['items'][0]['changes'][0]
        self.assertEqual(item['path'],'raw/invoice.pdf');self.assertFalse(item['readable'])
    def test_analysis_change_labels_ai_and_ignores_runtime_metadata(self):
        self.p['notification_state']['analysis']='changed'
        inbox.observe([self.p],self.root,2)
        self.assertEqual(self.feed()['items'],[])
        self.p['analysis_state']='running';self.p['analysis_meta']={'created_at':'tomorrow'}
        inbox.observe([self.p],self.root,3)
        self.assertEqual(self.feed()['items'],[])
    def test_disabled_inbox_preserves_bare_read_model(self):
        state=self.root/'unenabled';kb=self.root/'kb';(kb/'projects').mkdir(parents=True)
        (kb/'projects/a.md').write_text('# 项目A\n客户：[[客户甲]]\n')
        project_workspace.build_projects(kb,state)
        self.assertFalse(state.exists())
    def test_existing_build_observes_material_and_no_model(self):
        kb=self.root/'kb';(kb/'projects').mkdir(parents=True);(kb/'raw').mkdir()
        (kb/'projects/a.md').write_text('# 合成项目\n客户：[[合成客户]]\n[[raw/reply]]\n');(kb/'raw/reply.md').write_text('# 沟通\n客户反馈一')
        state=self.root/'state'
        inbox.listing(state)  # inbox enables observation; bare project reads remain read-only
        with patch('project_analysis.run_model',side_effect=AssertionError('no models')):
            first=project_workspace.build_projects(kb,state)
            self.assertEqual(inbox.listing(state)['unread_count'],0)
            (kb/'raw/reply.md').write_text('# 沟通\n客户反馈二')
            second=project_workspace.build_projects(kb,state)
        feed=inbox.listing(state);self.assertEqual(feed['unread_count'],1)
        self.assertEqual(feed['items'][0]['changes'][0]['path'],'raw/reply.md')
        self.assertEqual(first[0]['id'],second[0]['id']);self.assertNotIn('notification_state',second[0])

if __name__=='__main__':unittest.main()
