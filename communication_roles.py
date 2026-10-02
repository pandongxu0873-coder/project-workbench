"""Separate the audience of a conversation from the author of a claim."""
import re

LABELS={'customer':'客户沟通','internal':'内部沟通','partner':'合作方沟通','unknown':'沟通身份未核实','document':'文档依据'}


def describe(entry,rows,role_index=None):
    match=re.match(r'^wechat-(?:history|local)://([0-9a-f]{20})/',entry.get('origin',''))
    role=(role_index or {}).get(match[1],entry.get('communication',{})) if match else entry.get('communication',{})
    text='；'.join(r.get('summary','') for r in rows)
    levels={e.get('level') for r in rows for e in r.get('evidence',[])}
    if role.get('type') not in LABELS:
        if 'customer_statement' in levels:
            role={'type':'customer','reason':'本段已提炼出客户直接表述的原话依据。'}
        elif 'internal_statement' in levels and (re.search(r'[（(]内部[）)]|内部群',entry.get('title','')) or
                (entry.get('channel')!='wechat' and not re.search(r'客户.{0,2}内部',text) and re.search(r'^(?:内部|[^。；]{1,16}(?:在内部|内部(?:反馈|转述|讨论|评估|判断|称)))',text))):
            role={'type':'internal','reason':'本段原话及摘要明确为内部讨论或转述。'}
        elif levels=={'document_text'}:
            role={'type':'document','reason':'文档内容，不能仅凭文件认定沟通对象。'}
        else:role={'type':'unknown','reason':'现有材料不足以核实沟通对象的业务身份。'}
    kind=role['type']
    title_chat=re.match(r'^微信｜(.+)｜\d{2}:\d{2}:\d{2}$',entry.get('title',''))
    relay=kind in ('internal','partner') and bool(re.search(r'转述|转告|转达|内部反馈|内部反映|(?:称|说|反馈|表示|提到|反映).{0,8}客户(?:认为|希望|要求|表示|确认|提出)',text))
    own_message=entry.get('channel')=='wechat' and entry.get('message_direction')=='outgoing'
    return {'type':kind,'label':LABELS[kind],'reason':role.get('reason',''),
        'conversation':role.get('conversation') or (title_chat[1] if title_chat else ''),'customer_relay':relay,
        'our_message':own_message,'customer_direct':kind=='customer' and 'customer_statement' in levels and not own_message}


def evidence_label(level,communication):
    if communication.get('our_message'):return '我方发出，非客户回复'
    if level=='customer_statement' and communication.get('type')=='internal':return '内部转述，非客户直接确认'
    if level=='customer_statement' and communication.get('type')=='partner':return '合作方表述，非客户直接确认'
    if level=='customer_statement' and communication.get('type')=='unknown':return '原文记录，发言身份未核实'
    return {'customer_statement':'客户原话','internal_statement':'我方表述','document_text':'文件原文','unverified':'身份或事实仍需核对'}.get(level,'原文依据')
