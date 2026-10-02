import copy
from datetime import date
import json
import tempfile
import unittest

import project_analysis as ai
import project_history_synthesis as history
import project_history_reconcile as reconcile
import test_project_analysis as analysis_fixtures


class FinalIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        source = {'path': 'project.txt', 'date': '', 'relation': 'explicit_evidence',
                  'content': '客户要求先核对范围，完整物流分期但前端查询保留。'}
        self.context = {'sources': [source], 'config': {'model': 'test', 'effort': 'ultra'},
                        'today': date.today().isoformat(), 'local': {'record': {}, 'revision': 0},
                        'correction': '', 'project': {'id': 'test', 'title': '测试项目'}}
        full = analysis_fixtures.AnalysisTests.response(None, self.context)
        ledger = history.evidence_ledger([source])
        ref_id = next(iter(ledger['references']))

        def to_ref(value):
            if isinstance(value, list):
                return [to_ref(item) for item in value]
            if not isinstance(value, dict):
                return value
            if set(value) == {'path', 'quote'}:
                return {'reference_id': ref_id}
            return {key: to_ref(item) for key, item in value.items()}

        output = to_ref(full)
        chapter = {name: [] for name in ('requirements', 'evolution', 'lifecycle', 'context', 'constraints')}
        for name in ('evolution', 'lifecycle'):
            chapter[name] = [{'id': name + '-original', **row} for row in output['understanding'][name]]
            output['understanding'][name] = []
        self.bundle = {'coverage_complete': True, 'root': self.temp.name, 'ledger': ledger,
                       'chapters': [{'key': 'chapter1', 'chapter': chapter}]}
        self.relations = {'model_consistency_checked': True, 'conflicts': [], 'states': [
            {'id': 'state1', 'kind': 'requirement', 'topic': '当前范围', 'status': 'unresolved',
             'summary': source['content'], 'applicability': '最终冻结待核实',
             'evidence': [{'reference_id': ref_id}], 'origin_ids': ['fact1']}]}
        self.output = output

    def infer(self, context, prompt, schema):
        if schema == reconcile.REVIEW_SCHEMA:
            payload = json.loads(prompt.split('\nINPUT:\n', 1)[1])
            return {'checks': [{'input_id': row['id'], 'verdict': 'preserved',
                                'explanation': '未将分期等同取消，仍明确范围待核实。'} for row in payload['incoming']]}
        self.assertEqual(schema['properties']['understanding']['properties']['evolution']['maxItems'], 0)
        return copy.deepcopy(self.output)

    def run_final(self, infer=None):
        return reconcile.synthesize(self.context, self.bundle, self.relations, infer or self.infer,
                                    '测试整体分析规则。', ai.SCHEMA, ai.validate_result)

    def test_full_schema_validation_after_history_assembly_and_quote_hydration(self):
        result = self.run_final()
        self.assertEqual(len(result['understanding']['evolution']), 1)
        self.assertEqual(len(result['understanding']['lifecycle']), 1)
        self.assertEqual(result['evidence'][0]['path'], 'project.txt')
        self.assertEqual(result['evidence'][0]['quote'], self.context['sources'][0]['content'])
        self.assertIs(ai.validate_result(result, self.context['sources']), result)
        self.assertEqual(self.output['understanding']['lifecycle'], [])

    def test_final_model_cannot_replace_retained_history(self):
        def changed(context, prompt, schema):
            value = self.infer(context, prompt, schema)
            if schema != reconcile.REVIEW_SCHEMA:
                value['understanding']['evolution'] = copy.deepcopy(self.bundle['chapters'][0]['chapter']['evolution'])
                value['understanding']['evolution'][0].pop('id')
            return value
        with self.assertRaisesRegex(ValueError, '数组无效'):
            self.run_final(changed)

    def test_final_advice_mismatch_is_not_published_even_if_schema_is_valid(self):
        def conflict(context, prompt, schema):
            value = self.infer(context, prompt, schema)
            if schema == reconcile.REVIEW_SCHEMA:
                value['checks'][0].update(verdict='conflict', explanation='当前建议与早期承诺矛盾。')
            return value
        with self.assertRaisesRegex(ValueError, '最终建议与持续约定存在冲突'):
            self.run_final(conflict)


if __name__ == '__main__':
    unittest.main()
