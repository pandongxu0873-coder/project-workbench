"""Read-only, content-bound archive overlay. Never changes business confirmation."""
import hashlib,json,os,threading
from pathlib import Path
from functools import lru_cache
import material_library as lib

_LOCK=threading.RLock()

@lru_cache(maxsize=1024)
def _digest(root,rel,stamp):
    h=hashlib.sha256()
    with lib._open(root,rel) as f:
        before=os.fstat(f.fileno())
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=stamp:return ''
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
        after=os.fstat(f.fileno())
    if (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)!=stamp:return ''
    return h.hexdigest()

def load(state_root):
    path=Path(state_root)/'material_organization.json'
    if not path.exists():return {'version':1,'assets':{}}
    if path.is_symlink() or path.stat().st_size>8*1024*1024:raise lib.MaterialError('文件目录核验记录异常，未隐藏任何原件',503)
    try:value=json.loads(path.read_text())
    except (OSError,ValueError):raise lib.MaterialError('文件目录核验记录未能读取',503)
    if not isinstance(value,dict) or value.get('version')!=1 or not isinstance(value.get('assets'),dict):raise lib.MaterialError('文件目录核验记录格式异常',503)
    return value

def source_fingerprint(row):
    """Bind archive decisions to explicit identity and source receipts, order independent."""
    value={key:sorted({json.dumps(item,sort_keys=True,ensure_ascii=False,separators=(',',':')) for item in row.get(key,[])}) for key in ('project_ids','customers','project_titles','sources')}
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def apply(root,state_root,rows):
    manifest=load(state_root);index=lib.load_index(root)
    for row in rows:
        aid=row['asset_id'];saved=manifest['assets'].get(aid);asset=index['assets'].get(aid,{})
        valid=False
        if isinstance(saved,dict) and all(isinstance(saved.get(k),str) and saved[k] for k in ('path','sha256','customer_folder','folder_id','folder_title','review_state','placement')) and saved.get('source_fingerprint')==source_fingerprint(row) and saved.get('annotation_revision')==row.get('revision',0) and saved.get('path')==asset.get('path'):
            try:
                with lib._open(root,asset['path']) as f:
                    s=os.fstat(f.fileno());stamp=(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
                if s.st_size<=512*1024*1024:
                    with _LOCK:actual=_digest(str(root),asset['path'],stamp)
                    valid=actual==saved.get('sha256') and (not asset.get('sha256') or actual==asset['sha256'])
            except (OSError,lib.MaterialError):pass
        if valid:
            row['organization']={k:v for k,v in saved.items() if k not in ('path','annotation_revision','archive_path')}
        else:
            customer=next((x for x in row['customers'] if x),None) or '归属待补'
            title=row['project_titles'][0] if len(row['project_titles'])==1 else '客户资料（合同归属待补）'
            row['organization']={'customer_folder':customer,'folder_id':hashlib.sha256((customer+'\0'+title).encode()).hexdigest()[:20],
                'folder_title':title,'review_state':'待重新核对' if saved else '新材料待整理','placement':'current','basis':'原件、来源关联或人工标注已变化，旧目录结论未沿用。' if saved else '保留新材料，等待来源与版本核对。'}
    # Invalid/stale targets cannot justify hiding another original.
    lookup={r['asset_id']:r for r in rows}
    for row in rows:
        org=row['organization'];target=lookup.get(org.get('superseded_by'))
        if org.get('placement')=='history' and (not target or target is row or target['organization'].get('placement')!='current' or target['organization'].get('folder_id')!=org.get('folder_id') or target['organization'].get('review_state') in ('待重新核对','新材料待整理')):
            org={**org,'placement':'current','review_state':'版本待重新核对','basis':'当前替代件已变化或不可读，旧稿重新显示。'};row['organization']=org
    return manifest

def dedupe(rows):
    # Deduplicate only after scope/filter selection; no sources from another scope.
    groups={}
    for row in rows:
        org=row['organization'];key=org.get('duplicate_key') or org.get('sha256') or row['asset_id']
        groups.setdefault((org['folder_id'],key),[]).append(row)
    result=[]
    for group in groups.values():
        group=sorted(group,key=lambda r:(r['file_state']!='已确认材料',not bool(r['annotation']),r['asset_id']))
        first=dict(group[0]);first['duplicate_assets']=[{'asset_id':x['asset_id'],'title':x['title']} for x in group[1:]]
        first['sources']=list({json.dumps(s,sort_keys=True,ensure_ascii=False):s for x in group for s in x['sources']}.values())
        result.append(first)
    return result

def folder_result(matches,q):
    include_history=q.get('include_history')=='1';customer=q.get('folder_customer','');folder=q.get('folder_id','')
    if customer:matches=[r for r in matches if r['organization']['customer_folder']==customer]
    if folder:matches=[r for r in matches if r['organization']['folder_id']==folder]
    all_rows=dedupe(matches);visible=[r for r in all_rows if include_history or r['organization'].get('placement')!='history']
    groups={}
    if not folder:
        for r in all_rows:
            org=r['organization'];key=org['folder_id'] if customer else org['customer_folder']
            item=groups.setdefault(key,{'id':key,'title':org['folder_title'] if customer else org['customer_folder'],'current':0,'history':0,'folders':set(),'attention':0})
            item['folders'].add(org['folder_id']);item['history' if org.get('placement')=='history' else 'current']+=1
            item['attention']+=org.get('review_state') in ('归属待补','版本待确认','来源有缺口','待重新核对','新材料待整理','版本待重新核对')
    return visible,[{**g,'folders':len(g['folders'])} for g in sorted(groups.values(),key=lambda x:x['title'])],len(all_rows)-len(visible)
