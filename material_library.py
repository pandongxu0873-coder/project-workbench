"""Read-only indexed material access. No model calls, writes, arbitrary path parameters or KB scans."""
from __future__ import annotations
import json,mimetypes,os,re,stat
from pathlib import Path
from urllib.parse import parse_qs,quote,urlparse
# The archive has crossed 8 MiB; retain a bounded read without rejecting
# legitimate incremental imports and their project evidence.
MAX_INDEX_BYTES=32*1024*1024
MAX_SOURCE_BYTES=128*1024
MAX_SOURCE_CHARS=64000
TEXT_SUFFIXES={'.md','.txt','.json'}
ROUTES={'/api/material-library','/api/material-library/source','/api/material-library/file','/api/material-library/check'}
class MaterialError(Exception):
    def __init__(self,message,status=400):super().__init__(message);self.status=status

def _relative(value):
    if not isinstance(value,str) or not value or '\\' in value or '\x00' in value:raise MaterialError('素材路径无效',403)
    p=Path(value)
    if p.is_absolute() or '..' in p.parts or '.'==value:raise MaterialError('素材路径无效',403)
    return p

def _open(root,relative):
    """Walk descriptors with O_NOFOLLOW so ancestor replacement cannot escape KB."""
    root=Path(root).resolve();rel=_relative(relative)
    try:
        candidate=(root/rel).resolve()
        candidate.relative_to(root)
    except (ValueError,OSError,RuntimeError):raise MaterialError('素材路径无效',403)
    fd=None
    try:
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        for part in rel.parts[:-1]:
            nextfd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nextfd
        assetfd=os.open(rel.parts[-1],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
        if not stat.S_ISREG(os.fstat(assetfd).st_mode):os.close(assetfd);raise MaterialError('素材不可读取',403)
        return os.fdopen(assetfd,'rb')
    except FileNotFoundError:raise MaterialError('素材文件尚不可用',404)
    except OSError:raise MaterialError('素材不可读取',403)
    finally:
        if fd is not None:os.close(fd)

def load_index(root):
    try:
        with _open(root,'tracking/material_library.json') as f:raw=f.read(MAX_INDEX_BYTES+1)
        if len(raw)>MAX_INDEX_BYTES:raise MaterialError('资料索引过大',503)
        data=json.loads(raw)
        if not isinstance(data,dict) or not isinstance(data.get('assets',{}),dict):raise ValueError()
        if any(not isinstance(k,str) or not isinstance(v,dict) for k,v in data.get('assets',{}).items()):raise ValueError()
        for key in ['recordings','files','conflicts']:
            if not isinstance(data.get(key,[]),list) or any(not isinstance(row,dict) for row in data.get(key,[])):raise ValueError()
        return data
    except (ValueError,UnicodeError):raise MaterialError('资料索引暂不可用',503)
    except MaterialError as e:
        if e.status==404:raise MaterialError('资料索引尚未建立',503)
        raise

def _sensitive(asset):
    return any(bool(asset.get(k)) for k in ['sensitive','is_sensitive','restricted']) or asset.get('visibility') in {'private','restricted','sensitive'}

def asset(index,asset_id):
    if not isinstance(asset_id,str) or not asset_id or len(asset_id)>200:raise MaterialError('素材编号无效',404)
    a=index.get('assets',{}).get(asset_id)
    if not isinstance(a,dict):raise MaterialError('素材未收录',404)
    if _sensitive(a):raise MaterialError('该素材不提供在线读取或下载',403)
    _relative(a.get('path'))
    return a

def capability(root,index,asset_id,fallback=None):
    fallback=fallback or {};a=index.get('assets',{}).get(asset_id,{})
    out={'id':asset_id,'label':str(a.get('label',fallback.get('label','素材'))),'kind':str(a.get('kind',fallback.get('kind','file'))),'available':False,'readable':False,'downloadable':False}
    try:
        a=asset(index,asset_id)
        with _open(root,a['path']):pass
        out.update(available=True,readable=a.get('readable') is True and Path(a['path']).suffix.lower() in TEXT_SUFFIXES,downloadable=a.get('downloadable') is True)
    except MaterialError:pass
    return out

def library(root,state_root=None):
    index=load_index(root)
    resolved={}
    ledger=Path(state_root)/'communication_pipeline/ledger.json' if state_root is not None else None
    if ledger is not None and ledger.exists():
        try:
            items=json.loads(ledger.read_text()).get('items',{})
            resolved={'REF-'+ident[:20]:entry['associations'][0] for ident,entry in items.items() if entry.get('status')=='archived' and len(entry.get('associations',[]))==1}
        except (OSError,ValueError,KeyError,TypeError):pass
    def public(row):
        if not isinstance(row,dict):return {}
        result={k:v for k,v in row.items() if k not in {'assets','sources'}}
        if row.get('id') in resolved and row.get('category')=='已归档 · 项目归属待核':
            association=resolved[row['id']]
            result.update(category='项目关联已补齐',project_id=association['project_id'],project_title=association['title'],customer=association['customer'],summary='已自动关联至'+association['title']+'。首次提取记录与原件保留，可到项目查看最新整理结果。')
        sources=row.get('sources',[])
        if not isinstance(sources,list):sources=[]
        result['sources']=[capability(root,index,s if isinstance(s,str) else s.get('id',s.get('asset_id','')),s if isinstance(s,dict) else {}) for s in sources if isinstance(s,(dict,str))]
        return result
    recordings=[public(x) for x in index.get('recordings',[])];files=[public(x) for x in index.get('files',[])];summary=index.get('summary',{})
    if not isinstance(summary,dict):summary={}
    result={'ok':True,'summary':{'recording_count':len(recordings),'reviewed_count':summary.get('reviewed_count',sum(bool(x.get('reviewed')) for x in recordings)),'file_count':len(files),'moved_count':summary.get('moved_count',0)},'recordings':recordings,'files':files,'conflicts':index.get('conflicts',[])}
    if state_root is not None:
        import material_coverage, material_collectors
        # Browsing consumes existing receipts; the background loop owns collection.
        result['coverage']=material_coverage.enrich(state_root,root,index,recordings,files)
    return result

def source(root,asset_id):
    a=asset(load_index(root),asset_id)
    if a.get('readable') is not True or Path(a['path']).suffix.lower() not in TEXT_SUFFIXES:raise MaterialError('该素材不提供文本预览',403)
    with _open(root,a['path']) as f:raw=f.read(MAX_SOURCE_BYTES+1)
    txt=raw[:MAX_SOURCE_BYTES].decode('utf-8',errors='replace');truncated=len(raw)>MAX_SOURCE_BYTES or len(txt)>MAX_SOURCE_CHARS
    return {'ok':True,'title':str(a.get('label',Path(a['path']).name)),'path':a['path'],'content':txt[:MAX_SOURCE_CHARS],'truncated':truncated}

def byte_range(header,size):
    if header is None:return 0,max(0,size-1),False
    m=re.fullmatch(r'bytes=(\d*)-(\d*)',header.strip())
    if not m or not any(m.groups()) or size==0:raise MaterialError('Requested Range Not Satisfiable',416)
    try:
        if m[1]:start=int(m[1]);end=min(int(m[2]) if m[2] else size-1,size-1)
        else:
            suffix=int(m[2])
            if suffix<=0:raise ValueError()
            start=max(0,size-suffix);end=size-1
        if start>=size or start>end:raise ValueError()
    except ValueError:raise MaterialError('Requested Range Not Satisfiable',416)
    return start,end,True

def _json(handler,payload,status=200):
    body=json.dumps(payload,ensure_ascii=False).encode();handler.send_response(status);handler.send_header('Content-Type','application/json; charset=utf-8');handler.send_header('Cache-Control','no-store');handler.send_header('Content-Length',str(len(body)));handler.end_headers()
    if handler.command!='HEAD':handler.wfile.write(body)

def send_file(handler,root,asset_id):
    a=asset(load_index(root),asset_id)
    if a.get('downloadable') is not True:raise MaterialError('该素材不提供下载',403)
    with _open(root,a['path']) as f:
        size=os.fstat(f.fileno()).st_size
        try:start,end,partial=byte_range(handler.headers.get('Range'),size)
        except MaterialError:
            handler.send_response(416);handler.send_header('Content-Range',f'bytes */{size}');handler.send_header('Accept-Ranges','bytes');handler.send_header('Content-Length','0');handler.send_header('Cache-Control','no-store');handler.end_headers();return
        mime=mimetypes.guess_type(a['path'])[0] or 'application/octet-stream';mime={'.m4a':'audio/mp4','.wav':'audio/wav','.mp3':'audio/mpeg'}.get(Path(a['path']).suffix.lower(),mime)
        length=end-start+1 if size else 0
        handler.send_response(206 if partial else 200);handler.send_header('Content-Type',mime);handler.send_header('Content-Length',str(length));handler.send_header('Accept-Ranges','bytes');handler.send_header('Cache-Control','no-store');handler.send_header('X-Content-Type-Options','nosniff')
        disposition='inline' if mime.startswith('audio/') else 'attachment';name=Path(a['path']).name;handler.send_header('Content-Disposition',f"{disposition}; filename=\"material{Path(name).suffix if re.fullmatch(r'[.a-zA-Z0-9]+',Path(name).suffix) else ''}\"; filename*=UTF-8''{quote(name,safe='')}")
        if partial:handler.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        handler.end_headers()
        if handler.command=='HEAD':return
        f.seek(start)
        while length:
            chunk=f.read(min(length,64*1024))
            if not chunk:break
            handler.wfile.write(chunk);length-=len(chunk)

def handle(handler,root,state_root=None):
    parsed=urlparse(handler.path)
    if parsed.path not in ROUTES:return False
    try:
        if not handler._trusted_origin():raise MaterialError('来源不受信任',403)
        q=parse_qs(parsed.query)
        if parsed.path=='/api/material-library':_json(handler,library(root,state_root))
        elif parsed.path.endswith('/check'):
            index=load_index(root);aid=q.get('asset_id',[''])[0];a=asset(index,aid)
            with _open(root,a['path']):pass
            _json(handler,{'ok':True,'source':capability(root,index,aid),'message':'来源可以读取；未自动重新转写或确认业务事实'})
        elif parsed.path.endswith('/source'):_json(handler,source(root,q.get('asset_id',[''])[0]))
        else:send_file(handler,root,q.get('asset_id',[''])[0])
    except MaterialError as exc:_json(handler,{'ok':False,'error':str(exc)},exc.status)
    except (OSError,ValueError,TypeError):_json(handler,{'ok':False,'error':'素材暂不可用'},503)
    return True
