"""Publish immutable receipts from isolated imports without touching an active ledger."""
import json
import re
from pathlib import Path
from tools.communication_pipeline import Failure,save,now

TERMINAL={'archived','archived_reference','ignored'}

def publish(pipe,review,state,key):
    if not re.fullmatch(r'[a-z0-9-]{1,80}',key):raise Failure('导入回执名称无效')
    ids=review.get('completed',[])
    if not ids or any(pipe.ledger['items'].get(i,{}).get('status') not in TERMINAL for i in ids):
        raise Failure('导入尚未提交归档，不能发布为完成结果')
    fields=('id','status','title','sha256','channel','origin','business_date','communication','associations','message_direction')
    entries={i:{k:v for k,v in pipe.ledger['items'][i].items() if k in fields} for i in ids}
    # Fixed server-owned destination. The public packet contains no intake path.
    packet={'version':1,'published_at':now(),'ledger':entries,'review':{**review,'published_at':review.get('published_at') or now()}}
    target=Path(state)/'communication_pipeline/published_imports'/f'{key}.json'
    save(target,packet)
    if json.loads(target.read_text())!=packet:raise Failure('导入回执未读回')
    return target

def read(root,ledger):
    imported=[];merged=dict(ledger);hashes={e.get('sha256') for e in merged.values() if e.get('status') in TERMINAL}
    for path in sorted((Path(root)/'published_imports').glob('*.json')):
        if path.is_symlink() or path.stat().st_size>16*1024*1024:continue
        try:
            value=json.loads(path.read_text());entries=value.get('ledger');review=value.get('review')
            if value.get('version')!=1 or not isinstance(entries,dict) or not isinstance(review,dict):continue
            ids=review.get('completed',[])
            if not isinstance(ids,list) or not ids or any(not isinstance(entries.get(i),dict) or entries[i].get('status') not in TERMINAL for i in ids):continue
            if not isinstance(review.get('items'),list) or not isinstance(review.get('projects'),list):continue
            accepted=[]
            for ident in ids:
                entry=entries[ident]
                if merged.get(ident,{}).get('status') in TERMINAL or entry.get('sha256') in hashes:continue
                merged[ident]=entry;accepted.append(ident);hashes.add(entry.get('sha256'))
            if accepted:imported.append((path,{**review,'completed':accepted}))
        except (ValueError,OSError,AttributeError,TypeError):continue
    return merged,imported
