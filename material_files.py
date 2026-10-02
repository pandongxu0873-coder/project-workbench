"""Customer/project view over material_library assets; no collector or analysis engine.
Only human annotations are stored here. Originals remain in the existing managed KB.
"""
import base64
import fcntl
import hashlib
import io
import json
import os
import re
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse, quote
import material_library as library
from material_receipts import accepted

FILE_READ_SLOTS=threading.BoundedSemaphore(2)

MAX_FILE = 100 * 1024 * 1024
MAX_EXPORT = 256 * 1024 * 1024
KINDS = ('合同与补充协议','需求方案','报价商务','交付验收','其他文件')
ORIGINAL_SUFFIXES = {'.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx','.csv','.png','.jpg','.jpeg','.zip','.txt','.md'}

def annotations(root):
    path=Path(root)/'tracking/material_annotations.json'
    if not path.exists():return {'version':1,'assets':{}}
    with library._open(root,'tracking/material_annotations.json') as f:
        raw=f.read(library.MAX_INDEX_BYTES+1)
    if len(raw)>library.MAX_INDEX_BYTES:raise library.MaterialError('文件标注过大',503)
    value=json.loads(raw)
    if value.get('version')!=1 or not isinstance(value.get('assets'),dict):raise library.MaterialError('文件标注读取失败',503)
    for aid,item in value['assets'].items():
        if not isinstance(aid,str) or not isinstance(item,dict) or type(item.get('revision')) is not int or not isinstance(item.get('history'),list) or len(item['history'])!=item['revision']:
            raise library.MaterialError('文件标注格式异常，原记录保留',503)
        for i,event in enumerate(item['history'],1):
            if not isinstance(event,dict) or event.get('revision')!=i or not re.fullmatch('[a-f0-9]{64}',str(event.get('sha256',''))) or not isinstance(event.get('project_ids'),list):
                raise library.MaterialError('文件版本历史异常，原记录保留',503)
    return value

def document_type(name):
    for words,kind in [(r'合同|协议','合同与补充协议'),(r'报价|商务|价格','报价商务'),(r'验收|交付','交付验收'),(r'方案|需求|规划','需求方案')]:
        if re.search(words,name):return kind
    return '其他文件'

def catalog(root,state_root=None,projects=None):
    index=library.load_index(root);meta=annotations(root);projects=projects or []
    project_map={x['id']:x for x in projects};rows={}
    explicit={}
    for project in projects:
        for source in project.get('sources',[]):
            if source.get('relation')=='explicit_evidence':explicit.setdefault(source['path'],[]).append(project['id'])
    # Existing collector receipt is authoritative for exact project association.
    resolved={}
    if state_root:
        try:
            ledger=json.loads((Path(state_root)/'communication_pipeline/ledger.json').read_text())
            resolved={'REF-'+key[:20]:v['associations'][0] for key,v in ledger.get('items',{}).items() if v.get('status')=='archived' and len(v.get('associations',[]))==1}
        except (OSError,ValueError,KeyError,TypeError):pass
    for row in index.get('files',[]):
        association=resolved.get(row.get('id'),{})
        pid=association.get('project_id') or row.get('project_id','')
        customer=project_map.get(pid,{}).get('customer') or association.get('customer') or row.get('customer','')
        for source in row.get('sources',[]):
            aid=source if isinstance(source,str) else source.get('id',source.get('asset_id',''))
            asset=index['assets'].get(aid,{})
            path=asset.get('path','');suffix=Path(path).suffix.lower()
            # Transcripts/summaries are available in the communication view, not disguised as contracts.
            if suffix not in ORIGINAL_SUFFIXES or asset.get('kind')=='audio' or (suffix in ('.md','.txt') and not path.startswith('raw/assets/')):continue
            if library._sensitive(asset):continue
            if aid not in rows:
                cap=library.capability(root,index,aid)
                rows[aid]={'asset_id':aid,'title':asset.get('label') or Path(path).name,'filename':asset.get('label') or Path(path).name,
                    'kind':document_type(asset.get('label') or Path(path).name),'project_ids':[],'customers':[],'project_titles':[],
                    'sources':[],'text_assets':[],'search_text':'','metadata':meta['assets'].get(aid,{}),**{k:cap[k] for k in ('available','readable','downloadable')}}
            out=rows[aid]
            for linked_id in explicit.get(path,[]):
                if linked_id not in out['project_ids']:
                    out['project_ids'].append(linked_id);out['project_titles'].append(project_map[linked_id]['title'])
                linked_customer=project_map[linked_id]['customer']
                if linked_customer not in out['customers']:out['customers'].append(linked_customer)
            if pid and pid not in out['project_ids']:out['project_ids'].append(pid);out['project_titles'].append(project_map.get(pid,{}).get('title') or row.get('project_title') or pid)
            if customer and customer not in out['customers']:out['customers'].append(customer)
            receipt={'record_id':row.get('id'),'received_at':row.get('reviewed_at') or row.get('recorded_at',''),
                     'source':row.get('original_title') or row.get('title',''),'business_date':row.get('business_date',''),**row.get('attachment_receipt',{})}
            if receipt not in out['sources']:out['sources'].append(receipt)
            for ref in row.get('sources',[]):
                ref=ref if isinstance(ref,str) else ref.get('id','')
                source_asset=index['assets'].get(ref,{})
                if source_asset.get('readable') and not library._sensitive(source_asset) and Path(source_asset.get('path','')).suffix.lower() in library.TEXT_SUFFIXES and ref not in out['text_assets']:
                    out['text_assets'].append(ref)
            # Only already extracted text, no parser/OCR/model on browse.
            out['search_text']+=' '+str(row.get('summary',''))+' '+str(row.get('extracted_text',''))
    for out in rows.values():
        m=out['metadata'];latest=m.get('history',[])[-1] if m.get('history') else {}
        if latest:
            try:
                _,_,sha=verified(root,out['asset_id'])
                latest=next((x for x in reversed(m.get('history',[])) if x.get('sha256')==sha),{})
            except library.MaterialError:latest={}
        out['annotation']=latest;out['revision']=m.get('revision',0);out.pop('metadata')
        if latest.get('project_ids') is not None:
            out['project_ids']=latest['project_ids']
            out['project_titles']=[project_map.get(pid,{}).get('title') or pid for pid in latest['project_ids']]
            # Folder visibility does not automatically establish applicability.
            out['customers']=list(dict.fromkeys([*out['customers'],*[project_map.get(pid,{}).get('customer','') for pid in latest['project_ids']]]))
        out['kind']=latest.get('kind') or out['kind']
        out['confirmation_events']=index['assets'].get(out['asset_id'],{}).get('confirmation_events',[])
        if out['confirmation_events']:
            try:
                _,_,event_sha=verified(root,out['asset_id']);out['confirmation_events']=[e for e in out['confirmation_events'] if e.get('sha256')==event_sha]
            except library.MaterialError:out['confirmation_events']=[]
        out['file_state']='已确认材料' if latest.get('confirmation') in ('客户认可文本','已签署') or (not latest and accepted([e for e in out['confirmation_events'] if e.get('project_id') in out['project_ids']])) else '待核文件'
        out['search_text']=' '.join([out['search_text'],out['title'],out['filename'],*out['project_titles'],latest.get('contract_number','')])
    for out in rows.values():
        latest=out['annotation'];old=rows.get(latest.get('related_asset_id'))
        if old and out['project_ids'] and latest.get('relation')=='明确替代' and out['file_state']=='已确认材料' and set(out['project_ids'])==set(old['project_ids']) and out['kind']==old['kind']:
            old['file_state']='历史版本'
    return list(rows.values())

def in_file_scope(row,q):
    # A CRM subject view references its already-linked projects; it does not
    # copy originals or change their applicable scope/confirmation.
    linked=set(filter(None,str(q.get('project_ids','')).split(',')))
    customer=q.get('customer','');pid=q.get('project_id','')
    owned=(not customer and not linked) or customer in row['customers'] or bool(linked.intersection(row['project_ids']))
    return owned and (not pid or pid in row['project_ids'])

def listing(root,state_root,q,projects=None):
    rows=catalog(root,state_root,projects)
    grouped=q.get('view')=='folders'
    if grouped:
        import material_organization as organization
        organization.apply(root,state_root,rows)
        for row in rows:
            o=row['organization'];row['search_text']+=' '+ ' '.join(str(o.get(k,'')) for k in ('contract_number','folder_title','legal_entity','display_title'))
    customer=q.get('customer','');pid=q.get('project_id','');kind=q.get('kind','');term=q.get('q','').strip().lower()
    scope=[x for x in rows if in_file_scope(x,q)]
    if pid:
        for row in scope:
            if not row['annotation']:row['file_state']='已确认材料' if accepted(row['confirmation_events'],pid) else '待核文件'
    matches=[];read_chars=0;text_cache={};limited=False
    for row in scope:
        if kind and kind!=row['kind']:continue
        if q.get('file_state') and row['file_state']!=q['file_state']:continue
        found=not term or term in row['search_text'].lower()
        if not found:
            for aid in row['text_assets']:
                if aid not in text_cache:
                    if read_chars>=8*1024*1024:limited=True;break
                    try:content=library.source(root,aid)['content']
                    except library.MaterialError:content=''
                    read_chars+=len(content);text_cache[aid]=content.lower()
                if term in text_cache[aid]:found=True;break
        if found:matches.append(row)
    matches.sort(key=lambda x:({'已确认材料':0,'待核文件':1,'历史版本':2}[x['file_state']],x['title']))
    folders=[];hidden_history=0
    if grouped:matches,folders,hidden_history=organization.folder_result(matches,q)
    offset=max(0,int(q.get('offset',0)));limit=min(100,max(1,int(q.get('limit',40))))
    return {'ok':True,'folders':folders,'hidden_history':hidden_history,'grouped':grouped,'items':[] if grouped and not q.get('folder_id') else [{k:v for k,v in x.items() if k not in ('search_text','text_assets')} for x in matches[offset:offset+limit]],'total':len(matches),
            'states':{s:sum(x['file_state']==s for x in scope) for s in ('已确认材料','待核文件','历史版本')},
            'customers':sorted({c for x in rows for c in x['customers'] if c}),
            'projects':[{'id':i,'title':t} for i,t in dict((i,t) for x in rows if in_file_scope(x,{**q,'project_id':''}) for i,t in zip(x['project_ids'],x['project_titles'])).items()],
            'search_scope':'文件名、项目名、合同编号及已有提取正文（单份至多64000字）'+('；本次达到读取上限，请缩小客户范围' if limited else '；未声明全文完整索引')}

def verified(root,aid):
    asset=library.asset(library.load_index(root),aid)
    if not asset.get('downloadable'):raise library.MaterialError('原件未开放下载',403)
    with library._open(root,asset['path']) as f:
        size=os.fstat(f.fileno()).st_size
        if size>MAX_FILE:raise library.MaterialError('单份文件超过100MB，本入口未处理',413)
        raw=f.read(MAX_FILE+1)
    if len(raw)!=size or len(raw)>MAX_FILE:raise library.MaterialError('原件读取不完整',409)
    sha=hashlib.sha256(raw).hexdigest()
    expected=asset.get('sha256')
    if expected and expected!=sha:raise library.MaterialError('原件校验不一致，保留现有资料并待核',409)
    return asset,raw,sha

def detail(root,aid):
    asset,raw,sha=verified(root,aid)
    data=annotations(root)['assets'].get(aid,{})
    all_history=data.get('history',[])
    valid=[x for x in all_history if x.get('sha256')==sha]
    return {'ok':True,'asset_id':aid,'sha256':sha,'size_bytes':len(raw),'original_status':'原件已读取并校验',
            'confirmation_events':[e for e in asset.get('confirmation_events',[]) if e.get('sha256')==sha],
            'revision':data.get('revision',0),'annotation':valid[-1] if valid else {},'history':all_history,
            'changed_content':bool(all_history and not valid),'path':asset['path'],
            'preview':library.source(root,aid) if asset.get('readable') and Path(asset['path']).suffix.lower() in library.TEXT_SUFFIXES else None}

def annotate(root,payload,projects):
    if not isinstance(payload,dict):raise library.MaterialError('标注须为对象')
    aid=payload.get('asset_id','');asset,raw,sha=verified(root,aid)
    if sha!=payload.get('sha256'):raise library.MaterialError('原件版本已变化，请重新核对',409)
    pids=payload.get('project_ids',[])
    if not isinstance(pids,list) or len(pids)>30 or any(p not in {x['id'] for x in projects} for p in pids):raise library.MaterialError('请选择已有的具体项目')
    values={}
    for key in ('version_label','confirmation','basis','scope','related_asset_id','relation','contract_number','kind'):
        value=payload.get(key,'')
        if not isinstance(value,str) or len(value)>3000:raise library.MaterialError('标注格式无效')
        values[key]=value.strip()
    if values['confirmation'] not in ('待核验','我方提交','客户认可文本','已签署'):raise library.MaterialError('确认状态无效')
    if not values['basis']:raise library.MaterialError('请记录本次归属或版本判断的依据')
    if values['kind'] not in KINDS:raise library.MaterialError('文件类型无效')
    if values['related_asset_id']:
        library.asset(library.load_index(root),values['related_asset_id'])
        if values['related_asset_id']==aid or values['relation'] not in ('配套阅读','明确替代','另一版本'):raise library.MaterialError('版本关系无效')
    rid=payload.get('request_id','')
    if not isinstance(rid,str) or not re.fullmatch('[a-zA-Z0-9-]{16,80}',rid):raise library.MaterialError('缺少请求编号')
    entry={**values,'project_ids':list(dict.fromkeys(pids)),'sha256':sha,'request_id':rid}
    target=Path(root)/'tracking/material_annotations.json'
    with (target.parent/'material_annotations.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);data=annotations(root);prior=data['assets'].get(aid,{'revision':0,'history':[]})
        existing=next((x for x in prior['history'] if x.get('request_id')==rid),None)
        if existing:
            if any(existing.get(k)!=v for k,v in entry.items()):raise library.MaterialError('同次请求内容不同',409)
            return detail(root,aid)
        if payload.get('revision')!=prior['revision']:raise library.MaterialError('标注已变化，请重读后合并',409)
        entry.update(saved_at=datetime.now().astimezone().isoformat(),revision=prior['revision']+1)
        data['assets'][aid]={'revision':entry['revision'],'history':[*prior['history'],entry]}
        fd,tmp=tempfile.mkstemp(dir=target.parent,prefix='.material-')
        try:
            with os.fdopen(fd,'w') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
            os.replace(tmp,target)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    return detail(root,aid)

def upload(root,state_root,payload,projects):
    from tools.communication_pipeline import Pipeline, digest
    from material_receipts import preserve
    from datetime import date
    name=payload.get('filename','');pid=payload.get('project_id','');rid=payload.get('request_id','')
    if not isinstance(name,str) or not name or len(name)>240 or Path(name).name!=name or re.search(r'[\\/\x00-\x1f]',name):raise library.MaterialError('文件名称无效')
    if Path(name).suffix.lower() not in ORIGINAL_SUFFIXES:raise library.MaterialError('此格式暂不支持本入口保存')
    if not re.fullmatch('[a-zA-Z0-9-]{16,80}',rid):raise library.MaterialError('缺少保存请求编号')
    project=next((p for p in projects if p['id']==pid),None)
    if not project:raise library.MaterialError('请选择文件所属的具体项目')
    try:raw=base64.b64decode(payload.get('content',''),validate=True)
    except (ValueError,TypeError):raise library.MaterialError('文件内容不完整')
    if not raw or len(raw)>20*1024*1024:raise library.MaterialError('本入口支持20MB以内的文件')
    cfg={'knowledge_root':str(root),'local_roots':[]};pipe=Pipeline(cfg,Path(state_root),Path(root),date.today(),date.today())
    with (pipe.root/'pipeline.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise library.MaterialError('自动整理正在运行，请稍后保存；当前文件保留',409)
        # Reload inside the same lock used by scheduled sync; never overwrite its ledger.
        pipe.ledger=json.loads((pipe.root/'ledger.json').read_text()) if (pipe.root/'ledger.json').exists() else {'version':1,'items':{}}
        previous=[r for e in pipe.ledger['items'].values() for r in e.get('receipts',[]) if r.get('origin')=='workbench://upload/'+rid]
        if previous and any(r.get('project_id')!=pid or r.get('content_sha256')!=digest(raw) or r.get('title')!=name for r in previous):raise library.MaterialError('同次保存内容不同',409)
        # Preserve first. Existing scheduled extraction will retry; no model on upload.
        entry=pipe.stage(rid,name,raw,Path(name).suffix.lower(),'workbench_upload','workbench://upload/'+rid,text='')
        received=next(r for r in entry['receipts'] if r['origin']=='workbench://upload/'+rid)
        received.update(project_id=pid,customer=project['customer'],project_title=project['title'],content_sha256=digest(raw))
        pipe.checkpoint();preserve(pipe)
    index=library.load_index(root)
    row=next(r for r in index['files'] if r.get('attachment_receipt',{}).get('origin')=='workbench://upload/'+rid)
    aid=row['sources'][0];result=detail(root,aid)
    return {**result,'receipt':{'original_saved':True,'project_title':project['title'],'confirmation':'待核验','analysis_updated':False,'message':'原件已保存并校验，已归入本项目；客户确认待核验。正文提取沿用已有自动整理。'}}


def export_files(root,state_root,q,projects=None):
    if not q.get('customer') and not q.get('project_id') and not q.get('project_ids'):raise library.MaterialError('请先选择客户或项目再导出')
    rows=catalog(root,state_root,projects)
    rows=[x for x in rows if in_file_scope(x,q)]
    if len(rows)>250:raise library.MaterialError('当前范围超过250份，请按项目导出',413)
    manifest=[];total=0;seen={};buf=io.BytesIO();snapshot={'version':1,'assets':{},'files':[],'recordings':[],'conflicts':[]};meta={'version':1,'assets':{}}
    source_index=library.load_index(root);source_meta=annotations(root)
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for row in rows:
            asset,raw,sha=verified(root,row['asset_id']);total+=len(raw)
            if total>MAX_EXPORT:raise library.MaterialError('当前导出超过256MB，请缩小范围',413)
            name='raw/assets/export/'+sha+Path(asset['path']).suffix.lower()
            if sha not in seen:z.writestr(name,raw);seen[sha]=name
            name=seen[sha]
            # Shared original bytes, every received source and version event retained.
            snapshot['assets'][row['asset_id']]={**asset,'path':name,'sha256':sha}
            for original in source_index.get('files',[]):
                if row['asset_id'] in [x if isinstance(x,str) else x.get('id') for x in original.get('sources',[])]:
                    snapshot['files'].append({**original,'sources':[row['asset_id']]})
            if row['asset_id'] in source_meta['assets']:meta['assets'][row['asset_id']]=source_meta['assets'][row['asset_id']]
            manifest.append({k:v for k,v in row.items() if k not in ('search_text','text_assets')}|{'sha256':sha,'export_path':name})
        z.writestr('清单.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        z.writestr('tracking/material_library.json',json.dumps(snapshot,ensure_ascii=False,indent=2))
        z.writestr('tracking/material_annotations.json',json.dumps(meta,ensure_ascii=False,indent=2))
        z.writestr('读取说明.txt','原件字节保持不变，SHA-256见清单。解压后可直接打开原件；索引和人工版本依据一并保留。客户目录可见不等于适用于客户所有项目。此导出不是异地备份。')
    return buf.getvalue()

def analysis_annotations(root, project_id, existing_sources):
    if not (Path(root)/'tracking/material_annotations.json').exists():return []
    known={x.get('path') for x in existing_sources}
    index=library.load_index(root);out=[]
    for aid,meta in annotations(root)['assets'].items():
        asset=index['assets'].get(aid,{})
        if asset.get('path') not in known or library._sensitive(asset) or asset.get('allow_analysis') is False:continue
        try:_,_,sha=verified(root,aid)
        except library.MaterialError:continue
        history=[x for x in meta.get('history',[]) if x.get('sha256')==sha and project_id in x.get('project_ids',[])]
        if not history:continue
        last=history[-1]
        out.append({'path':'local://file-version/'+aid,'date':'','recorded_at':last['saved_at'][:10],
                    'content':json.dumps({'asset_id':aid,'original_path':asset['path'],'sha256':sha,'annotations':history},ensure_ascii=False),
                    'truncated':False,'relation':'explicit_evidence'})
    return out


def handle(h,root,state_root):
    parsed=urlparse(h.path)
    if parsed.path not in ('/api/material-library/files','/api/material-library/files/detail','/api/material-library/files/annotation','/api/material-library/files/upload','/api/material-library/files/export','/api/material-library/files/preview','/api/material-library/files/original'):return False
    acquired=FILE_READ_SLOTS.acquire(blocking=False)
    if not acquired:
        library._json(h,{'ok':False,'error':'文件读取忙，请稍后重试'},503);return True
    try:
        host=urlparse('http://'+h.headers.get('Host',''))
        if host.hostname not in ('127.0.0.1','localhost','::1') or host.port!=h.server.server_port or h.headers.get('Sec-Fetch-Site') in ('cross-site','same-site') or not h._trusted_origin():
            raise library.MaterialError('来源不受信任',403)
        q={k:v[0] for k,v in parse_qs(parsed.query).items()}
        from project_workspace import build_projects
        projects=build_projects(root,state_root) if parsed.path in ('/api/material-library/files','/api/material-library/files/annotation','/api/material-library/files/upload','/api/material-library/files/export') else []
        if h.command=='POST':
            if parsed.path not in ('/api/material-library/files/annotation','/api/material-library/files/upload'):raise library.MaterialError('方法不支持',405)
            if h.headers.get('X-Workbench-Request')!='local-v1':raise library.MaterialError('缺少本机写入标识',403)
            n=int(h.headers.get('Content-Length','0'))
            if n<=0 or n>(29*1024*1024 if parsed.path.endswith('/upload') else 32000):raise library.MaterialError('请求过大',413)
            h.connection.settimeout(10)
            payload=json.loads(h.rfile.read(n));result=upload(root,state_root,payload,projects) if parsed.path.endswith('/upload') else annotate(root,payload,projects)
        elif parsed.path.endswith('/original'):
            asset,raw,sha=verified(root,q.get('asset_id',''))
            if q.get('sha256') and q['sha256']!=sha:raise library.MaterialError('原件版本已变化，请重新核对再下载',409)
            h.send_response(200);h.send_header('Content-Type','application/octet-stream');h.send_header('Content-Length',str(len(raw)));h.send_header('Cache-Control','no-store');h.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(Path(asset.get('label') or asset['path']).name,safe=''));h.end_headers()
            if h.command!='HEAD':h.wfile.write(raw)
            return True
        elif parsed.path.endswith('/preview'):
            asset,raw,sha=verified(root,q.get('asset_id',''))
            if Path(asset['path']).suffix.lower()!='.pdf' or not raw.startswith(b'%PDF-'):
                raise library.MaterialError('此格式仅提供原件下载',415)
            h.send_response(200);h.send_header('Content-Type','application/pdf');h.send_header('Content-Length',str(len(raw)));h.send_header('Cache-Control','no-store');h.send_header('X-Content-Type-Options','nosniff');h.send_header('Content-Security-Policy',"sandbox; default-src 'none'");h.end_headers()
            if h.command!='HEAD':h.wfile.write(raw)
            return True
        elif parsed.path.endswith('/export'):
            raw=export_files(root,state_root,q,projects)
            h.send_response(200);h.send_header('Content-Type','application/zip');h.send_header('Content-Length',str(len(raw)));h.send_header('Cache-Control','no-store');h.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote('客户原件与清单.zip'));h.end_headers()
            if h.command!='HEAD':h.wfile.write(raw)
            return True
        elif parsed.path.endswith('/detail'):result=detail(root,q.get('asset_id',''))
        else:result=listing(root,state_root,q,projects)
        library._json(h,result)
    except library.MaterialError as e:library._json(h,{'ok':False,'error':str(e)},e.status)
    except (ValueError,TypeError,KeyError,OSError):library._json(h,{'ok':False,'error':'文件读取或保存未完成，已有原件保留'},503)
    finally:FILE_READ_SLOTS.release()
    return True
