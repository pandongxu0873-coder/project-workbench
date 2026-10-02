import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import project_history_synthesis as history
import project_history_reconcile as reconcile


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.context = {'config': {'model': 'test', 'effort': 'ultra'},
                        'project': {'id': 'realistic-example'}, '_state_root': self.temp.name}
        self.refs = {
            'r_old': {'path': 'old.txt', 'quote': '旧合同包含前端查询及完整物流。', 'relation': 'explicit_evidence'},
            'r_new': {'path': 'new.txt', 'quote': '客户要求完整物流改为二期，前端查询一期保留。', 'relation': 'explicit_evidence'},
        }
        self.old = self.state('old', ['r_old'], ['old-fact'])
        self.new = {'id': 'new', 'group': 'constraints', 'fact': {'claim': '完整物流二期，前端查询保留'},
                    'evidence': [{'reference_id': 'r_new'}], 'origin_ids': ['new-fact']}

    def state(self, key, refs, origins):
        return {'id': key, 'kind': 'obligation', 'topic': '物流与前端查询',
                'summary': '旧合同包含前端查询及完整物流。', 'applicability': '变更尚待相应确认，不取消前端查询。',
                'status': 'unresolved', 'evidence': [{'reference_id': ref} for ref in refs], 'origin_ids': origins}

    def merged(self):
        state = self.state('combined', ['r_old', 'r_new'], [])
        del state['origin_ids']
        state['summary'] = '原约定包含完整物流及前端查询；客户要求完整物流二期，查询仍保留，变更确认待核。'
        return {'states': [state],
                'bindings': [{'input_id': 'old', 'state_ids': ['combined']},
                             {'input_id': 'new', 'state_ids': ['combined']}],
                'relations': [{'from_id': 'old', 'to_id': 'new', 'relation': 'split_by',
                               'explanation': '分期与取消不同，完整物流二期不影响查询仍保留。',
                               'evidence': [{'reference_id': 'r_old'}, {'reference_id': 'r_new'}]}]}

    def test_split_preserves_original_lineage_and_both_scope_components(self):
        states = reconcile.validate_merge(self.merged(), [self.old], [self.new], self.refs)
        self.assertEqual(states[0]['origin_ids'], ['new-fact', 'old-fact'])
        self.assertIn('查询仍保留', states[0]['summary'])
        self.assertEqual(states[0]['status'], 'unresolved')
        self.assertNotEqual(states[0]['id'], 'combined')

    def test_old_contract_cannot_silently_become_fulfilled_or_superseded(self):
        for status in ('fulfilled', 'superseded'):
            value = self.merged()
            value['states'][0]['status'] = status
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, '缺少项目内关系证据'):
                reconcile.validate_merge(value, [self.old], [self.new], self.refs)

    def test_justified_replacement_keeps_old_obligation_in_lineage(self):
        value = self.merged()
        value['states'][0]['status'] = 'superseded'
        value['relations'][0]['relation'] = 'replaced_by'
        states = reconcile.validate_merge(value, [self.old], [self.new], self.refs)
        self.assertIn('old-fact', states[0]['origin_ids'])

    def test_cannot_lose_old_input_or_attach_unrelated_quote(self):
        for mode in ('missing', 'orphan', 'unrelated', 'one_sided'):
            value = self.merged()
            if mode == 'missing':
                value['bindings'].pop(0)
            elif mode == 'orphan':
                row = copy.deepcopy(value['states'][0])
                row['id'] = 'orphan'
                value['states'].append(row)
            elif mode == 'unrelated':
                value['states'][0]['evidence'].append({'reference_id': 'invented'})
            else:
                value['relations'][0]['evidence'] = [{'reference_id': 'r_new'}]
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                reconcile.validate_merge(value, [self.old], [self.new], self.refs)

    def test_customer_background_cannot_release_project_obligation(self):
        refs = copy.deepcopy(self.refs)
        refs['r_new']['relation'] = 'customer_background'
        value = self.merged()
        value['states'][0]['status'] = 'fulfilled'
        value['relations'][0]['relation'] = 'fulfilled_by'
        with self.assertRaisesRegex(ValueError, '客户背景不能'):
            reconcile.validate_merge(value, [self.old], [self.new], refs)

    def bundle(self):
        chapter = {group: [] for group in ('requirements', 'evolution', 'lifecycle', 'context', 'constraints')}
        chapter['constraints'] = [
            {'id': 'old', 'topic': '旧物流约定', 'claim': '旧合同包含前端查询及完整物流。', 'evidence': [{'reference_id': 'r_old'}]},
            {'id': 'new', 'topic': '物流分期', 'claim': '完整物流二期，查询保留。', 'evidence': [{'reference_id': 'r_new'}]},
        ]
        return {'coverage_complete': True, 'root': self.temp.name,
                'ledger': {'references': self.refs}, 'chapters': [{'key': 'chapter-1', 'chapter': chapter}]}

    def infer(self, context, prompt, schema):
        payload = json.loads(prompt.split('\nINPUT:\n')[1])
        if schema == reconcile.REVIEW_SCHEMA:
            return {'checks': [{'input_id': row['id'], 'verdict': 'preserved',
                                'explanation': '相应约定及未确认边界在状态中保留。'} for row in payload['incoming']]}
        states = copy.deepcopy(payload['previous_states'])
        bindings = [{'input_id': row['id'], 'state_ids': [row['id']]} for row in states]
        for index, row in enumerate(payload['incoming']):
            key = 'added-' + str(index)
            state = self.state(key, [item['reference_id'] for item in row['evidence']], [])
            del state['origin_ids']
            state['summary'] = row['fact']['claim']
            states.append(state)
            bindings.append({'input_id': row['id'], 'state_ids': [key]})
        return {'states': states, 'bindings': bindings, 'relations': []}

    def test_real_pipeline_resumes_and_rechecks_all_rows_against_final_states(self):
        calls = []
        def counted(*args):
            calls.append(args[2])
            return self.infer(*args)
        bundle = self.bundle()
        # Force two folds: this checks the old input survives a later fold, not
        # just that the local merge has two fields named old/new.
        original = reconcile.row_batches
        with patch.object(reconcile, 'row_batches', lambda rows: [[row] for row in rows]):
            result = reconcile.reconcile(self.context, bundle, counted)
            second = reconcile.reconcile(self.context, bundle, counted)
        self.assertEqual(len(calls), 4)  # 2 merges + 2 independent reviews, then cache reuse
        self.assertEqual(result, second)
        self.assertTrue(result['model_consistency_checked'])
        self.assertFalse(result['human_review_complete'])
        self.assertEqual({origin for state in result['states'] for origin in state['origin_ids']},
                         {row['id'] for row in reconcile.chapter_rows(bundle)})
        text = history.encoded(reconcile.decision_input(result))
        self.assertIn('旧合同包含', text)
        self.assertIn('查询保留', text)

    def test_semantic_conflict_blocks_publication_and_is_saved_for_correction(self):
        def conflict(context, prompt, schema):
            value = self.infer(context, prompt, schema)
            if schema == reconcile.REVIEW_SCHEMA:
                value['checks'][0].update(verdict='conflict', explanation='早期验收责任被忽略，需要恢复。')
            return value
        with self.assertRaisesRegex(ValueError, '语义冲突'):
            reconcile.reconcile(self.context, self.bundle(), conflict)
        path = next(Path(self.temp.name).glob('relations-*/result.json'))
        saved = json.loads(path.read_text())
        self.assertFalse(saved['model_consistency_checked'])
        self.assertEqual(saved['conflicts'][0]['explanation'], '早期验收责任被忽略，需要恢复。')
        with self.assertRaises(ValueError):
            reconcile.decision_input(saved)

    def test_review_missing_receipt_or_capacity_never_means_complete(self):
        with self.assertRaises(ValueError):
            reconcile.validate_review({'checks': []}, [self.new])
        with patch.object(reconcile, 'INPUT_CHARS', 10), self.assertRaisesRegex(ValueError, '未删除旧约定'):
            reconcile._payload([self.old], [self.new], self.refs)

    def test_yield_before_inference_does_not_consume_model_call(self):
        self.context['_should_yield'] = lambda: True
        with self.assertRaises(history.AnalysisYielded):
            reconcile.reconcile(self.context, self.bundle(), lambda *args: self.fail('model called'))


if __name__ == '__main__':
    unittest.main()
