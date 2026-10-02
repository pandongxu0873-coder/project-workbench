import fcntl,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
import communication_jobs as jobs
from tools.communication_pipeline import save,Pipeline,probe_directory,Failure
import subprocess
import datetime as dt

class CommunicationJobsTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.state=Path(self.tmp.name)/'state';self.kb=Path(self.tmp.name)/'kb';self.root=self.state/'communication_pipeline';self.root.mkdir(parents=True);self.kb.mkdir()
 def test_finished_progress_survives_server_restart_and_does_not_expose_paths(self):
  save(self.root/'active_run.json',{'request_id':'x','run_id':'run-x','state':'partial','phase':'done','pid':123,'receipt':{'run_id':'run-x','status':'partial','gaps':[{'source':'飞书','reason':'未授权'}],'unresolved':{},'refresh_pending':[]}})
  result=jobs.status(self.state,self.kb);self.assertFalse(result['job']['running']);self.assertEqual(result['receipt']['run_id'],'run-x');self.assertNotIn('pid',result['job'])
 def test_scoped_retry_receipt_preserves_count_inputs_in_public_projection(self):
  report={'run_id':'retry','status':'partial','checked_at':'2026-09-20T02:17:18+08:00','source_scope':['stored_material_retry'],'material_ids':['a'*64],'completed_material_ids':['a'*64],'observed':0,'unresolved':{'ready_for_review':0,'extraction_pending':2,'needs_review':0},'projects':[],'refreshed':[],'private_path':'/private/material'}
  save(self.root/'latest.json',report)
  for embedded in (False,True):
   with self.subTest(embedded=embedded):
    if embedded:save(self.root/'active_run.json',{'request_id':'retry-request','run_id':'retry','state':'partial','phase':'done','receipt':report})
    result=jobs.status(self.state,self.kb)['receipt']
    self.assertEqual(result['material_ids'],report['material_ids']);self.assertEqual(result['completed_material_ids'],report['completed_material_ids'])
    self.assertEqual(result['status'],'partial');self.assertEqual(result['unresolved']['extraction_pending'],2);self.assertEqual(result['observed'],0)
    self.assertNotIn('private_path',result)
 def test_history_progress_exposes_coverage_not_private_index(self):
  save(self.root/'wechat_history.json',{'state':'processing','phase':'triage','conversations':666,'messages':651570,'from':'2026-01-04','to':'2026-09-17','private_path':'/private/index','raw_key':'secret','chat_names':['private']})
  result=jobs.status(self.state,self.kb)['wechat_history']
  self.assertEqual(result['conversations'],666);self.assertEqual(result['state'],'processing')
  self.assertNotIn('private_path',result);self.assertNotIn('raw_key',result);self.assertNotIn('chat_names',result)
 def test_historical_results_keep_original_date_and_history_marker(self):
  ident='h'*64;day=jobs.now()[:10]
  save(self.root/'ledger.json',{'items':{ident:{'id':ident,'status':'archived','title':'微信历史｜客户甲','sha256':'sha','channel':'wechat_history','business_date':'2026-02-02'}}})
  row={'material_id':ident,'classification':'project','project_id':'p1','summary':'当时报价，未证明接受。','business_date':'2026-02-02','evidence':[]}
  save(self.root/'runs'/(day+'T10-00-history')/'review.json',{'completed':[ident],'items':[row],'projects':[{'id':'p1','title':'项目一','customer':'客户甲'}]})
  self.assertEqual(jobs.daily_digest(self.state,self.kb)['groups'],[])
  item=jobs.daily_digest(self.state,self.kb,history=True)['groups'][0]['items'][0]
  self.assertEqual(item['business_date'],'2026-02-02');self.assertTrue(item['historical'])
 def test_full_history_reuses_already_archived_recent_project_messages(self):
  day=jobs.now()[:10];ledger={}
  for ident,channel,date in [('old','wechat_history','2026-02-02'),('latest','wechat','2026-09-16')]:
   ledger[ident]={'id':ident,'status':'archived','title':'微信沟通','sha256':ident,'channel':channel,'business_date':date,'associations':[{'project_id':'p1'}]}
   row={'material_id':ident,'classification':'project','project_id':'p1','summary':ident,'business_date':date,'evidence':[]}
   save(self.root/'runs'/(day+'T10-00-'+ident)/'review.json',{'completed':[ident],'items':[row],'projects':[{'id':'p1','title':'项目一','customer':'客户甲'}]})
  save(self.root/'ledger.json',{'items':ledger})
  history=jobs.daily_digest(self.state,self.kb,history=True)
  self.assertEqual([i['id'] for i in history['groups'][0]['items']],['latest','old'])
  self.assertTrue(all(i['historical'] for i in history['groups'][0]['items']))
  latest=jobs.daily_digest(self.state,self.kb)
  self.assertEqual([i['id'] for i in latest['groups'][0]['items']],['latest'])
  self.assertFalse(latest['groups'][0]['items'][0]['historical'])

 def test_history_accumulates_across_import_days(self):
  ledger={}
  for number,day in enumerate(('2026-09-15','2026-09-17')):
   ident=str(number)*64
   ledger[ident]={'id':ident,'status':'archived','title':'微信历史','sha256':ident,'channel':'wechat_history','business_date':'2026-02-02'}
   row={'material_id':ident,'classification':'project','project_id':'p1','summary':'不同原话记录'+str(number),'business_date':'2026-02-02','evidence':[]}
   save(self.root/'runs'/(day+'T10-00-history')/'review.json',{'completed':[ident],'items':[row],'projects':[{'id':'p1','title':'项目一','customer':'客户甲'}]})
  save(self.root/'ledger.json',{'items':ledger})
  result=jobs.daily_digest(self.state,self.kb,history=True)
  self.assertEqual(len(result['groups'][0]['items']),2)
  self.assertEqual(result['date'],'2026-09-17')
 def test_dead_job_is_interrupted_not_successful(self):
  save(self.root/'active_run.json',{'request_id':'x','state':'running','phase':'analyzing','pid':123})
  with patch.object(jobs,'alive',return_value=True):result=jobs.status(self.state,self.kb)
  self.assertEqual(result['job']['state'],'interrupted')
 def test_newer_external_phone_receipt_replaces_completed_ui_result(self):
  save(self.root/'active_run.json',{'request_id':'old','run_id':'old','state':'completed','phase':'done','receipt':{'run_id':'old','checked_at':'2026-09-17T20:00:00+08:00'}})
  save(self.root/'latest.json',{'run_id':'phone','checked_at':'2026-09-17T23:00:00+08:00','status':'partial','observed':19})
  result=jobs.status(self.state,self.kb)
  self.assertEqual(result['receipt']['run_id'],'phone');self.assertFalse(result['job']['running'])
 def test_phone_review_is_recording_not_chat_and_keeps_internal_role(self):
  ident='p'*64;day=jobs.now()[:10]
  save(self.root/'ledger.json',{'items':{ident:{'status':'archived','title':'内部电话','sha256':'phone','channel':'phone_recording','business_date':'2026-09-15','communication':{'type':'internal','reason':'录音明确为同事复盘'}}}})
  save(self.root/'runs'/(day+'T23-00-phone')/'review.json',{'completed':[ident],'items':[{'material_id':ident,'classification':'project','project_id':'p1','summary':'内部讨论报价范围','evidence':[]}],'projects':[{'id':'p1','title':'项目一','customer':'客户甲'}]})
  save(self.kb/'tracking/material_library.json',{'assets':{'audio':{'path':'raw/'+ident[:20]+'.m4a','kind':'audio','downloadable':True}},'recordings':[{'sha256':'phone','sources':['audio']}]})
  result=jobs.daily_digest(self.state,self.kb);item=result['groups'][0]['items'][0]
  self.assertEqual(result['counts']['recordings'],1);self.assertEqual(item['kind'],'recording');self.assertEqual(item['communication']['type'],'internal');self.assertEqual(item['sources'][0]['id'],'audio')
 def test_overnight_import_appears_on_publication_day_without_redating_call(self):
  ident='n'*64
  save(self.root/'ledger.json',{'items':{ident:{'status':'archived','title':'客户电话','sha256':'phone','channel':'phone_recording','business_date':'2026-09-16'}}})
  save(self.root/'runs'/'2026-09-17T23-phone'/'review.json',{'published_at':'2026-09-18T00:03:00+08:00','completed':[ident],'items':[{'material_id':ident,'classification':'project','project_id':'p','summary':'当日报价','evidence':[]}],'projects':[{'id':'p','title':'项目','customer':'客户'}]})
  with patch.object(jobs,'now',return_value='2026-09-18T01:00:00+08:00'):result=jobs.daily_digest(self.state,self.kb)
  self.assertEqual(result['date'],'2026-09-18');self.assertTrue(result['is_today']);self.assertEqual(result['groups'][0]['items'][0]['business_date'],'2026-09-16')
 def test_mixed_call_knowledge_does_not_inherit_primary_customer(self):
  day=jobs.now()[:10];ident='m'*64
  save(self.root/'ledger.json',{'items':{ident:{'status':'archived','title':'混录电话','sha256':'mixed','channel':'phone_recording','business_date':'2026-09-15'}}})
  rows=[{'material_id':ident,'classification':'project','project_id':'p1','summary':'客户甲方案','evidence':[]},{'material_id':ident,'classification':'knowledge','project_id':'','summary':'另一个客户探索','evidence':[]}]
  save(self.root/'runs'/(day+'T20-mixed')/'review.json',{'completed':[ident],'items':rows,'projects':[{'id':'p1','title':'项目甲','customer':'客户甲'}]})
  save(self.kb/'tracking/material_library.json',{'assets':{},'recordings':[{'sha256':'mixed','customer':'客户甲','sources':[]}]})
  result=jobs.daily_digest(self.state,self.kb)
  self.assertEqual(result['counts']['recordings'],1)
  knowledge=next(g for g in result['groups'] if g['kind']=='knowledge')
  self.assertEqual(knowledge['customer'],'其他沟通与知识')
 def test_previous_receipt_not_used_as_new_run_result(self):
  save(self.root/'ui_request.json',{'request_id':'new','created_epoch':jobs.time.time(),'started_at':jobs.now()});save(self.root/'latest.json',{'run_id':'old','status':'completed','observed':10})
  result=jobs.status(self.state,self.kb);self.assertTrue(result['job']['running']);self.assertEqual(result['receipt'],{})
 def test_double_start_spawns_only_once_with_fixed_command(self):
  proc=MagicMock(pid=123)
  with patch.object(jobs.subprocess,'Popen',return_value=proc) as spawn,patch.object(jobs.threading,'Thread'):
   first=jobs.start({'action':'run'},self.state,self.kb);second=jobs.start({'action':'run'},self.state,self.kb)
  self.assertTrue(first['started']);self.assertFalse(second['started']);self.assertEqual(spawn.call_count,1)
  command=spawn.call_args.args[0];self.assertEqual(command[2],'run');self.assertIn('--request-id',command);self.assertTrue(spawn.call_args.kwargs['start_new_session']);self.assertNotIn('shell',spawn.call_args.kwargs)
 def test_external_cli_lock_prevents_second_writer(self):
  with (self.root/'pipeline.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   with patch.object(jobs.subprocess,'Popen') as spawn:
    result=jobs.start({},self.state,self.kb);self.assertFalse(result['started']);spawn.assert_not_called()
 def test_resume_interrupted_collection_collects_missing_sources(self):
  save(self.root/'active_run.json',{'request_id':'old','run_id':'old','action':'run','state':'running','phase':'local'})
  with patch.object(jobs.subprocess,'Popen',return_value=MagicMock(pid=123)) as spawn,patch.object(jobs.threading,'Thread'):
   jobs.start({'action':'resume'},self.state,self.kb)
  self.assertEqual(spawn.call_args.args[0][2],'run')
 def test_only_allowlisted_actions_can_be_started(self):
  for body in ({'action':'rm'}, {'action':[]},{'command':'run'}, {'action':'run','path':'/tmp/foo'},[]):
   with self.subTest(body=body),self.assertRaises(ValueError):jobs.start(body,self.state,self.kb)
 def test_daily_results_survive_repeat_sync_and_count_mixed_recording_once(self):
  today=jobs.now()[:10];ident='a'*64
  save(self.root/'ledger.json',{'items':{ident:{'id':ident,'status':'archived','title':'20260914 160659.m4a','sha256':'sha','channel':'computer','business_date':'2026-09-13'}}})
  save(self.kb/'tracking/material_library.json',{'assets':{},'recordings':[],'files':[]})
  row={'material_id':ident,'classification':'project','project_id':'p1','summary':'内部讨论，未确认客户接受。','business_date':'2026-09-13','evidence':[]}
  review={'completed':[ident],'items':[row,{**row,'project_id':'p2'}],'projects':[{'id':'p1','title':'项目一','customer':'客户甲'},{'id':'p2','title':'项目二','customer':'客户甲'}]}
  save(self.root/'runs'/f'{today}T10-00-r1'/'review.json',review)
  save(self.root/'runs'/f'{today}T11-00-r2'/'review.json',review)
  result=jobs.daily_digest(self.state,self.kb)
  self.assertEqual(result['counts']['recordings'],1);self.assertEqual(result['project_count'],2)
  self.assertEqual(result['groups'][0]['items'][0]['business_date'],'2026-09-13')
  self.assertEqual(len(result['groups'][0]['items']),1)
 def test_uncommitted_review_is_never_presented_as_archived_result(self):
  today=jobs.now()[:10];ident='a'*64
  save(self.root/'ledger.json',{'items':{ident:{'status':'ready_for_review'}}})
  save(self.root/'runs'/f'{today}T10-00-r1'/'review.json',{'completed':[ident],'projects':[],'items':[{'material_id':ident,'classification':'project','project_id':'p','summary':'不可展示'}]})
  self.assertEqual(jobs.daily_digest(self.state,self.kb)['groups'],[])
 def test_external_project_archive_is_visible_without_pipeline_run(self):
  today=jobs.now()[:10];folder=self.kb/'raw/transcripts/client';folder.mkdir(parents=True)
  note=folder/'meeting.md';note.write_text(f"---\ntitle: 现场沟通\ntype: project_communication\noccurred_at: {today}\nreviewed_at: {today}\n---\n# 现场沟通\n## 核心结论\n客户说明会员权益链路，报价未确认。\n\n## 下一步\n核对范围。")
  (self.kb/'projects').mkdir(exist_ok=True)
  (self.kb/'projects/demo.md').write_text(f'# 客户项目\n## 当前判断\n新沟通已归档。\n[[raw/transcripts/client/meeting.md]]')
  result=jobs.daily_digest(self.state,self.kb)
  self.assertTrue(result['is_today']);self.assertEqual(result['project_count'],1)
  item=result['groups'][0]['items'][0]
  self.assertIn('报价未确认',item['summaries'][0]);self.assertEqual(item['sources'][0]['path'],'raw/transcripts/client/meeting.md')
  self.assertEqual(jobs.daily_digest(self.state,self.kb)['material_count'],1)
  note.write_text(note.read_text().replace('type: project_communication','type: draft'))
  self.assertEqual(jobs.daily_digest(self.state,self.kb)['groups'],[])
 def test_previous_day_digest_is_explicitly_not_today(self):
  save(self.root/'runs'/'2026-01-01T10-00-r1'/'review.json',{'completed':[],'items':[],'projects':[]})
  self.assertFalse(jobs.daily_digest(self.state,self.kb)['is_today'])
 def test_pipeline_progress_is_bound_to_request_and_final_receipt(self):
  p=Pipeline({},self.state,self.kb,dt.date(2026,9,12),dt.date(2026,9,13));p.live_progress=True;p.command='run';p.request_id='request-x';p.started_at=jobs.now();p.progress('analyzing')
  before=json.loads((self.root/'active_run.json').read_text());self.assertEqual(before['request_id'],'request-x');self.assertEqual(before['phase'],'analyzing')
  result=p.receipt('completed',projects=[],refreshed=[]);p.progress('done',result);after=json.loads((self.root/'active_run.json').read_text());self.assertEqual(after['state'],'completed');self.assertEqual(after['receipt']['run_id'],p.run_id)
 def test_directory_permission_wait_is_bounded(self):
  with patch('tools.communication_pipeline.subprocess.run',side_effect=subprocess.TimeoutExpired('probe',12)):
   with self.assertRaisesRegex(Failure,'解锁电脑'):probe_directory(self.tmp.name)
 def test_unavailable_directory_is_not_reopened_by_collector(self):
  p=Pipeline({'local_roots':[{'name':'blocked','path':self.tmp.name}]},self.state,self.kb,dt.date(2026,9,12),dt.date(2026,9,13));p.unavailable_local.add(self.tmp.name)
  with patch('tools.communication_pipeline.os.walk',side_effect=AssertionError('blocked source reopened')):p.local()

if __name__=='__main__':unittest.main()
