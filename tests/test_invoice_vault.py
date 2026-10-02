import io,sys,tempfile,unittest,zipfile,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from invoice_vault import Vault,VaultError
from customer_branding import Branding,normalize
from unittest.mock import patch
from decimal import Decimal
class VaultTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.v=Vault(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def upload(self,extra=b''):
  return self.v.upload('合成测试.pdf',b'%PDF-1.4\nSYNTHETIC NOT A REAL INVOICE'+extra)['items'][0]
 def update(self,r,fields,request='request-123'):
  return self.v.mutate(r['id'],'update',{'request_id':request,'expected_revision':r['revision'],'fields':fields})['item']
 def test_original_duplicate_restart(self):
  raw=b'%PDF-1.4\nSYNTHETIC';r=self.v.upload('../../测试.pdf',raw)['items'][0]
  self.assertEqual(self.v.asset(r['asset_id'])[0].read_bytes(),raw)
  self.assertTrue(self.v.upload('other.pdf',raw)['duplicate']);self.assertEqual(Vault(self.temp.name).listing({})['total'],1)
  self.assertEqual(r['display_name'],'测试.pdf')
 def test_revision_and_idempotency(self):
  r=self.upload();a=self.update(r,{'number':'00001234','amount':'0.10','review':'confirmed'});b=self.update(r,{'number':'00001234','amount':'0.10','review':'confirmed'})
  self.assertEqual(a,b)
  with self.assertRaises(VaultError):self.update(r,{'amount':'2'},'request-new')
 def test_precise_currency_and_pending(self):
  a=self.update(self.upload(b'1'),{'amount':'0.10','review':'confirmed'},'request-a')
  b=self.update(self.upload(b'2'),{'amount':'0.20','review':'confirmed'},'request-b')
  self.update(self.upload(b'3'),{'amount':'10.00','currency':'USD','review':'confirmed'},'request-c')
  self.update(self.upload(b'4'),{'amount':'100'},'request-d')
  self.assertEqual(self.v.listing({})['totals'],{'CNY':'0.30','USD':'10.00'})
 def test_batch_conflict_export_trash_split(self):
  r=self.update(self.upload(),{'number':'001','amount':'12.30','review':'confirmed','note':'=HYPERLINK("bad")'},'request-edit')
  b=self.v.batch(None,'create',{'request_id':'create-batch','name':'合成验收批次'})['item']
  self.v.batch(b['id'],'items',{'request_id':'add-items','expected_revision':b['revision'],'ids':[r['id']],'record_revisions':{r['id']:r['revision']}})
  with self.v.db() as db:r=self.v.one(db,r['id'])
  c=self.v.batch(None,'create',{'request_id':'create-other','name':'另一批次'})['item']
  with self.assertRaises(VaultError):self.v.batch(c['id'],'items',{'request_id':'move-items','expected_revision':1,'ids':[r['id']],'record_revisions':{r['id']:r['revision']}})
  split=self.v.mutate(r['id'],'split',{'request_id':'split-new','expected_revision':r['revision'],'pages':'2'})['item']
  ids=[r['id'],split['id']];payload={'ids':ids,'record_revisions':{r['id']:r['revision'],split['id']:split['revision']}}
  self.assertTrue(self.v.export(payload)['confirmation_required']);raw,_,_=self.v.export({**payload,'acknowledge_warnings':True})
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   self.assertEqual(len(z.namelist()),2);self.assertIn("'=HYPERLINK",z.read('清单.csv').decode('utf-8-sig'))
  t=self.v.mutate(r['id'],'trash',{'request_id':'trash-record','expected_revision':r['revision']})['item'];self.assertTrue(t['trash'])
  restored=self.v.mutate(r['id'],'restore',{'request_id':'restore-record','expected_revision':t['revision']})['item'];self.assertEqual(restored['batch_id'],b['id'])
 def test_format_boundaries(self):
  for raw in [b'<html>bad</html>',b'MZexe']:
   with self.assertRaises(VaultError):self.v.upload('fake.pdf',raw)
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:z.writestr('OFD.xml','<OFD/>')
  r=self.v.upload('合成.ofd',out.getvalue())['items'][0];self.assertEqual(r['format'],'ofd')
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:z.writestr('OFD.xml','<OFD/>');z.writestr('../escape','bad')
  with self.assertRaises(VaultError):self.v.upload('bad.ofd',out.getvalue())
 def test_invalid_amount_and_pages(self):
  for x in ['NaN','Infinity','1.123']:
   with self.assertRaises(VaultError):self.v.validate({'amount':x})
  with self.assertRaises(VaultError):self.v.validate({'pages':'3-1'})
 def test_no_network_basic_flow(self):
  with patch('socket.create_connection',side_effect=AssertionError('network forbidden')):
   r=self.upload();self.update(r,{'amount':'1.00','review':'confirmed'});self.v.listing({})
class BrandTests(unittest.TestCase):
 def test_lock_failure_reset_and_conflict(self):
  from PIL import Image
  with tempfile.TemporaryDirectory() as root:
   b=Branding(root);buf=io.BytesIO();Image.new('RGB',(24,24),'blue').save(buf,'PNG');body={'entity_id':'account:sample','request_id':'request-upload','expected_revision':0,'project_ids':['stable-project']}
   r=b.mutate('upload',body,buf.getvalue())['item'];self.assertTrue(r['locked'])
   with patch('brand_asset_fetcher.discover',side_effect=ValueError('offline')):
    r=b.mutate('discover',{**body,'request_id':'request-fetch','expected_revision':1,'confirm_identity':True,'domain':'example.com'})['item']
   self.assertEqual(r['fetch_status'],'failed');self.assertTrue(r['asset_hash']);self.assertTrue(r['locked'])
   with self.assertRaises(VaultError):b.mutate('reset',{**body,'request_id':'request-reset'})
   self.assertFalse(b.mutate('reset',{**body,'request_id':'request-reset','expected_revision':2})['item']['asset_hash'])
 def test_ssrf_and_svg(self):
  import brand_asset_fetcher
  with self.assertRaises(VaultError):normalize(b'<svg/>')
  for url,domain in [('http://example.com','example.com'),('https://localhost','localhost'),('https://127.0.0.1','127.0.0.1'),('https://example.com:22','example.com')]:
   with self.assertRaises(VaultError):brand_asset_fetcher.fetch(url,domain)
if __name__=='__main__':unittest.main()
