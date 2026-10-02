"""File receipts over the existing intake ledger and material index.
No collector, inference calls, or second asset store. Called under pipeline.lock.
"""
import hashlib
import json
import re
from pathlib import Path
from email import policy, message_from_bytes
from email.utils import parseaddr
from xml.etree import ElementTree as ET

SUFFIXES={'.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx','.csv','.png','.jpg','.jpeg','.zip','.txt','.md'}

def sha(raw):return hashlib.sha256(raw).hexdigest()

def receipts(entry):
    first={k:entry.get(k,'') for k in ('channel','origin','business_date','title','key','collected_at')}
    return entry.get('receipts') or [first]

def confirmation_quote(row):
    # Use existing AI evidence; a filename, generic OK, price or start-work approval
    # alone never qualifies as acceptance of a whole file's text.
    for evidence in row.get('evidence',[]):
        quote=evidence.get('quote','')
        if evidence.get('level')!='customer_statement':continue
        if re.search(r'(合同|协议|方案|报价单).{0,20}(作废|撤回|不再适用)',quote):return quote
        if re.search(r'不|未|待|如果|若|仅|只确认|价格|金额|先启动|先开工|转述|转发|他说|客户说',quote):continue
        if re.search(r'(确认|同意|认可).{0,20}(合同|协议|方案|报价单).{0,12}(内容|文本|全文)',quote) or re.search(r'(合同|协议|方案|报价单).{0,12}(内容|文本|全文).{0,12}(确认|同意|认可|无异议)',quote):
            return quote
    return ''

def linked_hashes(entry,entries):
    """Only MIME attachment bytes or same-thread explicit reply references."""
    channel=entry.get('channel');path=Path(entry['original'])
    if channel=='email':
        msg=message_from_bytes(path.read_bytes(),policy=policy.default)
        sender=parseaddr(str(msg.get('From','')))[1].lower()
        own=entry.get('key','').split('/',1)[0].lower()
        if not sender or sender==own or ('@' in own and sender.rsplit('@',1)[-1]==own.rsplit('@',1)[-1]):return [],''
        reference=str(msg.get('In-Reply-To','')).strip()
        messages=[msg]
        if reference:
            candidates=[]
            for other in entries:
                if other.get('channel')!='email':continue
                prior=message_from_bytes(Path(other['original']).read_bytes(),policy=policy.default)
                if str(prior.get('Message-ID','')).strip()==reference:
                    # The replying customer must be an actual recipient of the target.
                    addresses=str(prior.get('To',''))+','+str(prior.get('Cc',''))
                    from email.utils import getaddresses
                    if sender in {a.lower() for _,a in getaddresses([addresses])}:candidates.append(prior)
            if len(candidates)==1:messages+=candidates
        hashes={sha(p.get_payload(decode=True) or b'') for m in messages for p in m.walk() if not p.is_multipart() and p.get_filename()}
        return sorted(hashes),sender
    if channel=='wechat' and entry.get('message_direction')=='incoming' and entry.get('communication',{}).get('type')=='customer':
        message=json.loads(path.read_text())['message']
        try:tree=ET.fromstring(message.get('raw_content',''))
        except ET.ParseError:return [],''
        reference=tree.findtext('.//refermsg/svrid')
        if not reference:return [],''
        chat=entry.get('origin','').rsplit('/',1)[0];matches=[]
        for other in entries:
            if other.get('channel')!='wechat' or other.get('origin','').rsplit('/',1)[0]!=chat:continue
            data=json.loads(Path(other['original']).read_text())['message']
            if str(data.get('source',{}).get('server_id'))==reference:
                for attachment in entries:
                    if any(r.get('origin')==other['origin']+'#file' for r in receipts(attachment)):matches.append(attachment['sha256'])
        return sorted(set(matches)),message.get('sender_name') or message.get('sender_id','')
    return [],''

def accepted(events,project_id=''):
    groups={}
    for event in events:
        if project_id and event.get('project_id')!=project_id:continue
        groups.setdefault(event.get('project_id'),[]).append(event)
    for rows in groups.values():
        latest=max(e.get('business_date','') for e in rows)
        current=[e for e in rows if e.get('business_date','')==latest]
        if current and all(e.get('confirmation')=='客户认可文本' for e in current):return True
    return False


def preserve(pipe,review=None):
    from tools.communication_pipeline import load, save, execute_transaction, stable_read, now, Failure
    import material_library as library
    index_path=pipe.kb/'tracking/material_library.json'
    before=index_path.read_bytes() if index_path.exists() else b'{"assets":{},"files":[],"recordings":[],"summary":{}}'
    index=json.loads(before);entries=list(pipe.ledger['items'].values());planned={};bysha={};blocked=set()
    # Prefer existing managed originals; verify bytes before reusing any index hash.
    for aid,asset in index.get('assets',{}).items():
        p=(pipe.kb/asset.get('path','')).resolve()
        if pipe.kb.resolve() not in p.parents or p.suffix.lower() not in SUFFIXES :continue
        try:
            with library._open(pipe.kb,asset['path']) as f:raw=f.read(100*1024*1024+1)
            if len(raw)>100*1024*1024:continue
            digest=sha(raw)
            if library._sensitive(asset) or not asset.get('downloadable'):
                blocked.add(digest);continue
            if asset.get('sha256') and asset['sha256']!=digest:continue
            bysha.setdefault(digest,aid)
        except (OSError,Failure,library.MaterialError):continue
    for entry in entries:
        suffix=Path(entry['original']).suffix.lower()
        if suffix not in SUFFIXES:continue
        if not any(r.get('channel') in ('email_attachment','wechat_attachment','feishu_attachment','workbench_upload') for r in receipts(entry)):continue
        try:
            raw=stable_read(Path(entry['original']),100*1024*1024);digest=sha(raw)
            if digest!=entry['sha256']:raise Failure('采集原件校验失败，保留原索引')
        except (OSError,Failure):
            pipe.gap(entry['title'],'原件未能完整读取或内容校验失败，保留旧资料');continue
        if digest in blocked:
            pipe.gap(entry['title'],'已有原件受限，未通过重复接收绕过原有范围');continue
        aid=bysha.get(digest)
        if not aid:
            rel='raw/assets/自动接收/'+digest+suffix;p=pipe.kb/rel
            if p.exists() and sha(p.read_bytes())!=digest:raise ValueError('原件目标冲突')
            if not p.exists():planned[rel]=raw
            aid=sha(rel.encode());index['assets'][aid]={'path':rel,'label':entry['title'],'kind':'document','readable':suffix in {'.txt','.md'},'downloadable':True,'sha256':digest,'sensitive':False};bysha[digest]=aid
        for received in receipts(entry):
            rid='ATT-'+sha(json.dumps([digest,received.get('channel'),received.get('origin')],ensure_ascii=False).encode())[:24]
            previous=next((r for r in index['files'] if r['id']==rid),None)
            associations=entry.get('associations',[])
            if not associations:
                parents=[e for e in entries if e.get('id') in entry.get('parent_message_ids',[]) or (received.get('channel')=='email_attachment' and e.get('channel')=='email' and e.get('origin')==received.get('origin','').split('#part')[0])]
                unique={a['project_id']:a for e in parents for a in e.get('associations',[])}
                if len(unique)==1:associations=list(unique.values())
            if received.get('project_id'):associations=[received]
            association=associations[0] if len(associations)==1 else {}
            row={'id':rid,'title':received.get('title') or entry['title'],'original_title':received.get('title') or entry['title'],
                 'customer':association.get('customer',''),'project_id':association.get('project_id',''),'project_title':association.get('project_title') or association.get('title',''),
                 'business_date':received.get('business_date',''),'reviewed_at':received.get('collected_at',entry.get('collected_at','')),
                 'sources':[aid],'original_sha256':digest,'processing':'original_preserved','summary':'原件已保存；客户确认与适用范围单独核验。',
                 'attachment_receipt':received}
            if previous:
                # Later analysis may attach an initially unassigned receipt; never erase
                # a prior explicit assignment merely because a later run has no result.
                if previous.get('project_id') and not row['project_id']:
                    for k in ('customer','project_id','project_title'):row[k]=previous[k]
                if row!=previous:previous.update(row)
            else:index['files'].append(row)
    if review:
        for row in review.get('items',[]):
            if row.get('classification')!='project':continue
            entry=pipe.ledger['items'].get(row.get('material_id'),{})
            if entry.get('communication',{}).get('type') in ('internal','partner'):continue
            quote=confirmation_quote(row)
            if not quote:continue
            try:hashes,actor=linked_hashes(entry,entries)
            except (OSError,ValueError,KeyError):continue
            # Multiple attachments need a filename in the confirmation quote. Do not
            # infer that accepting one document accepts every attached file.
            for digest in hashes:
                aid=bysha.get(digest)
                if not aid:continue
                candidates=[r for r in index['files'] if aid in r.get('sources',[]) and r.get('project_id')==row['project_id']]
                if not candidates:continue
                if len(hashes)>1 and not any(r['original_title'] in quote for r in candidates):continue
                body=Path(entry['text_path']).read_text()
                if quote not in body:continue
                event={'sha256':digest,'project_id':row['project_id'],'quote':quote,'actor':actor,'channel':entry['channel'],
                       'origin':entry['origin'],'business_date':row.get('business_date',''),'confirmation':'已撤回' if re.search(r'作废|撤回|不再适用',quote) else '客户认可文本',
                       'scope':'仅针对所引用文件的文本；签署、付款、验收分别核验','source_material_id':entry['id']}
                event['id']=sha(json.dumps(event,ensure_ascii=False,sort_keys=True).encode())
                asset=index['assets'][aid];events=asset.setdefault('confirmation_events',[])
                if not any(e['id']==event['id'] for e in events):events.append(event)
    after=json.dumps(index,ensure_ascii=False,indent=2).encode()
    if json.loads(before)==index:return {'new_originals':0,'changed':False}
    key=sha(before+after);folder=pipe.root/'file_transactions'/key;folder.mkdir(parents=True,exist_ok=True)
    planned['tracking/material_library.json']=after;ops=[]
    for n,(rel,raw) in enumerate(planned.items()):
        p=pipe.kb/rel;prior=p.read_bytes() if p.exists() else None
        if rel=='tracking/material_library.json' and (prior or b'')!=(before if index_path.exists() else b''):raise ValueError('资料索引已变化')
        name=str(n)+'.after';(folder/name).write_bytes(raw)
        ops.append({'path':rel,'before':sha(prior) if prior is not None else None,'after':sha(raw),'payload':name})
    save(folder/'plan.json',{'ops':ops,'projects':[]});execute_transaction(folder,pipe.kb)
    result={'new_originals':len(planned)-1,'changed':True,'checked_at':now()};save(pipe.root/'file_receipt.json',result)
    return result
