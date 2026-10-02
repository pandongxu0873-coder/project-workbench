import base64,hashlib,importlib.util,json,sys,unittest
from pathlib import Path
from email.message import EmailMessage
from unittest.mock import patch
import test_communication_pipeline as pipeline_tests
import material_receipts as receipts
import material_files as files

class FileChainTests(unittest.TestCase):
 setUp=pipeline_tests.PipelineTest.setUp
 tearDown=pipeline_tests.PipelineTest.tearDown
 def add(self,origin='imap://mail/INBOX/1#part0',raw=b'%PDF-1.4 synthetic'):
  entry=self.p.stage(origin,'一期合同.pdf',raw,'.pdf','email_attachment',origin,'2026-09-11',text='合同正文')
  entry['associations']=[{'project_id':self.pid,'customer':'客户甲','title':'项目甲'}]
  return entry
 def test_three_sources_one_original_preserves_receipts_and_repeat(self):
  a=self.add();self.add('imap://mail/INBOX/2#part0');self.add('wechat-local://chat/1#file')
  receipts.preserve(self.p);index=json.loads((self.k/'tracking/material_library.json').read_text())
  self.assertEqual(len(index['assets']),1);self.assertEqual(len(index['files']),3)
  self.assertFalse(receipts.preserve(self.p)['changed'])
  listing=files.listing(self.k,self.s,{'project_id':self.pid},[])
  self.assertEqual(listing['total'],1);self.assertEqual(len(listing['items'][0]['sources']),3)
  self.assertEqual(listing['items'][0]['file_state'],'待核文件')
 def test_same_filename_different_bytes_never_deduplicated(self):
  self.add();self.add('imap://mail/INBOX/2#part0',b'%PDF-1.4 different')
  receipts.preserve(self.p);self.assertEqual(files.listing(self.k,self.s,{},[])['total'],2)
 def test_real_mime_link_and_customer_quote_not_price_or_own_note(self):
  a=self.add();msg=EmailMessage();msg['From']='customer@client.example.test';msg['To']='sales@example.test';msg['Message-ID']='<confirmation>'
  quote='确认附件一期合同.pdf的合同文本内容。';msg.set_content(quote);msg.add_attachment(Path(a['original']).read_bytes(),maintype='application',subtype='pdf',filename='一期合同.pdf')
  entry=self.p.stage('sales@example.test/INBOX/1/3','客户邮件',msg.as_bytes(),'.eml','email','imap://mail/INBOX/3','2026-09-11',text=quote)
  row={'material_id':entry['id'],'classification':'project','project_id':self.pid,'business_date':'2026-09-11','evidence':[{'level':'customer_statement','quote':quote}]}
  receipts.preserve(self.p,{'items':[row]});out=files.listing(self.k,self.s,{},[])['items'][0]
  self.assertEqual(out['file_state'],'已确认材料');self.assertEqual(len(out['confirmation_events']),1)
  receipts.preserve(self.p,{'items':[row]});self.assertEqual(len(files.detail(self.k,out['asset_id'])['confirmation_events']),1)
  for text in ['价格确认，可以先启动。','合同内容还未确认。','收到','如果合同文本确认就可以启动','仅确认合同价格','我方确认合同文本']:
   if text.startswith('我方'):self.assertFalse(receipts.confirmation_quote({'evidence':[{'quote':text,'level':'internal_statement'}]}))
   else:self.assertFalse(receipts.confirmation_quote({'evidence':[{'quote':text,'level':'customer_statement'}]}))
 def test_upload_survives_source_deletion_and_idempotent_with_scope(self):
  from project_workspace import build_projects
  payload={'filename':'手动合同.pdf','project_id':self.pid,'content':base64.b64encode(b'%PDF-1.4 upload').decode(),'request_id':'file-upload-fixture-0001'}
  with patch('project_analysis.run_model',side_effect=AssertionError('model')):
   first=files.upload(self.k,self.s,payload,build_projects(self.k,self.s));again=files.upload(self.k,self.s,payload,build_projects(self.k,self.s))
  self.assertEqual(first['asset_id'],again['asset_id']);self.assertTrue(first['receipt']['original_saved']);self.assertFalse(first['receipt']['analysis_updated'])
  self.assertEqual(files.listing(self.k,self.s,{'project_id':self.pid},[])['total'],1)
  with self.assertRaises(Exception):files.upload(self.k,self.s,{**payload,'content':base64.b64encode(b'changed').decode()},build_projects(self.k,self.s))
 def test_original_saved_despite_extraction_failure(self):
  self.p.stage('badpdf','坏格式合同.pdf',b'nonparsable','.pdf','email_attachment','imap://mail/4#part0')
  receipts.preserve(self.p);out=files.listing(self.k,self.s,{},[])['items'][0]
  self.assertEqual(files.verified(self.k,out['asset_id'])[1],b'nonparsable')
 def test_wechat_exact_file_content_and_ambiguous_name(self):
  spec=importlib.util.spec_from_file_location('file_originals',Path(__file__).resolve().parents[1]/'wechat-local/file_originals.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  root=self.root/'account';folder=root/'msg/file';folder.mkdir(parents=True)
  (folder/'合同.pdf').write_bytes(b'correct');(folder/'合同 (1).pdf').write_bytes(b'wronggg')
  message={'details':{'file_md5':hashlib.md5(b'correct').hexdigest(),'file_size':7}}
  m.resolve(root,[message]);self.assertEqual(message['local_file']['sha256'],hashlib.sha256(b'correct').hexdigest())
  missing={'details':{'file_name':'合同.pdf','file_size':7}};m.resolve(root,[missing]);self.assertNotIn('local_file',missing)

 def test_withdrawal_and_phase_scope_do_not_leak(self):
  self.add();receipts.preserve(self.p)
  index=json.loads((self.k/'tracking/material_library.json').read_text());aid=next(iter(index['assets']));digest=index['assets'][aid]['sha256']
  event={'id':'one','sha256':digest,'project_id':self.pid,'business_date':'2026-09-10','confirmation':'客户认可文本'}
  index['assets'][aid]['confirmation_events']=[event]
  index['files'].append({**index['files'][0],'id':'phase2','project_id':'phase2'})
  (self.k/'tracking/material_library.json').write_text(json.dumps(index))
  self.assertEqual(files.listing(self.k,self.s,{'project_id':'phase2'},[])['items'][0]['file_state'],'待核文件')
  index['assets'][aid]['confirmation_events'].append({**event,'id':'withdrawn','business_date':'2026-09-11','confirmation':'已撤回'})
  (self.k/'tracking/material_library.json').write_text(json.dumps(index))
  self.assertEqual(files.listing(self.k,self.s,{'project_id':self.pid},[])['items'][0]['file_state'],'待核文件')
 def test_tampered_original_cannot_keep_confirmation(self):
  a=self.add();receipts.preserve(self.p);index=json.loads((self.k/'tracking/material_library.json').read_text());aid=next(iter(index['assets']))
  index['assets'][aid]['confirmation_events']=[{'id':'one','sha256':a['sha256'],'project_id':self.pid,'business_date':'2026-09-10','confirmation':'客户认可文本'}]
  (self.k/'tracking/material_library.json').write_text(json.dumps(index));(self.k/index['assets'][aid]['path']).write_bytes(b'changed')
  self.assertEqual(files.listing(self.k,self.s,{},[])['items'][0]['file_state'],'待核文件')
 def test_new_draft_does_not_replace_confirmed_and_signed_scan_is_separate(self):
  a=self.add();receipts.preserve(self.p);index=json.loads((self.k/'tracking/material_library.json').read_text());aid=next(iter(index['assets']))
  index['assets'][aid]['confirmation_events']=[{'id':'one','sha256':a['sha256'],'project_id':self.pid,'business_date':'2026-09-10','confirmation':'客户认可文本'}]
  (self.k/'tracking/material_library.json').write_text(json.dumps(index))
  self.add('imap://mail/INBOX/9#part0',b'%PDF-1.4 newer draft');self.add('imap://mail/INBOX/10#part0',b'%PDF-1.4 signed scan')
  receipts.preserve(self.p);rows=files.listing(self.k,self.s,{},[])['items']
  self.assertEqual(len(rows),3);self.assertEqual(sum(r['file_state']=='已确认材料' for r in rows),1)
 def test_existing_review_commit_and_file_receipt_share_one_asset(self):
  from tools import communication_pipeline as pipeline
  a=self.add();receipts.preserve(self.p)
  msg=EmailMessage();msg['From']='customer@client.test';msg['To']='sales@company.test';msg.set_content('确认附件合同文本内容。');msg.add_attachment(Path(a['original']).read_bytes(),maintype='application',subtype='pdf',filename='一期合同.pdf')
  entry=self.p.stage('sales@company.test/INBOX/1/4','客户邮件',msg.as_bytes(),'.eml','email','imap://mail/INBOX/4','2026-09-11',text='确认附件合同文本内容。')
  rows=[]
  for item in (a,entry):
   rows.append({'material_id':item['id'],'source_id':item['id']+':0','classification':'project','project_id':self.pid,'summary':'材料核对','business_date':'2026-09-11','date_quote':'','next_action':'','uncertainties':[], 'evidence':[{'level':'customer_statement' if item is entry else 'document_text','quote':'确认附件合同文本内容。' if item is entry else '合同正文','meaning':'文本依据'}]})
  review={'completed':[a['id'],entry['id']],'items':rows,'projects':pipeline.project_catalog(self.k,self.s)}
  pipeline.apply_review(self.p,review);receipts.preserve(self.p,review)
  result=files.listing(self.k,self.s,{'project_id':self.pid},review['projects'])
  self.assertEqual(result['total'],1);self.assertEqual(result['items'][0]['file_state'],'已确认材料')
  before=(self.k/'tracking/material_library.json').read_bytes();pipeline.apply_review(self.p,review);receipts.preserve(self.p,review)
  self.assertEqual((self.k/'tracking/material_library.json').read_bytes(),before)

 def test_stalled_analysis_still_collects_once_daily_without_reset(self):
  from unittest.mock import Mock
  import background_operations as bg
  job={'next_epoch':0,'recovery_attempts':3,'awaiting_result':True}
  (self.s/'background_operations.json').write_text(json.dumps({'jobs':{'communications':job}}))
  mock=Mock();mock.status.return_value={'job':{'running':False,'state':'completed'},'receipt':{'refresh_pending':['p1']}}
  mock.start.return_value={'started':True,'job':{'request_id':'collect-1'}}
  bg.run_once(self.s,self.k,clock=lambda:1790632800,communications=mock)
  mock.start.assert_called_once_with({'action':'collect'},self.s,self.k)
  saved=json.loads((self.s/'background_operations.json').read_text())['jobs']['communications'];self.assertEqual(saved['recovery_attempts'],3)
  mock.reset_mock();bg.run_once(self.s,self.k,clock=lambda:1790636401,communications=mock);mock.start.assert_not_called()
