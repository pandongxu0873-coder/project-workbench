import copy
import hashlib
import json
import threading
import time
import unittest
from unittest.mock import patch
import project_analysis as ai
import project_evidence_digest as digest
import test_project_analysis as fixtures


class SchedulerTests(unittest.TestCase):
    setUp=fixtures.AnalysisTests.setUp
    response=fixtures.AnalysisTests.response
    generate=fixtures.AnalysisTests.generate
    wait_finished=fixtures.AnalysisTests.wait_finished

    def other(self,name):
        path=self.k/'projects'/(name+'.md')
        path.write_text('# '+name+'\n客户 项目\n## 沟通反馈 2020-01-01\n客户希望核对本次业务范围。')
        return hashlib.sha256(('projects/'+name+'.md').encode()).hexdigest()[:20],path

    def wait_idle(self):
        for _ in range(500):
            if not any(v.get('running') for k,v in ai.JOBS.items() if k[0]==str(self.s)):return
            time.sleep(.005)
        self.fail('workers did not stop')

    def test_release_baseline_preserves_stale_result_but_new_facts_refresh(self):
        self.generate()
        saved=ai.read_cache(self.s,self.project)
        path=self.k/saved['result']['source_snapshot'][0]['path']
        # Use the authoritative project path, not an incidental source.
        project=next(p for p in ai.build_projects(self.k,self.s) if p['id']==self.project)
        path=self.k/project['source_path']
        path.write_text(path.read_text()+'\n发布前已有补充。')
        context=ai.packet(self.project,saved['correction'],self.k,self.s)
        saved['auto_refresh_baseline']={'analysis_id':saved['result']['analysis_id'],'input_fingerprint':ai.input_fingerprint(context)}
        ai.write_cache(self.s,self.project,saved)
        with patch('project_analysis.run_model') as model:
            self.assertIsNone(ai.sync_once(self.k,self.s));model.assert_not_called()
        self.assertTrue(ai.status(self.project,self.k,self.s)['stale'])
        path.write_text(path.read_text()+'\n发布后客户新增验收问题。')
        with patch('project_analysis.run_model',side_effect=self.response):
            self.assertTrue(ai.sync_once(self.k,self.s)['started']);self.wait_idle()
        self.assertFalse(ai.status(self.project,self.k,self.s)['stale'])

    def test_one_automatic_job_leaves_capacity_for_manual_analysis(self):
        second,_=self.other('second');third,_=self.other('third')
        release=threading.Event();entered=[]
        def slow(context):
            entered.append(context['project']['id']);release.wait(5);return self.response(context)
        with patch('project_analysis.run_model',side_effect=slow):
            try:
                self.assertTrue(ai.sync_once(self.k,self.s)['started'])
                self.assertIsNone(ai.sync_once(self.k,self.s))
                active=[(key,job) for key,job in ai.JOBS.items() if key[0]==str(self.s) and job.get('running')]
                self.assertEqual(len(active),1);self.assertEqual(active[0][1]['kind'],'backfill')
                target=next(i for i in (self.project,second,third) if i!=active[0][0][1])
                result=ai.start({'project_id':target,'correction':'会前新情况'},self.k,self.s)
                self.assertTrue(result['accepted']);self.assertTrue(result['started'])
                self.assertEqual(sum(v.get('running',False) for k,v in ai.JOBS.items() if k[0]==str(self.s)),2)
                self.assertIsNone(ai.sync_once(self.k,self.s))
            finally:release.set();self.wait_idle()

    def test_queued_request_survives_process_restart_and_has_idempotent_receipt(self):
        request_id='request-persisted-0000001'
        payload={'project_id':self.project,'correction':'最新付款口径待核实','request_id':request_id,'force':True}
        with patch('project_analysis.CAPACITY',threading.BoundedSemaphore(0)),patch('project_analysis.run_model') as model:
            first=ai.start(payload,self.k,self.s);again=ai.start(payload,self.k,self.s)
            self.assertTrue(first['accepted']);self.assertTrue(first['queued']);self.assertEqual(first['state'],'queued')
            self.assertEqual(first['request_receipt'],again['request_receipt']);self.assertTrue(again['replayed'])
            model.assert_not_called()
            with self.assertRaisesRegex(ValueError,'同一次分析请求'):
                ai.start({**payload,'correction':'不同内容'},self.k,self.s)
        saved=ai.read_cache(self.s,self.project)
        self.assertEqual(len(saved['requests']),1);self.assertEqual(saved['correction'],'最新付款口径待核实')
        ai.JOBS.pop((str(self.s),self.project),None)
        with patch('project_analysis.run_model',side_effect=self.response):
            self.assertTrue(ai.sync_once(self.k,self.s)['started']);self.wait_idle()
        final=ai.read_cache(self.s,self.project)
        self.assertEqual(final['requests'][0]['status'],'complete')
        self.assertEqual(final['result']['source_snapshot'][-1]['content'],'最新付款口径待核实')

    def test_running_result_cannot_erase_new_versions_and_superseded_input_stays_in_history(self):
        first_entered=threading.Event();latest_entered=threading.Event();first_release=threading.Event();latest_release=threading.Event();contexts=[]
        def slow(context):
            contexts.append(context)
            if context['correction']=='A':
                first_entered.set();first_release.wait(5)
                context['_progress']({'phase':'旧任务刚完成'})
            else:latest_entered.set();latest_release.wait(5)
            return self.response(context)
        with patch('project_analysis.run_model',side_effect=slow):
            try:
                ai.start({'project_id':self.project,'correction':'A'},self.k,self.s);self.assertTrue(first_entered.wait(2))
                b=ai.start({'project_id':self.project,'correction':'B'},self.k,self.s)
                c=ai.start({'project_id':self.project,'correction':'C'},self.k,self.s)
                self.assertTrue(b['queued']);self.assertTrue(c['queued']);self.assertEqual(c['request_receipt']['revision'],3)
                first_release.set();self.assertTrue(latest_entered.wait(2))
                saved=ai.read_cache(self.s,self.project)
                self.assertEqual(saved['correction'],'C');self.assertEqual([r['text'] for r in saved['correction_history']],['A','B','C'])
                self.assertEqual([r['status'] for r in saved['requests']],['complete','superseded','running'])
                self.assertEqual([c['correction'] for c in contexts],['A','C'])
                self.assertEqual([r['text'] for r in contexts[-1]['correction_history']],['A','B','C'])
            finally:first_release.set();latest_release.set();self.wait_idle()
        final=ai.status(self.project,self.k,self.s)
        self.assertFalse(final['stale']);self.assertIsNone(final['pending_request']);self.assertEqual(final['state'],'ready')

    def test_orphan_running_request_restarts_without_spending_an_extra_attempt(self):
        self.generate(correction='持续保留的新情况')
        saved=ai.read_cache(self.s,self.project)
        saved['requests'][-1]['status']='running';saved['sync'].update(status='running',attempt=2)
        ai.write_cache(self.s,self.project,saved);ai.JOBS.pop((str(self.s),self.project),None)
        waiting=ai.status(self.project,self.k,self.s)
        self.assertEqual(waiting['state'],'queued');self.assertIsNone(waiting['active_request'])
        with patch('project_analysis.run_model',side_effect=self.response):
            self.assertTrue(ai.sync_once(self.k,self.s)['started']);self.wait_idle()
        final=ai.read_cache(self.s,self.project)
        self.assertEqual(final['requests'][-1]['status'],'complete');self.assertEqual(final['sync']['attempt'],2)

    def test_manual_then_actual_input_change_then_schema_or_first_backfill(self):
        fresh,path=self.other('older-but-new-feedback');manual,_=self.other('manual')
        with patch('project_analysis.run_model',side_effect=self.response):
            ai.start({'project_id':fresh},self.k,self.s);self.wait_idle()
        path.write_text(path.read_text()+'\n客户刚提出验收异议。')
        with patch('project_analysis.CAPACITY',threading.BoundedSemaphore(0)):
            self.assertTrue(ai.start({'project_id':manual,'correction':'开会前先分析'},self.k,self.s)['queued'])
        release=threading.Event();order=[]
        def slow(context):order.append(context['project']['id']);release.wait(5);return self.response(context)
        with patch('project_analysis.run_model',side_effect=slow):
            try:
                ai.sync_once(self.k,self.s)
                ai.sync_once(self.k,self.s)
                self.assertEqual(order,[manual,fresh])
                self.assertEqual(ai.JOBS[(str(self.s),fresh)]['kind'],'refresh')
                self.assertIsNone(ai.sync_once(self.k,self.s))
            finally:release.set();self.wait_idle()

    def test_format_upgrade_alone_is_not_new_customer_input(self):
        self.generate();cache=ai.read_cache(self.s,self.project)
        cache['result'].pop('input_fingerprint')
        cache['result']['schema_version']=5
        for name in ('commercial_baseline','scope_comparisons'):cache['result']['analysis']['understanding'].pop(name)
        ai.write_cache(self.s,self.project,cache)
        context=ai.packet(self.project,'',self.k,self.s)
        self.assertFalse(ai.changed_input(context,cache['result']))
        with patch('project_analysis.run_model') as infer:
            self.assertIsNone(ai.sync_once(self.k,self.s))
            infer.assert_not_called()
        self.assertEqual(ai.read_cache(self.s,self.project)['result']['analysis_id'],cache['result']['analysis_id'])
        self.source.write_text(self.source.read_text()+'\n真实新增反馈。')
        self.assertTrue(ai.changed_input(ai.packet(self.project,'',self.k,self.s),cache['result']))

    def test_yielded_history_preserves_old_result_and_retry_allowance(self):
        self.generate();old=ai.read_cache(self.s,self.project)['result']
        # A real input change, not a schema upgrade, triggers automatic work.
        saved=ai.read_cache(self.s,self.project);saved['result']['schema_version']=5;saved['sync']['schema_version']=5
        for name in ('commercial_baseline','scope_comparisons'):saved['result']['analysis']['understanding'].pop(name)
        ai.write_cache(self.s,self.project,saved)
        self.source.write_text(self.source.read_text()+'\n客户新增验收条件。')
        with patch('project_analysis.run_model',side_effect=digest.AnalysisYielded):
            ai.sync_once(self.k,self.s);self.wait_idle()
        current=ai.read_cache(self.s,self.project)
        self.assertEqual(current['sync']['status'],'yielded');self.assertEqual(current['sync']['attempt'],0)
        self.assertEqual(current['result']['analysis_id'],old['analysis_id']);self.assertEqual(current['error'],'')
        with patch('project_analysis.run_model',side_effect=self.response):
            ai.sync_once(self.k,self.s);self.wait_idle()
        self.assertEqual(ai.read_cache(self.s,self.project)['sync']['attempt'],1)

    def test_slow_source_discovery_does_not_hold_global_state_lock(self):
        other,_=self.other('quick-manual');entered=threading.Event();release=threading.Event();completed=threading.Event();failures=[]
        real_packet=ai.packet
        def slow_packet(project_id,*args,**kwargs):
            if project_id==self.project:entered.set();release.wait(5)
            return real_packet(project_id,*args,**kwargs)
        def manual():
            try:ai.start({'project_id':other,'correction':'及时保存'},self.k,self.s)
            except Exception as error:failures.append(error)
            finally:completed.set()
        with patch('project_analysis.packet',side_effect=slow_packet),patch('project_analysis.run_model',side_effect=self.response):
            reader=threading.Thread(target=lambda:ai.status(self.project,self.k,self.s));reader.start()
            self.assertTrue(entered.wait(2));submitter=threading.Thread(target=manual);submitter.start()
            try:self.assertTrue(completed.wait(2),'another project submission was blocked by a source scan')
            finally:release.set();reader.join(5);submitter.join(5);self.wait_idle()
        self.assertEqual(failures,[])

    def test_full_capacity_marks_history_to_yield_and_dispatches_waiting_manual(self):
        manual,_=self.other('manual-ongoing');urgent,_=self.other('manual-new')
        history_entered=threading.Event();boundary=threading.Event();manual_release=threading.Event();urgent_entered=threading.Event()
        def work(context):
            project_id=context['project']['id']
            if project_id==self.project:
                history_entered.set();boundary.wait(5)
                if context['_should_yield']():raise digest.AnalysisYielded()
                raise ValueError('history was not asked to yield')
            if project_id==manual:manual_release.wait(5)
            if project_id==urgent:urgent_entered.set()
            return self.response(context)
        with patch('project_analysis.run_model',side_effect=work):
            try:
                ai.start({'project_id':self.project,'_automatic':True},self.k,self.s)
                self.assertTrue(history_entered.wait(2))
                ai.start({'project_id':manual},self.k,self.s)
                queued=ai.start({'project_id':urgent,'correction':'优先处理新问题'},self.k,self.s)
                self.assertTrue(queued['queued']);self.assertTrue(ai.JOBS[(str(self.s),self.project)]['yield_requested'])
                boundary.set();self.assertTrue(urgent_entered.wait(2))
                yielded=ai.read_cache(self.s,self.project)
                self.assertEqual(yielded['sync']['status'],'yielded');self.assertEqual(yielded['sync']['attempt'],0)
                self.assertTrue(ai.JOBS[(str(self.s),manual)]['running'])
            finally:boundary.set();manual_release.set();self.wait_idle()

    def test_invalid_final_candidate_is_archived_privately_without_replacing_valid_result(self):
        self.generate();cache_path=ai.cache_path(self.s,self.project);before=cache_path.read_bytes()
        context=ai.packet(self.project,'',self.k,self.s);candidate=self.response(context)
        claim=candidate['understanding']['requirements'][0]
        claim['evidence']=[{**claim['evidence'][0],'quote':'非连续改写内容，不能作为客户原话。'}]
        progress=[];context['_progress']=progress.append
        with patch('project_analysis.invoke_model',return_value=candidate):
            with self.assertRaisesRegex(ValueError,'连续原文'):ai.run_model(context)
        files=list((self.s/'rejected-analysis'/self.project).glob('*.json'))
        self.assertEqual(len(files),1);self.assertEqual(files[0].stat().st_mode & 0o777,0o600)
        archived=json.loads(files[0].read_text())
        self.assertEqual(archived['candidate'],candidate)
        self.assertEqual(archived['schema_version'],ai.SCHEMA_VERSION)
        self.assertEqual(archived['fingerprint'],context['fingerprint'])
        self.assertEqual(set(archived),{'project_id','schema_version','fingerprint','input_fingerprint','created_at','diagnostic','candidate'})
        self.assertEqual(cache_path.read_bytes(),before)
        self.assertTrue(progress[-1]['rejected_candidate_saved'])

    def test_archive_io_failure_preserves_original_validation_rejection(self):
        context=ai.packet(self.project,'',self.k,self.s);candidate=self.response(context);candidate.pop('judgement')
        progress=[];context['_progress']=progress.append
        with patch('project_analysis.invoke_model',return_value=candidate),patch('project_analysis.os.open',side_effect=PermissionError('denied')):
            with self.assertRaisesRegex(ValueError,'分析结果格式'):ai.run_model(context)
        self.assertEqual(progress[-1],{'rejected_candidate_saved':False})

if __name__=='__main__':unittest.main()
