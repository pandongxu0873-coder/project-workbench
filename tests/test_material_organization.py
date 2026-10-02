import hashlib,json,tempfile,unittest
from pathlib import Path
import material_organization as org

class ArchiveTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);(self.root/'tracking').mkdir();(self.root/'raw/assets').mkdir(parents=True);self.state=self.root/'state';self.state.mkdir();self.a=self.root/'raw/assets/a.txt';self.a.write_text('same original');self.sha=hashlib.sha256(self.a.read_bytes()).hexdigest();self.index={'version':1,'assets':{'a':{'path':'raw/assets/a.txt','label':'a.txt','downloadable':True,'sensitive':False}},'files':[],'recordings':[],'conflicts':[]};(self.root/'tracking/material_library.json').write_text(json.dumps(self.index));self.saved={'path':'raw/assets/a.txt','sha256':self.sha,'annotation_revision':0,'customer_folder':'A','folder_id':'one','folder_title':'contract1','review_state':'来源已核对','placement':'current'};self.saved['source_fingerprint']=org.source_fingerprint(self.row());self.save()
 def save(self):
  (self.state/'material_organization.json').write_text(json.dumps({'version':1,'assets':{'a':self.saved}}))
 def row(self,aid='a',folder='one',scope='A'):
  return {'title':aid+'.txt','asset_id':aid,'revision':0,'customers':[scope],'project_titles':[],'file_state':'待核文件','annotation':{},'sources':[{'origin':aid}], 'organization':{**self.saved,'folder_id':folder}}
 def test_review_is_bound_to_actual_content_and_manual_revision(self):
  rows=[self.row()];org.apply(self.root,self.state,rows);self.assertEqual(rows[0]['organization']['review_state'],'来源已核对');self.a.write_text('new original');org.apply(self.root,self.state,rows);self.assertEqual(rows[0]['organization']['review_state'],'待重新核对');self.a.write_text('same original');rows[0]['revision']=1;org.apply(self.root,self.state,rows);self.assertEqual(rows[0]['organization']['review_state'],'待重新核对')
 def test_changed_identity_or_receipt_invalidates_saved_review(self):
  for key,value in [('project_ids',['another']),('customers',['B']),('sources',[{'origin':'new source'}])]:
   r=self.row();r[key]=value;org.apply(self.root,self.state,[r]);self.assertEqual(r['organization']['review_state'],'待重新核对');self.assertEqual(r['organization']['placement'],'current')
 def test_source_order_is_not_a_change(self):
  a=self.row();a['project_ids']=['p2','p1'];b={**a,'project_ids':['p1','p2','p1']};self.assertEqual(org.source_fingerprint(a),org.source_fingerprint(b))
 def test_legacy_unbound_review_is_not_trusted(self):
  self.saved.pop('source_fingerprint');self.save();r=self.row();org.apply(self.root,self.state,[r]);self.assertEqual(r['organization']['review_state'],'待重新核对')
 def test_dedupe_after_scope_does_not_bring_other_customer_sources(self):
  a=self.row('a');b=self.row('b');self.assertEqual(len(org.dedupe([a,b])),1);self.assertEqual(org.dedupe([a])[0]['sources'],[{'origin':'a'}]);self.assertEqual(len(org.dedupe([a,self.row('b','two','B')])),2)
 def test_same_title_different_content_kept(self):
  a=self.row();b=self.row('b');b['organization']['sha256']='another';self.assertEqual(len(org.dedupe([a,b])),2)
 def test_folders_count_before_pagination_and_history_is_recoverable(self):
  rows=[self.row(str(i)) for i in range(45)]
  for i,r in enumerate(rows):r['organization']['sha256']=str(i)
  rows[0]['organization']['placement']='history';visible,folders,hidden=org.folder_result(rows,{});self.assertEqual((len(visible),folders[0]['current'],folders[0]['history'],hidden),(44,44,1,1));self.assertEqual(len(org.folder_result(rows,{'include_history':'1'})[0]),45)
 def test_changed_replacement_reveals_old_original(self):
  self.saved.update(placement='history',superseded_by='missing');self.save();r=self.row();org.apply(self.root,self.state,[r]);self.assertEqual(r['organization']['placement'],'current')
 def test_symlink_never_inherits_review(self):
  self.a.unlink();self.a.symlink_to(self.state/'material_organization.json');r=self.row();org.apply(self.root,self.state,[r]);self.assertEqual(r['organization']['review_state'],'待重新核对')
if __name__=='__main__':unittest.main()
