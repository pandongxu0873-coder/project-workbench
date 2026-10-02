"""Read-only WeChat source adapter, independent of UI and bootstrap operations.

No sending tools, process instrumentation, signing, credentials prompts, or
background watchers. Full dated exports are private and committed atomically.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
PRIVATE=ROOT/'private'
sys.path.insert(0,str(ROOT/'reader-source'))
import config
import crypto
import db
import contacts
import message
import appmsg
from bootstrap import save_private

TZ=ZoneInfo('Asia/Shanghai')
class NotReady(Exception): pass

def configure():
    key_path=PRIVATE/'key.json'
    if not key_path.is_file(): raise NotReady('needs_initial_connection')
    if key_path.is_symlink() or key_path.stat().st_mode & 0o077:
        raise NotReady('private_key_permissions')
    state=json.loads(key_path.read_text())
    raw=state.get('raw_key','')
    if not re.fullmatch(r'[a-f0-9]{64}',raw): raise NotReady('invalid_local_key')
    account=Path(state.get('account_directory','')).resolve()
    base=(Path.home()/'Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files').resolve()
    if account.parent!=base or not (account/'db_storage').is_dir():
        raise NotReady('account_directory_changed')
    config.SQLCIPHER_PATH='/opt/homebrew/bin/sqlcipher'
    config.WECHAT_DATA_GLOB=str(account/'db_storage')
    config.CONTACTS_FILE=str(PRIVATE/'contact-overrides.json')
    crypto._CACHE_FILE=str(PRIVATE/'derived-keys.json')
    crypto.load_key=lambda:raw
    db.reset_caches();contacts.invalidate_cache()
    candidates=sorted((account/'db_storage/message').glob('message_*.db'))
    candidates=[p for p in candidates if re.fullmatch(r'message_\d+\.db',p.name)]
    valid=[p for p in candidates if db.test_key(raw,str(p))]
    if not valid: raise NotReady('key_no_longer_valid')
    # Do not let upstream silently omit an unreadable shard or one numbered >=10.
    if len(valid)!=len(candidates): raise NotReady('some_message_shards_unreadable')
    db.get_message_dbs=lambda:[str(p) for p in valid]
    return account,valid

def doctor():
    try:
        account,shards=configure()
        contact_db=account/'db_storage/contact/contact.db'
        if not db.test_key(crypto.load_key(),str(contact_db)):
            raise NotReady('contact_database_unreadable')
        return {'ok':True,'state':'ready','message_shards':len(shards),'mode':'local_database_read_only',
                'ui_automation':False,'background_sync_enabled':False}
    except NotReady as exc:
        return {'ok':False,'state':str(exc),'mode':'local_database_read_only','ui_automation':False,
                'background_sync_enabled':False,'message_count_verified':0}
    except Exception:
        return {'ok':False,'state':'source_read_failed','background_sync_enabled':False}

def list_chats(match=''):
    configure()
    mapping=db.get_name2id()
    result=[{'chat_id':cid,'display_name':contacts.resolve_contact_name(cid),'kind':'group' if cid.endswith('@chatroom') else 'private'} for cid in sorted(set(mapping.values()))]
    if match:result=[x for x in result if match.casefold() in x['display_name'].casefold() or match==x['chat_id']]
    return result

def select_chat(selector):
    candidates=list_chats()
    exact=[x for x in candidates if selector in (x['chat_id'],x['display_name'])]
    matches=exact or [x for x in candidates if selector.casefold() in x['display_name'].casefold()]
    if len(matches)!=1: raise NotReady('chat_not_found' if not matches else 'chat_selection_ambiguous')
    return matches[0]

def dates(start,end):
    lo=dt.datetime.combine(dt.date.fromisoformat(start),dt.time.min,TZ)
    hi=dt.datetime.combine(dt.date.fromisoformat(end)+dt.timedelta(days=1),dt.time.min,TZ)
    if hi<=lo:raise ValueError('invalid date range')
    return int(lo.timestamp()),min(int(hi.timestamp()),int(time.time())+1)

def parse_record(row,account_id,chat_id,shard,senders):
    timestamp=int(row['create_time'])
    sender_id=str(row.get('real_sender_id',''))
    sender=senders.get(sender_id,'')
    typ=message.normalize_type(str(row.get('local_type','')))
    content=message.decode_message_hex(row.get('message_hex',''))
    extra={}
    if typ=='49':
        extra=appmsg.parse_app_message(content,row.get('local_type',''))
        text=extra.get('summary','')
    elif typ in ('10000','10002'):
        extra=message.parse_system_message(content,default_event='recall' if typ=='10002' else '')
        text=extra.get('text','')
    elif typ=='1':text=content
    else:text='['+message.MSG_TYPES.get(typ,'未解析消息')+']'
    # Direction must come from actual per-shard identity mapping, never majority voting.
    direction='outgoing' if sender==account_id else ('incoming' if sender else 'unknown')
    server_id=str(row.get('server_id',''))
    identity=(account_id,chat_id,'server',server_id) if server_id not in ('','0','None') else (account_id,chat_id,shard,str(row['source_rowid']),str(row.get('local_id','')),str(timestamp))
    uid=hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()
    return {'id':uid,'occurred_at':dt.datetime.fromtimestamp(timestamp,TZ).isoformat(),
            'timestamp':timestamp,'sender_id':sender,'sender_name':contacts.resolve_contact_name(sender) if sender else '',
            'direction':direction,'type':typ,'text':text,'raw_content':content,'details':extra,
            'source':{'channel':'wechat','chat_id':chat_id,'database':shard,'row_id':int(row['source_rowid']),
                      'local_id':str(row.get('local_id','')),'server_id':server_id},
            'attachments_read':False,'requires_media_processing':typ not in ('1','10000','10002')}

def export_chat(selector,start,end):
    chat=select_chat(selector)
    account,shards=configure()
    cid=chat['chat_id'];table='Msg_'+hashlib.md5(cid.encode()).hexdigest()
    lo,hi=dates(start,end)
    records={};coverage=[]
    # The account directory suffix is a device identifier, not part of the wxid.
    account_id=re.sub(r'_[^_]+$','',account.name)
    for path in shards:
        tables=set(db.query_raw(str(path),"SELECT name FROM sqlite_master WHERE type='table';"))
        if table not in tables:continue
        senders={str(x['sender_rowid']):x['user_name'] for x in db.query(str(path),'SELECT rowid AS sender_rowid,user_name FROM Name2Id;')}
        last_ts,last_row=lo,-1;count=0
        while True:
            sql=(f'SELECT rowid AS source_rowid,local_id,server_id,create_time,local_type,real_sender_id,hex(message_content) AS message_hex FROM "{table}" '
                 f'WHERE create_time>={lo} AND create_time<{hi} AND (create_time>{last_ts} OR (create_time={last_ts} AND rowid>{last_row})) '
                 'ORDER BY create_time,rowid LIMIT 500;')
            rows=db.query(str(path),sql)
            if not rows:break
            for row in rows:
                record=parse_record(row,account_id,cid,path.name,senders)
                previous=records.get(record['id'])
                if previous and (previous['raw_content'],previous['direction'])!=(record['raw_content'],record['direction']):
                    raise NotReady('conflicting_duplicate_message')
                records[record['id']]=record
            count+=len(rows)
            last_ts,last_row=int(rows[-1]['create_time']),int(rows[-1]['source_rowid'])
            if len(rows)<500:break
        coverage.append({'database':path.name,'rows_read':count})
    if not coverage:raise NotReady('chat_table_unavailable')
    from file_originals import resolve
    resolve(account,list(records.values()))
    return {'version':1,'channel':'wechat','chat':chat,'from':start,'to':end,
            'collected_at':dt.datetime.now(TZ).isoformat(),'read_before_timestamp':hi,
            'coverage':coverage,'messages':sorted(records.values(),key=lambda x:(x['timestamp'],x['id'])),
            'limitations':['只包含当前电脑本地已有记录，未证明覆盖手机或所有历史。',
                           '仅匹配本机已下载且内容校验一致的文件；其余附件、图片及语音未读取。',
                           '聊天原文是证据，客户确认、内部讨论和正式审批需后续交叉验证。']}

def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor')
    ls=sub.add_parser('chats');ls.add_argument('--match',default='')
    ex=sub.add_parser('export');ex.add_argument('chat');ex.add_argument('--from',dest='start',required=True);ex.add_argument('--to',dest='end',required=True)
    args=parser.parse_args()
    try:
        if args.command=='doctor':result=doctor()
        elif args.command=='chats':result={'ok':True,'chats':list_chats(args.match)}
        else:
            result=export_chat(args.chat,args.start,args.end)
            identity=hashlib.sha256(result['chat']['chat_id'].encode()).hexdigest()[:20]
            target=PRIVATE/'exports'/f'{identity}_{args.start}_{args.end}.json'
            save_private(target,result)
            result={'ok':True,'export_path':str(target),'messages':len(result['messages']),'attachments_read':False}
    except NotReady as exc:result={'ok':False,'state':str(exc)}
    except Exception:result={'ok':False,'state':'source_read_failed'}
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result.get('ok') else 2

if __name__=='__main__':raise SystemExit(main())
