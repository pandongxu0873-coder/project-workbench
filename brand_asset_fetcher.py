"""Small HTTPS fetcher: DNS validation + pinned public connection, no redirects."""
import http.client,ipaddress,socket,ssl,sys,subprocess,json,base64
from pathlib import Path
from urllib.parse import urlparse,urljoin
from html.parser import HTMLParser
from invoice_vault import VaultError

def fetch(url,domain,limit=3*1024*1024):
 try:
  result=subprocess.run([sys.executable,str(Path(__file__).resolve()),url,domain,str(limit)],capture_output=True,timeout=8,check=True)
  response=json.loads(result.stdout)
  return base64.b64decode(response['data']),response['type']
 except Exception:raise VaultError('官网读取失败、超时或触发安全限制；原图保留')

def _fetch(url,domain,limit=3*1024*1024):
 p=urlparse(url)
 if p.scheme!='https' or p.hostname!=domain or p.port not in {None,443} or p.username or p.password:raise VaultError('仅允许已确认官网的HTTPS同域资源')
 addrs={x[4][0] for x in socket.getaddrinfo(domain,443,type=socket.SOCK_STREAM)}
 if not addrs or any(not ipaddress.ip_address(a).is_global for a in addrs):raise VaultError('拒绝私网、回环或保留地址')
 class Pinned(http.client.HTTPSConnection):
  def connect(self):
   self.sock=socket.create_connection((sorted(addrs)[0],443),timeout=5)
   if self.sock.getpeername()[0] not in addrs:self.sock.close();raise VaultError('连接地址校验失败')
   self.sock=self._context.wrap_socket(self.sock,server_hostname=domain)
 conn=Pinned(domain,timeout=5,context=ssl.create_default_context())
 try:
  conn.request('GET',(p.path or '/')+('?' + p.query if p.query else ''),headers={'Host':domain,'User-Agent':'LocalWorkbenchBranding/1.0','Accept':'image/*,text/html;q=0.5'})
  r=conn.getresponse()
  if r.status!=200:raise VaultError('官网返回非200状态（不跟随重定向）')
  raw=r.read(limit+1)
  if len(raw)>limit:raise VaultError('官网资源超过大小上限')
  return raw,r.getheader('Content-Type','')
 finally:conn.close()

class Candidates(HTMLParser):
 def __init__(self):super().__init__();self.urls=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='img' and 'logo' in (a.get('alt','')+' '+a.get('class','')+' '+a.get('id','')).lower() and a.get('src'):self.urls.append((a['src'],'官网Logo候选，须人工核对'))
  if tag=='link' and 'icon' in a.get('rel','').lower() and a.get('href'):self.urls.append((a['href'],'网站图标（不是已确认品牌Logo）'))

def discover(domain):
 base='https://'+domain+'/'
 raw,kind=fetch(base,domain,512*1024)
 if 'text/html' not in kind:raise VaultError('官网未返回可识别HTML')
 parser=Candidates();parser.feed(raw.decode('utf-8',errors='replace'));out=[]
 for url,label in parser.urls:
  url=urljoin(base,url)
  if urlparse(url).hostname==domain and urlparse(url).scheme=='https' and url not in [x['url'] for x in out]:out.append({'url':url,'source':label})
 return out[:6]

if __name__=='__main__':
 raw,kind=_fetch(sys.argv[1],sys.argv[2],int(sys.argv[3]))
 print(json.dumps({'data':base64.b64encode(raw).decode(),'type':kind}))
