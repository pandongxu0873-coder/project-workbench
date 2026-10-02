import importlib.util,json,tempfile,unittest,hashlib,datetime,os
from pathlib import Path
from unittest.mock import patch
SPEC=importlib.util.spec_from_file_location('communication_pipeline',Path(__file__).resolve().parents[1]/'tools/communication_pipeline.py')
m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)
class PipelineTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.k=self.root/'kb';self.s=self.root/'state';self.k.mkdir();self.s.mkdir()
  (self.k/'projects').mkdir();(self.k/'tracking').mkdir();(self.k/'entities').mkdir()
  (self.k/'projects/项目甲.md').write_text('---\ntitle: 项目甲\n---\n# 项目甲\n\n**客户**：[[客户甲]]\n\n## 当前判断\n历史判断保留。\n')
  (self.k/'entities/客户甲.md').write_text('# 客户甲\n')
  (self.k/'tracking/client_registry.md').write_text('正式状态不能变')
  (self.k/'tracking/material_library.json').write_text(json.dumps({'assets':{},'recordings':[],'files':[],'summary':{}}))
  self.pid=m.digest('projects/项目甲.md')[:20];self.cfg={'knowledge_root':str(self.k),'local_roots':[]}
  self.p=m.Pipeline(self.cfg,self.s,self.k,datetime.date(2026,9,11),datetime.date(2026,9,13))
 def tearDown(self):self.tmp.cleanup()
 def stage(self,text='业务日期：2026-09-11\n客户要求复验订单导出。',name='甲.txt'):
  p=self.root/name;p.write_text(text);return self.p.stage(str(p),name,p.read_bytes(),'.txt','desktop',str(p))
 def answer(self,packet,cfg):
  return {'items':[{'source_id':s['source_id'],'project_id':self.pid,'classification':'project','summary':'客户要求复验，未验收。','business_date':s['business_date'],'date_quote':'','next_action':'协调复验安排。','uncertainties':['复验回执未取得'],'evidence':[{'quote':'客户要求复验订单导出。','level':'customer_statement','meaning':'待复验'}]} for s in packet['sources']]}
 def test_inference_command_uses_shared_isolation_without_changing_model_or_input(self):
  captured={};packet={'projects':[{'id':self.pid}],'sources':[{'source_id':'fixture','text':'隔离测试原文'}]}
  skill_config='skills.config=[{path="/fixture/SKILL.md",enabled=false}]'
  class Process:
   returncode=0
   def communicate(self,prompt,timeout):captured.update(prompt=prompt,timeout=timeout);return None,''
  def spawn(args,**kwargs):
   captured.update(args=args,options=kwargs);Path(args[args.index('-o')+1]).write_text('{"items":[]}');return Process()
  with patch('project_analysis.settings',return_value={'model':'gpt-6-astra','effort':'ultra','provider':'openai'}),patch('project_analysis.isolated_skills_config',return_value=skill_config) as isolation,patch.object(m.subprocess,'Popen',side_effect=spawn):
   self.assertEqual(m.infer(packet,{'classification_effort':'medium','model_timeout':600}),{'items':[]})
  args=captured['args'];disabled={args[i+1] for i,arg in enumerate(args[:-1]) if arg=='--disable'}
  self.assertEqual(disabled,{'shell_tool','unified_exec','plugins','apps','skill_search'});isolation.assert_called_once_with()
  overrides=[args[i+1] for i,arg in enumerate(args[:-1]) if arg=='-c']
  self.assertIn(skill_config,overrides);self.assertIn('web_search="disabled"',overrides);self.assertIn('model_reasoning_effort="medium"',overrides)
  self.assertEqual(args[args.index('-m')+1],'gpt-6-astra');self.assertEqual(args[args.index('--sandbox')+1],'read-only')
  self.assertIn('--ignore-user-config',args);self.assertIn('--ephemeral',args)
  self.assertEqual(captured['timeout'],600);self.assertEqual(json.loads(captured['prompt'].split('\nINPUT\n',1)[1]),packet)
 def test_phone_audio_project_and_knowledge_keep_their_own_playable_source(self):
  entries=[]
  for i in range(3):
   entries.append(self.p.stage('adb:'+str(i),'电话'+str(i),('audio-'+str(i)).encode(),'.m4a','phone_recording','adb://call/'+str(i),'2026-09-11',text='客户要求复验订单导出。'))
  def classify(packet,cfg):
   result=self.answer(packet,cfg)
   result['items'][-1].update(classification='knowledge',project_id='')
   return result
  review=m.review_pending(self.p,classify);m.apply_review(self.p,review)
  lib=m.load(self.k/'tracking/material_library.json');self.assertEqual(len(lib['recordings']),3)
  for entry in entries:
   row=next(r for r in lib['recordings'] if r['sha256']==entry['sha256'])
   audio=[lib['assets'][a] for a in row['sources'] if lib['assets'][a]['kind']=='audio']
   self.assertEqual(len(audio),1)
   self.assertEqual(m.digest((self.k/audio[0]['path']).read_bytes()),entry['sha256'])
   self.assertIn('手机',row['source_channel'])
  knowledge=next(r for r in lib['recordings'] if r['sha256']==entries[-1]['sha256'])
  self.assertEqual(knowledge['project_id'],'')
  m.apply_review(self.p,review)
  self.assertEqual(len(m.load(self.k/'tracking/material_library.json')['recordings']),3)
 def test_copy_dedup_and_existing_library(self):
  a=self.stage();b=self.stage(name='复制.txt');self.assertEqual(a['id'],b['id']);self.assertEqual(len(self.p.ledger['items']),1);self.assertEqual(self.p.duplicates,1)
 def test_tencent_meetings_get_separate_minutes_with_originals_and_idempotent_archive(self):
  entries=[]
  for i in range(2):
   raw=json.dumps({'meeting_event_id':'meeting'+str(i),'source_versions':[{'record_file_id':'a'+str(i)},{'record_file_id':'b'+str(i)}]}).encode()
   entries.append(self.p.stage('tencent-event:'+str(i),'业务会议'+str(i),raw,'.json','tencent_meeting','tencent-meeting://'+str(i),'2026-09-11',text='客户要求复验订单导出。'))
  originals={e['id']:Path(e['original']).read_bytes() for e in entries};review=m.review_pending(self.p,self.answer);m.apply_review(self.p,review)
  lib=m.load(self.k/'tracking/material_library.json');minutes=[r for r in lib['files'] if r['category']=='腾讯会议纪要'];self.assertEqual(len(minutes),2)
  for row in minutes:
   self.assertEqual(row['project_id'],self.pid);self.assertEqual(row['business_date'],'2026-09-11')
   note=lib['assets'][row['sources'][0]]['path'];text=(self.k/note).read_text()
   self.assertIn('不是客户签认纪要',text);self.assertIn('客户要求复验订单导出。',text);self.assertIn('跟进建议（未承诺、未执行）',text)
   self.assertTrue(all((self.k/lib['assets'][a]['path']).is_file() for a in row['sources']))
   self.assertIn('[['+note+']]',(self.k/'index.md').read_text()+(self.k/'raw/transcripts/自动沟通归档'/Path(note).parent.name/(self.pid+'_沟通整理.md')).read_text())
  before=(self.k/'tracking/material_library.json').read_bytes();m.apply_review(self.p,review);self.assertEqual((self.k/'tracking/material_library.json').read_bytes(),before)
  self.assertEqual((self.k/'tracking/client_registry.md').read_text(),'正式状态不能变')
  self.assertTrue(all(Path(e['original']).read_bytes()==originals[e['id']] for e in entries))
 def test_tencent_knowledge_only_minutes_do_not_invent_project_or_actions(self):
  self.p.stage('tencent-event:m','内部分享',b'original','.json','tencent_meeting','tencent-meeting://m','2026-09-11',text='客户要求复验订单导出。')
  review=m.review_pending(self.p,self.answer);review['items'][0].update(classification='knowledge',project_id='',next_action='')
  before=(self.k/'projects/项目甲.md').read_bytes();self.assertEqual(m.apply_review(self.p,review),[])
  row=next(r for r in m.load(self.k/'tracking/material_library.json')['files'] if r['category']=='腾讯会议纪要')
  self.assertEqual(row['project_id'],'');self.assertEqual(row['related_projects'],[]);self.assertEqual((self.k/'projects/项目甲.md').read_bytes(),before)
  self.assertNotIn('跟进建议',Path(row['archive_paths'][0]).read_text())
 def test_tencent_unresolved_identity_is_not_published_as_reviewed_minutes(self):
  self.p.stage('tencent-event:m','未核会议',b'original','.json','tencent_meeting','tencent-meeting://m','2026-09-11',text='客户要求复验订单导出。')
  review=m.review_pending(self.p,self.answer);review['items'][0].update(classification='needs_review',project_id='')
  m.apply_review(self.p,review)
  self.assertFalse(any(r.get('category')=='腾讯会议纪要' for r in m.load(self.k/'tracking/material_library.json')['files']))
 def test_existing_material_sha_is_not_reimported(self):
  self.p.existing_sha.add(m.digest(b'existing'));r=self.stage('existing');self.assertEqual(r['status'],'already_indexed')
 def test_business_date_not_review_date(self):
  self.assertEqual(m.event_date('reviewed_at: 2026-09-13\noccurred_at: 2026-09-11\n'),'2026-09-11')
  self.assertEqual(m.event_date('读取日期：2026-09-13'), '')
 def test_quote_and_project_validation_fail_closed(self):
  e=self.stage();s={'source_id':'x','text':Path(e['text_path']).read_text(),'business_date':'2026-09-11'};r=self.answer({'sources':[s]}, {})
  m.validate_review(r,[s],[{'id':self.pid}]);r['items'][0]['evidence'][0]['quote']='已验收通过'
  with self.assertRaises(m.Failure):m.validate_review(r,[s],[{'id':self.pid}])
  r=self.answer({'sources':[s]},{});r['items'][0]['project_id']='arbitrary'
  with self.assertRaises(m.Failure):m.validate_review(r,[s],[{'id':self.pid}])
 def test_missing_rows_fail_closed(self):
  with self.assertRaises(m.Failure):m.validate_review({'items':[]},[{'source_id':'x','text':'t','business_date':''}],[])
 def test_pages_loop_and_partial_not_complete(self):
  n=0
  def fetch(t):return {'data':{'messages':[1],'has_more':True,'page_token':'same'}}
  it=m.pages(fetch,'messages');self.assertEqual(next(it),[1]);self.assertEqual(next(it),[1])
  with self.assertRaises(m.Failure):next(it)
 def test_pdf_failure_preserves_original(self):
  r=self.p.stage('attachment','PDF附件',b'%PDF-1.0 broken','.pdf','feishu_attachment','om_x')
  self.assertEqual(r['status'],'extraction_pending');self.assertEqual(Path(r['original']).read_bytes(),b'%PDF-1.0 broken')
 def test_resume_review_cache_and_archive_idempotence(self):
  self.stage();review=m.review_pending(self.p,self.answer)
  cached=m.review_pending(self.p,lambda *a: (_ for _ in ()).throw(AssertionError('must reuse cache')))
  self.assertEqual(review['items'],cached['items']);changed=m.apply_review(self.p,review);self.assertEqual(changed,[self.pid])
  before=(self.k/'tracking/material_library.json').read_bytes();p2=m.Pipeline(self.cfg,self.s,self.k,self.p.start,self.p.end);m.recover(p2)
  empty=m.review_pending(p2,self.answer);self.assertEqual(empty['completed'],[])
  self.assertEqual((self.k/'tracking/material_library.json').read_bytes(),before)
  self.assertEqual((self.k/'tracking/client_registry.md').read_text(),'正式状态不能变')
  self.assertIn('历史判断保留',(self.k/'projects/项目甲.md').read_text())
 def test_selected_review_preserves_other_pending_materials_and_counts_only_selected(self):
  target=self.stage();other=self.stage('另一份：客户要求复验订单导出。','乙.txt')
  before=json.loads(json.dumps(self.p.ledger));seen=[]
  def classify(packet,cfg):
   seen.extend(s['material_id'] for s in packet['sources']);return self.answer(packet,cfg)
  review=m.review_pending(self.p,classify,material_ids=[target['id']])
  self.assertEqual(seen,[target['id']]);self.assertEqual(review['completed'],[target['id']]);self.assertFalse(self.p.gaps)
  m.apply_review(self.p,review)
  saved=m.load(self.p.root/'ledger.json')['items']
  self.assertEqual(set(saved),set(before['items']));self.assertEqual(saved[other['id']],before['items'][other['id']])
  self.assertEqual(saved[target['id']]['status'],'archived')
  self.assertEqual(m.review_pending(self.p,self.answer,material_ids=[target['id']])['completed'],[])
 def test_selected_failure_preserves_ledger_and_reports_only_requested_failure(self):
  target=self.stage();self.stage('另一份：客户要求复验订单导出。','乙.txt')
  before=(self.p.root/'ledger.json').read_bytes()
  def fail(*args):raise m.Failure('AI分析超时')
  result=m.review_pending(self.p,fail,material_ids=[target['id']])
  self.assertEqual(result['completed'],[]);self.assertEqual((self.p.root/'ledger.json').read_bytes(),before)
  gap=next(g for g in self.p.gaps if g['source']=='分析未完成')
  self.assertEqual(gap['reason'],'1条自动重试后仍未完成，原件已保存')
 def test_selected_review_rejects_unknown_or_unextracted_material_without_inference(self):
  self.stage();image=self.p.stage('image','扫描图',b'image','.png','desktop','image.png')
  def unexpected(*args):raise AssertionError('must not infer')
  for ids in ([],['f'*64],[image['id']], 'f'*64):
   with self.subTest(ids=ids),self.assertRaises(m.Failure):m.review_pending(self.p,unexpected,material_ids=ids)
 def test_retry_cli_uses_lock_skips_collection_and_preserves_timeout_config(self):
  target=self.stage();other=self.stage('另一份：客户要求复验订单导出。','乙.txt')
  before=json.loads(json.dumps(self.p.ledger['items'][other['id']]))
  cfg=self.root/'config.json';m.save(cfg,{**self.cfg,'model_timeout':180,'classification_effort':'medium'})
  cfg_before=cfg.read_bytes();review_pending=m.review_pending;calls=[]
  def classify(packet,config):
   self.assertEqual(config['model_timeout'],600);self.assertEqual(config['classification_effort'],'medium')
   with (self.p.root/'pipeline.lock').open('a') as lock:
    with self.assertRaises(BlockingIOError):m.fcntl.flock(lock,m.fcntl.LOCK_EX|m.fcntl.LOCK_NB)
   calls.extend(s['material_id'] for s in packet['sources']);return self.answer(packet,config)
  def review(pipe,**kwargs):return review_pending(pipe,classify,**kwargs)
  def forbidden(*args,**kwargs):raise AssertionError('retry must not collect or extract sources')
  with patch.object(m,'review_pending',side_effect=review),patch.object(m.Pipeline,'collect',side_effect=forbidden),patch.object(m.Pipeline,'doctor',side_effect=forbidden),patch.object(m.Pipeline,'retry_extractions',side_effect=forbidden),patch('tools.wechat_source.review_contexts',side_effect=forbidden),patch.object(m,'api',return_value={'state':'ready','stale':False}) as api,patch('builtins.print'):
   self.assertEqual(m.main(['retry','--material-id',target['id'],'--model-timeout','600','--config',str(cfg),'--state-root',str(self.s),'--knowledge-root',str(self.k)]),2)
  self.assertEqual(calls,[target['id']]);self.assertEqual(cfg.read_bytes(),cfg_before)
  saved=m.load(self.p.root/'ledger.json')['items'];self.assertEqual(saved[other['id']],before);self.assertEqual(saved[target['id']]['status'],'archived')
  receipt=m.load(self.p.root/'latest.json');self.assertEqual(receipt['material_ids'],[target['id']]);self.assertEqual(receipt['completed_material_ids'],[target['id']]);self.assertEqual(receipt['observed'],0)
  self.assertEqual(receipt['unresolved']['ready_for_review'],1);self.assertEqual(receipt['refreshed'],[self.pid]);self.assertEqual(api.call_count,1)
  with (self.p.root/'pipeline.lock').open('a') as lock:m.fcntl.flock(lock,m.fcntl.LOCK_EX|m.fcntl.LOCK_NB)
 def test_retry_cli_rejects_missing_scope_and_timeout_override_for_normal_runs(self):
  cfg=self.root/'config.json';m.save(cfg,self.cfg)
  for args in (['retry'],['retry','--material-id','not-an-id'],['run','--model-timeout','600'],['retry','--material-id','a'*64,'--model-timeout','0']):
   with self.subTest(args=args),self.assertRaises(m.Failure):m.main(args+['--config',str(cfg),'--state-root',str(self.s),'--knowledge-root',str(self.k)])
 def test_retry_cli_cannot_enter_while_another_pipeline_holds_lock(self):
  target=self.stage();cfg=self.root/'config.json';m.save(cfg,self.cfg);before=(self.p.root/'ledger.json').read_bytes()
  with (self.p.root/'pipeline.lock').open('a') as lock,patch.object(m,'review_pending') as review:
   m.fcntl.flock(lock,m.fcntl.LOCK_EX|m.fcntl.LOCK_NB)
   with self.assertRaisesRegex(m.Failure,'已有整理任务'):m.main(['retry','--material-id',target['id'],'--config',str(cfg),'--state-root',str(self.s),'--knowledge-root',str(self.k)])
   review.assert_not_called()
  self.assertEqual((self.p.root/'ledger.json').read_bytes(),before)
 def test_selected_weekly_report_stays_read_only(self):
  target=self.stage(name='青岳酒业自建云店项目双周周报.txt');self.stage('另一份：客户要求复验订单导出。','乙.txt')
  before=(self.k/'projects/项目甲.md').read_bytes()
  def classify(packet,cfg):
   self.assertTrue(all(s['informational_only'] for s in packet['sources']));return self.answer(packet,cfg)
  review=m.review_pending(self.p,classify,material_ids=[target['id']])
  self.assertEqual(m.apply_review(self.p,review),[]);self.assertEqual((self.k/'projects/项目甲.md').read_bytes(),before)
  lib=m.load(self.k/'tracking/material_library.json');self.assertEqual(len(lib['files']),1);self.assertEqual(lib['files'][0]['category'],'只读项目动态')
  note=next((self.k/'raw').rglob('*_项目动态.md')).read_text();self.assertNotIn('协调复验安排',note)
 def test_transaction_mid_crash_and_external_change(self):
  folder=self.root/'tx';folder.mkdir();(folder/'x.after').write_bytes(b'new');p=self.k/'index.md';p.write_bytes(b'old')
  m.save(folder/'plan.json',{'projects':[],'ops':[{'path':'index.md','before':m.digest(b'old'),'after':m.digest(b'new'),'payload':'x.after'}]})
  p.write_bytes(b'new');m.execute_transaction(folder,self.k);self.assertEqual(p.read_bytes(),b'new')
  p.write_bytes(b'external')
  with self.assertRaises(m.Failure):m.execute_transaction(folder,self.k)
  self.assertEqual(p.read_bytes(),b'external')
 def test_no_permission_keeps_error_separate_from_empty(self):
  with patch.object(m,'cli_json',return_value={'identities':{'bot':{'available':True},'user':{'available':False}}}):r=self.p.doctor()
  self.assertTrue(r['feishu_bot']);self.assertFalse(r['feishu_user']);self.assertTrue(any('用户' in x['source'] for x in r['gaps']))
 def test_unknown_event_does_not_replace_current_judgement(self):
  e=self.stage('客户要求复验订单导出。');review=m.review_pending(self.p,self.answer);m.apply_review(self.p,review)
  body=(self.k/'projects/项目甲.md').read_text();self.assertNotIn('communication-pipeline:start',body);self.assertIn('历史判断保留',body)
 def test_date_must_match_source(self):
  e=self.stage();src={'source_id':'x','text':Path(e['text_path']).read_text(),'business_date':'2026-09-11'};r=self.answer({'sources':[src]},{});r['items'][0]['business_date']='2026-09-13'
  with self.assertRaises(m.Failure):m.validate_review(r,[src],[{'id':self.pid}])
 def test_chinese_meeting_date_is_valid_without_inventing_missing_year(self):
  src={'source_id':'x','text':'会议日期：2026年9月13日。客户要求复验订单导出。','business_date':''}
  r=self.answer({'sources':[src]},{});r['items'][0].update(business_date='2026-09-13',date_quote='2026年9月13日')
  m.validate_review(r,[src],[{'id':self.pid}])
  r['items'][0]['date_quote']='9月13日'
  with self.assertRaises(m.Failure):m.validate_review(r,[src],[{'id':self.pid}])
  self.assertEqual(m.explicit_dates('2026年2月30日'),set())
 def test_existing_project_material_is_retrieved_without_becoming_new_evidence(self):
  m.save(self.k/'tracking/material_library.json',{'assets':{},'files':[],'recordings':[{'id':'prior','project_id':self.pid,'title':'部门关键词回复','summary':'按部门启停，每个部门独立关键词，旧报价待核。'}]})
  src={'source_id':'x','title':'方案','text':'按部门启停，每个部门独立关键词。','business_date':''}
  background=m.association_background(self.p,[src],[{'id':self.pid}]);self.assertEqual(background[0]['project_id'],self.pid)
  self.assertTrue(background[0]['reference_only'])
  r=self.answer({'sources':[src]},{});r['items'][0]['evidence'][0]['quote']='旧报价待核。'
  with self.assertRaises(m.Failure):m.validate_review(r,[src],[{'id':self.pid}])
 def test_pending_receipt_cannot_report_completed(self):
  self.p.stage('bad','扫描图片',b'image','.png','desktop','missing.png')
  self.p.gaps=[];r=self.p.receipt('completed')
  self.assertEqual(r['status'],'partial');self.assertEqual(r['unresolved']['extraction_pending'],1)
 def test_background_environment_includes_audio_decoder(self):
  with patch.dict(os.environ,{'PATH':'/usr/bin:/bin'}):
   self.assertIn('/opt/homebrew/bin',m.runtime_env()['PATH'].split(os.pathsep))
   self.assertEqual(os.environ['PATH'],'/usr/bin:/bin')
 def test_recording_date_can_be_recovered_without_duplicate_material(self):
  e=self.stage('客户要求复验订单导出。','录音.txt');self.assertFalse(e['business_date'])
  self.p.stage(e['key'],e['title'],Path(e['original']).read_bytes(),'.txt',e['channel'],e['origin'],'2026-09-13')
  self.assertEqual(e['business_date'],'2026-09-13');self.assertEqual(len(self.p.ledger['items']),1)
 def test_failed_extraction_retries_preserved_original(self):
  with patch.object(m,'extract',side_effect=m.Failure('temporary decoder failure')):
   e=self.p.stage('audio','录音.m4a',b'audio','.m4a','computer','/missing.m4a','2026-09-13')
  with patch.object(m,'extract',return_value=('客户要求复验订单导出。','machine transcript')) as extract:
   self.p.retry_extractions()
  self.assertEqual(e['status'],'ready_for_review');self.assertEqual(e['business_date'],'2026-09-13')
  self.assertEqual(extract.call_args.args[0],Path(e['original']));self.assertEqual(Path(e['original']).read_bytes(),b'audio')
 def test_one_run_processes_backlog_beyond_old_item_limit(self):
  self.p.cfg['max_items_per_run']=1
  self.stage();self.stage('另一段：客户要求复验订单导出。','乙.txt')
  self.assertEqual(len(m.review_pending(self.p,self.answer)['completed']),2)
 def test_temporary_ai_failure_retries_in_same_run(self):
  self.stage();calls=[]
  def recover(packet,cfg):
   calls.append(1)
   if len(calls)==1:raise m.Failure('temporary timeout')
   return self.answer(packet,cfg)
  self.assertEqual(len(m.review_pending(self.p,recover)['completed']),1)
  self.assertEqual(len(calls),2);self.assertFalse(self.p.gaps)
 def test_failed_batch_splits_automatically_and_preserves_valid_neighbor(self):
  good=self.stage();bad=self.stage('另一份：客户要求复验订单导出。','乙.txt')
  def picky(packet,cfg):
   if any(s['material_id']==bad['id'] for s in packet['sources']):raise m.Failure('无法核验')
   return self.answer(packet,cfg)
  result=m.review_pending(self.p,picky)
  self.assertEqual(result['completed'],[good['id']]);self.assertTrue(self.p.gaps)
  self.assertEqual(bad['status'],'ready_for_review')
 def test_reference_archive_is_visible_without_inventing_project_or_changing_original(self):
  e=self.stage(name='客户甲范围讨论.txt');review=m.review_pending(self.p,self.answer)
  r=review['items'][0];r.update(classification='needs_review',project_id='')
  project=(self.k/'projects/项目甲.md').read_bytes();original=Path(e['original']).read_bytes()
  self.assertEqual(m.apply_review(self.p,review),[])
  m.publish_references(self.p,review)
  lib=m.load(self.k/'tracking/material_library.json');card=lib['files'][0]
  self.assertEqual(card['customer'],'客户甲');self.assertEqual(card['project_id'],'')
  self.assertEqual(card['category'],'已归档 · 项目归属待核')
  for aid in card['sources']:self.assertTrue((self.k/lib['assets'][aid]['path']).is_file())
  self.assertEqual(Path(e['original']).read_bytes(),original);self.assertEqual((self.k/'projects/项目甲.md').read_bytes(),project)
  receipt=self.p.receipt('completed');self.assertEqual(receipt['unresolved']['needs_review'],0);self.assertEqual(receipt['archived_reference'],1)
  before=(self.k/'tracking/material_library.json').read_bytes();m.apply_review(self.p,review);m.publish_references(self.p,review)
  self.assertEqual((self.k/'tracking/material_library.json').read_bytes(),before)
  self.assertEqual(e['status'],'archived_reference')
 def test_reference_reuses_verified_asset_original_with_transaction_body(self):
  e=self.stage();review=m.review_pending(self.p,self.answer)
  review['items'][0].update(classification='needs_review',project_id='')
  raw='raw/assets/received/source.txt';path=self.k/raw;path.parent.mkdir(parents=True);path.write_bytes(Path(e['original']).read_bytes())
  lib=m.load(self.k/'tracking/material_library.json');lib['assets'][m.digest(raw)]={'path':raw,'sha256':e['sha256'],'kind':'document','sensitive':True,'readable':False,'downloadable':False};m.save(self.k/'tracking/material_library.json',lib)
  m.apply_review(self.p,review);m.publish_references(self.p,review)
  lib=m.load(self.k/'tracking/material_library.json');card=lib['files'][0];paths=[lib['assets'][aid]['path'] for aid in card['sources']]
  self.assertIn(raw,paths);self.assertEqual(lib['assets'][m.digest(raw)],{'path':raw,'sha256':e['sha256'],'kind':'document','sensitive':True,'readable':False,'downloadable':False});body=next(p for p in paths if p.endswith('_正文.txt'))
  self.assertTrue(body.startswith('raw/transcripts/'));self.assertEqual((self.k/body).read_bytes(),Path(e['text_path']).read_bytes())
  self.assertEqual(m.digest(path.read_bytes()),e['sha256']);self.assertEqual(e['status'],'archived_reference')
  before=(self.k/'tracking/material_library.json').read_bytes();m.publish_references(self.p,review);self.assertEqual(before,(self.k/'tracking/material_library.json').read_bytes())
 def test_reference_reused_asset_corruption_still_blocks_publication(self):
  e=self.stage();review=m.review_pending(self.p,self.answer);review['items'][0].update(classification='needs_review',project_id='')
  raw='raw/assets/received/source.txt';path=self.k/raw;path.parent.mkdir(parents=True);path.write_bytes(Path(e['original']).read_bytes())
  lib=m.load(self.k/'tracking/material_library.json');lib['assets'][m.digest(raw)]={'path':raw,'sha256':e['sha256'],'kind':'document','sensitive':True,'readable':False,'downloadable':False};m.save(self.k/'tracking/material_library.json',lib)
  m.apply_review(self.p,review);before=(self.k/'tracking/material_library.json').read_bytes();path.write_bytes(b'corrupted')
  with self.assertRaises(m.Failure):m.publish_references(self.p,review)
  self.assertEqual(before,(self.k/'tracking/material_library.json').read_bytes());self.assertEqual(e['status'],'needs_review')
 def test_knowledge_only_archive_has_library_card_and_original_links(self):
  self.stage();review=m.review_pending(self.p,self.answer);review['items'][0].update(classification='knowledge',project_id='')
  m.apply_review(self.p,review);m.publish_references(self.p,review)
  lib=m.load(self.k/'tracking/material_library.json');self.assertEqual(lib['files'][0]['category'],'可复用知识')
  self.assertEqual(lib['files'][0]['project_id'],'');self.assertEqual(self.p.receipt('completed')['archived_reference'],0)
 def test_history_customer_without_project_is_display_label_only(self):
  self.stage(name='客户乙历史讨论.txt');review=m.review_pending(self.p,self.answer)
  review['items'][0].update(classification='needs_review',project_id='')
  self.p.reference_customer_labels={'客户乙'}
  before=(self.k/'tracking/client_registry.md').read_bytes()
  m.apply_review(self.p,review);m.publish_references(self.p,review)
  card=m.load(self.k/'tracking/material_library.json')['files'][0]
  self.assertEqual(card['customer'],'客户乙');self.assertEqual(card['project_id'],'')
  self.assertEqual((self.k/'tracking/client_registry.md').read_bytes(),before)
 def test_history_backfill_never_replaces_current_summary(self):
  path=self.k/'projects/项目甲.md'
  marker='<!-- communication-pipeline:start -->\n## 最近归档线索（不是项目综合判断）\n最新核实结论保留\n<!-- communication-pipeline:end -->\n'
  path.write_text(path.read_text()+marker)
  e=self.stage();e['channel']='wechat_history'
  review=m.review_pending(self.p,self.answer);review['items'][0]['next_action']=''
  m.apply_review(self.p,review)
  self.assertIn(marker,path.read_text());self.assertIn('历史沟通回补',path.read_text())
  note=next((self.k/'raw/transcripts/自动沟通归档').glob('*/*_沟通整理.md')).read_text()
  self.assertIn('历史脉络索引',note);self.assertIn('不表示今天发生',note)
  project=m.project_catalog(self.k,self.s)[0]
  self.assertEqual(project['latest_evidence_date'],'2026-09-11')
 def test_history_customer_display_fix_is_transactional_and_preserves_current_marker(self):
  path=self.k/'projects/项目甲.md'
  marker='<!-- communication-pipeline:start -->\n最新判断不变\n<!-- communication-pipeline:end -->'
  path.write_text(path.read_text().replace('**客户**：[[客户甲]]','关联：[[客户甲]]')+marker)
  before=path.read_bytes();e=self.stage();e['channel']='wechat_history'
  review=m.review_pending(self.p,self.answer);review['projects'][0]['customer']='客户甲'
  self.p.history_customer_labels={self.pid:{'label':'客户甲','marker':'[[客户甲]]'}}
  self.assertEqual(path.read_bytes(),before)
  m.apply_review(self.p,review)
  self.assertIn('**客户**：[[客户甲]]',path.read_text());self.assertIn(marker,path.read_text())
  self.assertEqual(m.project_catalog(self.k,self.s)[0]['customer'],'客户甲')
  self.assertEqual((self.k/'tracking/client_registry.md').read_text(),'正式状态不能变')
  plans=list((self.p.root/'transactions').glob('*/plan.json'))
  self.assertTrue(any('projects/项目甲.md'==o['path'] for x in plans for o in m.load(x)['ops']))

 def test_ignored_wechat_stays_in_private_intake_not_sales_knowledge(self):
  e=self.stage('业务日期：2026-09-11\n私人闲聊原文');e['channel']='wechat'
  def ignore(packet,cfg):
   return {'items':[{'source_id':s['source_id'],'project_id':'','classification':'ignore','summary':'无业务增量','business_date':s['business_date'],'date_quote':'','next_action':'','uncertainties':[],'evidence':[{'quote':'私人闲聊原文','level':'unverified','meaning':'略过'}]} for s in packet['sources']]}
  review=m.review_pending(self.p,ignore);m.apply_review(self.p,review)
  self.assertTrue(Path(e['original']).exists());self.assertEqual(e['status'],'ignored')
  self.assertFalse(any('私人闲聊原文' in path.read_text() for path in self.k.rglob('*') if path.is_file()))
 def test_uncommitted_reference_cannot_be_marked_archived(self):
  e=self.stage();review=m.review_pending(self.p,self.answer);review['items'][0].update(classification='needs_review',project_id='')
  m.publish_references(self.p,review)
  self.assertEqual(e['status'],'ready_for_review');self.assertEqual(m.load(self.k/'tracking/material_library.json')['files'],[])
 def test_recovery_preserves_refresh_queue(self):
  self.stage();review=m.review_pending(self.p,self.answer);m.apply_review(self.p,review)
  folder=next((self.p.root/'transactions').iterdir());(folder/'finalized.json').unlink();(self.p.root/'refresh_pending.json').unlink()
  m.recover(self.p);self.assertEqual(m.load(self.p.root/'refresh_pending.json'),[self.pid])
 def test_selected_recovery_leaves_unrelated_transactions_untouched(self):
  target=self.stage();review=m.review_pending(self.p,self.answer);m.apply_review(self.p,review)
  folder=next((self.p.root/'transactions').iterdir());(folder/'finalized.json').unlink();(self.p.root/'refresh_pending.json').unlink()
  unrelated=self.p.root/'transactions'/'unrelated';unrelated.mkdir();m.save(unrelated/'plan.json',{'material_ids':['f'*64],'ops':[{'path':'invalid'}],'projects':['unrelated'],'statuses':{}})
  self.assertEqual(m.recover(self.p,material_ids=[target['id']]),[self.pid])
  self.assertFalse((unrelated/'finalized.json').exists());self.assertEqual(m.load(self.p.root/'refresh_pending.json'),[self.pid])
 def test_selected_recovery_preflights_mixed_transactions_before_any_write(self):
  target=self.stage();other=self.stage('另一份：客户要求复验订单导出。','乙.txt')
  review=m.review_pending(self.p,self.answer,material_ids=[target['id']]);m.apply_review(self.p,review)
  folder=next((self.p.root/'transactions').iterdir());(folder/'finalized.json').unlink();(self.p.root/'refresh_pending.json').unlink()
  mixed=self.p.root/'transactions'/'zz-mixed';mixed.mkdir()
  m.save(mixed/'plan.json',{'statuses':{target['id']:'archived',other['id']:'archived'},'projects':[self.pid],'ops':[]})
  before={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
  with patch.object(m,'execute_transaction',wraps=m.execute_transaction) as replay:
   with self.assertRaisesRegex(m.Failure,'包含其他材料'):m.recover(self.p,material_ids=[target['id']])
   replay.assert_not_called()
  self.assertEqual({str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()},before)
  self.assertEqual(self.p.ledger['items'][other['id']]['status'],'ready_for_review')
 def test_shared_strings_are_values_not_indexes(self):
  import io,zipfile
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:
   z.writestr('xl/sharedStrings.xml','<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>报价待核</t></si></sst>')
   z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="B1"><f>91*2000</f><v>182000</v></c></row></sheetData></worksheet>')
  text,limits=m.extract(Path('报价.xlsx'),b.getvalue(),{})
  self.assertIn('A1：报价待核',text);self.assertIn('B1：182000',text);self.assertIn('91*2000',text);self.assertNotIn('A1：0',text)
 def test_transaction_rejects_symlink(self):
  folder=self.root/'tx';folder.mkdir();(folder/'x.after').write_bytes(b'x');outside=self.root/'outside';outside.write_bytes(b'original');(self.k/'evil').symlink_to(outside)
  m.save(folder/'plan.json',{'projects':[],'ops':[{'path':'evil','before':m.digest(b'original'),'after':m.digest(b'x'),'payload':'x.after'}]})
  with self.assertRaises(m.Failure):m.execute_transaction(folder,self.k)
  self.assertEqual(outside.read_bytes(),b'original')
 def test_incremental_document_includes_every_changed_range(self):
  text='业务日期：2026-09-11\n'+'\n'.join(f'原文行{i}：订单、接口、交付背景保持不变。' for i in range(2000))
  first=self.stage(text,'周报.txt');self.p.ledger['items'][first['id']]['status']='archived'
  newer=text.replace('原文行200：','进度改为48%：').replace('原文行1800：','接口仍待联调：');second=self.stage(newer,'周报.txt')
  selected,scope=m.review_input(self.p,second)
  self.assertIn('进度改为48%',selected);self.assertIn('接口仍待联调',selected);self.assertLess(len(selected),len(newer)/2);self.assertEqual(len(scope['changes']),2)
 def test_refresh_requires_ready_and_non_stale(self):
  m.save(self.p.root/'refresh_pending.json',[self.pid])
  responses=iter([{'state':'ready','stale':True},{'started':True},{'state':'running','stale':True},{'state':'ready','stale':False}])
  with patch.object(m,'api',side_effect=lambda *a:next(responses)),patch.object(m.time,'sleep'):
   self.assertEqual(m.refresh(self.p,[self.pid]),[self.pid])
  self.assertEqual(m.load(self.p.root/'refresh_pending.json'),[])
 def test_queued_analysis_is_polled_without_resubmitting(self):
  m.save(self.p.root/'refresh_pending.json',[self.pid])
  replies=iter([{'state':'stale'}, {'accepted':True,'queued':True}, {'state':'queued'}, {'state':'queued'}, {'state':'running'}, {'state':'ready','stale':False}])
  with patch.object(m,'api',side_effect=lambda *a:next(replies)) as api,patch.object(m.time,'sleep'):
   self.assertEqual(m.refresh(self.p,[self.pid]),[self.pid])
  self.assertEqual(sum(len(c.args)>2 for c in api.call_args_list),1)

 def test_failed_project_refresh_retries_without_rerunning_archive(self):
  m.save(self.p.root/'refresh_pending.json',[self.pid])
  replies=iter([{'state':'ready','stale':True},{'started':True},{'state':'error','error':'temporary'},{'started':True},{'state':'ready','stale':False}])
  with patch.object(m,'api',side_effect=lambda *a:next(replies)),patch.object(m.time,'sleep'):
   self.assertEqual(m.refresh(self.p,[self.pid]),[self.pid])
  self.assertFalse(self.p.gaps)
 def test_refresh_follows_existing_transitive_dependencies_without_new_analysis(self):
  projects=[{'id':'a','source_path':'a.md'},
            {'id':'b','source_path':'b.md','sources':[{'path':'a.md'}]},
            {'id':'c','source_path':'c.md','sources':[{'path':'b.md'}]},
            {'id':'unanalysed','source_path':'new.md','sources':[{'path':'a.md'}]},
            {'id':'unrelated','source_path':'other.md'}]
  with patch('project_workspace.build_projects',return_value=projects),patch('project_analysis.read_cache',side_effect=lambda state,pid:{'result':{ 'summary':'existing'}} if pid!='unanalysed' else {}),patch.object(m,'api',return_value={'state':'ready','stale':False}) as api:
   self.assertEqual(m.refresh(self.p,['a']),['a','b','c'])
  self.assertEqual(api.call_count,3);self.assertEqual(m.load(self.p.root/'refresh_pending.json'),[])
 def test_selected_refresh_keeps_unrelated_pending_project_without_processing_it(self):
  m.save(self.p.root/'refresh_pending.json',['unrelated',self.pid])
  (self.k/'tools').mkdir();(self.k/'tools/update_sales_workbench.sh').write_text('exit 99\n')
  with patch.object(m,'api',return_value={'state':'ready','stale':False}) as api,patch.object(m.subprocess,'run',side_effect=AssertionError('scoped retry must not run full legacy export')):
   self.assertEqual(m.refresh(self.p,[self.pid],include_pending=False),[self.pid])
  self.assertEqual(api.call_count,1);self.assertIn(self.pid,api.call_args.args[1]);self.assertEqual(m.load(self.p.root/'refresh_pending.json'),['unrelated'])
  self.assertEqual(self.p.refresh_total,1);self.assertEqual(self.p.refresh_done,1)
 def test_daily_report_does_not_generate_project_actions(self):
  self.stage(name='项目群日报.txt');before=(self.k/'projects/项目甲.md').read_bytes();review=m.review_pending(self.p,self.answer)
  self.assertEqual(m.apply_review(self.p,review),[]);self.assertEqual((self.k/'projects/项目甲.md').read_bytes(),before)
  lib=m.load(self.k/'tracking/material_library.json');self.assertEqual(lib['files'][0]['project_id'],self.pid);self.assertEqual(lib['files'][0]['category'],'只读项目动态')
  note=next((self.k/'raw').rglob('*_项目动态.md')).read_text();self.assertNotIn('协调复验安排',note)
 def test_incremental_snippet_cannot_replace_whole_project_judgement(self):
  self.stage();review=m.review_pending(self.p,self.answer);m.apply_review(self.p,review)
  body=(self.k/'projects/项目甲.md').read_text()
  generated=body.split('<!-- communication-pipeline:start -->')[1].split('<!-- communication-pipeline:end -->')[0]
  self.assertNotIn('## 当前判断',generated);self.assertNotIn('## 下一步',generated)
  self.assertIn('全部历史和新材料共同生成',generated);self.assertIn('历史判断保留',body)
 def test_cli_dates_accept_text_and_epoch(self):
  self.assertEqual(m.timestamp_date('2026-09-11 13:17'),'2026-09-11')
  self.assertEqual(m.timestamp_date('2026-09-11T23:00:00Z'),'2026-09-12')
  self.assertEqual(m.timestamp_date('invalid'),'')
 def test_authorized_chat_message_is_collected(self):
  self.p.auth={'user':True};self.p.cfg.update(chats=[{'chat_id':'oc_test','name':'项目甲'}],search_minutes=False)
  def call(args,who):
   return {'data':{'chats':[],'has_more':False}} if '+chat-list' in args else {'data':{'messages':[{'message_id':'om_test','create_time':'2026-09-11 13:17','msg_type':'text','content':'客户要求复验订单导出。'}],'has_more':False}}
  with patch.object(self.p,'feishu_call',side_effect=call):self.p.feishu()
  self.assertEqual(len(self.p.ledger['items']),1);self.assertEqual(next(iter(self.p.ledger['items'].values()))['business_date'],'2026-09-11')
 def test_reply_context_retains_old_date_and_rejects_other_chat(self):
  msg={'message_id':'new','chat_id':'chat','reply_to':'old'}
  parent={'message_id':'old','chat_id':'chat','create_time':'2026-09-10 12:00','body':{'content':json.dumps({'text':'<p>原范围：仅同步发货</p>'})}}
  with patch.object(self.p,'feishu_call',return_value={'data':{'items':[parent]}}):result=self.p.reply_context(msg,'user')
  self.assertEqual(result[0]['business_date'],'2026-09-10');self.assertTrue(result[0]['reference_only']);self.assertEqual(result[0]['text'],'原范围：仅同步发货')
  parent['chat_id']='other'
  with patch.object(self.p,'feishu_call',return_value={'data':{'items':[parent]}}):self.assertEqual(self.p.reply_context(msg,'user'),[])
  self.assertTrue(self.p.gaps)
 def test_reply_context_stops_at_cycle(self):
  msg={'message_id':'new','chat_id':'chat','reply_to':'old'}
  parent={'message_id':'old','chat_id':'chat','parent_id':'new','create_time':'2026-09-10 12:00','body':{'content':'{"text":"旧范围"}'}}
  with patch.object(self.p,'feishu_call',return_value={'data':{'items':[parent]}}) as call:
   self.assertEqual(len(self.p.reply_context(msg,'user')),1);self.assertEqual(call.call_count,1)
 def test_participated_minutes_nested_link(self):
  self.p.auth={'user':True};link='https://example.feishu.cn/minutes/obcnexample'
  def call(args,who):
   if '+chat-list' in args:return {'data':{'chats':[],'has_more':False}}
   return {'data':{'items':[{'meta_data':{'app_link':link}}],'has_more':False}}
  with patch.object(self.p,'feishu_call',side_effect=call),patch.object(self.p,'document') as read:
   self.p.feishu();read.assert_called_once_with(link,['user'])
if __name__=='__main__':unittest.main()
