"""Resolve only local document cards by exact size and MD5; no network or copies."""
import hashlib
import os
import re
from pathlib import Path

def resolve(account,messages):
    wanted={}
    for message in messages:
        d=message.get('details',{});md5=d.get('file_md5','').lower();size=d.get('file_size',0)
        if re.fullmatch('[a-f0-9]{32}',md5) and isinstance(size,int) and 0<size<=100*1024*1024:
            wanted.setdefault((size,md5),[]).append(message)
    if not wanted:return
    root=(Path(account)/'msg/file').resolve();found={};checked=0
    if not root.is_dir():return
    for base,dirs,names in os.walk(root,followlinks=False):
        dirs[:]=[n for n in dirs if not (Path(base)/n).is_symlink()]
        for name in names:
            p=Path(base)/name
            if p.is_symlink():continue
            checked+=1
            if checked>20000:return
            try:
                a=p.stat()
                if a.st_size not in {k[0] for k in wanted}:continue
                raw=p.read_bytes();b=p.stat()
                if (a.st_size,a.st_mtime_ns)!=(b.st_size,b.st_mtime_ns):continue
                key=(len(raw),hashlib.md5(raw).hexdigest())
                if key in wanted:found.setdefault(key,{})[hashlib.sha256(raw).hexdigest()]=str(p)
            except OSError:continue
    for key,items in wanted.items():
        matches=found.get(key,{})
        if len(matches)!=1:continue
        digest,path=next(iter(matches.items()))
        for message in items:message['local_file']={'path':path,'sha256':digest,'size_bytes':key[0],'md5':key[1]}
