"""Private, resumable full local text index. Never writes to WeChat databases.

Each table is read in a single read transaction with a fixed cutoff, so paging
cannot skip same-timestamp rows. Completed tables are checkpointed atomically.
This index is a source archive, not a claim that every message is a sales fact.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import sqlite3
import time
import reader as r


def main():
    os.umask(0o077)
    folder=r.PRIVATE/'history'
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/'messages.sqlite3'
    con=sqlite3.connect(target)
    con.executescript('''
    CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,chat_id TEXT NOT NULL,
        occurred_at TEXT NOT NULL,timestamp INTEGER NOT NULL,type TEXT NOT NULL,
        text TEXT NOT NULL,record TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS messages_chat_time ON messages(chat_id,timestamp,id);
    CREATE TABLE IF NOT EXISTS coverage(database TEXT,table_name TEXT,chat_id TEXT,
        display_name TEXT,cutoff INTEGER,rows_read INTEGER,first INTEGER,last INTEGER,
        PRIMARY KEY(database,table_name));
    CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);
    ''')
    saved=con.execute("SELECT value FROM metadata WHERE key='cutoff'").fetchone()
    cutoff=int(saved[0]) if saved else int(time.time())+1
    con.execute("INSERT OR IGNORE INTO metadata VALUES('cutoff',?)",(str(cutoff),));con.commit()
    account,shards=r.configure()
    account_id=re.sub(r'_[^_]+$','',account.name)
    mapping=r.db.get_name2id()
    totals=[]
    for shard in shards:
        tables=r.db.query_raw(str(shard),"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%';")
        tables=sorted(t for t in tables if re.fullmatch(r'Msg_[0-9a-f]{32}',t))
        senders={str(x['sender_rowid']):x['user_name'] for x in r.db.query(str(shard),'SELECT rowid AS sender_rowid,user_name FROM Name2Id;')}
        for table in tables:
            if con.execute('SELECT 1 FROM coverage WHERE database=? AND table_name=?',(shard.name,table)).fetchone():continue
            if table not in mapping:raise r.NotReady('unmapped_history_table')
            cid=mapping[table]
            # One readonly SQLCipher query per table is a coherent SQLite snapshot.
            rows=r.db.query(str(shard),f'SELECT rowid AS source_rowid,local_id,server_id,create_time,local_type,real_sender_id,hex(message_content) AS message_hex FROM "{table}" WHERE create_time<{cutoff} ORDER BY create_time,rowid;')
            with con:
                for row in rows:
                    item=r.parse_record(row,account_id,cid,shard.name,senders)
                    old=con.execute('SELECT record FROM messages WHERE id=?',(item['id'],)).fetchone()
                    if old:
                        old=json.loads(old[0])
                        if (old['raw_content'],old['direction'])!=(item['raw_content'],item['direction']):
                            raise r.NotReady('conflicting_history_duplicate')
                    else:
                        con.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',(item['id'],cid,item['occurred_at'],item['timestamp'],item['type'],item['text'],json.dumps(item,ensure_ascii=False)))
                con.execute('INSERT INTO coverage VALUES(?,?,?,?,?,?,?,?)',
                    (shard.name,table,cid,r.contacts.resolve_contact_name(cid),cutoff,len(rows),
                     min((int(x['create_time']) for x in rows),default=None),max((int(x['create_time']) for x in rows),default=None)))
            done=con.execute('SELECT COUNT(*),COALESCE(SUM(rows_read),0) FROM coverage').fetchone()
            r.save_private(folder/'progress.json',{'phase':'reading','tables_read':done[0],'rows_read':done[1],'cutoff':cutoff})
            if done[0]%25==0:print(json.dumps({'tables_read':done[0],'rows_read':done[1]}),flush=True)
        totals.extend((shard.name,t) for t in tables)
    covered=set(con.execute('SELECT database,table_name FROM coverage'))
    if set(totals)!=covered:raise r.NotReady('history_table_coverage_changed')
    stats=dict(con.execute('SELECT type,COUNT(*) FROM messages GROUP BY type'))
    summary={'state':'read_complete','tables_read':len(covered),'rows_read':con.execute('SELECT SUM(rows_read) FROM coverage').fetchone()[0],
        'unique_messages':con.execute('SELECT COUNT(*) FROM messages').fetchone()[0],
        'message_types':stats,'cutoff':cutoff,'unmapped_tables':0,'media_bodies_read':False,
        'first':con.execute('SELECT MIN(occurred_at) FROM messages').fetchone()[0],
        'last':con.execute('SELECT MAX(occurred_at) FROM messages').fetchone()[0]}
    r.save_private(folder/'progress.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    con.close()


if __name__=='__main__':main()
