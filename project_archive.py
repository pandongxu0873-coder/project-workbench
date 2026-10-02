"""Explicit project lifecycle overlay, independent of source, CRM and analysis caches."""
import contextlib, fcntl, functools, hashlib, json, os, re, tempfile, threading
from datetime import datetime
from pathlib import Path
REASONS=('本轮无机会','客户取消','预算未通过','已丢单','我方不再投入','其他')
LOCK=threading.RLock(); LOCAL=threading.local()
class ArchiveConflict(ValueError): pass

def read(root):
 p=Path(root)/'project_archive'/'manifest.json'
 if not p.exists():return {'version':1,'projects':{},'requests':{}}
 try:
  m=json.loads(p.read_text());assert m['version']==1 and isinstance(m['projects'],dict) and isinstance(m['requests'],dict)
  for id,v in m['projects'].items():assert v['project_id']==id and v['revision']==len(v['history']) and type(v['archived']) is bool
  return m
 except Exception as e:raise ValueError('项目归档记录读取失败，原文件保留，请先核对') from e

def state(root,id,manifest=None):
 return (manifest or read(root))['projects'].get(id,{'project_id':id,'archived':False,'revision':0,'reason':'','note':'','updated_at':'','history':[],'suppressed_task_ids':[],'suppressed_task_revisions':{}})

@contextlib.contextmanager
def locked(root):
 key=str(Path(root).resolve())
 with LOCK:
  active=getattr(LOCAL,'roots',set())
  if key in active:yield;return
  folder=Path(tempfile.gettempdir())/('workbench-project-locks-'+str(os.getuid()));folder.mkdir(parents=True,exist_ok=True,mode=0o700)
  with (folder/(hashlib.sha256(key.encode()).hexdigest()+'.lock')).open('a') as f:
   fcntl.flock(f,fcntl.LOCK_EX);LOCAL.roots=active|{key}
   try:yield
   finally:LOCAL.roots=active

def commit(root,m):
 folder=Path(root)/'project_archive';folder.mkdir(parents=True,exist_ok=True,mode=0o700);fd,tmp=tempfile.mkstemp(dir=folder)
 try:
  with os.fdopen(fd,'w') as f:json.dump(m,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
  os.replace(tmp,folder/'manifest.json')
 finally:
  if os.path.exists(tmp):os.unlink(tmp)

def evidence_snapshot(project,knowledge_root=None):
 """Compare only explicit project evidence; never dates, AI output or customer aliases."""
 rows={}
 for source in project.get('sources',[]):
  if source.get('relation') not in ('project_source','explicit_evidence') or not source.get('exists'):continue
  digest=source.get('content_sha256')
  if not digest and knowledge_root:
   path=(Path(knowledge_root)/source['path']).resolve();root=Path(knowledge_root).resolve()
   if root not in path.parents:continue
   try:
    h=hashlib.sha256()
    with path.open('rb') as f:
     for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    digest=h.hexdigest()
   except OSError:continue
  if digest:rows[source['path']]={'sha256':digest,'title':source.get('title') or source.get('label') or Path(source['path']).name,'date':source.get('evidence_date',''),'readable':bool(source.get('readable'))}
 return rows

def evidence_review(project,a,knowledge_root=None):
 if not a['archived']:return {'has_new_material':False,'items':[]}
 baseline=a.get('evidence_baseline')
 if baseline is None:return {'has_new_material':False,'items':[],'baseline_missing':True}
 current=evidence_snapshot(project,knowledge_root);changes=[]
 for path,row in current.items():
  previous=baseline.get(path)
  if previous is None or row['sha256']!=previous['sha256']:
   changes.append({'path':path,**row,'change':'新增材料' if previous is None else '内容已更新'})
 return {'has_new_material':bool(changes),'items':changes}

def overlay(projects,root,knowledge_root=None):
 m=read(root);rows=[]
 for p in projects:
  a=state(root,p['id'],m)
  rows.append({**p,'archive':{**a,'review':evidence_review(p,a,knowledge_root)}})
 return rows

def owner(item,projects):
 from project_activity import project_owner
 return project_owner(item,projects)

def is_suppressed(a,item):
 if a['archived']:return True
 id=str(item.get('id',''))
 if id not in a['suppressed_task_ids']:return False
 # An explicit, revisioned new round after restore can become a new plan.
 if id.startswith('round:') and type(item.get('revision')) is int:
  return item['revision']<=a.get('suppressed_task_revisions',{}).get(id,10**12)
 return True

def decorate_items(items,root,projects):
 m=read(root);out=[]
 for item in items:
  p=owner(item,projects)
  a=state(root,p['id'],m) if p else None
  if not a or not a['history']:out.append(item);continue
  suppressed=is_suppressed(a,item)
  # Never discard uncertain obligations or real meetings. Suppress their sales projection only.
  label='已归档项目·待收尾' if a['archived'] else '恢复项目·原提醒不自动重发' if suppressed else ''
  out.append({**item,'project_id':p['id'],'project_archive':a,'sales_suppressed':suppressed,'archive_label':label})
 return out

def impact(project,root,projects=None,knowledge_root=None):
 from project_activity import read_store,project_owner
 from project_rounds import _read
 rows=read_store(Path(root)/'risk_todos.json',[])
 matched=[x for x in rows if (project_owner(x,projects or [project]) or {}).get('id')==project['id'] and x.get('status') not in ('已完成','已处理','已闭环','已取消')]
 local=_read(Path(root)/'project_rounds'/(project['id']+'.json'),project['id'])
 record=local.get('record') or {}
 reminders=[{'id':str(x.get('id','')),'title':str(x.get('title') or x.get('action') or '已有事项'),'due':x.get('deadline','')} for x in matched]
 if record and record.get('status') not in ('本轮完成','暂停跟进'):
  reminders.append({'id':'round:'+project['id'],'title':record.get('action') or record.get('next_step') or '已有项目跟进','due':record.get('due',''),'revision':local['revision']})
 meetings=[];calendar_state='尚未完整核对日程；本次不启动日程同步。'
 try:
  cache=read_store(Path(root)/'feishu_calendar_cache.json',{})
  events=[{'id':'feishu:'+str(x.get('event_id','')),'project_id':x.get('project_id',''),'source_type':'feishu_calendar','calendar':{'event_id':x.get('event_id','')},'title':x.get('summary') or x.get('title') or '已有会议','due':str((x.get('start_time') or {}).get('date') or (x.get('start_time') or {}).get('timestamp') or '')} for x in cache.get('items',[]) if x.get('status')!='cancelled']
  if knowledge_root:
   from calendar_project_links import link_project_calendar_items
   events=link_project_calendar_items(events,projects or [project],knowledge_root)
  meetings=[x for x in events if x.get('project_id')==project['id']]
  if cache:calendar_state='仅核对本机已保存日程快照 '+str(cache.get('fetched_at',''))+'；不代表最新或全部日程。'
 except (ValueError,TypeError,AttributeError):calendar_state='本机日程缓存暂无法读取；请另行核对，原记录保留。'
 return {'existing_items':reminders,'existing_meetings':meetings,'calendar_state':calendar_state,'calendar_notice':'真实会议、日程及外部已建任务不会取消或改写；请在提醒与日程核对，外部平台通知设置仍保留。','preserved':'交付、验收、回款责任、合同业绩、客户、Logo、材料、报价、沟通、执行记录及发票报销全部保留。'}

def mutate(root,projects,body,knowledge_root=None):
 action=body.get('action');ids=body.get('project_ids');rid=body.get('request_id');expected=body.get('expected_revisions')
 if action not in ('archive','restore') or not isinstance(ids,list) or not 1<=len(ids)<=100 or not all(isinstance(x,str) and re.fullmatch('[a-f0-9]{20}',x) for x in ids) or len(set(ids))!=len(ids):raise ValueError('请选择1到100个明确项目')
 if not isinstance(rid,str) or not re.fullmatch('[a-zA-Z0-9_-]{8,100}',rid):raise ValueError('缺少有效操作标识')
 if not isinstance(expected,dict) or any(type(expected.get(x)) is not int for x in ids):raise ValueError('缺少项目修订版本，请重新核对')
 reason=body.get('reason','');note=body.get('note','')
 if action=='archive' and reason not in REASONS:raise ValueError('归档原因必填，请选择有效原因')
 if not isinstance(note,str) or len(note)>2000:raise ValueError('补充备注最多2000字')
 known={p['id']:p for p in projects}
 if any(x not in known for x in ids):raise ValueError('项目已变化，请重新核对')
 signature=hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 with locked(root):
  m=read(root);prior=m['requests'].get(rid)
  if prior:
   if prior['signature']!=signature:raise ArchiveConflict('重复请求内容不同，请重新核对')
   return {**prior['result'],'replayed':True}
  for id in ids:
   a=state(root,id,m)
   if a['revision']!=expected[id]:raise ArchiveConflict('项目归档状态已被另一窗口更改，请重新核对；本次未修改任何项目')
   if a['archived']==(action=='archive'):raise ArchiveConflict('项目已处于目标状态，请重新核对')
  now=datetime.now().astimezone().isoformat(timespec='microseconds');changed=[]
  for id in ids:
   a=state(root,id,m);info=impact(known[id],root,projects,knowledge_root);suppressed=set(a['suppressed_task_ids'])
   suppressed_revisions=dict(a.get('suppressed_task_revisions',{}))
   if action=='archive':
    suppressed.update(x['id'] for x in info['existing_items'])
    suppressed_revisions.update({x['id']:x['revision'] for x in info['existing_items'] if 'revision' in x})
   event={'action':action,'reason':reason if action=='archive' else '', 'note':note.strip(),'at':now,'revision':a['revision']+1,'request_id':rid}
   a={**a,'archived':action=='archive','revision':event['revision'],'updated_at':now,'reason':event['reason'],'note':event['note'],'history':[*a['history'],event],'suppressed_task_ids':sorted(suppressed),'suppressed_task_revisions':suppressed_revisions,'evidence_baseline':evidence_snapshot(known[id],knowledge_root) if action=='archive' else a.get('evidence_baseline')}
   m['projects'][id]=a;changed.append(a)
  result={'ok':True,'items':changed,'message':'项目已归档，历史和未完责任保留' if action=='archive' else '已恢复原项目；禁联、暂停和旧提醒保持原规则'}
  m['requests'][rid]={'signature':signature,'result':result};commit(root,m)
  return result

def sales_write(fn):
 """Serialize sales writes with archive CAS; stale callbacks cannot resume a project."""
 @functools.wraps(fn)
 def call(payload,knowledge_root,state_root,*args,**kwargs):
  if not isinstance(payload,dict):raise ValueError('请求格式错误')
  with locked(state_root):
   id=payload.get('project_id') if isinstance(payload,dict) else None
   a=state(state_root,id);nested=getattr(LOCAL,'sales',set());key=(str(state_root),id)
   if key not in nested and (a['archived'] or payload.get('archive_revision',0)!=a['revision']):
    from project_rounds import RevisionConflict
    raise RevisionConflict('项目归档状态已变化或已归档，请重新核对；未执行本次销售操作')
   LOCAL.sales=nested|{key}
   try:return fn(payload,knowledge_root,state_root,*args,**kwargs)
   finally:LOCAL.sales=nested
 return call

def handle(h,knowledge_root,root):
 from urllib.parse import urlparse,parse_qs
 path=urlparse(h.path).path
 if path!='/api/project-archive':return False
 from local_resources import guard,read_json
 from invoice_vault import VaultError
 from project_workspace import build_projects
 try:
  guard(h);projects=build_projects(knowledge_root,root)
  if h.command=='GET':
   ids=parse_qs(urlparse(h.path).query).get('ids',[''])[0].split(',');m=read(root)
   result={'ok':True,'items':[{'project_id':p['id'],'title':p['title'],'archive':{**state(root,p['id'],m),'review':evidence_review(p,state(root,p['id'],m),knowledge_root)},'impact':impact(p,root,projects,knowledge_root)} for p in projects if not ids[0] or p['id'] in ids]}
  elif h.command=='POST':result=mutate(root,projects,read_json(h),knowledge_root)
  else:raise ValueError('不支持的方法')
  h._send_json(result)
 except ArchiveConflict as e:h._send_json({'ok':False,'error':str(e)},status=409)
 except VaultError as e:h._send_json({'ok':False,'error':str(e)},status=e.status)
 except ValueError as e:h._send_json({'ok':False,'error':str(e)},status=400)
 except OSError:h._send_json({'ok':False,'error':'归档未保存，原记录保留'},status=500)
 return True
