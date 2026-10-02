import json
import subprocess
import tempfile
import threading
import time
import unittest
from datetime import date, timedelta
import hashlib
from pathlib import Path
from unittest.mock import patch
import project_analysis as ai
import project_rounds
from project_workspace import build_projects

class AnalysisTests(unittest.TestCase):
    def test_packet_retains_all_local_versions_and_early_corrections(self):
        history=[]
        for i in range(1,10):
            record={field:'' for field in project_rounds.FIELDS}
            record.update(scenario='return',relationship='unknown',status='已收到反馈',feedback='同一反馈',action=f'动作{i}',due=f'2026-09-{i:02d}',saved_at=f'2026-09-{i:02d}T10:00:00+08:00')
            history.append({'revision':i,'record':record})
        path=self.s/'project_rounds'/f'{self.project}.json';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'project_id':self.project,'revision':9,'record':history[-1]['record'],'history':history}))
        corrections=[{'revision':i,'text':'原始范围' if i in (1,7) else f'补充{i}','date':f'2026-09-{i:02d}'} for i in range(1,10)]
        ai.write_cache(self.s,self.project,{'project_id':self.project,'correction':'补充9','correction_history':corrections,'result':None})
        context=ai.packet(self.project,'补充9',self.k,self.s)
        sources={row['path']:row for row in context['sources']}
        for i in range(1,9):
            self.assertIn(f'动作{i}',sources[f'local://round/history/{i}']['content'])
            self.assertIn(f'user://correction/{i}',sources)
        self.assertEqual(sources['local://round/history/1']['date'],'')
        self.assertIn('动作9',sources['local://round']['content'])
        self.assertNotIn('local://round/history/9',sources)
        self.assertEqual(sources['user://correction/1']['content'],'原始范围')
        self.assertEqual(sources['user://correction/7']['content'],'原始范围')

    def test_midnight_does_not_regenerate_but_new_evidence_still_does(self):
        ready=self.generate()
        tomorrow=date.today()+timedelta(days=1)
        with patch('project_analysis.date',wraps=date) as calendar:
            calendar.today.return_value=tomorrow
            current=ai.status(self.project,self.k,self.s)
            self.assertEqual(current['state'],'ready');self.assertFalse(current['stale'])
            with patch('project_analysis.run_model') as run:
                ai.sync_once(self.k,self.s);run.assert_not_called()
            self.source.write_text(self.source.read_text()+'\n客户补充：接口边界需要确认。')
            self.assertTrue(ai.status(self.project,self.k,self.s)['stale'])
            with patch('project_analysis.run_model',side_effect=self.response):
                self.assertTrue(ai.sync_once(self.k,self.s)['started'])
                refreshed=self.wait_finished()
            self.assertEqual(refreshed['state'],'ready')
            self.assertNotEqual(refreshed['result']['analysis_id'],ready['result']['analysis_id'])

    def test_legacy_date_hash_reused_only_with_identical_evidence_and_runtime(self):
        self.generate()
        with patch('project_analysis.evidence_fingerprint',wraps=ai.evidence_fingerprint) as compute:
            ai.packet(self.project,'',self.k,self.s)
            basis=compute.call_args.args[0]
        cache=ai.read_cache(self.s,self.project)
        legacy=hashlib.sha256(json.dumps(basis,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        cache['result']['fingerprint']=legacy
        ai.write_cache(self.s,self.project,cache)
        tomorrow=date.today()+timedelta(days=1)
        with patch('project_analysis.date',wraps=date) as calendar:
            calendar.today.return_value=tomorrow
            current=ai.status(self.project,self.k,self.s)
            self.assertEqual(current['state'],'ready')
            self.assertEqual(current['fingerprint'],legacy)
            self.assertEqual(ai.read_cache(self.s,self.project)['result'],cache['result'])
            with patch('project_analysis.settings',return_value={'model':'other-model','effort':'medium','provider':''}):
                self.assertTrue(ai.status(self.project,self.k,self.s)['stale'])
            refreshed=self.generate(force=True)
            self.assertEqual(refreshed['state'],'ready')
            self.assertNotEqual(refreshed['result']['fingerprint'],legacy)
            calendar.today.return_value=tomorrow+timedelta(days=1)
            self.assertFalse(ai.status(self.project,self.k,self.s)['stale'])
            self.source.write_text(self.source.read_text()+'\n真正新增的沟通。')
            self.assertTrue(ai.status(self.project,self.k,self.s)['stale'])

    def setUp(self):
        stopping=patch('project_analysis.STOPPING',threading.Event());stopping.start();self.addCleanup(stopping.stop)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.k=self.root/'knowledge';self.s=self.root/'state'
        (self.k/'projects').mkdir(parents=True)
        (self.k/'raw').mkdir()
        self.source=self.k/'projects'/'demo.md'
        self.source.write_text('# 测试项目\n客户 项目\n## 沟通反馈 '+date.today().isoformat()+'\n客户希望先核对范围。\n[[raw/reply]]\n')
        (self.k/'raw'/'reply.md').write_text('客户原话：请先核对范围，预算尚未确认。')
        self.project=build_projects(self.k,self.s)[0]['id']
        self.settings=patch('project_analysis.settings',return_value={'model':'test-model','effort':'medium','provider':''});self.settings.start();self.addCleanup(self.settings.stop)
    def response(self,context):
        source=context['sources'][0]
        evidence={'path':source['path'],'quote':source['content'].splitlines()[0]}
        story={'customer_goal':'核对业务范围','turning_point':'当前需要核对范围','internal_track':'内部准备','journey':[{'date':'','title':'客户提出问题','summary':'范围尚未核对','evidence':evidence}],'value_points':[{'title':'范围清晰','meaning':'围绕具体业务核对','evidence':evidence}],'conversation':{'goal':'核对范围','opening':'一起核对业务范围','questions':['核心业务是什么？'],'success_signal':'取得范围答复'}}
        understanding={'profile':{key:{'summary':'资料不足，待核实','evidence':[]} for key in ('business','users','stakeholders','systems')},'objective':{'summary':'核对业务范围','evidence':[evidence]},'scope_summary':'范围待核实，不能认定冻结','scope_status':'尚未冻结','requirements':[{'name':'范围确认','problem':'范围不清','scope':'范围待核实','owner':'业务负责人待核实','status':'待核实','evidence':[evidence]}],'evolution':[{'date':'','title':'首次范围讨论','change_type':'初始范围','previous':'此前范围未收录','current':'核对业务范围','reason':'需求待核实','impact':'需范围确认','confirmation':'待核实','evidence':[evidence]}],'lifecycle':[{'date':'','title':'业务起点','category':'业务起点','event':'核对业务范围','consequence':'范围待确认','confirmation':'待核实','evidence':[evidence]}],'interventions':[],'open_decisions':['范围尚未明确'],'coverage_note':'仅使用本项目材料'}
        understanding.update(commercial_baseline={'summary':'尚无已确认商业基线；未收录报价、签署及付款材料，待核实。','evidence':[]},scope_comparisons=[])
        return {'understanding':understanding,'story':story,'judgement':'需求范围仍需澄清','blocker':'预算未确认','next_action':'内部准备范围清单','role':'售前','draft':'请核对【范围清单】。','acceptance':'得到范围答复','uncertainties':['预算待核实'],'contact_boundary':'unknown','execution_signal':'unknown','control_evidence':[],'brief':{'stage':'需求澄清','attention':'需核实','situation':'范围待核对','blocker':'预算未确认','next_action':'内部准备范围清单','stage_reason':'客户要求先核对范围'},'evidence':[{'path':source['path'],'quote':source['content'].splitlines()[0]}]}
    def generate(self,**changes):
        with patch('project_analysis.run_model',side_effect=self.response):
            ai.start({'project_id':self.project,**changes},self.k,self.s)
            for _ in range(100):
                state=ai.status(self.project,self.k,self.s)
                if state['state']!='running':return state
                time.sleep(.005)
        self.fail('worker did not finish')
    def test_model_cache_and_stale_content_correction_history(self):
        ready=self.generate(correction='客户新补充：先澄清范围')
        self.assertEqual(ready['state'],'ready');self.assertFalse(ready['stale'])
        self.assertEqual(ai.status(self.project,self.k,self.s)['correction'], '客户新补充：先澄清范围')
        with patch('project_analysis.run_model') as run:
            self.assertEqual(ai.start({'project_id':self.project},self.k,self.s)['state'],'ready');run.assert_not_called()
        self.source.write_text(self.source.read_text()+'\n新材料：需要售前解释边界。')
        stale=ai.status(self.project,self.k,self.s)
        self.assertTrue(stale['stale']);self.assertEqual(stale['result']['analysis_id'],ready['result']['analysis_id'])
        latest=self.generate(correction='客户再次补充：预算暂停')
        self.assertEqual(len(latest['correction_history']),2)
        self.assertEqual(latest['correction_history'][0]['text'],'客户新补充：先澄清范围')
        self.assertEqual(latest['state'],'ready')
    def quick_payload(self,state,outcome='done',revision=0,request='receipt-request-00000001'):
        return {'project_id':self.project,'analysis_id':state['result']['analysis_id'],'revision':revision,'outcome':outcome,'request_id':request}
    def test_quick_done_is_execution_only_persisted_idempotent_and_undoable(self):
        state=self.generate();before=self.source.read_bytes();payload=self.quick_payload(state)
        saved=ai.quick_feedback(payload,self.k,self.s)
        self.assertEqual(saved['record']['status'],'本轮完成')
        self.assertIn('仅确认执行了该动作',saved['record']['feedback'])
        self.assertEqual(saved['record']['facts'],'')
        self.assertEqual(project_rounds.followups(self.k,self.s)['items'],[])
        self.assertEqual(ai.quick_feedback(payload,self.k,self.s)['revision'],1)
        self.assertEqual(project_rounds.read_round(self.project,self.k,self.s)['record'],saved['record'])
        self.assertTrue(ai.status(self.project,self.k,self.s)['stale'])
        undo=ai.quick_feedback(self.quick_payload(state,'undo',1,'receipt-request-00000002'),self.k,self.s)
        self.assertEqual(undo['record']['status'],'准备中')
        self.assertEqual(len(project_rounds.followups(self.k,self.s)['items']),1)
        self.assertEqual(self.source.read_bytes(),before)
    def test_quick_feedback_rejects_newer_source_or_other_project_analysis(self):
        state=self.generate();payload=self.quick_payload(state)
        payload['analysis_id']='another-project-analysis'
        with self.assertRaises(ValueError):ai.quick_feedback(payload,self.k,self.s)
        self.source.write_text(self.source.read_text()+'\n新增客户材料')
        with self.assertRaises(ValueError):ai.quick_feedback(self.quick_payload(state),self.k,self.s)
        self.assertEqual(project_rounds.read_round(self.project,self.k,self.s)['revision'],0)
    def test_quick_pending_keeps_one_action_and_optimistic_conflicts_fail(self):
        state=self.generate();saved=ai.quick_feedback(self.quick_payload(state,'pending'),self.k,self.s)
        self.assertEqual(saved['record']['status'],'准备中');self.assertEqual(saved['record']['due'],'')
        items=project_rounds.followups(self.k,self.s)['items']
        self.assertEqual(len(items),1);self.assertEqual(items[0]['action'],state['result']['analysis']['brief']['next_action'])
        with self.assertRaises(project_rounds.RevisionConflict):ai.quick_feedback(self.quick_payload(state,'done',0,'receipt-request-00000002'),self.k,self.s)
        with self.assertRaises(ValueError):ai.quick_feedback(self.quick_payload(state,'done'),self.k,self.s)
    def test_quick_feedback_respects_pause_and_undo_preserves_prior_fields(self):
        prior=project_rounds.save_round({'project_id':self.project,'revision':0,'scenario':'return','relationship':'unknown','status':'准备中','facts':'客户原话保留','action':'先前计划','due':'2026-10-01'},self.k,self.s)
        state=self.generate();ai.quick_feedback(self.quick_payload(state,'done',1),self.k,self.s)
        restored=ai.quick_feedback(self.quick_payload(state,'undo',2,'receipt-request-00000002'),self.k,self.s)
        for key in ('facts','action','due','status'):self.assertEqual(restored['record'][key],prior['record'][key])
        project_rounds.save_round({**restored['record'],'project_id':self.project,'revision':restored['revision'],'status':'暂停跟进','quick_outcome':'','quick_request_id':''},self.k,self.s)
        state=self.generate()
        with self.assertRaises(ValueError):ai.quick_feedback(self.quick_payload(state,'done',4,'receipt-request-00000003'),self.k,self.s)
    def test_story_requires_traceable_project_evidence_and_event_dates(self):
        context=ai.packet(self.project,'',self.k,self.s);story=self.response(context)['story']
        ai.validate_story(story,context['sources'])
        story['value_points'][0]['evidence']={'path':'another-project.md','quote':'客户已经接受'}
        with self.assertRaises(ValueError):ai.validate_story(story,context['sources'])
        story=self.response(context)['story'];story['journey'][0]['date']='2099-01-01'
        with self.assertRaises(ValueError):ai.validate_story(story,context['sources'])
    def test_old_brief_remains_readable_while_story_requires_fresh_analysis(self):
        self.generate();path=ai.cache_path(self.s,self.project);cache=json.loads(path.read_text())
        cache['result']['schema_version']=3;cache['result']['analysis'].pop('story');path.write_text(json.dumps(cache))
        self.assertIsNotNone(ai.read_cache(self.s,self.project)['result'])

    def test_date_retry_diagnostic_is_bound_to_the_cited_source(self):
        context=ai.packet(self.project,'',self.k,self.s)
        story=self.response(context)['story']
        source=context['sources'][0]
        source.update(date='',content=source['content'].replace(date.today().isoformat(),'')+'\n9月10日；2026-02-30；2099-01-01；2026-01-01')
        self.assertEqual(ai.supported_story_dates(source),['2026-01-01'])
        story['journey'][0]['date']='2026-01-02'
        with self.assertRaises(ValueError) as rejected:ai.validate_story(story,context['sources'])
        message=str(rejected.exception)
        for text in ('2026-01-02',source['path'],'2026-01-01','date须为空'):self.assertIn(text,message)
        story['journey'][0]['date']=''
        ai.validate_story(story,context['sources'])
    def test_story_quote_diagnostics_identify_item_and_source_without_echoing_content(self):
        context=ai.packet(self.project,'',self.k,self.s)
        source=context['sources'][0]
        other={'path':'raw/other.md','content':'只在另一来源出现的私密客户原话。'}
        sources=context['sources']+[other]
        cases=[
            ({'path':'raw/missing.md','quote':other['content']},'来源不在本次sources'),
            ({'path':source['path'],'quote':'  \n  '},'引用为空白'),
            ({'path':source['path'],'quote':other['content']},'引用不是该来源连续逐字原文'),
        ]
        for section in ('journey','value_points'):
            for evidence,reason in cases:
                with self.subTest(section=section,reason=reason):
                    story=self.response(context)['story']
                    story[section].append({**story[section][0],'evidence':evidence})
                    with self.assertRaises(ValueError) as rejected:ai.validate_story(story,sources)
                    message=str(rejected.exception)
                    for text in (section+'第2项',evidence['path'],'失败类型：'+reason):self.assertIn(text,message)
                    self.assertNotIn(other['content'],message)
                    self.assertNotIn(source['content'],message)
    def test_story_quote_keeps_exact_multiline_and_rejects_rewritten_or_joined_text(self):
        context=ai.packet(self.project,'',self.k,self.s)
        source=context['sources'][0]
        source['content']='客户：请先核对范围。\n预算尚未确认。\n只做内部评估。'
        for quote,valid in [
            ('客户：请先核对范围。\n预算尚未确认。',True),
            ('客户：请先核对范围。预算尚未确认。',False),
            ('客户：请先核对范围。\n只做内部评估。',False),
            ('客户:请先核对范围。',False),
        ]:
            with self.subTest(quote=quote):
                story=self.response(context)['story']
                story['journey'][0]['evidence']={'path':source['path'],'quote':quote}
                if valid:ai.validate_story(story,context['sources'])
                else:
                    with self.assertRaisesRegex(ValueError,'journey第1项.*连续逐字原文'):ai.validate_story(story,context['sources'])
    def test_reply_date_and_future_payment_deadline_keep_existing_date_guard(self):
        context=ai.packet(self.project,'',self.k,self.s)
        source=context['sources'][0]
        source.update(date='2026-08-21',content='双方于2026年8月31日前完成正式合同签署，我司于2026年9月30日前支付全部合同款项。')
        story=self.response(context)['story']
        with patch('project_analysis.date',wraps=date) as calendar:
            calendar.today.return_value=date(2026,9,20)
            story['journey'][0]['date']='2026-08-21'
            ai.validate_story(story,context['sources'])
            story['journey'][0]['date']='2026-09-30'
            with self.assertRaisesRegex(ValueError,'日期没有本项目来源支持'):ai.validate_story(story,context['sources'])
            source['date']='';story['journey'][0]['date']=''
            self.assertEqual(ai.supported_story_dates(source),[])
            ai.validate_story(story,context['sources'])
    def test_model_receives_date_role_rules_for_all_text_fields(self):
        context=ai.packet(self.project,'',self.k,self.s)
        expected=self.response(context)
        submitted=[]
        with patch('project_analysis.subprocess.Popen') as factory,patch('project_analysis.isolated_skills_config',return_value='skills.config=[]'):
            proc=factory.return_value;proc.returncode=0
            def communicate(prompt=None,timeout=None):
                submitted.append(prompt)
                command=factory.call_args.args[0]
                Path(command[command.index('-o')+1]).write_text(json.dumps(expected))
                return ('{"type":"turn.completed"}', '')
            proc.communicate.side_effect=communicate
            ai.run_model(context)
        instructions=submitted[0].split('\nINPUT:\n',1)[0]
        for rule in ('所有输出字段（brief、story、judgement、uncertainties、draft等）',
                     '消息/沟通发生日期、约定期限和实际履行日期',
                     '未来期限不能写成已发生事件','期限已过也不能推定已经履行',
                     '8月21日回邮约定9月30日前付款；实际签署/到账待核实',
                     '不能写“9月30日回邮”','付款承诺、开票和CRM计划均不等于实际到账'):
            self.assertIn(rule,instructions)
    def test_long_communication_keeps_middle_strategy_in_model_context(self):
        body=self.source.read_text()+'\n'+('原有技术背景。'*1300)+'\n关键策略：行业资源协同与老板价值沟通。\n'+('后续技术问题。'*1300)
        self.source.write_text(body)
        context=ai.packet(self.project,'',self.k,self.s)
        own=next(s for s in context['sources'] if s['path']=='projects/demo.md')
        self.assertIn('关键策略：行业资源协同与老板价值沟通。',own['content'])
        self.assertFalse(own['truncated'])

    def test_same_date_input_order_does_not_invalidate_evidence(self):
        project=next(p for p in build_projects(self.k,self.s) if p['id']==self.project)
        supplements=[]
        for name in ('a.txt','b.txt'):
            (self.k/'raw'/name).write_text('客户本次讨论：'+name)
            supplements.append({'path':'raw/'+name,'evidence_date':'','exists':True,'readable':True,'relation':'cited_attachment'})
        with patch('project_analysis.project_source_context.supplement_sources',return_value=supplements):
            first=ai.packet(self.project,'',self.k,self.s,project)
        reversed_project={**project,'sources':list(reversed(project['sources']))}
        with patch('project_analysis.project_source_context.supplement_sources',return_value=list(reversed(supplements))):
            reordered=ai.packet(self.project,'',self.k,self.s,reversed_project)
        self.assertEqual(first['fingerprint'],reordered['fingerprint'])
        self.assertEqual(first['sources'],reordered['sources'])
        (self.k/'raw'/'b.txt').write_text('客户改变实际范围。')
        with patch('project_analysis.project_source_context.supplement_sources',return_value=supplements):
            changed=ai.packet(self.project,'',self.k,self.s,project)
        self.assertNotEqual(first['fingerprint'],changed['fingerprint'])

    def test_explicit_source_also_named_in_body_keeps_single_identity_and_relation(self):
        (self.k/'raw'/'contract.txt').write_text('客户只认可文本，签署证据未收录。')
        self.source.write_text(self.source.read_text()+'\n[[raw/contract.txt]]\n参照 `raw/contract.txt`。\n')
        context=ai.packet(self.project,'',self.k,self.s)
        matching=[s for s in context['sources'] if s['path']=='raw/contract.txt']
        self.assertEqual(len(matching),1)
        self.assertEqual(matching[0]['relation'],'explicit_evidence')
    def test_story_cannot_bypass_saved_contact_boundary(self):
        context=ai.packet(self.project,'',self.k,self.s);original=self.response(context)
        guarded=ai.guarded(original,{'relationship':'no_contact'})
        self.assertEqual(guarded['draft'],'')
        self.assertIn('不生成主动联系话术',guarded['story']['conversation']['opening'])
        self.assertNotEqual(original['story']['conversation'],guarded['story']['conversation'])
    def test_evidence_schema_and_cache_corruption_fail_closed(self):
        context=ai.packet(self.project,'',self.k,self.s)
        bad=self.response(context);bad['evidence'][0]['quote']='未提供过的伪造原话'
        with self.assertRaises(ValueError):ai.validate_result(bad,context['sources'])
        self.generate();path=ai.cache_path(self.s,self.project);original=json.loads(path.read_text())
        for key,value in [('analysis',{'judgement':'broken'}),('created_at',123),('source_snapshot',None),('round_revision',True)]:
            corrupt=json.loads(json.dumps(original));corrupt['result'][key]=value;path.write_text(json.dumps(corrupt))
            with self.subTest(key=key),self.assertRaises(ValueError):ai.status(self.project,self.k,self.s)
            before=path.read_bytes()
            with self.assertRaises(ValueError):ai.start({'project_id':self.project},self.k,self.s)
            self.assertEqual(before,path.read_bytes())
    def test_failure_keeps_old_result_and_forbids_adoption(self):
        first=self.generate()
        with patch('project_analysis.run_model',side_effect=ValueError('模型失败')):
            ai.start({'project_id':self.project,'force':True,'correction':'新补充保留'},self.k,self.s)
            for _ in range(100):
                state=ai.status(self.project,self.k,self.s)
                if state['state']!='running':break
                time.sleep(.005)
        self.assertEqual(state['state'],'queued');self.assertEqual(state['correction'],'新补充保留')
        self.assertIn('模型失败',state['error'])
        self.assertEqual(state['result']['analysis_id'],first['result']['analysis_id'])
        with self.assertRaises(ValueError):ai.adopt({'project_id':self.project,'analysis_id':first['result']['analysis_id'],'revision':0},self.k,self.s)
    def test_single_flight_retains_submitted_input(self):
        entered=threading.Event();release=threading.Event()
        def slow(context):entered.set();release.wait(2);return self.response(context)
        with patch('project_analysis.run_model',side_effect=slow):
            ai.start({'project_id':self.project,'correction':'A'},self.k,self.s);entered.wait(1)
            queued=ai.start({'project_id':self.project,'correction':'B'},self.k,self.s)
            self.assertTrue(queued['accepted']);self.assertTrue(queued['queued']);self.assertEqual(queued['correction'],'B')
            release.set()
            # A queued replacement is accepted before the first worker exits.
            # Keep the model stub alive until both requests have completed.
            for _ in range(1000):
                cache=ai.read_cache(self.s,self.project)
                if len(cache.get('requests',[]))>=2 and all(r['status']=='complete' for r in cache['requests']):break
                time.sleep(.005)
            else:self.fail('Queued input did not finish in the isolated worker')
            self.assertEqual(ai.read_cache(self.s,self.project)['correction'],'B')
    def test_adopt_is_plan_not_completed_action_or_business_fact(self):
        source_before=self.source.read_bytes()
        project_rounds.save_round({'project_id':self.project,'revision':0,'scenario':'return','relationship':'unknown','status':'本轮完成','facts':'原事实','feedback':'上轮已反馈'},self.k,self.s)
        state=self.generate()
        saved=ai.adopt({'project_id':self.project,'analysis_id':state['result']['analysis_id'],'revision':1},self.k,self.s)
        self.assertEqual(saved['record']['status'],'准备中');self.assertEqual(saved['record']['facts'],'原事实')
        self.assertEqual(saved['record']['feedback'],'');self.assertEqual(self.source.read_bytes(),source_before)
        self.assertEqual(saved['history'][0]['record']['feedback'],'上轮已反馈')
        self.assertEqual(saved['record']['analysis_id'],state['result']['analysis_id'])
        with self.assertRaisesRegex(ValueError, '实际反馈'):
            project_rounds.save_round({**saved['record'],'project_id':self.project,'revision':2,'status':'本轮完成'},self.k,self.s)
        self.assertTrue(any('上轮已反馈' in source['content'] for source in ai.packet(self.project,'',self.k,self.s)['sources']))
        with self.assertRaises(ValueError):ai.adopt({'project_id':self.project,'analysis_id':state['result']['analysis_id'],'revision':2},self.k,self.s)
    def test_adopting_preparation_keeps_explicit_pause_out_of_followups(self):
        project_rounds.save_round({'project_id':self.project,'revision':0,'scenario':'return','relationship':'budget','status':'暂停跟进','facts':'预算暂停'},self.k,self.s)
        state=self.generate()
        saved=ai.adopt({'project_id':self.project,'analysis_id':state['result']['analysis_id'],'revision':1},self.k,self.s)
        self.assertEqual(saved['record']['status'],'暂停跟进')
        self.assertEqual(project_rounds.followups(self.k,self.s)['items'],[])

    def test_model_cannot_override_no_contact_or_waiting(self):
        for local in ({'relationship':'no_contact'},{'status':'已发出等待反馈'}):
            guarded=ai.guarded(self.response(ai.packet(self.project,'',self.k,self.s)),local)
            self.assertEqual(guarded['draft'],'');self.assertTrue(guarded['guard'])
    def test_brief_limits_enum_and_legacy_compatibility(self):
        context=ai.packet(self.project,'',self.k,self.s)
        for key,value in [('stage','已成交'),('attention','赢单'),('situation','字'*61),('blocker','字'*46),('next_action','字'*61),('stage_reason','字'*101)]:
            result=self.response(context);result['brief'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):ai.validate_result(result,context['sources'])
        result=self.response(context);result.pop('brief')
        ai.validate_result(result,context['sources'],allow_legacy=True)
        with self.assertRaises(ValueError):ai.validate_result(result,context['sources'])
    def test_overview_read_does_not_infer_and_uses_current_counts(self):
        self.generate()
        with patch('project_analysis.run_model') as run:
            result=ai.overview(self.k,self.s)
            self.assertEqual(result['projects'][0]['brief']['stage'],'需求澄清')
            self.assertEqual(result['projects'][0]['analysis_state'],'ready');run.assert_not_called()

    def test_cache_project_swap_rejected(self):
        self.generate()
        (self.k/'projects'/'other.md').write_text('# 另一个项目\n客户 项目')
        other=next(p['id'] for p in build_projects(self.k,self.s) if p['title']=='另一个项目')
        ai.cache_path(self.s,other).write_bytes(ai.cache_path(self.s,self.project).read_bytes())
        with self.assertRaises(ValueError):ai.status(other,self.k,self.s)
    def test_control_proposal_requires_user_evidence_and_adopts_local_pause(self):
        def no_contact(context):
            value=self.response(context)
            value.update(contact_boundary='no_contact',control_evidence=[{'path':'user://correction','quote':'客户明确要求暂勿联系'}])
            return value
        with patch.object(self,'response',side_effect=no_contact):
            pass
        original=self.response
        def proposed(context):
            value=original(context);value.update(contact_boundary='no_contact',control_evidence=[{'path':'user://correction','quote':'客户明确要求暂勿联系'}]);return value
        self.response=proposed
        ready=self.generate(correction='客户明确要求暂勿联系')
        self.assertEqual(ready['result']['analysis']['draft'],'')
        saved=ai.adopt({'project_id':self.project,'analysis_id':ready['result']['analysis_id'],'revision':0},self.k,self.s)
        self.assertEqual(saved['record']['relationship'],'no_contact');self.assertEqual(saved['record']['status'],'暂停跟进')
        bad=original(ai.packet(self.project,'',self.k,self.s));bad.update(contact_boundary='no_contact',control_evidence=[bad['evidence'][0]])
        with self.assertRaises(ValueError):ai.validate_result(bad,ai.packet(self.project,'',self.k,self.s)['sources'])
    def test_correction_date_preserves_original_day(self):
        self.generate(correction='昨天的客户反馈')
        path=ai.cache_path(self.s,self.project);cache=json.loads(path.read_text());cache['correction_history'][0]['date']='2026-08-28';path.write_text(json.dumps(cache))
        context=ai.packet(self.project,'昨天的客户反馈',self.k,self.s)
        source = next(s for s in context['sources'] if s['path']=='user://correction')
        self.assertEqual(source['recorded_at'], '2026-08-28')
        self.assertEqual(source['date'], '')

    def test_ultra_continues_after_fifteen_minutes_with_same_model(self):
        context=ai.packet(self.project,'',self.k,self.s)
        context['config']['effort']='ultra'
        expected=self.response(context)
        updates=[];context['_progress']=updates.append
        with patch('project_analysis.subprocess.Popen') as factory, patch('project_analysis.os.killpg') as kill, patch('project_analysis.time.monotonic',side_effect=[0,0,910,910,920]):
            proc=factory.return_value;proc.pid=321;proc.returncode=0
            def communicate(prompt=None,timeout=None):
                if prompt is not None:raise subprocess.TimeoutExpired('codex',30,output=b'{"type":"turn.started"}\n')
                command=factory.call_args.args[0]
                Path(command[command.index('-o')+1]).write_text(json.dumps(expected))
                return ('{"type":"turn.completed"}', '')
            proc.communicate.side_effect=communicate
            self.assertEqual(ai.run_model(context)['judgement'],expected['judgement'])
            kill.assert_not_called()
            command=factory.call_args.args[0]
            self.assertEqual(command[command.index('-m')+1],'test-model')
            self.assertIn('model_reasoning_effort="ultra"',command)
            self.assertTrue(any(p.get('elapsed_seconds')==910 for p in updates))

    def test_runtime_disables_tools_and_kills_timeout_group(self):
        context=ai.packet(self.project,'',self.k,self.s)
        with patch('project_analysis.subprocess.Popen') as factory,patch('project_analysis.os.killpg') as kill,patch('project_analysis.time.monotonic',side_effect=[0,0,301]):
            proc=factory.return_value;proc.pid=123;proc.communicate.side_effect=[subprocess.TimeoutExpired('codex',30),('', '')]
            with self.assertRaisesRegex(ValueError,'时限'):ai.run_model(context)
            command=factory.call_args.args[0]
            self.assertIn('--ignore-user-config',command);self.assertIn('shell_tool',command);self.assertIn('unified_exec',command);self.assertIn('web_search="disabled"',command)
            for feature in ('plugins','apps','skill_search'):self.assertIn(feature,command)
            self.assertTrue(any(arg.startswith('skills.config=[') for arg in command))
            self.assertTrue(factory.call_args.kwargs['start_new_session']);kill.assert_called_once()

    def wait_finished(self):
        for _ in range(200):
            value=ai.status(self.project,self.k,self.s)
            if value['state']!='running':return value
            time.sleep(.005)
        self.fail('worker stuck')

    def test_runtime_warning_is_not_a_network_failure(self):
        event={'type':'item.completed','item':{'type':'error','message':'Skill descriptions were shortened to fit the skills context budget.'}}
        progress=ai.inference_events(json.dumps(event))
        self.assertEqual(progress['inference_errors'],[])
        self.assertEqual(progress['runtime_warnings'],['skills_context_truncated'])
        self.assertEqual(progress['phase'],'模型处理中')
        event['item']['message']='Under-development features enabled: respect_system_proxy.'
        progress=ai.inference_events(json.dumps(event))
        self.assertEqual(progress['inference_errors'],[])
        self.assertEqual(progress['runtime_warnings'],['experimental_runtime_feature'])
        event['item']['message']='Reconnecting after HTTP 429. Bearer secret-test-data'
        progress=ai.inference_events(json.dumps(event))
        self.assertEqual(progress['inference_errors'][0]['http_codes'],['429'])
        self.assertNotIn('secret-test-data',json.dumps(progress))

    def test_skill_isolation_only_builds_per_invocation_overrides(self):
        skill=self.root/'skills'/'example'/'SKILL.md';skill.parent.mkdir(parents=True)
        skill.write_text('original skill remains installed')
        config=ai.isolated_skills_config([self.root/'skills'])
        self.assertIn(str(skill),config);self.assertIn('enabled=false',config)
        self.assertEqual(skill.read_text(),'original skill remains installed')

    def test_background_detects_external_archive_without_browser(self):
        original=self.generate()
        self.source.write_text(self.source.read_text()+'\n现场沟通新增：保留OA。')
        with patch('project_analysis.run_model',side_effect=self.response):
            self.assertTrue(ai.sync_once(self.k,self.s)['started'])
            value=self.wait_finished()
        self.assertEqual(value['state'],'ready');self.assertFalse(value['stale'])
        self.assertNotEqual(value['result']['analysis_id'],original['result']['analysis_id'])
        self.assertIn('现场沟通新增',json.dumps(ai.read_cache(self.s,self.project)['result']['source_snapshot'],ensure_ascii=False))
        with patch('project_analysis.run_model') as run:
            ai.sync_once(self.k,self.s);run.assert_not_called()

    def test_background_retry_survives_restart_and_is_bounded_per_source(self):
        self.generate();self.source.write_text(self.source.read_text()+'\n新内容')
        with patch('project_analysis.run_model',side_effect=ValueError('模型超时')),patch('project_analysis.SYNC_RETRY_SECONDS',0):
            ai.sync_once(self.k,self.s);first=self.wait_finished()
            self.assertEqual(first['sync']['attempt'],1)
            ai.JOBS.pop((str(self.s),self.project),None)
            ai.sync_once(self.k,self.s);second=self.wait_finished()
            self.assertEqual(second['sync']['attempt'],2)
            self.assertEqual(second['sync']['status'],'failed')
            self.assertIsNone(ai.sync_once(self.k,self.s))
            self.assertEqual(first['result']['analysis_id'],second['result']['analysis_id'])
        self.source.write_text(self.source.read_text()+'\n再次补充')
        with patch('project_analysis.run_model',side_effect=self.response):
            ai.sync_once(self.k,self.s);ready=self.wait_finished()
            self.assertEqual(ready['state'],'ready');self.assertEqual(ready['sync']['attempt'],1)

    def test_change_during_analysis_gets_followup_analysis(self):
        self.generate();self.source.write_text(self.source.read_text()+'\n增量一')
        def change(context):
            self.source.write_text(self.source.read_text()+'\n增量二')
            return self.response(context)
        with patch('project_analysis.run_model',side_effect=change):
            ai.sync_once(self.k,self.s);self.assertTrue(self.wait_finished()['stale'])
        with patch('project_analysis.run_model',side_effect=self.response):
            ai.sync_once(self.k,self.s);self.assertFalse(self.wait_finished()['stale'])

    def test_successful_automatic_retry_receives_validation_feedback(self):
        self.generate();self.source.write_text(self.source.read_text()+'\n新材料')
        with patch('project_analysis.run_model',side_effect=ValueError('沟通节点日期没有本项目来源支持')),patch('project_analysis.SYNC_RETRY_SECONDS',0):
            ai.sync_once(self.k,self.s);self.wait_finished()
        def retry(context):
            self.assertIn('日期',context['_retry_error'])
            return self.response(context)
        with patch('project_analysis.run_model',side_effect=retry):
            ai.sync_once(self.k,self.s);ready=self.wait_finished()
            self.assertEqual(ready['state'],'ready');self.assertEqual(ready['sync']['attempt'],2)
    def test_quote_rejection_keeps_old_result_and_retries_with_specific_diagnostic(self):
        first=self.generate();self.source.write_text(self.source.read_text()+'\n客户补充新材料。')
        def reject(context):
            value=self.response(context)
            value['story']['value_points'][0]['evidence']={**value['story']['value_points'][0]['evidence'],'quote':'不能记录到诊断中的客户私密原话。'}
            return ai.validate_result(value,context['sources'])
        with patch('project_analysis.run_model',side_effect=reject),patch('project_analysis.SYNC_RETRY_SECONDS',0):
            ai.sync_once(self.k,self.s);failed=self.wait_finished()
        self.assertEqual(failed['result']['analysis_id'],first['result']['analysis_id'])
        self.assertEqual(failed['sync']['status'],'retrying')
        self.assertNotIn('客户私密原话',failed['error'])
        def retry(context):
            for text in ('value_points第1项','projects/demo.md','失败类型：引用不是该来源连续逐字原文'):
                self.assertIn(text,context['_retry_error'])
            return self.response(context)
        with patch('project_analysis.run_model',side_effect=retry):
            ai.sync_once(self.k,self.s);ready=self.wait_finished()
        self.assertEqual(ready['state'],'ready');self.assertEqual(ready['sync']['attempt'],2)
        self.assertNotEqual(ready['result']['analysis_id'],first['result']['analysis_id'])

    def test_graceful_restart_does_not_consume_an_attempt(self):
        self.generate();cache=ai.read_cache(self.s,self.project)
        cache['sync']={'status':'running','attempt':2,'fingerprint':'same'}
        ai.write_cache(self.s,self.project,cache)
        key=(str(self.s),self.project);ai.JOBS[key]={'running':True}
        try: ai.stop_processes();ai.stop_processes()
        finally: ai.JOBS.pop(key,None)
        sync=ai.read_cache(self.s,self.project)['sync']
        self.assertEqual(sync['attempt'],1);self.assertEqual(sync['status'],'interrupted')

    def test_stop_between_spawn_and_registration_cancels_late_process(self):
        context=ai.packet(self.project,'',self.k,self.s)
        spawned=threading.Event();release=threading.Event();errors=[]
        with patch('project_analysis.subprocess.Popen') as factory,patch('project_analysis.os.killpg') as kill,patch('project_analysis.isolated_skills_config',return_value='skills.config=[]'):
            proc=factory.return_value;proc.pid=124;proc.poll.return_value=None;proc.communicate.return_value=('', '')
            def spawn(*args,**kwargs):
                spawned.set();release.wait(5);return proc
            factory.side_effect=spawn
            def invoke():
                try:ai.invoke_model(context,'input',{})
                except Exception as exc:errors.append(exc)
            worker=threading.Thread(target=invoke);worker.start()
            try:
                self.assertTrue(spawned.wait(5));ai.stop_processes()
            finally:release.set();worker.join(5)
            self.assertFalse(worker.is_alive());self.assertEqual(len(errors),1)
            self.assertIn('中断',str(errors[0]));kill.assert_called_once_with(124,ai.signal.SIGKILL)
            self.assertNotIn(proc,ai.PROCESSES)
            with self.assertRaisesRegex(ValueError,'中断'):ai.invoke_model(context,'next batch',{})
            self.assertEqual(factory.call_count,1)
            with self.assertRaisesRegex(ValueError,'停止'):ai.start({'project_id':self.project},self.k,self.s)
            self.assertIsNone(ai.sync_once(self.k,self.s))

    def test_late_worker_success_and_progress_cannot_replace_interrupted_cache(self):
        original=self.generate();self.source.write_text(self.source.read_text()+'\n新范围待确认。')
        entered=threading.Event();release=threading.Event()
        def late(context):
            entered.set();release.wait(5)
            context['_progress']({'phase':'不能覆盖停止状态'})
            return self.response(context)
        with patch('project_analysis.run_model',side_effect=late):
            ai.start({'project_id':self.project},self.k,self.s)
            try:self.assertTrue(entered.wait(5));ai.stop_processes()
            finally:release.set()
            self.wait_finished()
        saved=ai.read_cache(self.s,self.project)
        self.assertEqual(saved['result']['analysis_id'],original['result']['analysis_id'])
        self.assertEqual(saved['sync']['status'],'interrupted')
        self.assertEqual(saved['sync']['phase'],'服务重启后继续')

    def test_stop_flag_and_cache_transition_do_not_exhaust_retry(self):
        self.generate();self.source.write_text(self.source.read_text()+'\n新材料。')
        cache=ai.read_cache(self.s,self.project)
        cache['sync']={'fingerprint':ai.packet(self.project,'',self.k,self.s)['fingerprint'],'attempt':1}
        ai.write_cache(self.s,self.project,cache)
        entered=threading.Event();flag_set=threading.Event();allow_stop=threading.Event();raised=threading.Event()
        real_set=ai.STOPPING.set
        def set_flag():
            real_set();flag_set.set();allow_stop.wait(5)
        def fail_during_stop(context):
            entered.set();flag_set.wait(5);raised.set()
            raise ValueError('本项目分析已中断，原结果保留')
        with patch('project_analysis.run_model',side_effect=fail_during_stop),patch.object(ai.STOPPING,'set',side_effect=set_flag):
            ai.start({'project_id':self.project,'_automatic':True},self.k,self.s)
            self.assertTrue(entered.wait(5))
            stopper=threading.Thread(target=ai.stop_processes);stopper.start()
            try:
                self.assertTrue(flag_set.wait(5));self.assertTrue(raised.wait(5))
                time.sleep(.02)  # Give the error path a chance to acquire LOCK.
            finally:allow_stop.set();stopper.join(5)
            self.wait_finished()
        saved=ai.read_cache(self.s,self.project)
        self.assertEqual(saved['sync']['status'],'interrupted');self.assertEqual(saved['sync']['attempt'],1)
        ai.STOPPING.clear()  # Simulate a fresh service process.
        with patch('project_analysis.run_model',side_effect=self.response):
            self.assertTrue(ai.sync_once(self.k,self.s)['started'])
            self.assertEqual(self.wait_finished()['state'],'ready')

    def test_cancel_one_project_does_not_stop_another_project(self):
        context=ai.packet(self.project,'',self.k,self.s)
        other=ai.packet(self.project,'',self.k,self.s)
        with patch('project_analysis.subprocess.Popen') as factory,patch('project_analysis.os.killpg') as kill,patch('project_analysis.isolated_skills_config',return_value='skills.config=[]'):
            proc=factory.return_value;proc.pid=125;proc.returncode=0
            def communicate(prompt=None,timeout=None):
                command=factory.call_args.args[0]
                Path(command[command.index('-o')+1]).write_text('{"ok":true}')
                return ('', '')
            proc.communicate.side_effect=communicate
            ai.cancel_inference(context)
            with self.assertRaisesRegex(ValueError,'中断'):ai.invoke_model(context,'input',{})
            self.assertEqual(ai.invoke_model(other,'other input',{}),{'ok':True})
            kill.assert_not_called();self.assertFalse(ai.STOPPING.is_set())

    def test_abrupt_restart_recovers_inflight_latest_source(self):
        self.generate();self.source.write_text(self.source.read_text()+'\n服务退出期间新增材料')
        fingerprint=ai.packet(self.project,'',self.k,self.s)['fingerprint']
        prior=ai.read_cache(self.s,self.project)
        ai.write_cache(self.s,self.project,{**prior,'sync':{'status':'running','attempt':2,'fingerprint':fingerprint}})
        ai.JOBS.pop((str(self.s),self.project),None)
        with patch('project_analysis.run_model',side_effect=self.response):
            self.assertTrue(ai.sync_once(self.k,self.s)['started'])
            ready=self.wait_finished()
            self.assertEqual(ready['state'],'ready');self.assertEqual(ready['sync']['attempt'],2)

    def test_progress_does_not_store_model_text(self):
        value=ai.inference_events('{"type":"item.completed","item":{"text":"secret-test-data"}}')
        self.assertNotIn('secret-test-data',json.dumps(value))
        self.assertEqual(value['event_count'],1)

    def test_background_analysis_is_bounded_and_skips_active_project(self):
        for name in ('second','third'):
            (self.k/'projects'/f'{name}.md').write_text('# '+name+'\n客户 项目\n## 沟通反馈 '+date.today().isoformat()+'\n客户要求确认范围。')
        projects=build_projects(self.k,self.s);release=threading.Event()
        def slow(context):
            release.wait(2)
            return self.response(context)
        with patch('project_analysis.run_model',side_effect=slow):
            try:
                ai.start({'project_id':self.project},self.k,self.s)
                second=ai.sync_once(self.k,self.s)
                self.assertTrue(second['started'])
                self.assertIsNone(ai.sync_once(self.k,self.s))
                self.assertEqual(sum(bool(v.get('running')) for k,v in ai.JOBS.items() if k[0]==str(self.s)),2)
                self.assertEqual(ai.read_cache(self.s,self.project)['sync']['status'],'running')
            finally:release.set()
            for _ in range(200):
                if not any(v.get('running') for k,v in ai.JOBS.items() if k[0]==str(self.s)):break
                time.sleep(.005)

if __name__=='__main__':unittest.main()
