"""Prepare a local action from a qualified source. Does not create CRM entities."""
import hashlib
import json
import re
from datetime import datetime

def name_key(value):
    value=re.sub(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]',r'\1',str(value or ''))
    return re.sub(r'\s+','',value.split('/')[-1]).casefold()

def signature(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def qualification_context(kind, entity, notes, leads, accounts):
    """Share admitted qualification by explicit account identity; never by fuzzy name."""
    native=f"{kind}:{entity['id']}"
    account_id=entity.get('account_id') if kind=='lead' and entity.get('decision')=='accepted' else entity['id'] if kind=='account' else ''
    account=next((a for a in accounts if a.get('id')==account_id),None)
    company=entity.get('company') or entity.get('name')
    if account and name_key(account.get('name')) != name_key(company):
        raise ValueError('准入账户与来源主体不一致，请核对原账户关联')
    canonical=f"account:{account_id}" if account else native
    linked=[r for r in leads if account and r.get('decision')=='accepted' and r.get('account_id')==account_id and name_key(r.get('company'))==name_key(company)]
    aliases=list(dict.fromkeys([canonical,native,*[f"lead:{r['id']}" for r in linked]]))
    stored=notes.get('items',{})
    available=[key for key in aliases if stored.get(key)]
    if canonical in available: chosen=canonical
    elif len(available)==1: chosen=available[0]
    elif len(available)>1: raise ValueError('该账户有多份旧沟通记录，请先核对来源，未自动合并')
    else: chosen=f"lead:{linked[0]['id']}" if kind=='account' and len(linked)==1 else native
    note=stored.get(chosen,{})
    for key in available:
        if stored[key].get('company') and name_key(stored[key]['company']) != name_key(company):
            raise ValueError('来源主体已变化，旧沟通判断不能自动套用，请先核对')
    return canonical,chosen,note,aliases

def action_identity(key,note):
    return 'discovery-'+signature([key,{k:v for k,v in note.items() if k not in ('updated_at','_revision')}])[:24]

def prepare(kind, source_id, notes, leads, accounts, projects):
    rows=leads if kind=='lead' else accounts if kind=='account' else []
    entity=next((r for r in rows if r.get('id')==source_id),None)
    if not entity:raise ValueError('来源记录不存在，请重新选择')
    canonical,key,note,aliases=qualification_context(kind,entity,notes,leads,accounts)
    company=entity.get('company') or entity.get('name') or ''
    if note.get('company') and name_key(note['company']) != name_key(company):
        raise ValueError('来源主体已变化，旧沟通判断不能自动套用，请先核对')
    # An explicit admitted account ID wins; a malformed one never falls back to
    # matching a different company by fuzzy name.
    account_id=entity.get('account_id') if kind=='lead' else source_id
    account=next((a for a in accounts if a.get('id')==account_id),None) if account_id else next((a for a in accounts if name_key(a.get('name'))==name_key(company)),None)
    if account and name_key(account.get('name')) != name_key(company):
        raise ValueError('准入账户与来源主体不一致，请核对原账户关联')
    candidates=[{'id':p['id'],'title':p['title'],'customer':p['customer'],'source_path':p['source_path']} for p in projects if name_key(p.get('customer')) in {name_key(company), name_key(account.get('name')) if account else name_key(company)}]
    ready=bool(account) and (kind=='account' or entity.get('decision')=='accepted')
    blocked='先准入工作台账户，才能承接正式跟进' if not ready else ''
    if kind=='lead' and (entity.get('background_only') or entity.get('actionability') in ('stale','limited','needs_time_evidence','watch')):
        ready=False;blocked='历史或未核采购窗口只作参考；新的实际沟通在正式客户/项目中承接'
    if account and account.get('account_state','active')!='active':
        ready=False;blocked='正式账户已暂停或关闭，请先在正式账户核对状态'
    internal=not (note.get('owner_scope')=='mine' and note.get('protection') in ('mine','none') and note.get('checked_at') and note.get('ownership_evidence'))
    if internal:
        action='核对客户归属与保护状态，明确内部协作分工后再决定建联'
        if note.get('protection')=='other':action='与保护负责人核实协作边界；当前仅做内部协调'
    elif note.get('demand')=='confirmed':action='沿用本轮沟通，核对预算、决策链与下一采购节点'
    elif note.get('demand') in ('none','later'):action='按已约定窗口复访，核实需求变化与现有服务商情况'
    else:action='准备首次沟通要点：今年需求、现有供应商与评估负责人'
    due=note.get('next_date','')
    if due:datetime.strptime(due,'%Y-%m-%d')
    return {'ok':True,'kind':kind,'source_id':source_id,'source_key':key,'revision':notes['revision'],
            'entity_version':signature(entity),'source_version':signature([entity,note]),'company':company,'account_id':account.get('id','') if account else '',
            'projects':candidates,'ready':ready,'blocked':blocked,'internal_only':internal,'action':action,'due':due,
            'note':note,'signal':entity.get('title') or entity.get('recent_signal') or '',
            'source_url':entity.get('source_url') or entity.get('source') or '',
            'qualification_key':canonical,'lineage_keys':aliases,
            'action_ids':list(dict.fromkeys([action_identity(key,note),*[action_identity(a,notes.get('items',{}).get(a,{})) for a in aliases]])),
            'action_id':action_identity(key,note)}

def todo(prepared, project_id=''):
    if not prepared['ready']:raise ValueError(prepared['blocked'])
    project=next((p for p in prepared['projects'] if p['id']==project_id),None) if project_id else None
    if project_id and not project:raise ValueError('项目与来源客户不一致，未创建跟进')
    evidence={'public_signal':prepared['signal'],'source_url':prepared['source_url'],
              'qualification_note':prepared['note'],'boundary':'公开信号不证明客户有需求；本地准备不代表CRM认领、消息已发送或双方确认'}
    return {'id':prepared['action_id'],'workroom_request_id':'workroom:'+prepared['action_id'],
            'account_id':prepared['account_id'],'customer':prepared['company'],
            'title':('内部核实 · ' if prepared['internal_only'] else '本轮跟进 · ')+prepared['company'],
            'action':prepared['action'],'next_step':prepared['action'],'deadline':prepared['due'],
            'status':'待处理','priority':'P2',
            'evidence':'；'.join(filter(None,[prepared['note'].get('contact_result'), ('归属依据：'+prepared['note']['ownership_evidence']) if prepared['note'].get('ownership_evidence') else '归属尚待内部核实', '公开信号：'+prepared['signal']])), 'discovery_evidence':evidence,'source_type':'discovery','source_scope':'discovery',
            'discovery_source_key':prepared['source_key'],'discovery_note_revision':prepared['revision'],
            'discovery_source_version':prepared['source_version'],'internal_only':prepared['internal_only'],
            'project_id':project['id'] if project else '', 'project_source':project['source_path'] if project else '',
            'project_title':project['title'] if project else '',
            'created_at':datetime.now().astimezone().isoformat(timespec='seconds'),
            'calendar':{},'reminder_consent':{'enabled':False},'resolution_path':''}
