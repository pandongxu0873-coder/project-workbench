"""Local WeChat source for communication_pipeline. Never controls the client."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from tools.communication_pipeline import APP, Failure, digest

ROOT=APP/'wechat-local'
READER=ROOT/'reader.py'
PYTHON=ROOT/'.venv/bin/python'

def call(args,timeout=180):
    try:
        proc=subprocess.run([str(PYTHON),str(READER),*args],capture_output=True,text=True,timeout=timeout)
        result=json.loads(proc.stdout)
    except (OSError,ValueError,subprocess.TimeoutExpired):
        raise Failure('微信本地读取未完成；原数据不动，其他来源继续') from None
    if not isinstance(result,dict):
        raise Failure('微信读取结果格式异常，未将失败当作没有新消息')
    if proc.returncode or result.get('ok') is not True:
        state=result.get('state','source_read_failed')
        reasons={'needs_initial_connection':'微信尚未完成首次本地接入',
                 'key_no_longer_valid':'微信本地读取授权需重新验证',
                 'some_message_shards_unreadable':'部分微信消息库不可读，未宣称同步完整',
                 'chat_selection_ambiguous':'微信会话匹配不唯一，未合并不同联系人的消息'}
        raise Failure(reasons.get(state,'微信本地读取失败；未将失败当作没有新消息'))
    return result

def probe(cfg):
    if not cfg.get('wechat',{}).get('enabled'):
        return {'available':False,'configured':False,'reason':'尚未启用个人微信本地读取'}
    try:
        result=call(['doctor'],timeout=30)
        return {'available':True,'configured':True,'message_shards':result.get('message_shards'),
                'scope':'匹配业务会话的本机文字和消息卡片；不代表手机历史及附件正文完整'}
    except Failure as exc:
        return {'available':False,'configured':True,'reason':str(exc)}

def selected_chats(chats,cfg):
    settings=cfg.get('wechat',{})
    explicit={x['chat_id']:x for x in settings.get('chats',[]) if x.get('chat_id')}
    excluded=set(settings.get('excluded_chats',[]))
    keywords=settings.get('chat_keywords',cfg.get('chat_keywords',[]))
    selected=[]
    for chat in chats:
        cid=chat.get('chat_id','');name=chat.get('display_name','')
        if cid in explicit or (cid not in excluded and any(k and k in name for k in keywords)):
            selected.append({**chat,'customer_hint':explicit.get(cid,{}).get('customer_hint','')})
    return selected

def load_export(result):
    path=Path(result.get('export_path','')).resolve()
    allowed=(ROOT/'private/exports').resolve()
    if allowed not in path.parents or not path.is_file() or path.stat().st_size>100_000_000:
        raise Failure('微信导出路径或大小异常；未读取其他文件')
    data=json.loads(path.read_text())
    if data.get('channel')!='wechat' or not isinstance(data.get('messages'),list):
        raise Failure('微信导出格式变化，原数据保留')
    return data

def review_contexts(pipe):
    """Nearby messages clarify replies, but cannot supply a new evidence quote."""
    groups={};result={}
    for entry in pipe.ledger['items'].values():
        if entry.get('channel')!='wechat' or not entry.get('text_path'):continue
        origin=entry.get('origin','')
        if not origin.startswith('wechat-local://'):continue
        groups.setdefault(origin.rsplit('/',1)[0],[]).append(entry)
    for entries in groups.values():
        entries.sort(key=lambda e:(e.get('business_date',''),e['title'],e['id']))
        for index,entry in enumerate(entries):
            neighbors=entries[max(0,index-2):index]+entries[index+1:index+3]
            context=[]
            for other in neighbors:
                try:
                    data=json.loads(Path(other['original']).read_text())['message']
                    context.append({'reference_only':True,'material_id':other['id'],
                        'occurred_at':data['occurred_at'],'sender':data.get('sender_name',''),
                        'direction':data['direction'],'text':data['text'][:600]})
                except (OSError,ValueError,KeyError):continue
            result[entry['id']]=context
    return result

def collect(pipe):
    if not pipe.cfg.get('wechat',{}).get('enabled'):return
    from tools.communication_pipeline import load
    role_index=load(pipe.root/'communication_roles.json',{})
    health=probe(pipe.cfg)
    if not health['available']:
        pipe.gap('个人微信',health['reason']);return
    try:
        all_chats=call(['chats'])['chats']
        choices=selected_chats(all_chats,pipe.cfg)
        known={x['chat_id'] for x in all_chats}
        missing=[x for x in pipe.cfg['wechat'].get('chats',[]) if x.get('chat_id') not in known]
        if missing:pipe.gap('个人微信会话范围',f'{len(missing)}个已关联会话未在本机找到，未视为没有新消息')
    except (Failure,KeyError,TypeError) as exc:
        pipe.gap('个人微信会话清单',str(exc) if isinstance(exc,Failure) else '会话清单格式变化，未视为没有新消息');return
    pipe.wechat_coverage={'checked_at':__import__('datetime').datetime.now().astimezone().isoformat(),
                          'selected_chats':len(choices),'read_chats':0,'messages':0,'attachments_read':False}
    for chat in choices:
        try:
            result=call(['export',chat['chat_id'],'--from',str(pipe.start),'--to',str(pipe.end)])
            data=load_export(result)
            if data['chat']['chat_id']!=chat['chat_id']:
                raise Failure('微信导出会话不一致，未混入其他联系人')
            for item in data['messages']:
                date=item['occurred_at'][:10]
                if not str(pipe.start)<=date<=str(pipe.end):
                    raise Failure('微信消息日期超出采集范围')
                # No collection timestamps or volatile paths in the content hash.
                body={'version':1,'channel':'wechat','chat':chat,'business_date':date,'message':{k:v for k,v in item.items() if k!='local_file'}}
                original=json.dumps(body,ensure_ascii=False,sort_keys=True).encode()
                direction={'outgoing':'本人发出','incoming':'对方发出','unknown':'发言身份未核实'}.get(item['direction'],'发言身份未核实')
                limit='微信本地文字与消息卡片；附件正文、图片和语音未核验。群成员不自动认定为客户，本人发出报价不等于客户接受。单独的好的、收到、OK不作为报价接受或验收依据。'
                text=(f'业务日期：{date}\n沟通时间：{item["occurred_at"]}\n会话：{chat["display_name"]}\n'
                      f'业务归属线索：{chat["customer_hint"] or "按原文识别"}\n发言者：{item["sender_name"] or "身份未核实"}（{direction}）\n'
                      f'消息类型：{item["type"]}\n正文：\n{item["text"]}\n\n读取边界：{limit}')
                title=f'微信｜{chat["display_name"]}｜{item["occurred_at"][11:19]}'
                entry=pipe.stage('wechat:'+item['id'],title,original,'.json','wechat',
                           'wechat-local://'+digest(chat['chat_id'])[:20]+'/'+item['id'],date,text=text,limitations=limit)
                role=role_index.get(digest(chat['chat_id'])[:20])
                if role:entry['communication']=role
                entry['message_direction']=item['direction']
                local=item.get('local_file',{})
                if local:
                    from tools.communication_pipeline import stable_read
                    import hashlib
                    candidate=Path(local['path']);base=Path.home()/'Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files'
                    if base.resolve() not in candidate.resolve().parents or any(p.is_symlink() for p in (candidate,*candidate.parents)):
                        raise Failure('微信附件路径不可信，保留消息待核')
                    raw=stable_read(candidate,100*1024*1024)
                    if digest(raw)!=local['sha256'] or hashlib.md5(raw).hexdigest()!=local['md5'] or len(raw)!=local['size_bytes']:
                        raise Failure('微信附件内容变化，未关联错误原件')
                    name=item.get('details',{}).get('file_name') or candidate.name
                    attachment=pipe.stage('wechat-file:'+item['id'],name,raw,Path(name).suffix.lower(),'wechat_attachment',entry['origin']+'#file',date)
                    attachment.setdefault('parent_message_ids',[])
                    if entry['id'] not in attachment['parent_message_ids']:attachment['parent_message_ids'].append(entry['id'])
                    pipe.wechat_coverage['attachments_preserved']=pipe.wechat_coverage.get('attachments_preserved',0)+1
                elif item.get('details',{}).get('file_name'):
                    pipe.gap('微信文件：'+item['details']['file_name'],'本机原件未找到或缺少内容校验依据，文件卡片不算原件已保存')

            pipe.wechat_coverage['read_chats']+=1
            pipe.wechat_coverage['messages']+=len(data['messages'])
        except (Failure,OSError,ValueError,KeyError) as exc:
            pipe.gap('微信：'+chat['display_name'],str(exc) if isinstance(exc,Failure) else '会话读取失败，已有材料保留')
    from tools.communication_pipeline import save
    pipe.checkpoint()
    save(pipe.root/'wechat_coverage.json',pipe.wechat_coverage)
