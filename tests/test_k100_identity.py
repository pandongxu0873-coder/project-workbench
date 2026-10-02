import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import k100_sync as sync
class IdentityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.k=self.root/'kb';(self.k/'raw').mkdir(parents=True);self.path=self.k/'raw/contract.txt';self.path.write_text('甲方：甲公司分公司\n')
  self.project={'id':'one','title':'一期','customer':'品牌','sources':[{'path':'raw/contract.txt','readable':True,'exists':True,'relation':'explicit_evidence'}]}
  self.roster=[{'id':'parent','legalName':'甲公司','isMine':True},{'id':'branch','legalName':'甲公司分公司','isMine':True}]
 def audit(self):
  with patch('project_crm.audit',return_value={'matches':[],'issues':[]}):return sync.identity_audit(self.root,self.k,self.roster,[self.project])['items']
 def test_exact_branch_no_parent_prefix_or_background_inheritance(self):
  x=self.audit()[0];self.assertEqual(x['state'],'verified');self.assertEqual(x['proofs'][0]['customer_id'],'branch')
  self.project['sources'][0]['relation']='background_reference';self.assertEqual(self.audit()[0]['state'],'needs_identity')
 def test_conflicting_parties_or_not_owned_not_auto_linked(self):
  self.path.write_text('甲方：甲公司\n甲方：甲公司分公司\n');self.assertEqual(self.audit()[0]['state'],'needs_identity')
  self.path.write_text('甲方：甲公司分公司\n');self.roster[1]['isMine']=False;self.assertEqual(self.audit()[0]['state'],'needs_identity')
 def test_mentions_and_uncertain_prose_not_accepted(self):
  self.path.write_text('尚未确认甲方：甲公司分公司\n例如甲方：甲公司\n');self.assertEqual(self.audit()[0]['state'],'needs_identity')
 def test_preserves_existing_link_and_archive(self):
  with sync.locked(self.root) as folder:
   state=sync.read_state(folder);state['links']['one']={'customer_id':'old'};sync.write_state(folder,state)
  self.assertEqual(self.audit(),[])
 def test_link_verified_rechecks_and_keeps_evidence_without_sending(self):
  customer={**self.roster[1],'availableActions':['ADD_FOLLOW_UP']}
  with patch('project_workspace.build_projects',return_value=[self.project]),patch('project_crm.audit',return_value={'matches':[],'issues':[]}),patch.object(sync,'customers',return_value={'items':self.roster}),patch.object(sync,'target',return_value=('user',customer)),patch.object(sync,'keychain',return_value=True),patch.object(sync,'deliver') as deliver:
   result=sync.link_verified(self.root,'one',self.k);deliver.assert_not_called();self.assertEqual(result['link']['customer_id'],'branch');self.assertEqual(result['link']['identity_evidence'][0]['evidence']['sha256'],hashlib.sha256(self.path.read_bytes()).hexdigest())
