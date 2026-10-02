import sys,tempfile,unittest,json,io,threading,http.client
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import local_resources
class ResourceRoutes(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
  class H(BaseHTTPRequestHandler):
   def _send_json(self,p,status=200):
    raw=json.dumps(p).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
   def do_GET(self):local_resources.handle(self,root)
   def do_POST(self):local_resources.handle(self,root)
   def log_message(self,*args):pass
  self.server=ThreadingHTTPServer(('127.0.0.1',0),H);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
 def request(self,method,path,body=None,headers=None):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port);c.request(method,path,body=body,headers=headers or {});r=c.getresponse();data=r.read();code=r.status;c.close();return code,data
 def test_reads_no_creation_and_cross_site(self):
  self.assertEqual(self.request('GET','/api/invoices')[0],200);self.assertFalse((Path(self.temp.name)/'invoice_vault').exists())
  self.assertEqual(self.request('GET','/api/invoices',headers={'Host':'evil.example','Sec-Fetch-Site':'cross-site'})[0],403)
  self.assertEqual(self.request('POST','/api/reimbursement-batches','{}',{'Content-Type':'application/json'})[0],403)
  self.assertEqual(self.request('POST','/api/reimbursement-batches','{}',{'X-Workbench-Request':'local-v1','Origin':'https://evil.example'})[0],403)
 def test_path_and_revision_contract(self):
  h={'Content-Type':'application/json','X-Workbench-Request':'local-v1'}
  code,raw=self.request('POST','/api/reimbursement-batches',json.dumps({'name':'合成','request_id':'request-create'}),h);self.assertEqual(code,200);item=json.loads(raw)['item']
  self.assertEqual(self.request('POST',f"/api/reimbursement-batches/{item['id']}/update",json.dumps({'name':'changed','request_id':'request-update','expected_revision':0}),h)[0],409)
  self.assertEqual(self.request('GET','/api/invoice-assets/../../server.py/original')[0],404)
 def test_partial_multipart_and_readback(self):
  boundary='WorkBenchSyntheticBoundary';parts=[]
  for name,raw in [('synthetic.pdf',b'%PDF-1.4 synthetic'),('fake.pdf',b'<html>bad</html>')]:parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+raw+b'\r\n')
  body=b''.join(parts)+f'--{boundary}--\r\n'.encode();h={'Content-Type':f'multipart/form-data; boundary={boundary}','X-Workbench-Request':'local-v1'}
  code,raw=self.request('POST','/api/invoices/upload',body,h);r=json.loads(raw)['results'];self.assertEqual(code,200);self.assertTrue(r[0]['ok']);self.assertFalse(r[1]['ok']);id=r[0]['items'][0]['id'];self.assertEqual(self.request('GET','/api/invoices/'+id)[0],200)
