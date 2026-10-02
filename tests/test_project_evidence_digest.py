import copy
import json
import tempfile
import unittest
import threading
from pathlib import Path
from unittest.mock import patch
import project_evidence_digest as digest
import project_source_context as sources
import project_analysis as ai
import test_project_analysis as fixtures


class DigestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.config={'model':'test','effort':'ultra','provider':'openai'}
        self.doc={'path':'raw/history.md','date':'','relation':'explicit_evidence','content':
            '2026-01-01 客户新增物流。\n'+('一般沟通。\n'*8500)+'2026-02-01 客户撤销物流。\n'+('一般沟通。\n'*8500)+'2026-03-01 客户重确认物流查询。'}

    def infer(self,context,prompt,schema):
        chunks=json.loads(prompt.split('\nINPUT:\n',1)[1])
        if 'classification' in schema.get('properties',{}):
            chunk=chunks[0]
            return {'id':chunk['id'],'classification':'no_business_facts',
                    'reason':'此测试区间只有一般沟通占位文字，没有具体业务事实。','quote':chunk['content'][:30]}
        markers=['2026-01-01 客户新增物流。','2026-02-01 客户撤销物流。','2026-03-01 客户重确认物流查询。']
        return {'chunks':[{'id':c['id'],'entries':[{'summary':m,'quote':m} for m in markers if m in c['content']]} for c in chunks]}

    def test_all_intervals_including_middle_changes_are_read_and_retained(self):
        plan=digest.plan([self.doc],'p1',self.root,self.config)
        chunks=plan['chunks'];self.assertEqual(chunks[0]['start'],0);self.assertEqual(chunks[-1]['end'],len(self.doc['content']))
        for left,right in zip(chunks,chunks[1:]):self.assertLess(right['start'],left['end'])
        digest.process(plan,{},self.infer,lambda **kw:None)
        ready=digest.plan([self.doc],'p1',self.root,self.config)
        self.assertFalse(ready['pending']);self.assertEqual(len(ready['sources']),1)
        value=ready['sources'][0]
        for fact in ('客户新增物流','客户撤销物流','客户重确认物流查询'):self.assertIn(fact,value['content'])
        self.assertFalse(value['truncated']);self.assertTrue(value['extracted'])
        self.assertIn('2026-02-01',value['original_dates'])
        self.assertTrue(value['digest_entries'])
        for entry in value['digest_entries']:
            self.assertIn(entry['quote'],self.doc['content'][entry['source_start']:entry['source_end']])
            self.assertTrue(entry['id'] and entry['chunk_id'])

    def test_parallel_batches_are_bounded_and_keep_all_intervals(self):
        document={**self.doc,'content':self.doc['content']*3}
        plan=digest.plan([document],'parallel',self.root,self.config)
        lock=threading.Lock();paired=threading.Event();counts={'active':0,'max':0}
        def concurrent(context,prompt,schema):
            with lock:
                counts['active']+=1;counts['max']=max(counts['max'],counts['active'])
                if counts['active']==2:paired.set()
            try:
                if not paired.wait(3):raise ValueError('independent batches did not overlap')
                return self.infer(context,prompt,schema)
            finally:
                with lock:counts['active']-=1
        digest.process(plan,{},concurrent,lambda **kw:None)
        self.assertEqual(counts,{'active':0,'max':2})
        self.assertFalse(digest.plan([document],'parallel',self.root,self.config)['pending'])

    def test_interruption_cancels_inference_before_waiting_for_workers(self):
        plan=digest.plan([self.doc],'cancel',self.root,self.config)
        cancelled=threading.Event()
        def blocking(context,prompt,schema):
            if not cancelled.wait(3):raise ValueError('cancellation hook was not called')
            return self.infer(context,prompt,schema)
        with patch.object(digest,'wait',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                digest.process(plan,{},blocking,lambda **kw:None,cancelled.set)
        self.assertTrue(cancelled.is_set())

    def test_cooperative_yield_drains_started_batches_and_resumes_every_remaining_interval(self):
        document={**self.doc,'content':self.doc['content']*4}
        plan=digest.plan([document],'yielding',self.root,self.config)
        paired=threading.Event();yield_now=threading.Event();cancelled=threading.Event();lock=threading.Lock();calls=[]
        def finish_current(context,prompt,schema):
            with lock:
                calls.append(prompt)
                if len(calls)==2:paired.set()
            self.assertTrue(paired.wait(3))
            yield_now.set()
            return self.infer(context,prompt,schema)
        with self.assertRaises(digest.AnalysisYielded):
            digest.process(plan,{},finish_current,lambda **kw:None,cancelled.set,yield_now.is_set)
        self.assertEqual(len(calls),2);self.assertFalse(cancelled.is_set())
        resumed=digest.plan([document],'yielding',self.root,self.config)
        self.assertGreater(len(resumed['pending']),0);self.assertLess(len(resumed['pending']),len(plan['chunks']))
        completed={chunk['id'] for chunk in plan['chunks'] if digest.read_chunk(Path(plan['root']),chunk)}
        self.assertTrue(completed)
        submitted=[]
        def resume(context,prompt,schema):
            submitted.extend(c['id'] for c in json.loads(prompt.split('\nINPUT:\n',1)[1]))
            return self.infer(context,prompt,schema)
        digest.process(resumed,{},resume,lambda **kw:None)
        self.assertFalse(completed.intersection(submitted))
        ready=digest.plan([document],'yielding',self.root,self.config)
        self.assertFalse(ready['pending'])
        for fact in ('客户新增物流','客户撤销物流','客户重确认物流查询'):
            self.assertIn(fact,ready['sources'][0]['content'])

    def test_incomplete_batch_never_saves_partial_or_becomes_ready_and_retry_resumes(self):
        plan=digest.plan([self.doc],'p1',self.root,self.config)
        calls=[]
        def fail_second(context,prompt,schema):
            calls.append(1)
            if len(calls)==2:raise ValueError('网络断开')
            return self.infer(context,prompt,schema)
        # Force one chunk per batch with a real long fixture.
        bigger={**self.doc,'content':self.doc['content']*2}
        plan=digest.plan([bigger],'p1',self.root,self.config)
        with self.assertRaisesRegex(ValueError,'网络断开'):digest.process(plan,{},fail_second,lambda **kw:None)
        retry=digest.plan([bigger],'p1',self.root,self.config)
        self.assertGreater(len(retry['pending']),0);self.assertLess(len(retry['pending']),len(retry['chunks']))
        self.assertEqual(retry['sources'],[])
        digest.process(retry,{},self.infer,lambda **kw:None)
        self.assertFalse(digest.plan([bigger],'p1',self.root,self.config)['pending'])

    def test_fabricated_quotes_missing_chunks_and_overflow_are_rejected(self):
        plan=digest.plan([self.doc],'p1',self.root,self.config)
        chunk=plan['chunks'][0]
        for entry in [{'summary':'已签约','quote':'客户已签约'}, {'summary':'抽取容量不足','quote':chunk['content'][:20]}]:
            with self.assertRaises(ValueError):digest.validate_chunk({'id':chunk['id'],'entries':[entry]},chunk)
        with self.assertRaises(ValueError):digest.process(plan,{},lambda *args:{'chunks':[]},lambda **kw:None)
        self.assertFalse(list(Path(plan['root']).glob('*.json')))
        self.assertTrue(list((Path(plan['root'])/'rejected').glob('*.json')))

    def test_invalid_peer_preserves_verified_intervals_without_completing_document(self):
        plan=digest.plan([self.doc],'p1',self.root,self.config)
        bad=plan['chunks'][1]
        def one_invalid(context,prompt,schema):
            answer=self.infer(context,prompt,schema)
            chunk=json.loads(prompt.split('\nINPUT:\n',1)[1])[0]
            if 'chunks' in answer and bad['start']<=chunk['start'] and chunk['end']<=bad['end']:
                answer['chunks'][0]['entries']=[{'summary':'错误引用','quote':'原文不存在的引文'}]
            return answer
        with self.assertRaisesRegex(ValueError,'引用须来自'):
            digest.process(plan,{},one_invalid,lambda **kw:None)
        retry=digest.plan([self.doc],'p1',self.root,self.config)
        self.assertGreater(len(retry['pending']),0)
        # Recursive children add leaves; compare against the current leaf count,
        # not the pre-split denominator, and prove successful peers survived.
        self.assertLess(len(retry['pending']),len(retry['chunks']))
        self.assertTrue(any(digest.read_chunk(retry['root'],c) for c in plan['chunks']))
        self.assertEqual(retry['sources'],[])
        digest.process(retry,{},self.infer,lambda **kw:None)
        self.assertFalse(digest.plan([self.doc],'p1',self.root,self.config)['pending'])

    def test_cache_identity_changes_with_project_source_model_and_policy(self):
        baseline=digest.digest_key('p1',self.doc,self.config)
        self.assertNotEqual(baseline,digest.digest_key('p2',self.doc,self.config))
        self.assertNotEqual(baseline,digest.digest_key('p1',{**self.doc,'content':self.doc['content']+'修订'},self.config))
        self.assertNotEqual(baseline,digest.digest_key('p1',self.doc,{**self.config,'model':'different'}))
        self.assertNotEqual(baseline,digest.digest_key('p1',{**self.doc,'date':'2026-02-03'},self.config))
        self.assertNotEqual(baseline,digest.digest_key('p1',{**self.doc,'relation':'customer_background'},self.config))
        with patch.object(digest,'POLICY',99):self.assertNotEqual(baseline,digest.digest_key('p1',self.doc,self.config))

    def test_missing_or_duplicate_id_retains_only_unambiguous_valid_peers(self):
        for mode in ('missing','duplicate'):
            with self.subTest(mode=mode):
                plan=digest.plan([self.doc],mode,self.root,self.config)
                bad_id=plan['chunks'][1]['id']
                def incomplete(context,prompt,schema):
                    answer=self.infer(context,prompt,schema)
                    if 'chunks' in answer and answer['chunks'][0]['id']==bad_id:
                        if mode=='missing':answer['chunks'].pop()
                        else:answer['chunks'].append(copy.deepcopy(answer['chunks'][-1]))
                    return answer
                with self.assertRaisesRegex(ValueError,'遗漏或重复'):
                    digest.process(plan,{},incomplete,lambda **kw:None)
                retry=digest.plan([self.doc],mode,self.root,self.config)
                self.assertGreater(len(retry['pending']),0)
                self.assertLess(len(retry['pending']),len(plan['pending']))
                self.assertEqual(retry['sources'],[])
                digest.process(retry,{},self.infer,lambda **kw:None)
                self.assertFalse(digest.plan([self.doc],mode,self.root,self.config)['pending'])

    def test_final_model_cannot_quote_ai_intermediate_summary_as_original(self):
        source={'content':'事实整理：客户已确认\n原文：我方建议','extracted':True,'original_quotes':['我方建议']}
        self.assertFalse(sources.has_original_quote(source,'客户已确认'))
        self.assertTrue(sources.has_original_quote(source,'我方建议'))


class AdaptiveRecoveryTests(unittest.TestCase):
    setUp=DigestTests.setUp

    def make_plan(self,content,project='adaptive'):
        document={**self.doc,'content':content}
        with patch.object(sources,'covered_excerpts',return_value=[{**document,'truncated':True}]):
            return digest.plan([document],project,self.root,self.config)

    def input(self,prompt):
        chunks=json.loads(prompt.split('\nINPUT:\n',1)[1]);self.assertEqual(len(chunks),1)
        self.assertLessEqual(len(chunks[0]['content']),digest.CHUNK_SIZE)
        return chunks[0]

    def fact(self,context,prompt,schema):
        chunk=self.input(prompt)
        return {'chunks':[{'id':chunk['id'],'entries':[{'summary':'本区间业务沟通，确认层级仍以原文为准。','quote':chunk['content'][:35]}]}]}

    def test_legacy_nonempty_reused_unchanged_but_legacy_empty_is_pending(self):
        plan=self.make_plan('客户要求确认预算。\n'*1000)
        chunk=plan['chunks'][0];path=digest._path(plan['root'],chunk)
        value={'id':chunk['id'],'entries':[{'summary':'客户要求确认预算。','quote':'客户要求确认预算。'}]}
        digest._atomic(path,value);before=path.read_bytes()
        ready=self.make_plan('客户要求确认预算。\n'*1000)
        self.assertFalse(ready['pending']);self.assertEqual(path.read_bytes(),before)
        self.assertTrue(ready['sources'][0]['digest_entries'])
        digest._atomic(path,{'id':chunk['id'],'entries':[]})
        pending=self.make_plan('客户要求确认预算。\n'*1000)
        self.assertEqual(len(pending['pending']),1);self.assertEqual(pending['sources'],[])

    def test_empty_needs_separate_review_and_certificate_is_source_bound(self):
        content='您好。谢谢。再见。\n'*300;plan=self.make_plan(content);calls=[]
        def infer(context,prompt,schema):
            chunk=self.input(prompt);calls.append(schema)
            if 'classification' in schema['properties']:
                return {'id':chunk['id'],'classification':'no_business_facts','reason':'完整区间只有问候与告别，没有业务事实或业务条件。','quote':'您好。谢谢。再见。'}
            return {'chunks':[{'id':chunk['id'],'entries':[]}]}
        digest.process(plan,{},infer,lambda **kw:None)
        self.assertEqual(len(calls),2)
        ready=self.make_plan(content);self.assertFalse(ready['pending'])
        self.assertEqual(ready['sources'][0]['digest_entries'],[])
        certificate=digest._path(plan['root'],plan['chunks'][0],'empty_reviews')
        self.assertFalse(json.loads(certificate.read_text())['semantic_coverage_proven'])
        self.assertTrue(self.make_plan(content+'客户新增预算条件。')['pending'])

    def test_empty_business_or_uncertain_review_is_not_completion(self):
        for classification in ('has_business_facts','uncertain'):
            plan=self.make_plan('客户预算尚未批准。',classification);chunk=plan['chunks'][0]
            def infer(context,prompt,schema):
                if 'classification' in schema['properties']:
                    return {'id':chunk['id'],'classification':classification,'reason':'本区间明确出现客户预算的业务条件。','quote':chunk['content']}
                return {'chunks':[{'id':chunk['id'],'entries':[]}]}
            with self.assertRaises(digest.ChunkFailure):digest.process_batch([chunk],Path(plan['root']),{},infer)
            self.assertIsNone(digest.read_chunk(plan['root'],chunk))
            self.assertTrue(list((Path(plan['root'])/'rejected').glob('*.json')))

    def test_failed_tree_yields_then_resumes_only_unfinished_child(self):
        content='2026-01-01 客户新增物流，预算待批准。\n'*500
        initial=self.make_plan(content);parent=initial['chunks'][0];yield_now=threading.Event()
        def capacity(context,prompt,schema):
            chunk=self.input(prompt);yield_now.set()
            return {'chunks':[{'id':chunk['id'],'entries':[{'summary':'抽取容量不足','quote':chunk['content'][:20]}]}]}
        with self.assertRaises(digest.AnalysisYielded):
            digest.process(initial,{},capacity,lambda **kw:None,should_yield=yield_now.is_set)
        resumed=self.make_plan(content);self.assertEqual(len(resumed['chunks']),2)
        left,right=resumed['chunks']
        self.assertEqual((left['start'],right['end']),(parent['start'],parent['end']))
        self.assertLess(right['start'],left['end'])
        def one_network_failure(context,prompt,schema):
            if self.input(prompt)['id']==right['id']:raise ValueError('网络断开')
            return self.fact(context,prompt,schema)
        with self.assertRaisesRegex(ValueError,'网络断开'):
            digest.process(resumed,{},one_network_failure,lambda **kw:None)
        retry=self.make_plan(content);self.assertEqual([c['id'] for c in retry['pending']],[right['id']])
        saved=digest._path(retry['root'],left).read_bytes();submitted=[]
        def infer(context,prompt,schema):submitted.append(self.input(prompt)['id']);return self.fact(context,prompt,schema)
        digest.process(retry,{},infer,lambda **kw:None)
        self.assertEqual(submitted,[right['id']]);self.assertEqual(digest._path(retry['root'],left).read_bytes(),saved)
        ready=self.make_plan(content);self.assertFalse(ready['pending'])
        self.assertEqual(len(ready['sources'][0]['digest_entries']),2)

    def test_minimum_and_depth_are_terminal_without_holes_or_false_ready(self):
        content='客户新增范围并撤销之前的范围。\n'*40
        plan=self.make_plan(content);calls=[];progress=[]
        def bad(context,prompt,schema):
            chunk=self.input(prompt);calls.append(chunk)
            return {'chunks':[{'id':chunk['id'],'entries':[{'summary':'错误引用','quote':'完全不存在的业务内容'}]}]}
        with patch.object(digest,'MIN_CHUNK_SIZE',40),patch.object(digest,'MAX_SPLIT_DEPTH',2):
            with self.assertRaisesRegex(ValueError,'最小大小或最大拆分深度'):
                digest.process(plan,{},bad,lambda **kw:progress.append(kw))
            current=self.make_plan(content)
        self.assertTrue(current['pending']);self.assertEqual(current['sources'],[])
        self.assertLessEqual(len(calls),7)
        leaves=current['chunks'];self.assertEqual(leaves[0]['start'],0);self.assertEqual(leaves[-1]['end'],len(content))
        self.assertTrue(all(right['start']<=left['end'] for left,right in zip(leaves,leaves[1:])))
        self.assertEqual(progress[-1]['root_segments_done'],0)
        self.assertTrue(any('minimum_interval_blocked'==json.loads(p.read_text())['kind'] for p in (Path(plan['root'])/'rejected').glob('*.json')))

    def test_whitespace_only_repair_keeps_original_and_never_changes_amount(self):
        content='已确认\n\t预算 12 万元，交付仍待核实。';plan=self.make_plan(content);chunk=plan['chunks'][0]
        def infer(context,prompt,schema):
            return {'chunks':[{'id':chunk['id'],'entries':[{'summary':'预算已确认，交付仍待核实。','quote':'已确认 预算 12 万元，交付仍待核实。'}]}]}
        digest.process_batch([chunk],Path(plan['root']),{},infer)
        self.assertEqual(digest.read_chunk(plan['root'],chunk)['entries'][0]['quote'],content)
        self.assertTrue(list((Path(plan['root'])/'rejected').glob('*.json')))
        other={**chunk,'id':chunk['id']+'different'}
        def wrong(context,prompt,schema):
            return {'chunks':[{'id':other['id'],'entries':[{'summary':'预算13万元','quote':'已确认 预算 13 万元，交付仍待核实。'}]}]}
        for _ in range(2):
            with self.assertRaises(digest.ChunkFailure):digest.process_batch([other],Path(plan['root']),{},wrong)
        self.assertIsNone(digest.read_chunk(plan['root'],other))
        self.assertEqual(len(list((Path(plan['root'])/'rejected').glob('*.json'))),3)

    def test_yield_before_empty_review_resumes_review_without_reextracting(self):
        content='您好，谢谢，再见。';plan=self.make_plan(content);yield_now=threading.Event();calls=[]
        def empty(context,prompt,schema):
            chunk=self.input(prompt);yield_now.set();calls.append('extraction')
            return {'chunks':[{'id':chunk['id'],'entries':[]}]}
        with self.assertRaises(digest.AnalysisYielded):
            digest.process(plan,{},empty,lambda **kw:None,should_yield=yield_now.is_set)
        self.assertIsNone(digest.read_chunk(plan['root'],plan['chunks'][0]))
        def review(context,prompt,schema):
            self.assertIn('classification',schema['properties']);chunk=self.input(prompt);calls.append('review')
            return {'id':chunk['id'],'classification':'no_business_facts','reason':'完整区间只有问候告别，没有具体业务信息。','quote':content}
        digest.process(self.make_plan(content),{},review,lambda **kw:None)
        self.assertEqual(calls,['extraction','review'])

    def test_cancellation_prevents_a_second_empty_review_call(self):
        plan=self.make_plan('您好，谢谢，再见。');cancelled=threading.Event();calls=[]
        def empty(context,prompt,schema):
            chunk=self.input(prompt);calls.append(1);cancelled.set()
            return {'chunks':[{'id':chunk['id'],'entries':[]}]}
        with self.assertRaisesRegex(ValueError,'已中断'):
            digest.process_batch(plan['chunks'],Path(plan['root']),{},empty,cancelled=cancelled)
        self.assertEqual(len(calls),1);self.assertIsNone(digest.read_chunk(plan['root'],plan['chunks'][0]))

    def test_invalid_branch_gap_fails_closed_and_changed_source_does_not_reuse_tree(self):
        content='客户新增范围。\n'*1000;plan=self.make_plan(content);parent=plan['chunks'][0]
        digest.split_failed(plan['root'],parent)
        path=digest._path(plan['root'],parent,'branches');value=json.loads(path.read_text())
        value['children'][0][1]=value['children'][1][0]-1;digest._atomic(path,value)
        with self.assertRaisesRegex(ValueError,'恢复清单异常'):self.make_plan(content)
        revised=self.make_plan(content+'明确撤回上述需求。')
        self.assertEqual(len(revised['chunks']),1);self.assertTrue(revised['pending'])


class PacketDigestTests(unittest.TestCase):
    setUp=fixtures.AnalysisTests.setUp
    response=fixtures.AnalysisTests.response
    generate=fixtures.AnalysisTests.generate
    wait_finished=fixtures.AnalysisTests.wait_finished

    def test_model_payload_does_not_duplicate_original_quote_ledgers(self):
        ctx=ai.packet(self.project,'',self.k,self.s)
        ctx['sources'][0].update(extracted=True,original_quotes=['原话'],original_dates=['2026-01-01'])
        payload=ai.model_input(ctx)
        self.assertNotIn('original_quotes',payload['sources'][0]);self.assertNotIn('original_dates',payload['sources'][0])
        self.assertIn('original_quotes',ctx['sources'][0])
        self.assertNotIn('sources',payload['project'])

    def test_capacity_failure_keeps_old_result_readable_and_blocks_final_inference(self):
        original=self.generate()
        self.source.write_text(self.source.read_text()+'\n新增资料')
        real_plan=digest.plan
        def oversized(*args,**kwargs):
            value=real_plan(*args,**kwargs)
            value['capacity_error']='全文抽取完成，但综合材料仍超过容量；尚未完成综合'
            return value
        with patch.object(digest,'plan',side_effect=oversized),patch('project_analysis.invoke_model') as invoke, \
                patch('project_analysis.project_history_synthesis.prepare',side_effect=ValueError('分层历史仍超过容量，未截断')) as prepare:
            self.assertEqual(ai.status(self.project,self.k,self.s)['result']['analysis_id'],original['result']['analysis_id'])
            ai.start({'project_id':self.project,'force':True},self.k,self.s)
            result=self.wait_finished()
            self.assertIn('超过容量',result['error']);self.assertEqual(result['result']['analysis_id'],original['result']['analysis_id'])
            invoke.assert_not_called()
            prepare.assert_called_once()

    def test_large_input_routes_to_history_layers_before_final_decision(self):
        context=ai.packet(self.project,'',self.k,self.s)
        real_plan=digest.plan
        def oversized(*args,**kwargs):
            value=real_plan(*args,**kwargs);value['capacity_error']='综合材料超过容量'
            return value
        with patch.object(digest,'plan',side_effect=oversized),patch('project_analysis.invoke_model') as invoke, \
                patch('project_analysis.project_history_synthesis.prepare',return_value={'chapters':[]}) as chapters, \
                patch('project_analysis.project_history_reconcile.reconcile',return_value={'states':[]}) as relations, \
                patch('project_analysis.project_history_reconcile.synthesize',return_value=self.response(context)) as final, \
                patch('project_analysis.project_history_reconcile.completion_receipt',return_value={'test_receipt':True}) as receipt:
            value=ai.run_model(context)
            chapters.assert_called_once();relations.assert_called_once();final.assert_called_once();receipt.assert_called_once();invoke.assert_not_called()
            self.assertEqual(context['source_coverage']['history_completion'],{'test_receipt':True})
            self.assertEqual(value['understanding']['scope_status'],'尚未冻结')
            self.assertEqual(context['source_coverage']['synthesis_error'],'')
            self.assertTrue(context['source_coverage']['relation_model_checked'])

    def test_same_originals_different_extraction_strategy_invalidates_result(self):
        original=ai.packet(self.project,'',self.k,self.s)
        with patch.object(digest,'POLICY',99):changed=ai.packet(self.project,'',self.k,self.s)
        self.assertNotEqual(original['stable_fingerprint'],changed['stable_fingerprint'])

    def test_prepared_cache_fingerprint_matches_readback_and_raw_revision_invalidates(self):
        self.source.write_text(self.source.read_text()+'\n'+('长沟通。\n'*6000))
        context=ai.packet(self.project,'',self.k,self.s)
        before=context['stable_fingerprint']
        def infer(context,prompt,schema):
            chunks=json.loads(prompt.split('\nINPUT:\n',1)[1])
            return {'chunks':[{'id':c['id'],'entries':[{'summary':'已有范围沟通，确认边界待核','quote':c['content'][:30]}]} for c in chunks]}
        with patch('project_analysis.invoke_model',side_effect=infer):ai.prepare_inference(context)
        self.assertNotEqual(context['stable_fingerprint'],before)
        current=ai.packet(self.project,'',self.k,self.s)
        self.assertEqual(context['stable_fingerprint'],current['stable_fingerprint'])
        self.assertFalse(current['source_coverage']['pending_segments'])
        self.source.write_text(self.source.read_text()+'新增范围')
        changed=ai.packet(self.project,'',self.k,self.s)
        self.assertNotEqual(changed['stable_fingerprint'],current['stable_fingerprint'])
        self.assertTrue(changed['source_coverage']['pending_segments'])


if __name__=='__main__':unittest.main()
