"""Explicitly configured IMAP reader. Uses EXAMINE/BODY.PEEK; never SMTP or flag writes."""
from __future__ import annotations
import contextlib,datetime as dt,email,email.policy,getpass,imaplib,json,re,ssl,sys,time
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
APP=Path(__file__).resolve().parents[1]
SERVICE='SalesWorkbenchPublic.IMAP'
class MailError(Exception):pass

def configuration(state):
    path=Path(state)/'mail_connection.json'
    if not path.exists():return None
    cfg=json.loads(path.read_text())
    if not re.fullmatch(r'[A-Za-z0-9.-]+',cfg.get('host','')) or '@' not in cfg.get('username',''):raise MailError('邮箱连接配置无效')
    if cfg.get('port')!=993:raise MailError('邮箱只支持验证证书的SSL 993端口')
    return cfg

def vault():
    # Explicit native backend: never silently fall back to a plaintext password file.
    from keyring.backends.macOS import Keyring
    return Keyring()

def account_key(cfg):return cfg['username']+'@'+cfg['host']

def tls_context():
    context=ssl.create_default_context()
    if not context.cert_store_stats()['x509_ca']:
        import certifi
        context.load_verify_locations(cafile=certifi.where())
    return context

@contextlib.contextmanager
def connection(cfg,password=None):
    if password is None:password=vault().get_password(SERVICE,account_key(cfg))
    if not password:raise MailError('尚未保存公司邮箱专用密码，请双击「连接公司邮箱」')
    client=None
    try:
        client=imaplib.IMAP4_SSL(cfg['host'],993,ssl_context=tls_context(),timeout=25)
        client.login(cfg['username'],password)
        yield client
    except imaplib.IMAP4.error:raise MailError('邮箱拒绝登录或读取，请核对IMAP服务和客户端专用密码；未修改邮件') from None
    except (OSError,TimeoutError):raise MailError('邮箱加密连接失败，请检查服务器地址及网络；未修改邮件') from None
    finally:
        if client:
            with contextlib.suppress(Exception):client.logout()

def folders(client):
    result=['INBOX'];status,rows=client.list()
    if status!='OK':raise MailError('无法列出邮件文件夹，未声称扫描完整')
    for raw in rows or []:
        if not isinstance(raw,bytes):continue
        match=re.match(rb'\(([^)]*)\)\s+(?:"[^"]*"|NIL)\s+(.+)$',raw)
        if not match:raise MailError('邮件文件夹响应格式变化')
        flags=match[1].lower();name=match[2].decode('ascii',errors='strict')
        if '\r' in name or '\n' in name:raise MailError('邮件文件夹名称无效')
        if any(x in flags for x in (b'\\noselect',b'\\trash',b'\\junk',b'\\drafts')):continue
        if re.search(r'trash|junk|spam|draft|deleted',name,re.I):continue
        if name.strip('"').upper()=='INBOX':continue
        result.append(name)
    return list(dict.fromkeys(result))

class PlainHTML(HTMLParser):
    def __init__(self):super().__init__();self.out=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
        if tag in ('br','p','div','tr','li'):self.out.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.hidden:self.hidden-=1
    def handle_data(self,data):
        if not self.hidden:self.out.append(data)

def unpack(raw):
    msg=email.message_from_bytes(raw,policy=email.policy.default);texts=[];attachments=[]
    for part in msg.walk():
        if part.is_multipart():continue
        name=part.get_filename();payload=part.get_payload(decode=True) or b''
        if name or part.get_content_disposition()=='attachment':
            attachments.append((Path(name or '未命名附件').name,payload));continue
        if part.get_content_type() in ('text/plain','text/html'):
            try:text=payload.decode(part.get_content_charset() or 'utf-8',errors='replace')
            except LookupError:text=payload.decode('utf-8',errors='replace')
            if part.get_content_type()=='text/html':parser=PlainHTML();parser.feed(text);text=''.join(parser.out)
            texts.append(text)
    date=''
    try:
        stamp=parsedate_to_datetime(str(msg.get('Date','')))
        if stamp is not None:date=(stamp.astimezone(dt.timezone(dt.timedelta(hours=8))) if stamp.tzinfo else stamp).date().isoformat()
    except (ValueError,TypeError,OverflowError):pass
    headers='\n'.join(k+'：'+str(msg.get(k,'')) for k in ('Subject','From','To','Cc','Date','Message-ID','In-Reply-To'))
    return {'title':str(msg.get('Subject','无主题邮件')),'date':date,'text':headers+'\n\n'+'\n\n'.join(texts),'attachments':attachments}

def probe(state):
    cfg=configuration(state)
    if not cfg:return {'configured':False,'available':False,'reason':'未连接公司邮箱；可双击「连接公司邮箱」在本机输入专用密码'}
    for attempt in range(2):
        try:
            with connection(cfg) as client:
                status,_=client.select('INBOX',readonly=True)
                if status!='OK':raise MailError('公司邮箱收件箱不可只读访问')
            return {'configured':True,'available':True,'reason':'公司邮箱只读连接已验证'}
        except Exception as e:
            reason=str(e) if isinstance(e,MailError) else '公司邮箱连接未通过验证；凭据未输出'
            if attempt or '拒绝登录' in reason:return {'configured':True,'available':False,'reason':reason}
            time.sleep(1)

def collect(pipe):
    for attempt in range(2):
        try:return collect_once(pipe)
        except MailError as e:
            if attempt or '拒绝登录' in str(e):pipe.gap('公司邮箱',str(e));return
            time.sleep(1)

def collect_once(pipe):
    cfg=configuration(pipe.state)
    if not cfg:return
    try:
        with connection(cfg) as client:
            count=0
            for folder in folders(client):
                status,_=client.select(folder,readonly=True)
                if status!='OK':pipe.gap('公司邮箱','某个文件夹不可只读访问');continue
                _,validity=client.response('UIDVALIDITY')
                if not validity or not isinstance(validity[0],bytes) or not validity[0].isdigit():pipe.gap('公司邮箱','缺少文件夹版本标识，不能安全续跑');continue
                status,uids=client.uid('search',None,'SINCE',pipe.start.strftime('%d-%b-%Y'),'BEFORE',(pipe.end+dt.timedelta(days=1)).strftime('%d-%b-%Y'))
                if status!='OK':pipe.gap('公司邮箱','日期范围检索失败');continue
                for uid in (uids[0] or b'').split():
                    key=cfg['username']+'/'+folder+'/'+validity[0].decode()+'/'+uid.decode();origin='imap://'+cfg['host']+'/'+folder+'/'+uid.decode()
                    if any(e['key']==key and e['channel']=='email' and e['status']!='extraction_pending' for e in pipe.ledger['items'].values()):pipe.duplicates+=1;continue
                    status,size_data=client.uid('fetch',uid,'(RFC822.SIZE)')
                    sizes=re.findall(rb'RFC822.SIZE (\d+)',b' '.join(x for x in size_data or [] if isinstance(x,bytes)))
                    if status!='OK' or not sizes or int(sizes[0])>30_000_000:pipe.gap('公司邮箱','邮件大小未确认或超过30MB，附件保留待单独读取');continue
                    status,rows=client.uid('fetch',uid,'(BODY.PEEK[])')
                    raw=next((x[1] for x in rows or [] if isinstance(x,tuple)),None)
                    if status!='OK' or not isinstance(raw,bytes):pipe.gap('公司邮箱','邮件原文未完整返回');continue
                    count+=1;m=unpack(raw)
                    # Corporate mailbox is scoped to project keywords; unrelated mail stays out of the KB.
                    keywords=pipe.cfg.get('chat_keywords',[])+pipe.cfg.get('mail_keywords',[])
                    if not any(word in m['text']+' '.join(n for n,_ in m['attachments']) for word in keywords):continue
                    pipe.stage(key,m['title'],raw,'.eml','email',origin,m['date'],m['text'],'IMAP只读原始邮件；邮件原文和附件分别处理，未发送、标记已读或修改任何邮件。')
                    for i,(name,b) in enumerate(m['attachments']):
                        pipe.stage(key+'/part/'+str(i),name,b,Path(name).suffix.lower(),'email_attachment',origin+'#part'+str(i),m['date'])
    except Exception as e:raise MailError(str(e) if isinstance(e,MailError) else '读取未完成，原件和已处理结果保留；凭据未输出') from None

def setup():
    if not sys.stdin.isatty():raise MailError('请从访达双击连接入口，在本机终端输入；不要把专用密码发到聊天里')
    print('连接公司邮箱：仅使用IMAP只读邮件及附件，不发送、不删除、不标记已读。')
    print('请按企业邮箱设置填写服务器。输入专用密码并回车后，将验证连接并保存到本机系统钥匙串。')
    host=input('IMAP服务器（回车使用 imap.exmail.qq.com）：').strip() or 'imap.exmail.qq.com'
    username=input('公司邮箱地址：').strip()
    if not re.fullmatch(r'[A-Za-z0-9.-]+',host) or '@' not in username:raise MailError('服务器或邮箱格式不正确')
    cfg={'host':host,'port':993,'username':username,'max_messages':120}
    password=getpass.getpass('客户端专用密码／授权码（输入不显示）：')
    with connection(cfg,password) as client:
        status,_=client.select('INBOX',readonly=True)
        if status!='OK':raise MailError('收件箱读取验证未通过，未保存连接')
    vault().set_password(SERVICE,account_key(cfg),password);password=None
    from communication_pipeline import save
    save(APP/'workbench_data/mail_connection.json',cfg)
    print('公司邮箱只读连接成功，专用密码已存入系统钥匙串。今后双击「整理近期沟通」即可一并读取。')

if __name__=='__main__':
    try:setup()
    except (KeyboardInterrupt,EOFError):print('\n连接已取消。');sys.exit(1)
    except Exception as e:print(str(e) if isinstance(e,MailError) else '连接未完成，专用密码未写入文件或日志。');sys.exit(1)
