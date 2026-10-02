import io, socket, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, Mock
from customer_branding import Branding, normalize
import brand_asset_fetcher as fetcher
from local_http import LocalError as VaultError
class BrandingPublicTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
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
