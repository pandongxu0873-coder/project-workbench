"""Local UI bridge to the existing collector; fixed commands, durable progress."""
import datetime as dt
import fcntl
import os
import subprocess
import threading
import time
import uuid
import re
import hashlib
from pathlib import Path
from tools.communication_pipeline import load,save,now,runtime_env

APP=Path(__file__).resolve().parent
ACTIONS={'run','resume','doctor','collect'}
PHASES={'starting':'正在连接本机','checking':'检查来源连接','local':'读取电脑文件与录音','wechat':'读取微信客户沟通','feishu':'读取飞书沟通与妙记','email':'读取邮件与附件','tencent_meeting':'读取腾讯会议逐字稿','analyzing':'AI按客户与项目整理','archiving':'保存原件与归档记录','refreshing':'更新工作台摘要','done':'本轮结束','failed':'本轮未完成'}

def busy(state):
    root=Path(state)/'communication_pipeline';root.mkdir(parents=True,exist_ok=True)
    with (root/'pipeline.lock').open('a') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
    return False

def alive(pid):
    if not isinstance(pid,int) or pid<=0:return False
    try:os.kill(pid,0);return True
    except (ProcessLookupError,PermissionError):return False

def archived_project_notes(state,knowledge):
    """Explicitly linked, dated archive notes also count when saved outside the collector."""
    from project_workspace import build_projects
    knowledge=Path(knowledge).resolve();notes=[]
    for project in build_projects(knowledge,Path(state)):
        for source in project['sources']:
            rel=source['path']
            if source.get('relation')=='background_reference':continue
            if not rel.startswith(('raw/transcripts/','raw/articles/')) or '/自动沟通归档/' in rel or not rel.endswith('.md'): continue
            path=(knowledge/rel).resolve()
            if knowledge not in path.parents or not source.get('readable'): continue
            try: text=path.read_text(encoding='utf-8')
            except (OSError,UnicodeError): continue
            parts=text.split('---',2)
            if len(parts)!=3 or parts[0].strip():continue
            fields=dict(re.findall(r'^([a-z_]+):\s*([^\n]+)',parts[1],re.M))
            if fields.get('type')!='project_communication':continue
            occurred=fields.get('occurred_at','');reviewed=fields.get('reviewed_at',occurred)
            try:
                if dt.date.fromisoformat(occurred).isoformat()!=occurred or dt.date.fromisoformat(reviewed).isoformat()!=reviewed or reviewed>now()[:10]:continue
            except ValueError:continue
            section=re.search(r'^## (?:核心结论|当前结论|一句话结论|本次结论)\n+(.*?)(?=\n## |\Z)',parts[2],re.M|re.S)
            lead=re.search(r'^\*\*(.+)\*\*$',parts[2],re.M)
            summary=section.group(1) if section else lead.group(1) if lead else ''
            paragraphs=[p.strip().replace('**','') for p in summary.split('\n\n') if p.strip() and not p.lstrip().startswith('- ')]
            if not paragraphs:continue
            notes.append({'project':project,'day':reviewed,'id':'archive-'+hashlib.sha256(rel.encode()).hexdigest()[:20],'title':fields.get('title',path.stem),'kind':'document','business_date':occurred,'summaries':paragraphs[:3],'evidence':[],'sources':[{'id':rel,'label':'知识库整理原文','readable':True,'kind':'document','project_id':project['id'],'path':rel}]})
    return notes


def daily_digest(state,knowledge,history=False):
    """Read committed classification receipts, deduplicated across today's retries.

    Collection date labels the digest, while each entry retains its business date.
    No model call or inferred project assignment happens in this read endpoint.
    """
    root=Path(state)/'communication_pipeline';today=now()[:10]
    reviews=sorted((root/'runs').glob('*/review.json')) if (root/'runs').exists() else []
    ledger=load(root/'ledger.json',{}).get('items',{})
    from tools.communication_imports import read as read_imports
    ledger,imports=read_imports(root,ledger)
    import_reviews=dict(imports)
    reviews += list(import_reviews)
    def read_review(path):return import_reviews.get(path) or load(path,{})
    role_index=load(root/'communication_roles.json',{})
    # Previously archived recent project messages were deduplicated during the
    # history import. Reuse them in the full journey instead of hiding its end.
    history_available=any(e.get('channel')=='wechat_history' and e.get('status') in ('archived','archived_reference') for e in ledger.values())
    def history_member(entry):
        return entry.get('channel')=='wechat_history' or (history_available and entry.get('channel')=='wechat' and bool(entry.get('associations')))
    def in_scope(path):
        review=read_review(path)
        ids=review.get('completed',[])
        if not ids:return (review.get('source_scope')==['wechat_history'])==history
        return any(history_member(ledger.get(ident,{})) if history else ledger.get(ident,{}).get('channel')!='wechat_history' for ident in ids)
    reviews=[path for path in reviews if in_scope(path)]
    notes=[] if history else archived_project_notes(state,knowledge)
    def publication_day(path):
        published=read_review(path).get('published_at','')[:10]
        try:return dt.date.fromisoformat(published).isoformat() if published and published<=today else path.parent.name[:10]
        except ValueError:return path.parent.name[:10]
    days=[publication_day(p) for p in reviews]+[n['day'] for n in notes]
    day=max(days) if days else today
    library=load(Path(knowledge)/'tracking/material_library.json',{})
    assets=library.get('assets',{});reference={r.get('original_sha256'):r for r in library.get('files',[]) if r.get('original_sha256')}
    material_assets={};recording_customers={};by_prefix={}
    for aid,asset in assets.items():
        prefix=Path(asset.get('path','')).name.split('_')[0].split('.')[0]
        by_prefix.setdefault(prefix,[]).append(aid)
    for r in library.get('recordings',[]):
        material_assets[r.get('sha256')]=r.get('sources',[])
        recording_customers[r.get('sha256')]=r.get('customer','')
    rows_by_material={};catalog={}
    for path in reviews:
        if not history and publication_day(path)!=day:continue
        review=read_review(path);catalog.update({p['id']:p for p in review.get('projects',[])})
        for ident in review.get('completed',[]):
            if ledger.get(ident,{}).get('status') not in ('archived','archived_reference','ignored'):continue
            if history and not history_member(ledger[ident]):continue
            if not history and ledger[ident].get('channel')=='wechat_history':continue
            rows_by_material[ident]=[r for r in review.get('items',[]) if r.get('material_id')==ident and r.get('classification')!='ignore']
    groups={};seen=set();counts={'recordings':0,'documents':0,'messages':0,'emails':0};ignored=0
    for ident,rows in rows_by_material.items():
        if not rows:ignored+=1;continue
        entry=ledger[ident];channel=entry.get('channel','');kind='recording' if channel in ('computer','phone_recording') else 'email' if channel.startswith('email') else 'document' if channel in ('desktop','feishu_document','tencent_meeting') else 'message'
        if ident not in seen:counts[{'recording':'recordings','email':'emails','document':'documents','message':'messages'}[kind]]+=1;seen.add(ident)
        ref=reference.get(entry.get('sha256'),{});source_assets=ref.get('sources') or material_assets.get(entry.get('sha256')) or by_prefix.get(ident[:20],[])
        local_groups={}
        for row in rows:
            pid=row.get('project_id','') if row['classification']=='project' else ''
            project=catalog.get(pid,{})
            customer=project.get('customer') or ref.get('customer') or (recording_customers.get(entry.get('sha256')) if not any(r.get('classification')=='project' for r in rows) else '') or '其他沟通与知识'
            if customer in ('星海汽车商城','示例汽车集团汽车','星海汽车'):customer='星海汽车／示例汽车集团'
            group_kind='project' if pid else 'knowledge' if row['classification']=='knowledge' else 'context'
            key=pid or customer+'|'+group_kind
            group=groups.setdefault(key,{'id':key,'customer':customer,'project_id':pid,'project_title':project.get('title') or ('客户知识与方案' if group_kind=='knowledge' else '业务背景与沟通' if customer!='其他沟通与知识' else '业务线索与参考'),'kind':group_kind,'items':[]})
            item=local_groups.get(key)
            if item is None:
                item={'id':ident,'title':entry['title'],'kind':kind,'business_date':entry.get('business_date') or row.get('business_date',''),'summaries':[],'evidence':[],'sources':[],'historical':history or channel=='wechat_history'}
                # A grouped project note may link several recordings: select this physical source only.
                for aid in source_assets:
                    a=assets.get(aid,{})
                    if a.get('sensitive') or a.get('restricted'):continue
                    rel=a.get('path','')
                    if ident[:20] not in rel and kind=='recording':continue
                    if a.get('readable') or a.get('kind')=='audio' or rel.endswith(('.pdf','.pptx','.xlsx','.docx')):
                        item['sources'].append({'id':aid,'label':a.get('label','原文'),'kind':a.get('kind','document'),'readable':bool(a.get('readable')),'downloadable':bool(a.get('downloadable'))})
                group['items'].append(item);local_groups[key]=item
            if row['summary'] not in item['summaries']:item['summaries'].append(row['summary'])
            for e in row.get('evidence',[]):
                if e not in item['evidence']:item['evidence'].append(e)
    for note in notes:
        if note['day']!=day:continue
        project=note['project'];pid=project['id']
        group=groups.setdefault(pid,{'id':pid,'customer':project['customer'],'project_id':pid,'project_title':project['title'],'kind':'project','items':[]})
        group['items'].append({k:v for k,v in note.items() if k not in ('project','day')})
        if note['id'] not in seen:counts['documents']+=1;seen.add(note['id'])
    priority={'recording':0,'document':1,'email':2,'message':3}
    result=sorted(groups.values(),key=lambda g:(g['kind']!='project',not any(i['kind']=='recording' for i in g['items']),g['customer'],g['project_title']))
    for group in result:
        from communication_roles import describe,evidence_label
        for item in group['items']:
            entry=ledger.get(item['id'],{})
            if not entry and item['kind']=='document':entry={'communication':{'type':'document','reason':'知识库依据原始材料形成的整理或复核说明。'}}
            if entry.get('channel')=='wechat' and not entry.get('message_direction') and entry.get('original'):
                original=load(Path(entry['original']),{})
                entry={**entry,'message_direction':original.get('message',{}).get('direction','')}
            item['communication']=describe(entry,[{'summary':'；'.join(item['summaries']),'evidence':item['evidence']}],role_index)
            item['evidence']=[{**e,'display_label':evidence_label(e.get('level'),item['communication'])} for e in item['evidence']]
        group['items'].sort(key=lambda i:(i['business_date'],(re.search(r'_(\d{6})$',i['title'])[1] if re.search(r'_(\d{6})$',i['title']) else ''),i['title']),reverse=True)
        group['items'].sort(key=lambda i:priority[i['kind']])
    return {'date':day,'is_today':day==today,'groups':result,'counts':counts,'material_count':len(seen),'project_count':sum(bool(g['project_id']) for g in result),'customer_count':len({g['customer'] for g in result if g['customer']!='其他沟通与知识'}),'ignored_count':ignored}

def status(state,knowledge):
    state=Path(state);root=state/'communication_pipeline'
    launch=load(root/'ui_request.json',{}) or {};active=load(root/'active_run.json',{}) or {};locked=busy(state)
    same=bool(active and active.get('request_id')==launch.get('request_id'))
    if active and (same or not launch or active.get('started_at','')>launch.get('started_at','') or (locked and active.get('state')=='running')):
        current=dict(active)
        if current.get('state')=='running' and not locked:current.update(state='interrupted',phase='failed')
    elif launch:
        current={**launch,'state':'running' if time.time()-launch.get('created_epoch',0)<15 else 'interrupted','phase':'starting'}
    else:current={'state':'idle','phase':'done'}
    if locked and current['state'] not in ('running','starting'):
        current={'state':'running','phase':'checking','external':True,'request_id':active.get('request_id','external')}
    latest=load(root/'latest.json',{}) or {}
    receipt=current.get('receipt') or latest
    # A completed UI job must not hide a newer local CLI/phone import.
    # Never attach an old result to a different job while that job is running.
    if not locked and current.get('state') not in ('running','starting') and latest.get('checked_at','')>receipt.get('checked_at',''):
        receipt=latest
        current={'state':'idle','phase':'done','run_id':receipt.get('run_id'),'action':'external'}
    # A receipt from a previous invocation never becomes the new job's result.
    matching=not current.get('request_id') or receipt.get('run_id')==current.get('run_id')
    report=receipt if matching or current['state']=='idle' else {}
    source=load(root/'source_status.json',{}) or {}
    if not source:
        old=load(state/'source_access_status.json',{}) or {}
        source={'checked_at':old.get('checked_at'),'feishu_user':old.get('feishu_user')=='ready','company_mail':{'available':isinstance(old.get('company_mail'),dict) and old['company_mail'].get('available',False)},'sources':[{'name':'电脑语音备忘录','status':old.get('computer_recording_directory','unknown')}]}
    connections=[{'name':'企业邮箱','available':source.get('company_mail',{}).get('available')}, {'name':'飞书沟通与妙记','available':source.get('feishu_user')}]
    connections.append({'name':'个人微信（本地记录）','available':source.get('wechat',{}).get('available',False)})
    tencent=source.get('tencent_meeting',{})
    connections.append({'name':'腾讯会议（含可读共享记录）','available':tencent.get('available',False)})
    connections += [{'name':x['name'],'available':x.get('status')=='readable'} for x in source.get('sources',[])]
    pids=list(dict.fromkeys(report.get('projects',[])+report.get('refreshed',[])));projects=[]
    if pids:
        from project_workspace import build_projects
        catalog={p['id']:p for p in build_projects(Path(knowledge),state)}
        projects=[{'id':pid,'title':catalog.get(pid,{}).get('title','查看项目'),'customer':catalog.get(pid,{}).get('customer','')} for pid in pids]
    analysis_refresh={'active':False,'pending':0,'failed':0}
    if report.get('refresh_pending'):
        from project_analysis import status as analysis_status
        waiting=[];ready=[];failed=[]
        for pid in report['refresh_pending']:
            try:
                a=analysis_status(pid,Path(knowledge),state)
                if a.get('state')=='ready' and not a.get('stale'):ready.append(pid)
                elif a.get('sync',{}).get('status')=='failed' or a.get('state')=='error':failed.append(pid)
                else:waiting.append(pid)
            except (ValueError,OSError):failed.append(pid)
        report={**report,'refresh_pending':waiting+failed,'refreshed':list(dict.fromkeys(report.get('refreshed',[])+ready))}
        analysis_refresh={'active':bool(waiting) and not failed,'pending':len(waiting)+len(failed),'failed':len(failed)}
    public={k:current[k] for k in ('request_id','run_id','state','phase','action','started_at','updated_at','from','to','observed','new','duplicates','external','analysis_done','analysis_total','refresh_done','refresh_total') if k in current}
    public['phase_label']=PHASES.get(current.get('phase'),'正在整理')
    public['running']=current['state']=='running'
    history=load(root/'wechat_history.json',{}) or {}
    if history.get('state')=='processing' and history.get('phase')=='refreshing' and current.get('action')=='history':
        history.update(done=current.get('refresh_done',0),total=current.get('refresh_total',0))
    history={k:history[k] for k in ('state','phase','done','total','updated_at','conversations','messages','from','to','media_bodies_read','events','customers','project_count') if k in history}
    return {'ok':True,'job':public,'analysis_refresh':analysis_refresh,'receipt':{k:report[k] for k in ('run_id','status','from','to','checked_at','observed','new','duplicates','unresolved','archived_reference','refresh_pending','gaps','projects','refreshed','source_scope','excluded','material_ids','completed_material_ids') if k in report},'connections':connections,'connections_checked_at':source.get('checked_at'),'projects':projects,'digest':daily_digest(state,knowledge),'history_digest':daily_digest(state,knowledge,history=True),'wechat_history':history}

def start(payload,state,knowledge):
    if not isinstance(payload,dict) or set(payload)-{'action'}:raise ValueError('只支持工作台内置整理动作')
    action=payload.get('action','run')
    if not isinstance(action,str) or action not in ACTIONS:raise ValueError('整理动作无效')
    state=Path(state);root=state/'communication_pipeline';root.mkdir(parents=True,exist_ok=True)
    with (root/'ui_dispatch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        current=status(state,knowledge)
        if current['job']['running'] or busy(state):return {**current,'started':False}
        if action=='resume' and current['job']['state']=='interrupted':
            previous=load(root/'active_run.json',{}) or {}
            if previous.get('action')=='doctor':action='doctor'
            elif previous.get('phase') in ('checking','local','wechat','feishu','email','tencent_meeting'):action='run'
        interpreter=APP/'tools/.communication-venv/bin/python'
        if not interpreter.exists():raise ValueError('本机整理环境暂不可用，请修复连接后重试')
        ident=uuid.uuid4().hex
        request={'request_id':ident,'action':action,'started_at':now(),'created_epoch':time.time()}
        save(root/'ui_request.json',request)
        command=[str(interpreter),str(APP/'tools/communication_pipeline.py'),action,'--state-root',str(state),'--knowledge-root',str(knowledge),'--request-id',ident]
        try:
            with (root/'ui-worker.log').open('ab') as log:
                proc=subprocess.Popen(command,cwd=APP,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,env=runtime_env())
        except OSError:
            request['created_epoch']=0;save(root/'ui_request.json',request);raise ValueError('本机任务未启动，已保留原有资料') from None
        request['pid']=proc.pid;save(root/'ui_request.json',request)
        threading.Thread(target=proc.wait,daemon=True).start()
        return {**status(state,knowledge),'started':True}
