import copy
import unittest
from unittest.mock import patch
import project_analysis as ai
import project_understanding as understanding
import test_project_analysis as fixtures

class UnderstandingTests(unittest.TestCase):
    setUp=fixtures.AnalysisTests.setUp
    response=fixtures.AnalysisTests.response
    generate=fixtures.AnalysisTests.generate
    wait_finished=fixtures.AnalysisTests.wait_finished
    # Run these cases against the same real cache/identity fixtures; inherited
    # analysis tests also exercise the new required schema in all transitions.
    def test_content_schema_requires_scope_history_and_intervention_semantics(self):
        ctx=ai.packet(self.project,'',self.k,self.s)
        answer=self.response(ctx)
        for key in ('profile','requirements','evolution','lifecycle','interventions','commercial_baseline','scope_comparisons'):
            wrong=copy.deepcopy(answer);del wrong['understanding'][key]
            with self.assertRaises(ValueError):ai.validate_result(wrong,ctx['sources'])

    def test_fact_claim_without_evidence_cannot_hide_behind_empty_references(self):
        ctx=ai.packet(self.project,'',self.k,self.s);value=self.response(ctx)['understanding']
        value['profile']['business']={'summary':'集团已确认统一下单范围','evidence':[]}
        with self.assertRaises(ValueError):understanding.validate(value,ctx['sources'])

    def test_full_scope_is_not_cut_off_at_a_fixed_module_count(self):
        ctx=ai.packet(self.project,'',self.k,self.s)
        value=self.response(ctx)['understanding']
        sample=value['requirements'][0]
        value['requirements']=[{**sample,'name':f'业务能力{i}'} for i in range(30)]
        self.assertEqual(len(understanding.validate(value,ctx['sources'])['requirements']),30)

    def test_unconfirmed_owner_does_not_excuse_unreferenced_confirmed_scope(self):
        ctx=ai.packet(self.project,'',self.k,self.s)
        for group in ('requirements','evolution','lifecycle'):
            value=self.response(ctx)['understanding'];value[group][0]['evidence']=[]
            with self.assertRaises(ValueError):understanding.validate(value,ctx['sources'])
        value=self.response(ctx)['understanding']
        value['requirements'][0].update(scope='客户已确认全包物流',owner='负责人待核实',status='客户已明确',evidence=[])
        with self.assertRaises(ValueError):understanding.validate(value,ctx['sources'])

    def test_historical_projects_are_upgraded_without_becoming_current(self):
        project=next(p for p in ai.build_projects(self.k,self.s) if p['id']==self.project)
        project['is_current']=False
        with patch('project_analysis.build_projects',return_value=[project]),patch('project_analysis.run_model',side_effect=self.response):
            self.assertTrue(ai.sync_once(self.k,self.s)['started'])
            updated=self.wait_finished()
        self.assertIn('understanding',updated['result']['analysis'])
        self.assertFalse(project['is_current'])

    def test_other_project_scope_cannot_justify_current_scope_or_intervention(self):
        ctx=ai.packet(self.project,'',self.k,self.s);value=self.response(ctx)['understanding']
        ctx['sources'].append({'path':'projects/other.md','content':'客户确认物流二期','relation':'background_reference','date':''})
        value['requirements'][0]['evidence']=[{'path':'projects/other.md','quote':'客户确认物流二期'}]
        with self.assertRaises(ValueError):understanding.validate(value,ctx['sources'])

    def test_customer_entity_cannot_prove_a_project_event_in_old_story(self):
        ctx=ai.packet(self.project,'',self.k,self.s)
        ctx['sources'].append({'path':'entities/customer.md','content':'另一个项目已经验收','relation':'customer_background','date':''})
        story=self.response(ctx)['story'];story['journey'][0]['evidence']={'path':'entities/customer.md','quote':'另一个项目已经验收'}
        with self.assertRaises(ValueError):ai.validate_story(story,ctx['sources'])

    def test_top_level_judgement_cannot_use_background_project_facts(self):
        for relation in ('customer_background','background_reference'):
            ctx=ai.packet(self.project,'',self.k,self.s)
            ctx['sources'].append({'path':'projects/other.md','content':'其他项目已验收到账','relation':relation,'date':''})
            value=self.response(ctx)
            value['evidence']=[{'path':'projects/other.md','quote':'其他项目已验收到账'}]
            with self.assertRaisesRegex(ValueError,'当前项目判断依据'):
                ai.validate_result(value,ctx['sources'])

    def test_requirement_changes_need_exact_quotes_and_supported_nonfuture_dates(self):
        ctx=ai.packet(self.project,'',self.k,self.s);value=self.response(ctx)['understanding']
        value['evolution'][0]['evidence'][0]['quote']='客户确认新增范围全包'
        with self.assertRaises(ValueError):understanding.validate(value,ctx['sources'])
        value=self.response(ctx)['understanding'];value['lifecycle'][0]['date']='2099-01-01'
        with self.assertRaises(ValueError):understanding.validate(value,ctx['sources'])

    def test_v4_upgrade_preserves_result_until_explicit_update(self):
        self.generate();cache=ai.read_cache(self.s,self.project)
        with patch('project_analysis.evidence_fingerprint',wraps=ai.evidence_fingerprint) as compute:
            ai.packet(self.project,'',self.k,self.s)
            basis=compute.call_args.args[0]
        import hashlib,json
        legacy={**basis,'schema_version':4};legacy.pop('today')
        cache['result']['schema_version']=4
        cache['result']['analysis'].pop('understanding')
        cache['result']['fingerprint']=hashlib.sha256(json.dumps(legacy,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        ai.write_cache(self.s,self.project,cache)
        before=ai.status(self.project,self.k,self.s)
        self.assertEqual(before['state'],'ready');self.assertFalse(before['stale'])
        self.assertEqual(ai.read_cache(self.s,self.project)['result'],cache['result'])
        with patch('project_analysis.run_model',side_effect=self.response) as infer:
            self.assertIsNone(ai.sync_once(self.k,self.s))
            infer.assert_not_called()
            self.assertTrue(ai.start({'project_id':self.project,'force':True},self.k,self.s)['accepted'])
            refreshed=self.wait_finished()
        self.assertEqual(refreshed['result']['schema_version'],6)
        self.assertIn('understanding',refreshed['result']['analysis'])
        self.assertFalse(refreshed['stale'])

    def test_new_source_invalidates_old_profile_and_preserves_history_until_refreshed(self):
        before=self.generate();old=before['result']['analysis']['understanding']
        self.source.write_text(self.source.read_text()+'\n客户改变范围：物流交由其他系统。')
        current=ai.status(self.project,self.k,self.s)
        self.assertTrue(current['stale']);self.assertEqual(current['result']['analysis']['understanding'],old)

    def test_intervention_cannot_reissue_contact_after_execution_or_contact_restriction(self):
        ctx=ai.packet(self.project,'',self.k,self.s);value=self.response(ctx)
        value['understanding']['interventions']=[{'action':'邀请客户评审','owner':'客户负责人','success_signal':'确认范围','trigger':'范围变化'}]
        original=copy.deepcopy(value)
        for local,state in [({'relationship':'no_contact'},''),({},'done_waiting')]:
            result=ai.guarded(value,local,state)
            self.assertIn('仅内部复核',result['understanding']['interventions'][0]['action'])
            self.assertEqual(result['understanding']['evolution'],value['understanding']['evolution'])
        self.assertEqual(value,original)

    def comparison(self,ctx):
        source=ctx['sources'][0]
        return {'name':'本次范围是否进入评估','baseline':'此前书面或已签基线未收录，不能判定增量。',
            'change':'客户要求先核对范围。','confirmation':'客户提出，最终范围待核实。',
            'impact':'AI判断：范围及同口径成本不足，尚不能量化增量费用。',
            'recommendation':'AI建议：与业务负责人核对本次范围；取得明确答复后再决定方案投入。',
            'evidence':[{'path':source['path'],'quote':source['content'].splitlines()[0]}]}

    def test_commercial_baseline_without_evidence_must_explain_unknowns(self):
        ctx=ai.packet(self.project,'',self.k,self.s);value=self.response(ctx)['understanding']
        understanding.validate(value,ctx['sources'])
        value['commercial_baseline']={'summary':'客户已签30万元合同并已到账。','evidence':[]}
        with self.assertRaisesRegex(ValueError,'缺乏来源'):
            understanding.validate(value,ctx['sources'])

    def test_comparison_can_explain_unknown_prior_scope_but_needs_real_change_evidence(self):
        ctx=ai.packet(self.project,'',self.k,self.s);value=self.response(ctx)['understanding']
        value['scope_comparisons']=[self.comparison(ctx)]
        understanding.validate(value,ctx['sources'])
        value['scope_comparisons'][0]['evidence']=[]
        with self.assertRaises(ValueError):understanding.validate(value,ctx['sources'])

    def test_commercial_claims_reject_other_projects_and_unverifiable_quotes(self):
        ctx=ai.packet(self.project,'',self.k,self.s)
        for relation in ('background_reference','customer_background'):
            source={'path':'projects/other.md','content':'合同已签30万元。','relation':relation,'date':''}
            for section in ('commercial_baseline','scope_comparisons'):
                value=self.response(ctx)['understanding']
                evidence=[{'path':source['path'],'quote':source['content']}]
                if section=='commercial_baseline':value[section]={'summary':'合同已签30万元。','evidence':evidence}
                else:value[section]=[{**self.comparison(ctx),'evidence':evidence}]
                with self.subTest(section=section,relation=relation),self.assertRaisesRegex(ValueError,'其他项目背景'):
                    understanding.validate(value,ctx['sources']+[source])
        value=self.response(ctx)['understanding'];value['scope_comparisons']=[self.comparison(ctx)]
        value['scope_comparisons'][0]['evidence'][0]['quote']='双方已确认免费交付全部新增范围。'
        with self.assertRaisesRegex(ValueError,'连续原文'):understanding.validate(value,ctx['sources'])

    def test_commercial_comparison_is_bounded_without_shortening_full_history(self):
        ctx=ai.packet(self.project,'',self.k,self.s);value=self.response(ctx)['understanding']
        value['scope_comparisons']=[self.comparison(ctx) for _ in range(4)]
        value['evolution']*=30
        understanding.validate(value,ctx['sources'])
        value['scope_comparisons'].append(self.comparison(ctx))
        with self.assertRaises(ValueError):understanding.validate(value,ctx['sources'])

    def test_v5_compatibility_never_accepts_a_partial_new_contract(self):
        ctx=ai.packet(self.project,'',self.k,self.s);value=self.response(ctx)
        del value['understanding']['commercial_baseline']
        with self.assertRaises(ValueError):ai.validate_result(value,ctx['sources'],allow_legacy=True)
        del value['understanding']['scope_comparisons']
        ai.validate_result(value,ctx['sources'],allow_legacy=True)
        with self.assertRaises(ValueError):ai.validate_result(value,ctx['sources'])

    def test_v5_cache_survives_and_explicit_update_can_upgrade(self):
        self.generate();cache=ai.read_cache(self.s,self.project)
        basis=ai.packet(self.project,'',self.k,self.s)['_basis']
        import hashlib,json
        old_basis={k:v for k,v in basis.items() if k!='today'};old_basis['schema_version']=5
        legacy=hashlib.sha256(json.dumps(old_basis,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        cache['result']['schema_version']=5;cache['result']['fingerprint']=legacy
        del cache['result']['analysis']['understanding']['commercial_baseline']
        del cache['result']['analysis']['understanding']['scope_comparisons']
        cache['sync']={'status':'complete','fingerprint':legacy,'schema_version':5,'attempt':2,'retry_at':0}
        ai.write_cache(self.s,self.project,cache)
        before=ai.status(self.project,self.k,self.s)
        self.assertEqual(before['state'],'ready');self.assertFalse(before['stale'])
        self.assertEqual(ai.read_cache(self.s,self.project)['result'],cache['result'])
        with patch('project_analysis.run_model',side_effect=self.response) as infer:
            self.assertIsNone(ai.sync_once(self.k,self.s))
            infer.assert_not_called()
            self.assertTrue(ai.start({'project_id':self.project,'force':True},self.k,self.s)['accepted'])
            refreshed=self.wait_finished()
        self.assertEqual(refreshed['result']['schema_version'],6)
        self.assertEqual(refreshed['sync']['attempt'],1)
        self.assertIn('commercial_baseline',refreshed['result']['analysis']['understanding'])
        self.assertFalse(refreshed['stale'])

    def test_commercial_recommendations_respect_execution_and_pause_without_rewriting_facts(self):
        ctx=ai.packet(self.project,'',self.k,self.s);value=self.response(ctx)
        value['understanding']['scope_comparisons']=[self.comparison(ctx)]
        original=copy.deepcopy(value)
        for local,state in [({'relationship':'no_contact'},''),({'status':'暂停跟进'},''),
                            ({'status':'已发出等待反馈'},''),({},'done_waiting'),({},'new_evidence_review')]:
            with self.subTest(local=local,state=state):
                result=ai.guarded(value,local,state)
                self.assertEqual(result['draft'],'')
                comparison=result['understanding']['scope_comparisons'][0]
                if local.get('status') == '已发出等待反馈':
                    # Waiting on one sent request must not erase independent obligations.
                    self.assertIn('原有责任不自动暂停',comparison['recommendation'])
                    self.assertIn(original['understanding']['scope_comparisons'][0]['recommendation'],comparison['recommendation'])
                else:
                    self.assertIn('仅内部复核',comparison['recommendation'])
                    self.assertNotIn('与业务负责人核对本次范围',comparison['recommendation'])
                    self.assertLessEqual(len(comparison['recommendation']),260)
                for key in ('baseline','change','confirmation','impact','evidence'):
                    self.assertEqual(comparison[key],original['understanding']['scope_comparisons'][0][key])
                for key in ('commercial_baseline','evolution','lifecycle'):
                    self.assertEqual(result['understanding'][key],original['understanding'][key])
        self.assertEqual(value,original)

if __name__=='__main__': unittest.main()
