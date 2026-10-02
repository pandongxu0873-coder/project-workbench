import copy,hashlib,io,json,shutil,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import material_files as files
import material_library
import project_analysis as ai
import project_rounds
from project_workspace import build_projects

class IncrementalV2Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.k=self.root/'kb';self.s=self.root/'state'
  for folder in ('projects','tracking','raw/assets'): (self.k/folder).mkdir(parents=True)
  for phase in ('一期','二期'):(self.k/'projects'/f'{phase}.md').write_text(f'# 澄明零售{phase}\n客户：[[澄明零售]]\n## 当前判断\n按本项目范围处理\n')
  self.projects=build_projects(self.k,self.s);self.p,self.q=[x['id'] for x in self.projects]
  self.raw=b'%PDF-1.4\nsynthetic contract phase 1\n%%EOF';self.raw2=b'%PDF-1.4\nsynthetic contract phase 2\n%%EOF'
  (self.k/'raw/assets/一期最终版.pdf').write_bytes(self.raw);(self.k/'raw/assets/二期最终版.pdf').write_bytes(self.raw2)
  self.index={'assets':{'one':{'path':'raw/assets/一期最终版.pdf','downloadable':True,'kind':'document'},'two':{'path':'raw/assets/二期最终版.pdf','downloadable':True,'kind':'document'}},'files':[{'id':'receipt1','title':'一期合同','customer':'澄明零售','project_id':self.p,'sources':['one'],'summary':'合同编号 CM-001'}, {'id':'receipt2','title':'二期合同','customer':'澄明零售','project_id':self.q,'sources':['two']},{'id':'receipt3','title':'另一次邮件接收一期合同','customer':'澄明零售','project_id':self.p,'sources':['one']}],'recordings':[]}
  (self.k/'tracking/material_library.json').write_text(json.dumps(self.index))
 def annotation(self,**extra):
  return {'asset_id':'one','sha256':hashlib.sha256(self.raw).hexdigest(),'revision':0,'project_ids':[self.p],'version_label':'V1','confirmation':'客户认可文本','basis':'合成客户邮件明确确认附件哈希','scope':'仅一期','kind':'合同与补充协议','request_id':'annotation-request-001',**extra}
 def test_crm_legal_subject_uses_linked_project_scope_without_copy(self):
  q={'customer':'澄明零售有限公司','project_ids':self.p}
  listing=files.listing(self.k,self.s,q,self.projects)
  self.assertEqual([x['asset_id'] for x in listing['items']],['one'])
  self.assertEqual(len(listing['items'][0]['sources']),2)
  self.assertEqual(files.listing(self.k,self.s,{**q,'project_id':self.q},self.projects)['total'],0)
  bundle=files.export_files(self.k,self.s,q,self.projects)
  with zipfile.ZipFile(io.BytesIO(bundle)) as z:
   originals=[n for n in z.namelist() if n.endswith('.pdf')]
   self.assertEqual(len(originals),1)
   self.assertEqual(z.read(originals[0]),self.raw)
 def test_same_original_receipts_and_phase_scope(self):
  listing=files.listing(self.k,self.s,{'project_id':self.p},self.projects)
  self.assertEqual(len(listing['items']),1);self.assertEqual(len(listing['items'][0]['sources']),2)
  self.assertEqual(listing['items'][0]['annotation'],{})
  self.assertEqual(files.detail(self.k,'one')['annotation'],{}) # filename final proves nothing
  self.assertEqual(files.listing(self.k,self.s,{'q':'CM-001'},self.projects)['total'],1)
 def test_version_confirmation_retry_conflict_and_changed_bytes(self):
  value=files.annotate(self.k,self.annotation(),self.projects);self.assertEqual(value['revision'],1)
  self.assertEqual(files.annotate(self.k,self.annotation(),self.projects)['revision'],1)
  with self.assertRaises(material_library.MaterialError):files.annotate(self.k,self.annotation(request_id='annotation-request-002'),self.projects)
  (self.k/'raw/assets/一期最终版.pdf').write_bytes(self.raw2)
  self.assertTrue(files.detail(self.k,'one')['changed_content']);self.assertEqual(files.detail(self.k,'one')['annotation'],{})
 def test_export_restore_sources_versions_hash_and_no_extra_copy(self):
  files.annotate(self.k,self.annotation(),self.projects)
  before=sorted(str(x) for x in self.k.rglob('*'))
  raw=files.export_files(self.k,self.s,{'customer':'澄明零售'},self.projects)
  self.assertEqual(before,sorted(str(x) for x in self.k.rglob('*')))
  restored=self.root/'restore';restored.mkdir()
  with zipfile.ZipFile(io.BytesIO(raw)) as z:z.extractall(restored)
  self.assertEqual(files.detail(restored,'one')['sha256'],hashlib.sha256(self.raw).hexdigest())
  self.assertEqual(files.detail(restored,'one')['annotation']['scope'],'仅一期')
  self.assertEqual(files.listing(restored,None,{'project_id':self.p},self.projects)['total'],1)
  self.assertEqual(len(files.listing(restored,None,{'project_id':self.p},self.projects)['items'][0]['sources']),2)
  # Original external source no longer exists; existing managed original remains usable.
  source=self.root/'download.pdf';source.write_bytes(self.raw);source.unlink();self.assertEqual(files.verified(self.k,'one')[1],self.raw)
 def test_restricted_and_traversal_never_exported(self):
  self.index['assets']['two']['restricted']=True;(self.k/'tracking/material_library.json').write_text(json.dumps(self.index))
  self.assertEqual(files.listing(self.k,self.s,{},self.projects)['total'],1)
  with self.assertRaises(material_library.MaterialError):files.verified(self.k,'two')
  with self.assertRaises(material_library.MaterialError):files.detail(self.k,'../../etc/passwd')
 def test_browsing_has_no_collector_or_model_side_effect(self):
  with patch('material_collectors.start_due',side_effect=AssertionError('collection')),patch('project_analysis.run_model',side_effect=AssertionError('model')):
   material_library.library(self.k,self.s);files.listing(self.k,self.s,{},self.projects)
 def test_body_only_progress_idempotent_does_not_reset_arrangement(self):
  record={x:'' for x in project_rounds.FIELDS};record.update(scenario='return',relationship='no_contact',status='暂停跟进',facts='保留原约定',contact='原联系人',due='2027-01-01')
  prior=project_rounds.save_round({'project_id':self.p,'revision':0,**record},self.k,self.s)
  payload={'project_id':self.p,'text':'内部补充：合同仅适用于一期。','request_id':'progress-request-00001'}
  with patch('project_analysis.run_model',side_effect=AssertionError('model')),patch('project_analysis.dispatch_pending',side_effect=AssertionError('dispatch')):
   saved=ai.save_progress(payload,self.k,self.s);again=ai.save_progress(payload,self.k,self.s)
  self.assertEqual(saved,again);self.assertEqual(len(ai.progress_records(self.p,self.k,self.s)['items']),1)
  self.assertEqual(project_rounds.read_round(self.p,self.k,self.s),prior)
  self.assertEqual(ai.read_cache(self.s,self.p)['correction_history'][0]['text'],payload['text'])
 def test_failed_progress_write_does_not_claim_success(self):
  with patch('project_analysis.write_cache',side_effect=OSError('disk full')):
   with self.assertRaises(OSError):ai.save_progress({'project_id':self.p,'text':'正文','request_id':'progress-request-00002'},self.k,self.s)
  self.assertEqual(ai.progress_records(self.p,self.k,self.s)['items'],[])
 def test_completed_proposal_does_not_suspend_payment(self):
  item={'action':'核对一期回款到账','evidence':[{'path':'raw/payment.md','quote':'应于本周到账'}],'owner':'财务'}
  value={'brief':{'next_action':'再次发送方案','attention':'可推进'},'next_action':'再次发送方案','draft':'对外话术','understanding':{'interventions':[item,{'action':'重新提交方案','evidence':[{'path':'raw/proposal.md'}]}]}}
  result=ai.guarded(value,{'quick_action':'发送方案','status':'已发出等待反馈'},'done_waiting')
  self.assertEqual(result['next_action'],item['action']);self.assertEqual(result['understanding']['interventions'][0],item)
  self.assertNotEqual(result['understanding']['interventions'][1]['action'],'重新提交方案')
  self.assertEqual(value['next_action'],'再次发送方案')
 def test_metadata_write_failure_keeps_prior_version(self):
  first=files.annotate(self.k,self.annotation(),self.projects)
  with patch('material_files.os.replace',side_effect=OSError('disk full')):
   with self.assertRaises(OSError):files.annotate(self.k,self.annotation(revision=1,request_id='annotation-request-003',confirmation='已签署'),self.projects)
  self.assertEqual(files.detail(self.k,'one')['annotation'],first['annotation'])
 def test_missing_original_and_extracted_text_search(self):
  (self.k/'raw/assets/二期最终版.pdf').unlink()
  rows=files.listing(self.k,self.s,{},self.projects)['items'];self.assertFalse(next(x for x in rows if x['asset_id']=='two')['available'])
  (self.k/'raw/extracted.txt').write_text('独有的验收编号 CM-2027-09')
  self.index['assets']['text']={'path':'raw/extracted.txt','readable':True};self.index['files'][0]['sources'].append('text')
  (self.k/'tracking/material_library.json').write_text(json.dumps(self.index))
  found=files.listing(self.k,self.s,{'q':'CM-2027-09'},self.projects)['items'];self.assertTrue(any(x['asset_id']=='one' for x in found))
 def test_annotation_only_flows_to_already_permitted_source(self):
  files.annotate(self.k,self.annotation(),self.projects)
  self.assertEqual(files.analysis_annotations(self.k,self.p,[]),[])
  rows=files.analysis_annotations(self.k,self.p,[{'path':'raw/assets/一期最终版.pdf'}]);self.assertEqual(len(rows),1);self.assertIn('仅一期',rows[0]['content'])
 def test_renamed_duplicate_material_does_not_notify_and_stage_change_does(self):
  import project_notifications as notifications
  p={'id':self.p,'sources':[{'path':'raw/a.md','content_sha256':'same','relation':'explicit_evidence'}],'notification_state':{'decision':{'stage':'方案验证','attention':'可推进'}}}
  notifications.observe([p],self.s,1)
  p['sources'].append({'path':'raw/copy.md','content_sha256':'same','relation':'explicit_evidence'})
  notifications.observe([p],self.s,2);self.assertEqual(notifications.listing(self.s)['unread_count'],0)
  p['notification_state']['decision']['attention']='等反馈';notifications.observe([p],self.s,3)
  self.assertEqual(notifications.listing(self.s)['items'][0]['changes'][0]['kind'],'decision')
 def test_original_detail_skips_unrelated_project_scan(self):
  from types import SimpleNamespace
  handler=SimpleNamespace(path='/api/material-library/files/detail?asset_id=one',headers={'Host':'127.0.0.1:9999'},server=SimpleNamespace(server_port=9999),command='GET',_trusted_origin=lambda:True,wfile=io.BytesIO(),send_response=lambda code:None,send_header=lambda *a:None,end_headers=lambda:None)
  with patch('project_workspace.build_projects',side_effect=AssertionError('unrelated scan')):
   self.assertTrue(files.handle(handler,self.k,self.s))
  value=json.loads(handler.wfile.getvalue());self.assertEqual(value['sha256'],hashlib.sha256(self.raw).hexdigest());self.assertEqual(value['original_status'],'原件已读取并校验')
