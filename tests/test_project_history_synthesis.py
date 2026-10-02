import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import project_history_synthesis as history


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = [
            {'path': 'old.txt', 'date': '2026-01-03', 'relation': 'explicit_evidence',
             'content': '2026-01-03 我方书面方案包含完整物流，尚待客户确认。'},
            {'path': 'new.txt', 'date': '2026-02-04', 'relation': 'explicit_evidence',
             'content': '2026-02-04 客户要求完整物流另行讨论，但一期保留前端查询。'},
        ]
        self.context = {'sources': self.sources, 'project': {'id': 'example'},
                        'config': {'model': 'test', 'effort': 'ultra'}, '_state_root': str(self.root)}

    def infer(self, context, prompt, schema):
        data = json.loads(prompt.split('\nINPUT:\n', 1)[1])
        value = {name: [] for name in history.CHAPTER_SCHEMA['required']}
        for index, unit in enumerate(data['units']):
            row_id = 'constraint-' + str(index)
            row = {'id': row_id, 'topic': '物流分工', 'claim': unit['summary'],
                   'evidence': [{'reference_id': ref} for ref in unit['reference_ids']]}
            value['constraints'].append(row)
            value['coverage'].append({'unit_id': unit['id'], 'disposition': 'represented',
                                      'destinations': [row_id], 'reason': '保留范围与确认条件'})
        return value

    def test_inserted_source_reuses_intact_chapters_despite_shifted_boundaries(self):
        def individual(ledger, budget=None):
            return [[u] for u in ledger['units']]
        with patch.object(history, 'batches', side_effect=individual):
            old = history.prepare(self.context, self.infer)
        changed = {**self.context, 'sources': [{'path':'insert.txt','date':'2026-01-01','relation':'explicit_evidence','content':'新增内部范围说明，客户未确认。'}, *self.sources]}
        calls = []
        def infer(context, prompt, schema):
            calls.append(json.loads(prompt.split('\nINPUT:\n',1)[1])['units'])
            return self.infer(context, prompt, schema)
        new = history.prepare(changed, infer)
        old_ids = {u['id'] for u in old['ledger']['units']}
        generated = {u['id'] for batch in calls for u in batch}
        self.assertTrue(generated)
        self.assertFalse(old_ids & generated)
        all_ids = [row['unit_id'] for chapter in new['chapters'] for row in chapter['chapter']['coverage']]
        self.assertEqual(len(all_ids),len(set(all_ids)))
        self.assertEqual(set(all_ids),{u['id'] for u in new['ledger']['units']})
        self.assertTrue(new['coverage_complete'])
        resumed = history.prepare(changed, lambda *args: self.fail('unchanged completed chapters must resume without inference'))
        self.assertEqual([c['key'] for c in new['chapters']],[c['key'] for c in resumed['chapters']])

    def test_changed_model_does_not_reuse_chapters(self):
        history.prepare(self.context,self.infer)
        changed={**self.context,'config':{'model':'different','effort':'ultra'}}
        calls=[]
        def infer(context,prompt,schema):
            calls.append(True);return self.infer(context,prompt,schema)
        history.prepare(changed,infer)
        self.assertTrue(calls)

    def test_model_schema_only_allows_exact_batch_references(self):
        ledger = history.evidence_ledger(self.sources)
        units = ledger['units'][:1]
        schema = history.batch_schema(units)
        ref = schema['properties']['constraints']['items']['properties']['evidence']['items']['properties']['reference_id']
        self.assertEqual(set(ref['enum']),set(units[0]['reference_ids']))
        self.assertNotIn('enum',history.CHAPTER_SCHEMA['properties']['constraints']['items']['properties']['evidence']['items']['properties']['reference_id'])

    def test_every_character_block_has_verbatim_reference_and_old_constraints_survive(self):
        bundle = history.prepare(self.context, self.infer)
        self.assertTrue(bundle['coverage_complete'])
        self.assertFalse(bundle['semantic_review_complete'])
        decision = history.decision_input(bundle)
        text = history.encoded(decision)
        self.assertIn('完整物流', text)
        self.assertIn('一期保留前端查询', text)
        self.assertIn('尚待客户确认', text)
        for ref in bundle['ledger']['references'].values():
            source = next(s for s in self.sources if s['path'] == ref['path'])
            self.assertIn(ref['quote'], source['content'])

    def test_background_note_is_rebucketed_without_second_model_call(self):
        self.sources[0]['relation'] = 'background_reference'
        calls = []
        def counted(*args):
            calls.append(1)
            return self.infer(*args)
        bundle = history.prepare(self.context, counted)
        chapter = bundle['chapters'][0]['chapter']
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(chapter['context']), 1)
        self.assertEqual(len(chapter['constraints']), 1)
        self.assertEqual(chapter['context'][0]['claim'], self.sources[0]['content'])
        history.prepare(self.context, counted)
        self.assertEqual(len(calls), 1)

    def test_missing_row_link_is_repaired_without_rewriting_or_second_call(self):
        calls = []
        def counted(*args):
            calls.append(1)
            value = self.infer(*args)
            extra = copy.deepcopy(value['constraints'][0])
            extra['id'] = 'unlinked-note'
            value['constraints'].append(extra)
            return value
        bundle = history.prepare(self.context, counted)
        chapter = bundle['chapters'][0]['chapter']
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(chapter['constraints']), 3)
        self.assertIn('unlinked-note', chapter['coverage'][0]['destinations'])

    def test_mixed_background_and_project_constraint_requires_review(self):
        self.sources[0]['relation'] = 'background_reference'
        ledger = history.evidence_ledger(self.sources)
        units = ledger['units']
        value = self.infer({}, '\nINPUT:\n' + history.encoded(history.batch_input(units, ledger)), {})
        value['constraints'][0]['evidence'].extend(value['constraints'][1]['evidence'])
        before = copy.deepcopy(value)
        with self.assertRaises(ValueError):
            history.repair_chapter_bookkeeping(value, units, ledger)
        self.assertEqual(value, before)

    def test_missing_duplicated_or_dangling_receipts_are_rejected(self):
        ledger = history.evidence_ledger(self.sources)
        units = ledger['units']
        good = self.infer({}, '\nINPUT:\n' + history.encoded(history.batch_input(units, ledger)), {})
        for mode in ('missing', 'duplicate', 'dangling', 'wrong_reference'):
            value = copy.deepcopy(good)
            if mode == 'missing':
                value['coverage'].pop()
            elif mode == 'duplicate':
                value['coverage'].append(copy.deepcopy(value['coverage'][0]))
            elif mode == 'dangling':
                value['coverage'][0]['destinations'] = ['does-not-exist']
            else:
                value['constraints'][0]['evidence'] = [{'reference_id': 'fabricated'}]
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                history.validate_chapter(value, units, ledger)

    def test_coverage_error_identifies_missing_unit_and_unlinked_row(self):
        ledger = history.evidence_ledger(self.sources)
        units = ledger['units']
        value = self.infer({}, '\nINPUT:\n' + history.encoded(history.batch_input(units, ledger)), {})
        missing = value['coverage'].pop()
        with self.assertRaises(ValueError) as caught:
            history.validate_chapter(value, units, ledger)
        self.assertIn(missing['unit_id'], str(caught.exception))
        self.assertIn(missing['destinations'][0], str(caught.exception))
        self.assertIn('不得删除业务事实', str(caught.exception))

    def test_resume_does_not_repeat_valid_chapters_and_corrupt_cache_is_recomputed(self):
        calls = []
        def counted(*args):
            calls.append(1)
            return self.infer(*args)
        first = history.prepare(self.context, counted)
        self.assertEqual(len(calls), 1)
        second = history.prepare(self.context, counted)
        self.assertEqual(len(calls), 1)
        path = next(Path(first['root']).glob('chapter-*.json'))
        content = json.loads(path.read_text())
        content['chapter']['coverage'] = []
        path.write_text(json.dumps(content))
        history.prepare(self.context, counted)
        self.assertEqual(len(calls), 2)
        self.assertEqual(first['ledger'], second['ledger'])

    def test_source_change_cannot_reuse_old_chapters(self):
        first = history.prepare(self.context, self.infer)
        self.sources[1]['content'] += '2026-03-04 查询改由第三方承担。'
        second = history.prepare(self.context, self.infer)
        self.assertNotEqual(first['root'], second['root'])
        self.assertTrue(Path(first['root']).exists())

    def test_capacity_refuses_instead_of_deleting_earlier_constraints(self):
        bundle = history.prepare(self.context, self.infer)
        before = copy.deepcopy(bundle)
        with patch.object(history, 'DECISION_CHARS', 10), self.assertRaisesRegex(ValueError, '未删减历史'):
            history.decision_input(bundle)
        self.assertEqual(bundle, before)

    def test_new_snapshot_reuses_only_unchanged_valid_batches(self):
        calls = []
        def counted(*args):
            calls.append(1)
            return self.infer(*args)
        with patch.object(history, 'batches', lambda ledger: [[u] for u in ledger['units']]):
            first = history.prepare(self.context, counted)
            self.sources[1]['content'] += ' 查询改由第三方承担。'
            second = history.prepare(self.context, counted)
        self.assertNotEqual(first['root'], second['root'])
        self.assertEqual(len(calls), 3)
        reused = [json.loads(p.read_text()) for p in Path(second['root']).glob('chapter-*.json')]
        self.assertEqual(sum('reused_from' in row for row in reused), 1)
        self.assertFalse(second['semantic_review_complete'])

    def test_invalid_sibling_cache_is_not_reused(self):
        calls = []
        def counted(*args):
            calls.append(1)
            return self.infer(*args)
        with patch.object(history, 'batches', lambda ledger: [[u] for u in ledger['units']]):
            first = history.prepare(self.context, counted)
            for path in Path(first['root']).glob('chapter-*.json'):
                cached = json.loads(path.read_text())
                cached['chapter']['coverage'] = []
                path.write_text(json.dumps(cached))
            self.sources[1]['content'] += ' 查询改由第三方承担。'
            history.prepare(self.context, counted)
        self.assertEqual(len(calls), 4)

    def test_model_config_change_does_not_reuse_chapters(self):
        calls = []
        def counted(*args):
            calls.append(1)
            return self.infer(*args)
        history.prepare(self.context, counted)
        self.context['config']['model'] = 'different-model'
        history.prepare(self.context, counted)
        self.assertEqual(len(calls), 2)

    def test_cancellation_and_yield_prevent_next_model_call(self):
        for key, value, error in [('_should_yield', lambda: True, history.AnalysisYielded),
                                  ('_cancel_inference_requested', True, ValueError)]:
            context = {**self.context, key: value}
            with self.subTest(key=key), self.assertRaises(error):
                history.prepare(context, lambda *args: self.fail('must not invoke model'))

    def test_assembly_keeps_all_history_and_never_accepts_fabricated_quote(self):
        bundle = history.prepare(self.context, self.infer)
        refs = list(bundle['ledger']['references'])
        for index, chapter in enumerate(bundle['chapters']):
            chapter['chapter']['lifecycle'] = [
                {'id': 'first', 'date': '2026-01-03', 'title': '首次方案', 'category': '业务起点',
                 'event': '我方提出完整物流', 'consequence': '形成待确认方案',
                 'confirmation': '我方方案，未获客户确认', 'evidence': [{'reference_id': refs[0]}]},
                {'id': 'later', 'date': '2026-02-04', 'title': '重新分期', 'category': '需求变化',
                 'event': '客户提出物流另议并保留查询', 'consequence': '物流和前端查询不能一并取消',
                 'confirmation': '客户要求，最终冻结待核', 'evidence': [{'reference_id': refs[1]}]},
            ]
        candidate = {'understanding': {'lifecycle': [], 'evolution': []},
                     'evidence': [{'reference_id': refs[0]}]}
        result = history.assemble(candidate, bundle)
        self.assertEqual(len(result['understanding']['lifecycle']), 2)
        self.assertEqual(result['evidence'][0]['quote'], self.sources[0]['content'])
        self.assertEqual(candidate['understanding']['lifecycle'], [])
        with self.assertRaisesRegex(ValueError, '不存在'):
            history.assemble({'understanding': {}, 'evidence': [{'reference_id': 'invented'}]}, bundle)

    def test_long_verbatim_quotes_split_without_losing_non_whitespace_content(self):
        quote = '旧报价和条件。' * 400
        source = {'path': 'long.txt', 'content': quote, 'extracted': True,
                  'original_quotes': [quote], 'digest_entries': [{'summary': '原商业约定', 'quote': quote}]}
        ledger = history.evidence_ledger([source])
        recovered = ''.join(ledger['references'][key]['quote'] for key in ledger['units'][0]['reference_ids'])
        self.assertEqual(recovered, quote)
        self.assertTrue(all(len(ref['quote']) <= 700 for ref in ledger['references'].values()))

    def test_previously_extracted_business_fact_cannot_be_relabelled_non_business(self):
        source = {**self.sources[0], 'extracted': True, 'original_quotes': [self.sources[0]['content']],
                  'digest_entries': [{'summary': '仍待确认的物流范围', 'quote': self.sources[0]['content']}]}
        ledger = history.evidence_ledger([source])
        value = {name: [] for name in history.CHAPTER_SCHEMA['required']}
        value['coverage'] = [{'unit_id': ledger['units'][0]['id'], 'disposition': 'non_business',
                              'destinations': [], 'reason': '不能把已抽取业务事实以无意义丢弃'}]
        with self.assertRaisesRegex(ValueError, '业务事实不能'):
            history.validate_chapter(value, ledger['units'], ledger)

    def test_background_cannot_become_contract_constraint(self):
        source = {**self.sources[0], 'relation': 'customer_background'}
        ledger = history.evidence_ledger([source])
        value = self.infer({}, '\nINPUT:\n' + history.encoded(history.batch_input(ledger['units'], ledger)), {})
        with self.assertRaisesRegex(ValueError, '背景材料不能'):
            history.validate_chapter(value, ledger['units'], ledger)

    def test_rejected_chapter_retries_only_itself_with_the_validation_reason(self):
        prompts = []
        def infer(context, prompt, schema):
            prompts.append(prompt)
            value = self.infer(context, prompt, schema)
            if len(prompts) == 1:
                value['coverage'] = []
            return value
        result = history.prepare(self.context, infer)
        self.assertTrue(result['coverage_complete'])
        self.assertEqual(len(prompts), 2)
        self.assertIn('历史章节覆盖不完整', prompts[1])
        self.assertEqual(len(list((Path(result['root']) / 'rejected').glob('*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
