"""Local invoice records. No network, model or business scheduler imports."""
import contextlib,csv,hashlib,io,json,os,re,sqlite3,tempfile,uuid,zipfile,subprocess,sys,threading
_PARSE_LIMIT=threading.BoundedSemaphore(2)
from datetime import datetime,date,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path
MAX_FILE=20*1024*1024
FIELDS={'display_name','number','code','issued_on','seller','buyer','amount','currency','expense_type','note','customer_id','project_id','review','reimbursement','pages'}
class VaultError(ValueError):
 def __init__(self,message,status=400):super().__init__(message);self.status=status

def now():return datetime.now(timezone.utc).isoformat()
def uid():return uuid.uuid4().hex

def detect(raw):
 if len(raw)>MAX_FILE:raise VaultError('单文件不得超过20MB',413)
 if raw.startswith(b'%PDF-'):return 'pdf','application/pdf'
 if raw.startswith(b'\x89PNG\r\n\x1a\n'):return 'png','image/png'
 if raw.startswith(b'\xff\xd8\xff'):return 'jpg','image/jpeg'
 if raw[:4]==b'RIFF' and raw[8:12]==b'WEBP':return 'webp','image/webp'
 if raw[:4]==b'PK\x03\x04':
  try:
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    items=z.infolist()
    if len(items)>2000 or sum(i.file_size for i in items)>100*1024*1024:raise VaultError('OFD容器超限')
    if any(i.filename.startswith(('/','\\')) or '..' in i.filename.replace('\\','/').split('/') or i.flag_bits&1 for i in items):raise VaultError('不安全的OFD容器')
    if 'OFD.xml' in z.namelist():return 'ofd','application/octet-stream'
  except zipfile.BadZipFile:pass
 raise VaultError('仅支持PDF、PNG、JPEG、WebP和OFD原件')

def safe_csv(v):
 s=str(v or '');return "'"+s if s.lstrip().startswith(('=','+','-','@','\t','\r')) else s

class Vault:
 def __init__(self,root):self.root=Path(root)/'invoice_vault'
 @contextlib.contextmanager
 def db(self,write=False):
  if not write and not (self.root/'metadata.sqlite3').exists():yield None;return
  self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
  db=sqlite3.connect(self.root/'metadata.sqlite3',timeout=10);db.row_factory=sqlite3.Row
  try:
   if write:
    db.executescript('CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,ext TEXT,mime TEXT,bytes INTEGER,created TEXT); CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,asset_id TEXT,payload TEXT,revision INTEGER,trash INTEGER DEFAULT 0,batch_id TEXT,updated TEXT); CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,payload TEXT,revision INTEGER); CREATE TABLE IF NOT EXISTS operations(request_id TEXT PRIMARY KEY,signature TEXT,result TEXT,created TEXT);')
    db.execute('BEGIN IMMEDIATE')
   yield db
   if write:db.commit()
  except:db.rollback();raise
  finally:db.close()
 def record(self,row):
  return {**json.loads(row['payload']),'id':row['id'],'asset_id':row['asset_id'],'revision':row['revision'],'trash':bool(row['trash']),'batch_id':row['batch_id'],'updated_at':row['updated']}
 def one(self,db,id):
  row=db.execute('SELECT * FROM records WHERE id=?',(id,)).fetchone() if db else None
  if not row:raise VaultError('记录不存在',404)
  return self.record(row)
 def operation(self,db,body,action):
  request=str(body.get('request_id',''))
  if not re.fullmatch('[a-zA-Z0-9_-]{8,100}',request):raise VaultError('缺少有效request_id')
  signature=hashlib.sha256(json.dumps([action,body],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
  row=db.execute('SELECT * FROM operations WHERE request_id=?',(request,)).fetchone()
  if row:
   if row['signature']!=signature:raise VaultError('request_id已用于其他操作',409)
   return request,signature,json.loads(row['result'])
  return request,signature,None
 def receipt(self,db,op,result):
  db.execute('INSERT INTO operations VALUES(?,?,?,?)',(op[0],op[1],json.dumps(result,ensure_ascii=False),now()));return result
 def upload(self,name,raw):
  ext,mime=detect(raw)
  if ext in {'png','jpg','webp'}:
   try:subprocess.run([os.environ.get('WORKBENCH_DOCUMENT_PYTHON','/Library/Frameworks/Python.framework/Versions/3.14/bin/python3'),str(Path(__file__).with_name('invoice_extraction.py')),'--validate-image'],input=raw,capture_output=True,timeout=5,check=True)
   except Exception:raise VaultError('图片内容损坏、伪装或解码超限；未保存')
  asset=hashlib.sha256(raw).hexdigest()
  with self.db(True) as db:
   existing=db.execute('SELECT * FROM records WHERE asset_id=? ORDER BY trash,id',(asset,)).fetchall()
   if existing:return {'ok':True,'duplicate':True,'items':[self.record(r) for r in existing]}
   folder=self.root/'originals';folder.mkdir(exist_ok=True,mode=0o700);target=folder/f'{asset}.{ext}'
   if not target.exists():
    fd,temp=tempfile.mkstemp(dir=folder)
    try:
     with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
     os.replace(temp,target)
    finally:
     if os.path.exists(temp):os.unlink(temp)
   elif hashlib.sha256(target.read_bytes()).hexdigest()!=asset:raise VaultError('已有原件校验失败',500)
   db.execute('INSERT OR IGNORE INTO assets VALUES(?,?,?,?,?)',(asset,ext,mime,len(raw),now()))
   id=uid();payload={'display_name':Path(name.replace('\\','/')).name[:180] or '未命名原件','number':'','code':'','issued_on':'','seller':'','buyer':'','amount':'','currency':'CNY','expense_type':'其他','note':'','customer_id':'','project_id':'','review':'pending','reimbursement':'unassigned','pages':'','uploaded_at':now(),'file_state':'saved','extraction_note':'原件已保存，待手工核对','field_sources':{},'format':ext,'bytes':len(raw)}
   parsing=_PARSE_LIMIT.acquire(timeout=1)
   if parsing:
    try:
     worker=subprocess.run([os.environ.get('WORKBENCH_DOCUMENT_PYTHON','/Library/Frameworks/Python.framework/Versions/3.14/bin/python3'),str(Path(__file__).with_name('invoice_extraction.py')),str(target),ext],capture_output=True,timeout=12,check=True)
     extracted=json.loads(worker.stdout)
     payload.update({k:v for k,v in extracted.items() if k!='fields'});payload.update(extracted.get('fields',{}))
    except Exception:payload.update(file_state='unrecognized',extraction_note='原件已保存，本地读取超时或不可用；请手工核对')
    finally:_PARSE_LIMIT.release()
   else:payload.update(file_state='unrecognized',extraction_note='原件已保存，本地读取繁忙；请手工核对')
   db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?)',(id,asset,json.dumps(payload,ensure_ascii=False),1,0,None,now()))
   result={'ok':True,'duplicate':False,'items':[self.one(db,id)]}
  return result
 def validate(self,p):
  for k in FIELDS:
   if k in p and (not isinstance(p[k],str) or len(p[k])>4000):raise VaultError('字段格式或长度无效：'+k)
  if p.get('amount'):
   try:
    value=Decimal(p['amount'])
    if not value.is_finite() or abs(value)>Decimal('999999999999') or value.as_tuple().exponent < -2:raise InvalidOperation
    p['amount']=format(value.quantize(Decimal('.01')),'f')
   except (InvalidOperation,ValueError):raise VaultError('金额须为最多两位小数的有限数值')
  if p.get('currency') and not re.fullmatch('[A-Z]{3}',p['currency']):raise VaultError('币种须为三位大写代码')
  if p.get('issued_on'):
   try:date.fromisoformat(p['issued_on'])
   except ValueError:raise VaultError('开票日期无效')
  if p.get('pages') and not re.fullmatch('[1-9][0-9]*(?:-[1-9][0-9]*)?',p['pages']):raise VaultError('页范围示例：1 或 1-3')
  if p.get('pages') and '-' in p['pages'] and int(p['pages'].split('-')[0])>int(p['pages'].split('-')[1]):raise VaultError('页范围顺序错误')
  if p.get('pages') and p.get('page_count') and max(map(int,p['pages'].split('-')))>p['page_count']:raise VaultError('页范围超出原件页数')
  if p.get('review','pending') not in {'pending','confirmed','excluded'}:raise VaultError('核对状态无效')
  if p.get('reimbursement','unassigned') not in {'unassigned','pending','submitted','paid'}:raise VaultError('报销状态无效')
 def duplicates(self,items):
  for r in items:
   r['possible_duplicates']=[x['id'] for x in items if x['id']!=r['id'] and r.get('number') and r['number']==x.get('number') and (r.get('code') or r.get('seller')) and ((r.get('code') and r['code']==x.get('code')) or (r.get('seller') and r['seller']==x.get('seller')))]
  return items
 def listing(self,q):
  with self.db() as db:
   rows=[self.record(r) for r in db.execute('SELECT * FROM records ORDER BY updated DESC,id')] if db else []
  rows=self.duplicates(rows);items=[r for r in rows if r['trash']==(q.get('trash')=='1')]
  for key in ['review','expense_type','batch_id']:
   if q.get(key):items=[r for r in items if r.get(key)==q[key]]
  if q.get('q'):items=[r for r in items if q['q'].lower() in ' '.join(str(r.get(k,'')) for k in ['display_name','seller','number','note']).lower()]
  if q.get('from'):items=[r for r in items if r.get('issued_on','')>=q['from']]
  if q.get('to'):items=[r for r in items if r.get('issued_on','') and r['issued_on']<=q['to']]
  sums={}
  for r in items:
   if r['review']=='confirmed' and r.get('amount'):sums[r['currency']]=sums.get(r['currency'],Decimal(0))+Decimal(r['amount'])
  offset=max(0,int(q.get('offset',0)));limit=min(100,max(1,int(q.get('limit',50))))
  return {'ok':True,'items':items[offset:offset+limit],'total':len(items),'offset':offset,'limit':limit,'totals':{k:format(v,'f') for k,v in sums.items()},'pending':sum(r['review']=='pending' for r in items)}
 def mutate(self,id,action,body):
  with self.db(True) as db:
   op=self.operation(db,body,[id,action])
   if op[2] is not None:return op[2]
   r=self.one(db,id)
   if body.get('expected_revision')!=r['revision']:raise VaultError('记录已变化，请重新读取后再保存',409)
   payload={k:v for k,v in r.items() if k not in {'id','asset_id','revision','trash','batch_id','updated_at'}}
   if action=='update':
    changed={k:v for k,v in body.get('fields',{}).items() if k in FIELDS and payload.get(k)!=v}
    payload.update(changed);self.validate(payload)
    payload['field_sources']={**payload.get('field_sources',{}),**{k:{'source':'manual','at':now()} for k in changed}}
   elif action=='split':
    new=uid();payload.update(number='',code='',amount='',review='pending',reimbursement='unassigned',pages=body.get('pages',''),field_sources={})
    self.validate(payload);db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?)',(new,r['asset_id'],json.dumps(payload,ensure_ascii=False),1,0,None,now()))
    return self.receipt(db,op,{'ok':True,'item':self.one(db,new)})
   elif action not in {'trash','restore'}:raise VaultError('未知操作',404)
   trash=1 if action=='trash' else 0 if action=='restore' else int(r['trash'])
   db.execute('UPDATE records SET payload=?,revision=revision+1,trash=?,updated=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),trash,now(),id))
   return self.receipt(db,op,{'ok':True,'item':self.one(db,id)})
 def batches(self):
  with self.db() as db:return {'ok':True,'items':[{**json.loads(r['payload']),'id':r['id'],'revision':r['revision']} for r in db.execute('SELECT * FROM batches')] if db else []}
 def batch(self,id,action,body):
  with self.db(True) as db:
   op=self.operation(db,body,[id,action])
   if op[2] is not None:return op[2]
   if not id:
    id=uid();payload={'name':str(body.get('name','')).strip()[:120],'note':'','submitted_at':'','paid_at':''}
    if not payload['name']:raise VaultError('请填写批次名称')
    db.execute('INSERT INTO batches VALUES(?,?,1)',(id,json.dumps(payload,ensure_ascii=False)))
   else:
    row=db.execute('SELECT * FROM batches WHERE id=?',(id,)).fetchone()
    if not row:raise VaultError('批次不存在',404)
    if body.get('expected_revision')!=row['revision']:raise VaultError('批次已变化，请重新读取',409)
    payload=json.loads(row['payload'])
    if action=='items':
     ids=body.get('ids',[])
     if not isinstance(ids,list) or not ids or len(ids)>100:raise VaultError('每次选择1至100条记录')
     records=[self.one(db,k) for k in set(ids)]
     for r in records:
      if r['trash']:raise VaultError('请先恢复回收站记录')
      if body.get('record_revisions',{}).get(r['id'])!=r['revision']:raise VaultError('所选发票已变化',409)
      if body.get('remove') and r['batch_id']!=id:raise VaultError('发票不属于所选批次',409)
      if r['batch_id'] and r['batch_id']!=id and not body.get('confirm_move'):raise VaultError('发票已在其他批次；确认移动后重试',409)
     for r in records:
      batch=None if body.get('remove') else id
      db.execute('UPDATE records SET batch_id=?,revision=revision+1,updated=? WHERE id=?',(batch,now(),r['id']))
    elif action=='update':
     for k in ['name','note','submitted_at','paid_at']:
      if k in body:payload[k]=str(body[k])[:4000]
     if not payload['name'].strip():raise VaultError('批次名称不能为空')
     for k in ['submitted_at','paid_at']:
      if payload[k]:
       try:date.fromisoformat(payload[k])
       except ValueError:raise VaultError('提交/到账日期无效')
    else:raise VaultError('未知操作',404)
    db.execute('UPDATE batches SET payload=?,revision=revision+1 WHERE id=?',(json.dumps(payload,ensure_ascii=False),id))
   row=db.execute('SELECT * FROM batches WHERE id=?',(id,)).fetchone()
   return self.receipt(db,op,{'ok':True,'item':{**json.loads(row['payload']),'id':id,'revision':row['revision']}})
 def asset(self,id):
  if not re.fullmatch('[a-f0-9]{64}',id):raise VaultError('资产不存在',404)
  with self.db() as db:r=db.execute('SELECT * FROM assets WHERE id=?',(id,)).fetchone() if db else None
  if not r:raise VaultError('资产不存在',404)
  path=self.root/'originals'/f"{id}.{r['ext']}"
  if path.is_symlink() or not path.is_file():raise VaultError('原件不可读取',404)
  return path,r['mime']
 def export(self,body,batch_id=None):
  ids=body.get('ids',[])
  if not isinstance(ids,list) or not ids or any(not isinstance(k,str) for k in ids) or len(ids)>100 or len(set(ids))!=len(ids):raise VaultError('请选择1至100条不同记录')
  with self.db() as db:
   if not db:raise VaultError('记录不存在',404)
   db.execute('BEGIN')
   if batch_id and not db.execute('SELECT 1 FROM batches WHERE id=?',(batch_id,)).fetchone():raise VaultError('批次不存在',404)
   all_rows=self.duplicates([self.record(r) for r in db.execute('SELECT * FROM records WHERE trash=0')]); indexed={r['id']:r for r in all_rows}; items=[indexed[k] if k in indexed else self.one(db,k) for k in ids]
   for r in items:
    if r['trash']:raise VaultError('回收站记录不能导出')
    if batch_id and r['batch_id']!=batch_id:raise VaultError('所选发票已不属于该批次，请重新读取',409)
    if body.get('record_revisions',{}).get(r['id'])!=r['revision']:raise VaultError('导出记录已变化，请重新核对',409)
   warnings=[{'id':r['id'],'pending':r['review']!='confirmed','missing_amount':not r['amount'],'duplicates':r['possible_duplicates']} for r in items if r['review']!='confirmed' or not r['amount'] or r['possible_duplicates']]
   if warnings and not body.get('acknowledge_warnings'):return {'ok':True,'confirmation_required':True,'warnings':warnings}
   originals={}
   for r in items:
    path,mime=self.asset(r['asset_id']);originals[r['asset_id']]=(path,f"{r['asset_id'][:16]}{path.suffix}")
   if sum(p.stat().st_size for p,n in originals.values())>100*1024*1024:raise VaultError('单次导出最多100MB',413)
   csvbuf=io.StringIO(newline='');writer=csv.writer(csvbuf);writer.writerow(['序号','开票日期','开票方','号码','代码','费用类型','价税合计','币种','核对状态','报销状态','备注','原件文件名','页范围','记录ID'])
   for i,r in enumerate(items,1):writer.writerow([i,*[safe_csv(r.get(k,'')) for k in ['issued_on','seller','number','code','expense_type']],r['amount'],r['currency'],r['review'],r['reimbursement'],safe_csv(r['note']),originals[r['asset_id']][1],r['pages'],r['id']])
   csvraw=b'\xef\xbb\xbf'+csvbuf.getvalue().encode()
   if body.get('format')=='csv':return csvraw,'text/csv; charset=utf-8','invoices.csv'
   out=io.BytesIO()
   with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('清单.csv',csvraw)
    for path,name in originals.values():z.write(path,name)
   return out.getvalue(),'application/zip','invoices.zip'
