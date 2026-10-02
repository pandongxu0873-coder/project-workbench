"""Synthetic-only regression: extraction, conflict boundaries and branding failures."""
import sys,io,tempfile,unittest,json,socket,subprocess
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from invoice_vault import Vault,VaultError,MAX_FILE
from invoice_extraction import inspect
from customer_branding import Branding,normalize
import brand_asset_fetcher as fetcher
class LocalRegression(unittest.TestCase):
 def setUp(self):self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name);self.v=Vault(self.root)
 def tearDown(self):self.t.cleanup()
 def pdf(self,scan=False,password=False):
  import fitz
  d=fitz.open();p=d.new_page()
  if not scan:p.insert_text((40,40),'发票号码：000012345678\n开票日期：2026年09月26日',fontname='china-s')
  raw=d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256,owner_pw='synthetic',user_pw='synthetic') if password else d.tobytes();d.close();return raw
 def test_native_scan_password_damaged_and_manual_sources(self):
  r=self.v.upload('synthetic.pdf',self.pdf())['items'][0]
  self.assertEqual(r['number'],'000012345678');self.assertEqual(r['review'],'pending');self.assertEqual(r['field_sources']['number']['page'],1)
  r=self.v.mutate(r['id'],'update',{'request_id':'manual-change','expected_revision':1,'fields':{'amount':'1.20','number':r['number']}})['item']
  self.assertEqual(r['field_sources']['number']['source'],'native_pdf_text');self.assertEqual(r['field_sources']['amount']['source'],'manual')
  for raw in [self.pdf(scan=True),self.pdf(password=True),b'%PDF-1.4 broken']:
   item=self.v.upload('synthetic.pdf',raw)['items'][0];self.assertEqual(item['file_state'],'unrecognized');self.assertEqual(self.v.asset(item['asset_id'])[0].read_bytes(),raw)
  with self.assertRaises(VaultError):self.v.mutate(r['id'],'split',{'request_id':'invalid-pages','expected_revision':2,'pages':'2'})
 def test_limits_fake_images_and_export_membership(self):
  for raw in [b'%PDF-'+b'x'*MAX_FILE,b'\x89PNG\r\n\x1a\nnot-image']:
   with self.assertRaises(VaultError):self.v.upload('fake.pdf',raw)
  r=self.v.upload('synthetic.pdf',self.pdf())['items'][0];b=self.v.batch(None,'create',{'request_id':'batch-create','name':'合成'})['item']
  with self.assertRaises(VaultError):self.v.export({'ids':[r['id']],'record_revisions':{r['id']:1}},b['id'])
  with self.assertRaises(VaultError):self.v.batch(b['id'],'items',{'request_id':'batch-remove','expected_revision':1,'ids':[r['id']],'record_revisions':{r['id']:1},'remove':True})
 def test_interrupted_db_save_does_not_report_success_and_retry_recovers(self):
  raw=self.pdf()
  with patch('invoice_vault.subprocess.run',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):self.v.upload('synthetic.pdf',raw)
  self.assertEqual(self.v.listing({})['total'],0)
  self.assertEqual(self.v.upload('retry.pdf',raw)['items'][0]['file_state'],'read')
 def test_image_20mp_vault_limit_separate_from_logo(self):
  from PIL import Image
  buf=io.BytesIO();Image.new('RGB',(2400,2400),'white').save(buf,'PNG');raw=buf.getvalue()
  self.assertTrue(self.v.upload('synthetic.png',raw)['ok'])
  with self.assertRaises(VaultError):normalize(raw)
 def test_brand_candidates_select_reject_undo_idempotency(self):
  from PIL import Image
  buf=io.BytesIO();Image.new('RGB',(32,32),'blue').save(buf,'PNG');raw=buf.getvalue();b=Branding(self.root)
  def args(n,**kw):return {'entity_id':'customer:合成','expected_revision':n,'request_id':'request-%d'%n,'confirm_identity':True,'domain':'example.com',**kw}
  with patch.object(fetcher,'discover',return_value=[{'url':'https://example.com/logo.png','source':'官网Logo候选'}]),patch.object(fetcher,'fetch',return_value=(raw,'image/png')):
   r=b.mutate('discover',args(0))['item']
  self.assertIsNone(r['asset_hash']);h=r['candidates'][0]['asset_hash']
  with self.assertRaises(VaultError):b.mutate('select',args(1,confirm_identity=False,asset_hash=h))
  r=b.mutate('select',args(1,asset_hash=h))['item'];self.assertTrue(r['locked'])
  self.assertEqual(b.mutate('select',args(1,asset_hash=h))['item'],r)
  r=b.mutate('reset',args(2))['item'];self.assertIsNone(r['asset_hash'])
  r=b.mutate('undo',args(3))['item'];self.assertEqual(r['asset_hash'],h)
  b.mutate('select',args(4,reject=h))
  with self.assertRaises(VaultError):b.mutate('select',args(5,asset_hash=h))
 def test_brand_private_redirect_404_timeout_fake_and_huge(self):
  with patch.object(socket,'getaddrinfo',return_value=[(2,1,6,'',('169.254.169.254',443))]):
   with self.assertRaises(VaultError):fetcher._fetch('https://example.com/logo','example.com')
  for status in [302,404]:
   with patch.object(socket,'getaddrinfo',return_value=[(2,1,6,'',('93.184.216.34',443))]),patch('http.client.HTTPSConnection.request'),patch('http.client.HTTPSConnection.getresponse',return_value=Mock(status=status)),patch('http.client.HTTPSConnection.close'):
    with self.assertRaises(VaultError):fetcher._fetch('https://example.com/logo','example.com')
  with patch.object(subprocess,'run',side_effect=subprocess.TimeoutExpired('worker',8)):
   with self.assertRaises(VaultError):fetcher.fetch('https://example.com','example.com')
  for raw in [b'<svg><script/></svg>',b'\x89PNG\r\n\x1a\nfake',b'x'*(3*1024*1024+1)]:
   with self.assertRaises(VaultError):normalize(raw)
if __name__=='__main__':unittest.main()
