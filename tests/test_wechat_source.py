import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import wechat_source as w
from tools.communication_pipeline import Pipeline,Failure

class WechatSourceTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.cfg={'wechat':{'enabled':True,'chats':[{'chat_id':'contact','customer_hint':'客户甲'}]},'chat_keywords':['客户甲']}
        self.chat={'chat_id':'contact','display_name':'联系人','kind':'private'}
        self.message={'id':'message-1','occurred_at':'2026-09-16T17:17:45+08:00','sender_name':'本人','direction':'outgoing','type':'49','text':'整体报价.xlsx','raw_content':'<file/>','attachments_read':False}
        self.p=Pipeline(self.cfg,self.root/'state',self.root/'kb',dt.date(2026,9,16),dt.date(2026,9,17))
    def collect(self,data=None):
        with patch.object(w,'probe',return_value={'available':True}),patch.object(w,'call',side_effect=[{'chats':[self.chat]},{}]),patch.object(w,'load_export',return_value=data or {'chat':self.chat,'messages':[self.message]}):
            w.collect(self.p)
    def test_selects_verified_contact_and_business_name_not_personal(self):
        result=w.selected_chats([self.chat,{'chat_id':'group','display_name':'客户甲实施群'},{'chat_id':'friend','display_name':'朋友'}],self.cfg)
        self.assertEqual([x['chat_id'] for x in result],['contact','group'])
        self.assertEqual(result[0]['customer_hint'],'客户甲')
    def test_content_review_excludes_keyword_false_positive_but_keeps_explicit_contact(self):
        self.cfg['wechat']['excluded_chats']=['personal','contact']
        result=w.selected_chats([self.chat,{'chat_id':'personal','display_name':'客户甲车友闲聊'}],self.cfg)
        self.assertEqual([x['chat_id'] for x in result],['contact'])
    def test_repeat_collection_deduplicates_and_preserves_sender_and_attachment_boundary(self):
        self.collect();self.collect()
        self.assertEqual(self.p.new,1);self.assertEqual(self.p.duplicates,1)
        item=next(iter(self.p.ledger['items'].values()))
        self.assertEqual(item['channel'],'wechat')
        text=Path(item['text_path']).read_text()
        self.assertIn('本人发出',text);self.assertIn('不等于客户接受',text);self.assertIn('附件正文、图片和语音未核验',text)
        self.assertEqual(json.loads(Path(item['original']).read_text())['message']['id'],'message-1')
    def test_wrong_chat_and_date_are_not_archived(self):
        self.collect({'chat':{'chat_id':'other'},'messages':[self.message]})
        self.assertEqual(self.p.new,0);self.assertTrue(self.p.gaps)
        self.collect({'chat':self.chat,'messages':[{**self.message,'occurred_at':'2026-09-15T12:00:00+08:00'}]})
        self.assertEqual(self.p.new,0)
    def test_missing_linked_chat_is_not_zero_success(self):
        with patch.object(w,'probe',return_value={'available':True}),patch.object(w,'call',return_value={'chats':[]}):w.collect(self.p)
        self.assertTrue(self.p.gaps);self.assertEqual(self.p.new,0)
    def test_source_failure_keeps_existing_records(self):
        self.collect()
        with patch.object(w,'probe',return_value={'available':False,'reason':'连接失效'}):w.collect(self.p)
        self.assertEqual(len(self.p.ledger['items']),1);self.assertTrue(self.p.gaps)
    def test_export_cannot_escape_private_directory(self):
        with self.assertRaises(Failure):w.load_export({'export_path':'/etc/hosts'})
    def test_reply_context_keeps_time_and_direction_and_never_crosses_chat(self):
        self.collect()
        first=next(iter(self.p.ledger['items']))
        later={**self.message,'id':'message-2','occurred_at':'2026-09-17T09:00:00+08:00','text':'请补充范围','direction':'incoming'}
        self.collect({'chat':self.chat,'messages':[later]})
        self.chat={**self.chat,'chat_id':'another'}
        self.cfg['wechat']['chats'].append({'chat_id':'another'})
        self.collect({'chat':self.chat,'messages':[{**later,'id':'other','text':'其他客户资料'}]})
        context=w.review_contexts(self.p)[first]
        self.assertEqual(len(context),1)
        self.assertEqual(context[0]['text'],'请补充范围')
        self.assertEqual(context[0]['direction'],'incoming')
        self.assertEqual(context[0]['occurred_at'],later['occurred_at'])
        self.assertTrue(context[0]['reference_only'])

if __name__=='__main__':unittest.main()
