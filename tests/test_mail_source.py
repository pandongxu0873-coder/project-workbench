import contextlib,datetime,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from email.message import EmailMessage
from tools import mail_source as m
class MailTest(unittest.TestCase):
 def test_mime_keeps_attachment_bytes_and_date(self):
  msg=EmailMessage();msg['Subject']='星海汽车沟通';msg['From']='sales@example.test';msg['Date']='Fri, 11 Sep 2026 23:30:00 +0000';msg.set_content('项目范围待确认。');msg.add_attachment(b'original bytes',maintype='application',subtype='octet-stream',filename='报价.xlsx')
  r=m.unpack(msg.as_bytes());self.assertEqual(r['date'],'2026-09-12');self.assertEqual(r['attachments'],[('报价.xlsx',b'original bytes')]);self.assertIn('项目范围待确认',r['text'])
 def test_html_is_text_only(self):
  msg=EmailMessage();msg.set_content('<p>正文</p><script>send_secret()</script><img src="https://example.test/tracker">',subtype='html');r=m.unpack(msg.as_bytes());self.assertIn('正文',r['text']);self.assertNotIn('send_secret',r['text']);self.assertNotIn('tracker',r['text'])
 def test_folders_exclude_drafts_deleted_and_junk(self):
  client=MagicMock();client.list.return_value=('OK',[b'(\\HasNoChildren) "/" "INBOX"',b'(\\Sent) "/" "Sent Messages"',b'(\\Trash) "/" "Deleted"',b'(\\Drafts) "/" "Drafts"',b'(\\HasNoChildren) "/" "Deleted Messages"'])
  self.assertEqual(m.folders(client),['INBOX','"Sent Messages"'])
 def test_connection_uses_tls_and_never_smtp(self):
  client=MagicMock()
  with patch.object(m.imaplib,'IMAP4_SSL',return_value=client) as factory:
   with m.connection({'host':'imap.example.test','username':'sales@example.test'},'test-only-value') as opened:self.assertIs(opened,client)
   factory.assert_called_once();self.assertEqual(factory.call_args.kwargs['ssl_context'].verify_mode,m.ssl.CERT_REQUIRED);client.logout.assert_called_once()
 def test_probe_is_readonly(self):
  with tempfile.TemporaryDirectory() as d:
   Path(d,'mail_connection.json').write_text(json.dumps({'host':'imap.example.test','port':993,'username':'sales@example.test'}));client=MagicMock();client.select.return_value=('OK',[b'1'])
   @contextlib.contextmanager
   def connect(cfg):yield client
   with patch.object(m,'connection',connect):self.assertTrue(m.probe(Path(d))['available'])
   client.select.assert_called_once_with('INBOX',readonly=True)
 def test_setup_refuses_noninteractive_secret_input(self):
  with patch.object(m.sys.stdin,'isatty',return_value=False):
   with self.assertRaises(m.MailError):m.setup()
 def test_collection_retries_temporary_network_failure_without_user_click(self):
  pipe=MagicMock()
  with patch.object(m,'collect_once',side_effect=[m.MailError('邮箱加密连接失败'),None]) as collect,patch.object(m.time,'sleep'):
   m.collect(pipe)
  self.assertEqual(collect.call_count,2);pipe.gap.assert_not_called()
 def test_authentication_rejection_is_not_retried_forever(self):
  pipe=MagicMock()
  with patch.object(m,'collect_once',side_effect=m.MailError('邮箱拒绝登录或读取')) as collect:
   m.collect(pipe)
  self.assertEqual(collect.call_count,1);pipe.gap.assert_called_once()
 def test_collect_uses_peek_and_uidvalidity(self):
  msg=EmailMessage();msg['Subject']='非车险项目';msg['Date']='Fri, 11 Sep 2026 13:00:00 +0800';msg.set_content('非车险范围待确认。');raw=msg.as_bytes();client=MagicMock();client.list.return_value=('OK',[]);client.select.return_value=('OK',[b'1']);client.response.return_value=('UIDVALIDITY',[b'7'])
  client.uid.side_effect=[('OK',[b'1']),('OK',[b'1 (RFC822.SIZE 999)']),('OK',[(b'1 (BODY[] {999}',raw),b')'])]
  @contextlib.contextmanager
  def conn(cfg):yield client
  pipe=MagicMock();pipe.cfg={'chat_keywords':['星海汽车'],'mail_keywords':['非车险']};pipe.ledger={'items':{}};pipe.start=datetime.date(2026,9,11);pipe.end=datetime.date(2026,9,13)
  with patch.object(m,'configuration',return_value={'host':'imap.example.test','username':'sales@example.test'}),patch.object(m,'connection',conn):m.collect(pipe)
  client.select.assert_called_once_with('INBOX',readonly=True);self.assertEqual(client.uid.call_args_list[-1].args,('fetch',b'1','(BODY.PEEK[])'));self.assertIn('/INBOX/7/1',pipe.stage.call_args.args[0]);pipe.gap.assert_not_called()
if __name__=='__main__':unittest.main()
