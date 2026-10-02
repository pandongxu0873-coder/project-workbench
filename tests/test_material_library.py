import json,tempfile,unittest,threading,http.client
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import material_library as m
class MaterialTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'kb';(self.root/'tracking').mkdir(parents=True);(self.root/'raw').mkdir();(self.root/'raw/笔记.md').write_text('正文');(self.root/'raw/音频.m4a').write_bytes(b'0123456789');self.idx={'assets':{'txt':{'path':'raw/笔记.md','label':'笔记','kind':'text','readable':True,'downloadable':True},'audio':{'path':'raw/音频.m4a','kind':'audio','downloadable':True},'missing':{'path':'raw/missing.txt','readable':True},'secret':{'path':'raw/笔记.md','sensitive':True,'readable':True,'downloadable':True}},'recordings':[{'id':'VM-001','sources':[{'id':'audio','available':False},{'id':'missing','available':True},{'id':'secret'}]}],'files':[],'conflicts':[],'summary':{'reviewed_count':1,'moved_count':108}};self.save();root=self.root
  class H(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def _trusted_origin(self):return self.headers.get('Origin','') in ('','http://localhost')
   def do_GET(self):m.handle(self,root)
   def do_HEAD(self):m.handle(self,root)
  self.server=ThreadingHTTPServer(('127.0.0.1',0),H);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def save(self):(self.root/'tracking/material_library.json').write_text(json.dumps(self.idx))
 def request(self,path,method='GET',headers=None):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port);c.request(method,path,headers=headers or {});r=c.getresponse();result=(r.status,dict(r.getheaders()),r.read());c.close();return result
 def test_public_index_caps_from_readback(self):
  x=m.library(self.root);self.assertNotIn('assets',x);s=x['recordings'][0]['sources'];self.assertTrue(s[0]['available']);self.assertFalse(s[1]['available']);self.assertFalse(s[2]['available']);self.assertNotIn('path',s[0]);self.assertEqual(x['summary']['moved_count'],108)
 def test_verified_association_replaces_old_unassigned_label_without_rewriting_original(self):
  from unittest.mock import patch
  ident='a'*64;state=Path(self.tmp.name)/'state';(state/'communication_pipeline').mkdir(parents=True)
  (state/'communication_pipeline/ledger.json').write_text(json.dumps({'items':{ident:{'status':'archived','associations':[{'project_id':'p1','title':'项目甲','customer':'客户甲'}]}}}))
  self.idx['files']=[{'id':'REF-'+ident[:20],'title':'方案','category':'已归档 · 项目归属待核','sources':['txt']}];self.save();before=(self.root/'tracking/material_library.json').read_bytes()
  with patch('material_collectors.start_due'):
   row=m.library(self.root,state)['files'][0]
  self.assertEqual(row['category'],'项目关联已补齐');self.assertEqual(row['project_id'],'p1')
  self.assertEqual((self.root/'tracking/material_library.json').read_bytes(),before)
 def test_text_and_limits(self):
  self.assertEqual(m.source(self.root,'txt')['content'],'正文');(self.root/'raw/笔记.md').write_text('中'*100000);x=m.source(self.root,'txt');self.assertTrue(x['truncated']);self.assertLessEqual(len(x['content']),m.MAX_SOURCE_CHARS)
 def test_allowlist_and_sensitive_and_missing(self):
  for id,code in [('unknown',404),('secret',403),('missing',404),('audio',403)]:
   self.assertEqual(self.request('/api/material-library/source?asset_id='+id)[0],code)
  self.assertEqual(self.request('/api/material-library/file?asset_id=secret')[0],403)
 def test_traversal_absolute_and_symlink(self):
  outside=Path(self.tmp.name)/'outside.txt';outside.write_text('secret');(self.root/'raw/link.txt').symlink_to(outside)
  for value in ['../outside.txt',str(outside),'raw/link.txt']:
   self.idx['assets']['bad']={'path':value,'readable':True,'downloadable':True};self.save();self.assertEqual(self.request('/api/material-library/source?asset_id=bad')[0],403)
  (self.root/'escape').symlink_to(Path(self.tmp.name),target_is_directory=True);self.idx['assets']['bad']['path']='escape/outside.txt';self.save();self.assertEqual(self.request('/api/material-library/file?asset_id=bad')[0],403)
 def test_full_and_range(self):
  s,h,b=self.request('/api/material-library/file?asset_id=audio');self.assertEqual((s,b),(200,b'0123456789'));self.assertEqual(h['Content-Type'],'audio/mp4');self.assertIn("filename*=UTF-8''",h['Content-Disposition'])
  for header,want in [('bytes=2-5',b'2345'),('bytes=7-',b'789'),('bytes=-3',b'789'),('bytes=8-99',b'89')]:
   s,h,b=self.request('/api/material-library/file?asset_id=audio',headers={'Range':header});self.assertEqual((s,b),(206,want));self.assertEqual(int(h['Content-Length']),len(want))
 def test_416_and_head(self):
  for h in ['bytes=99-','bytes=5-2','bytes=-0','bytes=0-1,3-4','bad']:
   s,headers,b=self.request('/api/material-library/file?asset_id=audio',headers={'Range':h});self.assertEqual(s,416);self.assertEqual(headers['Content-Range'],'bytes */10');self.assertEqual(b,b'')
  s,h,b=self.request('/api/material-library/file?asset_id=audio','HEAD',{'Range':'bytes=2-5'});self.assertEqual(s,206);self.assertEqual(h['Content-Length'],'4');self.assertEqual(b,b'')
  self.assertEqual(self.request('/api/material-library/source?asset_id=txt','HEAD')[2],b'')
 def test_origin_and_empty_range(self):
  self.assertEqual(self.request('/api/material-library',headers={'Origin':'http://evil.example'})[0],403);(self.root/'raw/音频.m4a').write_bytes(b'');self.assertEqual(self.request('/api/material-library/file?asset_id=audio')[0],200);self.assertEqual(self.request('/api/material-library/file?asset_id=audio',headers={'Range':'bytes=0-'})[0],416)
 def test_index_missing_invalid_and_download_disabled(self):
  self.assertEqual(self.request('/api/material-library/file?asset_id=missing')[0],403);(self.root/'tracking/material_library.json').write_text('{');self.assertEqual(self.request('/api/material-library')[0],503);(self.root/'tracking/material_library.json').unlink();self.assertEqual(self.request('/api/material-library')[0],503)
 def test_archive_growth_above_eight_mib_remains_readable(self):
  self.idx['archive_note']='x'*(8*1024*1024);self.save()
  self.assertEqual(m.load_index(self.root)['archive_note'],self.idx['archive_note'])
  self.assertEqual(m.library(self.root)['recordings'][0]['id'],self.idx['recordings'][0]['id'])
 def test_archive_size_remains_bounded(self):
  (self.root/'tracking/material_library.json').write_bytes(b' '*(m.MAX_INDEX_BYTES+1))
  self.assertEqual(self.request('/api/material-library')[0],503)
 def test_valid_json_corruption_fails_closed(self):
  self.idx['assets']['bad']='not-an-object';self.save();self.assertEqual(self.request('/api/material-library')[0],503)
  self.idx['assets'].pop('bad');self.idx['recordings']=['bad-row'];self.save();self.assertEqual(self.request('/api/material-library')[0],503)
if __name__=='__main__':unittest.main()
