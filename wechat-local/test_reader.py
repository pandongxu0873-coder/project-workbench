import hashlib
from pathlib import Path
import re
import reader

def test_missing_key_cannot_report_connected(monkeypatch,tmp_path):
    monkeypatch.setattr(reader,'PRIVATE',tmp_path)
    result=reader.doctor()
    assert result['ok'] is False
    assert result['state']=='needs_initial_connection'
    assert result['background_sync_enabled'] is False

def row(i,ts=1789603200):
    return {'create_time':str(ts),'source_rowid':str(i),'local_id':str(i),'server_id':str(i+1000),'real_sender_id':'7','local_type':'1','message_hex':'完整消息'.encode().hex()}

def test_sender_mapping_is_per_shard_and_never_guessed(monkeypatch):
    monkeypatch.setattr(reader.contacts,'resolve_contact_name',lambda s:s)
    a=reader.parse_record(row(1),'wxid_me','wxid_customer','message_0.db',{'7':'wxid_me'})
    b=reader.parse_record(row(1),'wxid_me','wxid_customer','message_1.db',{'7':'wxid_customer'})
    c=reader.parse_record(row(1),'wxid_me','wxid_customer','message_1.db',{})
    assert (a['direction'],b['direction'],c['direction'])==('outgoing','incoming','unknown')
    assert a['text']=='完整消息'

def test_pagination_does_not_drop_same_second_messages(monkeypatch,tmp_path):
    chat={'chat_id':'wxid_customer','display_name':'测试客户','kind':'private'}
    table='Msg_'+hashlib.md5(chat['chat_id'].encode()).hexdigest()
    data=[row(i) for i in range(1,503)]
    monkeypatch.setattr(reader,'select_chat',lambda s:chat)
    monkeypatch.setattr(reader,'configure',lambda:(tmp_path/'wxid_me_abcd',[Path('/fake/message_0.db')]))
    monkeypatch.setattr(reader.db,'query_raw',lambda *_:[table])
    monkeypatch.setattr(reader.contacts,'resolve_contact_name',lambda s:s)
    def query(path,sql):
        if 'FROM Name2Id' in sql:return [{'sender_rowid':'7','user_name':'wxid_customer'}]
        after=int(re.search(r'rowid>(-?\d+)',sql)[1])
        return [r for r in data if int(r['source_rowid'])>after][:500]
    monkeypatch.setattr(reader.db,'query',query)
    result=reader.export_chat('测试客户','2026-09-17','2026-09-17')
    assert len(result['messages'])==502
    assert result['coverage'][0]['rows_read']==502
    assert all(x['direction']=='incoming' for x in result['messages'])

def test_duplicate_servers_are_deduplicated_across_shards(monkeypatch,tmp_path):
    chat={'chat_id':'wxid_customer','display_name':'测试客户','kind':'private'}
    table='Msg_'+hashlib.md5(chat['chat_id'].encode()).hexdigest()
    monkeypatch.setattr(reader,'select_chat',lambda s:chat)
    monkeypatch.setattr(reader,'configure',lambda:(tmp_path/'wxid_me_abcd',[Path('/fake/message_0.db'),Path('/fake/message_1.db')]))
    monkeypatch.setattr(reader.db,'query_raw',lambda *_:[table])
    monkeypatch.setattr(reader.contacts,'resolve_contact_name',lambda s:s)
    monkeypatch.setattr(reader.db,'query',lambda path,sql:[{'sender_rowid':'7','user_name':'wxid_customer'}] if 'FROM Name2Id' in sql else [row(1)])
    result=reader.export_chat('测试客户','2026-09-17','2026-09-17')
    assert len(result['messages'])==1
    assert len(result['coverage'])==2
