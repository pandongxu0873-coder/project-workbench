"""Local qualification notes; never claim or mutate CRM entities."""
import fcntl
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime
from project_workspace import identity
from discovery_handoff import signature, qualification_context

LOCK = threading.RLock()
SCOPES = {'unknown', 'mine', 'other_k100', 'direct', 'channel', 'standard', 'unowned'}
FIELDS = ('owner_scope','protection','owner_name','checked_at','ownership_evidence','demand','contact_result','next_date')
class NoteConflict(ValueError): pass

def load_notes(root):
    path = root / 'qualification_notes.json'
    if not path.exists(): return {'revision':0,'items':{}}
    try:
        value=json.loads(path.read_text())
        if not isinstance(value,dict) or type(value.get('revision')) is not int or value['revision']<0 or not isinstance(value.get('items'),dict):raise ValueError()
        for key,row in value['items'].items():
            if not isinstance(row,dict) or any(not isinstance(row.get(k),str) for k in FIELDS):raise ValueError()
            if row['owner_scope'] not in SCOPES or row['protection'] not in {'unknown','mine','other','none'} or row['demand'] not in {'unknown','confirmed','none','later'}:raise ValueError()
            if key != f"{row['kind']}:{row['source_id']}":raise ValueError()
        return value
    except (ValueError,KeyError,TypeError):raise ValueError('线索判断记录异常，原记录已保留；不能按空记录覆盖')

def save_note(payload, root, lead_rows, account_rows):
    root.mkdir(parents=True,exist_ok=True)
    with LOCK, (root/'qualification_notes.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        kind=payload.get('kind');rows=lead_rows if kind=='lead' else account_rows if kind=='account' else []
        entity=next((r for r in rows if r.get('id')==payload.get('source_id')),None)
        if not entity:raise ValueError('来源记录不存在，未保存判断')
        if payload.get("entity_version") != signature(entity):raise NoteConflict("来源主体或内容已变化，请重新读取后核对；输入保留")
        notes=load_notes(root)
        if type(payload.get('revision')) is not int or payload['revision']!=notes['revision']:raise NoteConflict('判断记录已更新，请核对新版后合并；你的输入保留')
        record={k:str(payload.get(k,'')).strip()[:3000] for k in FIELDS}
        if record['owner_scope'] not in SCOPES or record['protection'] not in {'unknown','mine','other','none'} or record['demand'] not in {'unknown','confirmed','none','later'}:raise ValueError('请选择有效的核实状态')
        for k in ('checked_at','next_date'):
            if record[k]:datetime.strptime(record[k],'%Y-%m-%d')
        if record['checked_at']>datetime.now().strftime('%Y-%m-%d'):raise ValueError('归属核实日期不能在未来')
        if (record['owner_scope']!='unknown' or record['protection']!='unknown') and (not record['checked_at'] or not record['ownership_evidence']):raise ValueError('已核实的归属或保护必须附上日期和 CRM 查询依据')
        if record['demand']!='unknown' and not record['contact_result']:raise ValueError('需求判断必须有实际沟通结果，不能只依据历史采购')
        key,_,existing_note,_=qualification_context(kind,entity,notes,lead_rows,account_rows)
        if existing_note and all(existing_note.get(k)==v for k,v in record.items()):return {'ok':True,**notes}
        stored_kind,stored_id=key.split(':',1)
        record.update(kind=stored_kind,source_id=stored_id,company=entity.get('company') or entity.get('name'),updated_at=datetime.now().astimezone().isoformat(timespec='seconds'))
        notes['items'][key]=record;notes['revision']+=1
        history=root/'qualification_history';history.mkdir(exist_ok=True)
        with (history/f"{notes['revision']}-{identity(key)}-{uuid.uuid4().hex}.json").open('x') as f:json.dump(record,f,ensure_ascii=False,indent=2)
        fd,tmp=tempfile.mkstemp(prefix='.qualification-',dir=root)
        try:
            with os.fdopen(fd,'w') as f:json.dump(notes,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
            os.replace(tmp,root/'qualification_notes.json')
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        return {'ok':True,**notes}
