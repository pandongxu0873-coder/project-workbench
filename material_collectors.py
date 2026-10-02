"""Incremental read-only desktop inventory while the material workspace is used.

Inventory is not parsing, project association, or customer confirmation. No external
app is scraped here; its acquisition receipts stay explicitly scoped.
"""
import hashlib
import fcntl
import json
import os
import subprocess
import threading
import time
from pathlib import Path
import material_coverage as coverage

LOCK = threading.Lock()
RUNNING = set()
ATTEMPT = {}
SKIP = {'.git','node_modules','__pycache__','.venv','venv','.DS_Store'}
SUFFIXES = {'.pdf','.doc','.docx','.xlsx','.xls','.pptx','.ppt','.md','.txt','.csv','.png','.jpg','.jpeg','.m4a','.mp3','.wav','.ofd'}

def fingerprint(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        before=os.fstat(f.fileno())
        for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
        after=os.fstat(f.fileno())
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise OSError('文件正在变化，稍后重试')
    return h.hexdigest(),after

def scan_desktop(state_root, config):
    state_root=Path(state_root);state_root.mkdir(parents=True,exist_ok=True)
    # The web service and a one-off collector may run in separate processes.
    with (state_root/'desktop_scan.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _scan_desktop_locked(state_root,config)

def _scan_desktop_locked(state_root, config):
    root=Path(config['desktop_root']).resolve()
    if not root.is_dir():raise OSError('桌面目录暂不可访问')
    baseline=config.get('files',{})
    prior_path=Path(state_root)/'desktop_scan_snapshot.json'
    prior=json.loads(prior_path.read_text()) if prior_path.exists() else {'files':{}}
    if not isinstance(prior,dict) or not isinstance(prior.get('files'),dict) or any(not isinstance(v,dict) or not all(k in v for k in ('size','mtime_ns','sha256')) for v in prior['files'].values()):raise ValueError('桌面扫描记录异常，原记录保留')
    paths=set();errors=[]
    def walk_error(exc):
        try: errors.append(str(Path(exc.filename).resolve().relative_to(root)))
        except (TypeError,ValueError): errors.append("子目录读取失败")
    for p in root.iterdir():
        if p.is_file() and not p.is_symlink() and not p.name.startswith('.') and p.suffix.lower() in SUFFIXES:paths.add(p)
    for rel in config.get('directories',[]):
        directory=root/rel
        if directory.is_symlink() or root not in directory.resolve().parents:raise ValueError('扫描目录超出授权桌面范围')
        if not directory.is_dir():raise OSError('已配置业务目录暂不可访问')
        for base, folders, files in os.walk(directory,followlinks=False,onerror=walk_error):
            folders[:]=[n for n in folders if n not in SKIP and not n.startswith('.') and not (Path(base)/n).is_symlink()]
            for name in files:
                p=Path(base)/name
                if not name.startswith('.') and p.suffix.lower() in SUFFIXES and not p.is_symlink():paths.add(p)
    snapshot={};new=[];changed=[];excluded=0
    for p in sorted(paths):
        rel=str(p.relative_to(root))
        if any(w in p.name.lower() for w in ('password','credential','.env','token','secret','批量创建员工','吃饭')):
            excluded+=1;continue
        try:
            stat=p.stat();old=prior['files'].get(rel,{})
            if old.get('size')==stat.st_size and old.get('mtime_ns')==stat.st_mtime_ns:
                sha=old['sha256']
            else:sha,stat=fingerprint(p)
            snapshot[rel]={'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'sha256':sha}
            expected=baseline.get(rel)
            if expected is None:new.append(rel)
            elif expected!=sha:changed.append(rel)
        except OSError: errors.append(rel)
    missing=[r for r in baseline if r not in snapshot and (root/r).suffix.lower() in SUFFIXES
             and not any(w in Path(r).name.lower() for w in ('password','credential','.env','token','secret','批量创建员工','吃饭'))]
    record={'checked_at':coverage.stamp(),'scope':config['scope'],'status':'partial' if errors or missing else 'ok',
            'complete_scope':not bool(errors or missing),'observed':len(snapshot),'new_count':len(new),'changed_count':len(changed),'excluded':excluded,
            'receipt':'desktop_scan_snapshot.json','note':'只核文件清单与内容版本；新增或变化内容仍需提取和业务核验。其他目录未在本轮扫描。',
            'pending_files':[{'title':r,'stage':'新增待整理'} for r in new]+[{'title':r,'stage':'内容变化待复核'} for r in changed],
            'failed_files':[{'title':r,'stage':'读取失败，下次重试'} for r in errors]+[{'title':r,'stage':'原位置未找到，保留旧记录'} for r in missing]}
    # Failed reads keep their prior fingerprints for retry; no false disappearance.
    merged={**prior.get('files',{}),**snapshot}
    tmp=prior_path.with_suffix('.tmp');tmp.write_text(json.dumps({
        'files':merged,'observed_paths':sorted(snapshot),'scope':record['scope'],
        'scan_status':record['status'],'observed_count':record['observed'],
        'checked_at':record['checked_at']},ensure_ascii=False,indent=2));os.replace(tmp,prior_path)
    coverage.record_scan(state_root,'desktop',record)
    return record

def start_due(state_root):
    path=Path(state_root)/'material_collectors.json';key=str(Path(state_root).resolve())
    if not path.exists():return
    with LOCK:
        if key in RUNNING or time.monotonic()-ATTEMPT.get(key,-301)<300:return
        RUNNING.add(key);ATTEMPT[key]=time.monotonic()
    def run():
        config={}
        try:
            config=json.loads(path.read_text())
            # Use the same already-authorized interpreter as recent communication sync.
            # The API server's system Python has a different macOS file-access identity.
            app=Path(__file__).resolve().parent;interpreter=app/'tools/.communication-venv/bin/python'
            if not interpreter.is_file():raise OSError('本机资料读取环境不可用')
            from tools.communication_pipeline import runtime_env
            result=subprocess.run([str(interpreter),'-c','import json,sys; from pathlib import Path; from material_collectors import scan_desktop; p=Path(sys.argv[1]); scan_desktop(p,json.loads((p/"material_collectors.json").read_text()))',str(Path(state_root).resolve())],cwd=app,env=runtime_env(),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120,start_new_session=True)
            if result.returncode:raise OSError('本轮桌面盘点未完成')
        except subprocess.TimeoutExpired:
            try:coverage.record_scan(state_root,'desktop',{'checked_at':coverage.stamp(),'scope':config.get('scope','已配置桌面范围'),'status':'unavailable','receipt':'collector timeout','note':'桌面盘点超时，原材料和上次回执保留。'})
            except (OSError,ValueError):pass
        except (OSError,ValueError,KeyError,TypeError) as exc:
            note='系统拒绝后台读取桌面目录，需恢复该运行进程的文件访问权限。' if isinstance(exc,PermissionError) else '本轮扫描未完成，原材料和上次回执保留；下次打开资料中心时重试。'
            try:coverage.record_scan(state_root,'desktop',{'checked_at':coverage.stamp(),'scope':config.get('scope','已配置桌面范围'),'status':'unavailable','receipt':'collector failure','error_type':type(exc).__name__,'error_code':getattr(exc,'errno',None),'note':note})
            except (OSError,ValueError):pass
        finally:
            with LOCK:RUNNING.discard(key)
    threading.Thread(target=run,daemon=True,name='material-desktop-scan').start()
