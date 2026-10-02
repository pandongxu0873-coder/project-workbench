import json, tempfile, unittest, threading, subprocess, sys
from pathlib import Path
from unittest.mock import patch
import project_archive as ar
import project_workspace as pw
import project_rounds as rounds
import project_analysis as ai
class ArchiveTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name);self.k=root/'knowledge';self.s=root/'state';(self.k/'projects').mkdir(parents=True);self.s.mkdir()
  for title in ['合成项目A','合成项目B']:(self.k/'projects'/(title+'.md')).write_text('# '+title+'\n**客户**：[[合成同客户]]\n## 沟通 2026-09-26\n合成资料，预算待核。\n')
  self.projects=pw.build_projects(self.k,self.s);self.a,self.b=[p['id'] for p in self.projects]
 def body(self,ids=None,revision=0,action='archive',rid='test-archive-0001'):
  ids=ids or [self.a];return {'action':action,'project_ids':ids,'expected_revisions':dict.fromkeys(ids,revision),'request_id':rid,'reason':'本轮无机会','note':'合成验收，不是真实项目'}
 def mutate(self,**kw):return ar.mutate(self.s,pw.build_projects(self.k,self.s),self.body(**kw))
 def test_single_reason_required_idempotence_and_history(self):
  b=self.body();b['reason']=''
  with self.assertRaises(ValueError):ar.mutate(self.s,self.projects,b)
  self.assertFalse((self.s/'project_archive/manifest.json').exists())
  first=self.mutate();self.assertTrue(first['items'][0]['archived']);self.assertTrue(self.mutate()['replayed'])
  changed=self.body();changed['note']='changed'
  with self.assertRaises(ar.ArchiveConflict):ar.mutate(self.s,self.projects,changed)
  self.mutate(revision=1,action='restore',rid='test-restore-0001');a=ar.state(self.s,self.a)
  self.assertEqual(a['revision'],2);self.assertEqual([h['action'] for h in a['history']],['archive','restore']);self.assertFalse(a['archived'])
 def test_batch_atomic_conflict_and_same_customer(self):
  self.mutate();before=ar.read(self.s)
  with self.assertRaises(ar.ArchiveConflict):self.mutate(ids=[self.a,self.b],rid='batch-conflict-01')
  self.assertEqual(ar.read(self.s),before);self.assertFalse(ar.state(self.s,self.b)['archived'])
  self.mutate(ids=[self.b],rid='single-other-0001');self.assertTrue(ar.state(self.s,self.b)['archived'])
 def test_batch_success(self):
  self.mutate(ids=[self.a,self.b]);self.assertTrue(all(p['archive']['archived'] for p in pw.build_projects(self.k,self.s)))
 def test_restart_and_no_external_state_writes(self):
  sentinels=['invoice_vault/originals/keep.pdf','invoice_vault/metadata.sqlite3','branding/manifest.json','crm_snapshot.json','feishu_calendar_cache.json','commercial_drafts/keep.json']
  for x in sentinels:p=self.s/x;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'unchanged')
  sources={str(p):p.read_bytes() for p in (self.k/'projects').iterdir()};self.mutate()
  code='import project_archive;from pathlib import Path;assert project_archive.state(Path('+repr(str(self.s))+'),'+repr(self.a)+')["archived"]'
  subprocess.run([sys.executable,'-c',code],check=True)
  self.mutate(action='restore',revision=1,rid='restore-persist-01')
  for x in sentinels:self.assertEqual((self.s/x).read_bytes(),b'unchanged')
  for x,v in sources.items():self.assertEqual(Path(x).read_bytes(),v)
 def test_new_material_and_old_analysis_write_do_not_restore(self):
  self.mutate();before=ar.read(self.s)
  (self.k/'projects/合成项目A.md').write_text('# 合成项目A\n**客户**：[[合成同客户]]\n## 新资料 2026-09-27\n合成新资料。\n')
  ai.write_cache(self.s,self.a,{'project_id':self.a,'correction':'old callback','result':None})
  self.assertTrue(next(p for p in pw.build_projects(self.k,self.s) if p['id']==self.a)['archive']['archived']);self.assertEqual(ar.read(self.s),before)
 def test_overlay_after_slow_overview_read(self):
  def status(*args,**kw):
   if not ar.state(self.s,self.a)['archived']:self.mutate()
   return {'result':None,'state':'empty','stale':False,'error':'','fingerprint':'x'}
  with patch('project_analysis.status',side_effect=status):out=ai.overview(self.k,self.s)
  self.assertTrue(next(x for x in out['projects'] if x['id']==self.a)['archive']['archived']);self.assertEqual(out['active_project_count'],1)
 def test_two_windows_and_old_callback_race(self):
  self.mutate()
  with self.assertRaises(ar.ArchiveConflict):self.mutate(action='restore',revision=0,rid='stale-window-01')
  calls=[]
  @ar.sales_write
  def old_callback(body,k,s):calls.append(True)
  with self.assertRaises(rounds.RevisionConflict):old_callback({'project_id':self.a},self.k,self.s)
  self.mutate(action='restore',revision=1,rid='restore-race-01')
  with self.assertRaises(rounds.RevisionConflict):old_callback({'project_id':self.a,'archive_revision':0},self.k,self.s)
  old_callback({'project_id':self.a,'archive_revision':2},self.k,self.s);self.assertEqual(calls,[True])
 def test_concurrent_duplicate_one_commit(self):
  results=[];errors=[]
  def run():
   try:results.append(self.mutate())
   except Exception as e:errors.append(e)
  threads=[threading.Thread(target=run) for _ in range(2)]
  for t in threads:t.start()
  for t in threads:t.join(5)
  self.assertFalse(errors);self.assertEqual(len(results),2);self.assertEqual(ar.state(self.s,self.a)['revision'],1)
 def test_restore_preserves_no_contact_pause_and_old_due(self):
  record=rounds.save_round({'project_id':self.a,'revision':0,'scenario':'return','relationship':'no_contact','status':'暂停跟进','action':'合成旧动作','due':'2020-01-01'},self.k,self.s)
  self.mutate();self.mutate(action='restore',revision=1,rid='restore-paused-01')
  self.assertEqual(rounds.read_round(self.a,self.k,self.s)['record'],record['record']);self.assertEqual(rounds.followups(self.k,self.s)['items'],[])
 def test_responsibilities_and_calendar_retained_reminders_suppressed(self):
  tasks=[{'id':'obligation-A','project_id':self.a,'title':'合成验收及回款责任','deadline':'2020-01-01','status':'执行中'},{'id':'same-customer-B','project_id':self.b,'title':'合成销售推进','status':'执行中'}]
  (self.s/'risk_todos.json').write_text(json.dumps(tasks));self.mutate()
  meetings=[{'id':'meeting','project_id':self.a,'source_type':'feishu_calendar','title':'真实会议的合成样例'}]
  out=ar.decorate_items(tasks+meetings,self.s,self.projects);self.assertEqual(len(out),3);self.assertTrue(out[0]['sales_suppressed']);self.assertFalse(out[1].get('sales_suppressed'));self.assertIn('待收尾',out[0]['archive_label']);self.assertEqual(out[2]['title'],meetings[0]['title'])
  self.mutate(action='restore',revision=1,rid='restore-todos-01');out=ar.decorate_items(tasks,self.s,self.projects)
  self.assertTrue(out[0]['sales_suppressed']);self.assertEqual(json.loads((self.s/'risk_todos.json').read_text()),tasks)
 def test_archived_round_write_rejected_without_data_loss(self):
  self.mutate()
  with self.assertRaises(rounds.RevisionConflict):rounds.save_round({'project_id':self.a,'revision':0,'scenario':'return','relationship':'unknown','status':'准备中','action':'旧页面动作'},self.k,self.s)
  self.assertFalse((self.s/'project_rounds'/(self.a+'.json')).exists())
 def test_real_reminder_and_dashboard_gate(self):
  import server
  (self.s/'risk_todos.json').write_text(json.dumps([{'id':'t','project_id':self.a,'title':'合成提醒'}]));self.mutate()
  item={'id':'t','project_id':self.a,'schedule_bucket':'overdue','sales_suppressed':True}
  with patch.object(server,'WORKBENCH_DATA_ROOT',self.s):self.assertFalse(server.feishu_reminder_gate(item,server.datetime.now(server.LOCAL_TZ))['eligible']);self.assertEqual(server.build_due_followup_actions([item]),[])
 def test_shared_source_never_archives_sibling_responsibility(self):
  shared=[{**p,'sources':[{'path':'raw/shared.md','relation':'project_evidence'}]} for p in self.projects]
  (self.s/'risk_todos.json').write_text(json.dumps([{'id':'shared','source_path':'raw/shared.md','title':'身份待核的共有记录'}]))
  result=ar.mutate(self.s,shared,self.body())
  self.assertNotIn('shared',result['items'][0]['suppressed_task_ids']);self.assertEqual(ar.impact(shared[0],self.s,shared)['existing_items'],[])
 def test_new_explicit_round_after_restore_is_not_old_reminder(self):
  body={'project_id':self.a,'revision':0,'scenario':'return','relationship':'unknown','status':'准备中','action':'合成原计划','due':'2020-01-01'}
  rounds.save_round(body,self.k,self.s);self.mutate();self.mutate(action='restore',revision=1,rid='restore-new-round')
  self.assertTrue(rounds.followups(self.k,self.s)['items'][0]['sales_suppressed'])
  rounds.save_round({**body,'revision':1,'archive_revision':2,'action':'用户明确重新安排的新计划','due':'2026-10-20'},self.k,self.s)
  self.assertFalse(rounds.followups(self.k,self.s)['items'][0]['sales_suppressed'])
 def test_inflight_write_then_archive_captures_result(self):
  entered=threading.Event();release=threading.Event();errors=[]
  @ar.sales_write
  def callback(body,k,s):
   entered.set();release.wait(3);(s/'risk_todos.json').write_text(json.dumps([{'id':'inflight','project_id':self.a,'title':'旧请求先提交'}]))
  def archive():
   try:self.mutate()
   except Exception as e:errors.append(e)
  t=threading.Thread(target=lambda:callback({'project_id':self.a},self.k,self.s));t.start();self.assertTrue(entered.wait(2))
  u=threading.Thread(target=archive);u.start();release.set();t.join(3);u.join(3)
  self.assertFalse(errors);self.assertFalse(t.is_alive() or u.is_alive());self.assertIn('inflight',ar.state(self.s,self.a)['suppressed_task_ids'])
 def test_cross_process_compare_and_swap(self):
  code='''import json,sys;from pathlib import Path;import project_archive as a
try:a.mutate(Path(sys.argv[1]),json.loads(sys.argv[2]),json.loads(sys.argv[3]));print("committed")
except a.ArchiveConflict:print("conflict")
'''
  jobs=[subprocess.Popen([sys.executable,'-c',code,str(self.s),json.dumps(self.projects),json.dumps(self.body(rid='cross-process-0'+str(i)))],stdout=subprocess.PIPE,text=True) for i in range(2)]
  results=[p.communicate(timeout=5)[0].strip() for p in jobs];self.assertCountEqual(results,['committed','conflict']);self.assertEqual(ar.state(self.s,self.a)['revision'],1)
 def test_related_old_writes_and_external_retries_do_not_escape(self):
  import server
  items=[{'id':'t','project_id':self.a,'title':'合成销售提醒','deadline':'2026-10-01'}]
  (self.s/'risk_todos.json').write_text(json.dumps(items));self.mutate()
  with patch.object(server,'WORKBENCH_DATA_ROOT',self.s),patch.object(server,'SALES_WORKBENCH_KNOWLEDGE_ROOT',self.k),patch.object(server,'load_risk_todos',return_value=items),patch.object(server,'load_pm_daily_todos',return_value=[]),patch.object(server,'create_manual_todo_impl') as manual,patch.object(server,'_submit_risk_evidence_current') as evidence,patch.object(server,'retry_todo_calendar_impl') as retry:
   for operation,body in [(server.create_manual_todo,{'project_id':self.a}), (server.submit_risk_evidence,{'todo_id':'t','status':'推进中'}),(server.retry_todo_calendar,'t')]:
    with self.assertRaises(rounds.RevisionConflict):operation(body)
   manual.assert_not_called();evidence.assert_not_called();retry.assert_not_called()
   server.submit_risk_evidence({'todo_id':'t','status':'已处理','archive_revision':1});evidence.assert_called_once()
 def test_old_outbox_update_held_without_cancelling_external_task(self):
  import server
  todos=[{'id':'t','project_id':self.a,'title':'合成提醒'}];(self.s/'risk_todos.json').write_text(json.dumps(todos));self.mutate()
  queue=[{'id':'q','status':'pending','operation':'update','task_id':'external-test','payload':{'todo_id':'t','deadline':'2026-10-01'}}]
  with patch.object(server,'WORKBENCH_DATA_ROOT',self.s),patch.object(server,'SALES_WORKBENCH_KNOWLEDGE_ROOT',self.k),patch.object(server,'load_risk_todos',return_value=todos),patch.object(server,'load_external_sync_outbox',return_value=queue),patch.object(server,'write_private_json') as write,patch.object(server,'update_feishu_task_reminder') as update,patch.object(server,'complete_feishu_task_reminder') as complete:
   result=server.process_external_sync_outbox(force=True);update.assert_not_called();complete.assert_not_called();self.assertEqual(result['completed'],0);self.assertEqual(result['pending'],1);self.assertTrue(write.call_args.args[1][0]['archive_hold'])
 def test_local_http_reason_conflict_idempotence_and_readback(self):
  from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
  from urllib.request import Request,urlopen
  from urllib.error import HTTPError
  outer=self
  class Handler(BaseHTTPRequestHandler):
   def _send_json(self,value,status=200):
    body=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
   def do_GET(self):ar.handle(self,outer.k,outer.s)
   def do_POST(self):ar.handle(self,outer.k,outer.s)
   def log_message(self,*args):pass
  http=ThreadingHTTPServer(('127.0.0.1',0),Handler);t=threading.Thread(target=http.serve_forever,daemon=True);t.start()
  def call(body=None,headers=None):
   req=Request('http://127.0.0.1:'+str(http.server_port)+'/api/project-archive',data=json.dumps(body).encode() if body is not None else None,headers=headers or {})
   try:
    with urlopen(req,timeout=3) as r:return r.status,json.load(r)
   except HTTPError as e:return e.code,json.load(e)
  try:
   self.assertEqual(call(self.body())[0],403);headers={'X-Workbench-Request':'local-v1'}
   self.assertEqual(call({**self.body(),'reason':''},headers)[0],400)
   self.assertEqual(call(self.body(),headers)[0],200);self.assertTrue(call(self.body(),headers)[1]['replayed'])
   self.assertEqual(call(self.body(rid='other-http-window'),headers)[0],409)
   self.assertTrue(next(x for x in call()[1]['items'] if x['project_id']==self.a)['archive']['archived'])
  finally:http.shutdown();http.server_close();t.join(2)
 def test_archive_confirmation_lists_cached_meeting_without_refresh(self):
  cached={'fetched_at':'2026-09-20','items':[{'event_id':'meeting-A','project_id':self.a,'summary':'合成真实会议','start_time':{'date':'2026-10-01'}},{'event_id':'meeting-B','project_id':self.b,'summary':'同客户另一项目会议'}]}
  path=self.s/'feishu_calendar_cache.json';path.write_text(json.dumps(cached));before=path.read_bytes();impact=ar.impact(self.projects[0],self.s,self.projects,self.k)
  self.assertEqual([x['title'] for x in impact['existing_meetings']],['合成真实会议']);self.assertIn('不代表最新',impact['calendar_state']);self.mutate();self.assertEqual(path.read_bytes(),before)
 def test_new_evidence_banner_keeps_archived_and_original_dates(self):
  self.mutate();before=ar.read(self.s)
  p=next(x for x in self.projects if x['id']==self.a);path=self.k/p['source_path'];path.write_text(path.read_text()+'\n## 沟通 2026-09-26\n新增沟通方向，请核实。\n')
  row=next(x for x in pw.build_projects(self.k,self.s) if x['id']==self.a)
  self.assertTrue(row['archive']['archived']);self.assertTrue(row['archive']['review']['has_new_material']);self.assertEqual(row['archive']['review']['items'][0]['change'],'内容已更新');self.assertEqual(ar.read(self.s),before)
  self.assertFalse(next(x for x in pw.build_projects(self.k,self.s) if x['id']==self.b)['archive']['review']['has_new_material'])
 def test_file_touch_ai_result_and_review_date_do_not_imply_new_opportunity(self):
  self.mutate();p=next(x for x in self.projects if x['id']==self.a);(self.k/p['source_path']).touch()
  ai.write_cache(self.s,self.a,{'project_id':self.a,'correction':'AI方向变化','result':None})
  row=next(x for x in pw.build_projects(self.k,self.s) if x['id']==self.a);self.assertFalse(row['archive']['review']['has_new_material']);self.assertTrue(row['archive']['archived'])
 def test_new_link_then_restore_and_rearchive_resets_baseline(self):
  self.mutate();p=next(x for x in self.projects if x['id']==self.a);(self.k/'raw').mkdir();(self.k/'raw/new.md').write_text('# 合成新沟通\n沟通日期：2026-09-26\n新方向待核实。')
  path=self.k/p['source_path'];path.write_text(path.read_text()+'\n[[raw/new]]\n')
  row=next(x for x in pw.build_projects(self.k,self.s) if x['id']==self.a);self.assertTrue(any(x['path']=='raw/new.md' and x['change']=='新增材料' for x in row['archive']['review']['items']))
  self.mutate(action='restore',revision=1,rid='restore-with-material');self.mutate(revision=2,rid='archive-new-baseline')
  row=next(x for x in pw.build_projects(self.k,self.s) if x['id']==self.a);self.assertFalse(row['archive']['review']['has_new_material']);self.assertEqual(len(row['archive']['history']),3)
 def test_legacy_archive_does_not_guess_new_material(self):
  self.mutate();m=ar.read(self.s);del m['projects'][self.a]['evidence_baseline'];ar.commit(self.s,m)
  row=next(x for x in pw.build_projects(self.k,self.s) if x['id']==self.a);self.assertTrue(row['archive']['review']['baseline_missing']);self.assertFalse(row['archive']['review']['has_new_material'])
 def test_review_metadata_does_not_invalidate_analysis_input(self):
  import copy
  project=next(p for p in pw.build_projects(self.k,self.s) if p['id']==self.a)
  before=copy.deepcopy(project)
  for source in before['sources']:source.pop('content_sha256',None)
  a=ai.packet(self.a,'',self.k,self.s,before);b=ai.packet(self.a,'',self.k,self.s,project)
  self.assertEqual(a['fingerprint'],b['fingerprint']);self.assertEqual(ai.input_fingerprint(a),ai.input_fingerprint(b))
