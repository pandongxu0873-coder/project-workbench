"""Separate persistent entity mapping, manual selection and bounded discovery."""
import hashlib,io,json,os,re,tempfile,threading,time,subprocess,sys,contextlib,fcntl
from pathlib import Path
from urllib.parse import urlparse
from invoice_vault import VaultError,now
LOCK=threading.RLock();FETCH=threading.BoundedSemaphore(2)

def normalize(raw):
 if len(raw)>3*1024*1024:raise VaultError('Logo不得超过3MB')
 try:
  worker=subprocess.run([os.environ.get('WORKBENCH_DOCUMENT_PYTHON','/Library/Frameworks/Python.framework/Versions/3.14/bin/python3'),str(Path(__file__).with_name('brand_image_worker.py'))],input=raw,capture_output=True,timeout=5,check=True)
  if not worker.stdout:raise ValueError()
  return worker.stdout
 except Exception:raise VaultError('Logo格式、像素、大小或解码时间超限；仅支持位图')

class Branding:
 def __init__(self,root):self.root=Path(root)/'branding'
 @contextlib.contextmanager
 def locked(self):
  self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
  with LOCK,open(self.root/'.write.lock','a') as lock:
   fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
   try:yield
   finally:fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
 def read(self):
  p=self.root/'manifest.json'
  return json.loads(p.read_text()) if p.exists() else {'version':1,'policy_version':1,'third_party_provider_enabled':False,'periodic_refresh_enabled':False,'revision':0,'entities':{},'operations':{}}
 def write(self,m):
  self.root.mkdir(parents=True,exist_ok=True,mode=0o700);fd,name=tempfile.mkstemp(dir=self.root)
  try:
   with os.fdopen(fd,'w') as f:json.dump(m,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
   os.replace(name,self.root/'manifest.json')
  finally:
   if os.path.exists(name):os.unlink(name)
 def asset(self,raw):
  raw=normalize(raw);hash=hashlib.sha256(raw).hexdigest();folder=self.root/'assets';folder.mkdir(parents=True,exist_ok=True);p=folder/(hash+'.webp')
  if not p.exists():
   fd,tmp=tempfile.mkstemp(dir=folder)
   with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
   os.replace(tmp,p)
  return hash
 def mutate(self,action,body,raw=None):
  id=str(body.get('entity_id',''))
  if not id or len(id)>240:raise VaultError('需要稳定实体ID')
  rid=str(body.get('request_id',''))
  if not re.fullmatch('[a-zA-Z0-9_-]{8,100}',rid):raise VaultError('需要request_id')
  sig=hashlib.sha256(json.dumps([action,body,hashlib.sha256(raw).hexdigest() if raw else None],sort_keys=True).encode()).hexdigest()
  with self.locked():
   m=self.read();cached=m['operations'].get(rid)
   if cached:
    if cached['signature']!=sig:raise VaultError('request_id冲突',409)
    return cached['result']
   entity=m['entities'].get(id,{'entity_id':id,'policy_version':1,'revision':0,'name':body.get('name',''),'project_ids':body.get('project_ids',[]),'locked':False,'asset_hash':None,'candidates':[],'rejected':[],'identity_status':'unconfirmed','fetch_status':'not_requested','domain':''})
   if int(body.get('expected_revision',-1))!=entity['revision']:raise VaultError('品牌记录已变化，请重新读取',409)
   entity=dict(entity)
   if action in {'upload','reset'} or (action=='select' and body.get('asset_hash')):
    entity['previous_selection']={k:entity.get(k) for k in ['asset_hash','source','source_url','locked','identity_status','usage_conditions']}
   if action=='undo':
    previous=entity.get('previous_selection')
    if not previous:raise VaultError('没有可恢复的上次选择')
    entity.update(previous);entity['previous_selection']=None
   elif action=='upload':
    entity.update(asset_hash=self.asset(raw),source='人工上传',locked=True,last_success_at=now(),usage_conditions='用户选定的本机身份展示资源；不代表取得其他传播授权')
   elif action=='select':
    if 'locked' in body:entity['locked']=bool(body['locked'])
    if body.get('reject'):
     entity['rejected']=list(set(entity['rejected']+[body['reject']]))
    if body.get('asset_hash'):
     h=body['asset_hash'];candidate=next((c for c in entity['candidates'] if c.get('asset_hash')==h),None)
     if not candidate or h in entity['rejected']:raise VaultError('候选不存在或已拒绝')
     if not body.get('confirm_identity'):raise VaultError('请明确确认主体与Logo对应')
     entity.update(asset_hash=h,source=candidate['source'],source_url=candidate['url'],identity_status='confirmed',last_success_at=now(),locked=bool(body.get('locked',True)),usage_conditions='官网公开资源，仅作本机客户身份展示；外部分发需另核许可')
   elif action=='reset':entity.update(asset_hash=None,source='首字占位',locked=False)
   elif action=='discover':
    domain=str(body.get('domain','')).strip().lower()
    if not body.get('confirm_identity') or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}',domain):raise VaultError('须确认官网域名及客户主体')
    if entity.get('last_attempt_epoch',0)>time.time()-60:raise VaultError('一分钟内已获取，请稍后重试',429)
    entity.update(domain=domain,identity_status='confirmed',last_attempt_at=now(),last_attempt_epoch=time.time())
    import brand_asset_fetcher
    candidates=[]
    try:
     with FETCH:
      for c in brand_asset_fetcher.discover(domain):
       try:
        data,_=brand_asset_fetcher.fetch(c['url'],domain);h=self.asset(data)
        if h not in entity['rejected']:candidates.append({**c,'asset_hash':h})
       except VaultError:continue
     entity.update(candidates=candidates,fetch_status='ready' if candidates else 'no_candidate',fetch_reason='' if candidates else '未取得可安全显示的位图候选；可人工上传',fetched_at=now())
    except Exception:entity.update(fetch_status='failed',fetch_reason='官网获取失败或安全限制，原图保留')
   else:raise VaultError('未知操作',404)
   entity['revision']+=1;m['revision']+=1;m['entities'][id]=entity;result={'ok':True,'item':entity};m['operations'][rid]={'signature':sig,'result':result};self.write(m);return result

def handle(h,root,path,q):
 from local_resources import binary,upload_parts,read_json
 b=Branding(root)
 if h.command=='GET':
  m=b.read()
  if path=='/api/customer-branding':
   items=list(m['entities'].values());ids=q.get('ids','').split(',') if q.get('ids') else []
   if ids:items=[x for x in items if x['entity_id'] in ids]
   h._send_json({'ok':True,'revision':m['revision'],'items':items});return True
  match=re.fullmatch('/api/customer-branding/assets/([a-f0-9]{64}).webp',path)
  hashes={h for e in m['entities'].values() for h in [e.get('asset_hash'),*[c.get('asset_hash') for c in e.get('candidates',[])]]}
  if not match or match[1] not in hashes:raise VaultError('资源不存在',404)
  p=b.root/'assets'/(match[1]+'.webp')
  if p.is_symlink() or not p.is_file():raise VaultError('资源不可用',404)
  binary(h,p.read_bytes(),'image/webp',cache=True);return True
 if h.command=='POST':
  action=path.split('/')[-1];raw=None
  if action=='upload':
   fields,files=upload_parts(h)
   if len(files)!=1:raise VaultError('每次上传一张Logo')
   body=json.loads(fields.get('metadata','{}'));raw=files[0][1]
  else:body=read_json(h)
  h._send_json(b.mutate(action,body,raw));return True
 raise VaultError('方法不支持',405)
