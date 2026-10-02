"""Routes for local-only vault and customer branding. Explicit same-origin gate."""
import json,re,socket
from email.parser import BytesParser
from email.policy import default
from urllib.parse import urlparse,parse_qs
from invoice_vault import Vault,VaultError

def guard(h):
 host=urlparse('http://'+h.headers.get('Host',''))
 if host.hostname not in {'127.0.0.1','localhost','::1'} or host.port!=h.server.server_port:raise VaultError('Host不受信任',403)
 if h.headers.get('Sec-Fetch-Site','') in {'cross-site','same-site'}:raise VaultError('跨站请求已拒绝',403)
 origin=h.headers.get('Origin')
 if origin and origin!=f'http://{h.headers.get("Host")}':raise VaultError('Origin不受信任',403)
 if h.command=='POST' and h.headers.get('X-Workbench-Request')!='local-v1':raise VaultError('缺少本机写入请求标识',403)

def upload_parts(h):
 length=int(h.headers.get('Content-Length','0'))
 if length<=0 or length>100*1024*1024:raise VaultError('上传总量须在100MB以内',413)
 kind=h.headers.get('Content-Type','')
 if not kind.startswith('multipart/form-data;'):raise VaultError('需要multipart上传')
 h.connection.settimeout(30)
 raw=h.rfile.read(length)
 if len(raw)!=length:raise VaultError('上传中断，请重试')
 msg=BytesParser(policy=default).parsebytes(('Content-Type: '+kind+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
 parts=list(msg.iter_parts())
 if len(parts)>55:raise VaultError('每次最多50个文件')
 files=[];fields={}
 for part in parts:
  data=part.get_payload(decode=True) or b''
  if part.get_filename() is not None:files.append((part.get_filename(),data))
  else:
   if len(data)>8000:raise VaultError('表单字段过长')
   fields[part.get_param('name',header='content-disposition')]=data.decode('utf-8')
 if len(files)>50:raise VaultError('每次最多50个文件')
 return fields,files

def read_json(h):
 n=int(h.headers.get('Content-Length','0'))
 if n<0 or n>256*1024:raise VaultError('请求过大',413)
 h.connection.settimeout(10)
 result=json.loads(h.rfile.read(n) or b'{}')
 if not isinstance(result,dict):raise VaultError('需要JSON对象')
 return result

def binary(h,raw,mime,name=None,cache=False):
 h.send_response(200);h.send_header('Content-Type',mime);h.send_header('Content-Length',str(len(raw)));h.send_header('Cache-Control','private, max-age=31536000, immutable' if cache else 'no-store')
 h.send_header('Content-Security-Policy',"sandbox; default-src 'none'; style-src 'unsafe-inline'")
 if name:h.send_header('Content-Disposition','attachment; filename="'+name+'"')
 h.end_headers();h.wfile.write(raw)

def handle(h,root):
 parsed=urlparse(h.path);path=parsed.path
 if not any(path.startswith(p) for p in ['/api/invoices','/api/invoice-assets/','/api/reimbursement-batches','/api/customer-branding']):return False
 try:
  guard(h);vault=Vault(root);q={k:v[0] for k,v in parse_qs(parsed.query).items()}
  if path.startswith('/api/customer-branding'):
   import customer_branding
   return customer_branding.handle(h,root,path,q)
  if h.command=='GET':
   if path=='/api/invoices':result=vault.listing(q)
   elif path=='/api/reimbursement-batches':result=vault.batches()
   elif re.fullmatch('/api/invoices/[a-f0-9]{32}',path):
    with vault.db() as db:result={'ok':True,'item':vault.one(db,path.split('/')[-1])}
   elif re.fullmatch('/api/invoice-assets/[a-f0-9]{64}/(original|preview)',path):
    file,mime=vault.asset(path.split('/')[-2])
    if path.endswith('/preview') and mime=='application/octet-stream':raise VaultError('该格式仅提供原件下载',415)
    binary(h,file.read_bytes(),mime,file.name if path.endswith('/original') else None);return True
   else:raise VaultError('不存在',404)
  elif h.command=='POST':
   if path=='/api/invoices/upload':
    fields,files=upload_parts(h);results=[]
    for name,raw in files:
     try:results.append({'name':name,**vault.upload(name,raw)})
     except VaultError as e:results.append({'name':name,'ok':False,'error':str(e)})
    result={'ok':True,'results':results}
   else:
    body=read_json(h)
    if path=='/api/invoices/export' or re.fullmatch('/api/reimbursement-batches/[a-f0-9]{32}/export',path):
     result=vault.export(body,path.split('/')[-2] if path.startswith('/api/reimbursement-batches/') else None)
     if isinstance(result,tuple):binary(h,*result);return True
    elif path=='/api/reimbursement-batches':result=vault.batch(None,'create',body)
    elif re.fullmatch('/api/reimbursement-batches/[a-f0-9]{32}/(update|items)',path):result=vault.batch(*path.split('/')[-2:],body)
    elif re.fullmatch('/api/invoices/[a-f0-9]{32}/(update|trash|restore|split)',path):result=vault.mutate(*path.split('/')[-2:],body)
    else:raise VaultError('不存在',404)
  else:raise VaultError('方法不支持',405)
  h._send_json(result)
 except VaultError as e:h._send_json({'ok':False,'error':str(e)},status=e.status)
 except (ValueError,TypeError,KeyError):h._send_json({'ok':False,'error':'请求字段无效'},status=400)
 except Exception:h._send_json({'ok':False,'error':'本地资源操作未完成，已有文件保留'},status=500)
 return True
