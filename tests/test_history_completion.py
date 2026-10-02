import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import project_history_reconcile as r

class CompletionTests(unittest.TestCase):
    def fixture(self, root):
        context={'stable_fingerprint':'fingerprint','sources':[{'path':'合同','content':'原约定'}]}
        bundle={'root':str(root),'coverage_complete':True,'ledger':{'fingerprint':'a'*64},'chapters':[{}]}
        relations={'model_consistency_checked':True,'conflicts':[],'states':[{'origin_ids':['old','new']} ]}
        candidate={'understanding':{'evolution':[{'date':'2026-01-01'}],'lifecycle':[{'date':'2026-02-01'}]}}
        (root/'current-decision').mkdir()
        (root/'current-decision/review.json').write_text(json.dumps({'model_consistency_checked':True,'conflicts':[]}))
        return context,bundle,relations,candidate
    def test_receipt_binds_current_inputs_and_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            context,bundle,relations,candidate=self.fixture(Path(tmp))
            with patch.object(r,'chapter_rows',return_value=[{'id':'old'},{'id':'new'}]),patch.object(r.history,'history_rows',side_effect=lambda b,n:candidate['understanding'][n]):
                proof=r.completion_receipt(context,bundle,relations,candidate)
            result={'source_coverage':{'history_completion':proof},'analysis':candidate}
            self.assertTrue(r.validate_completion(result,context))
            for field in ('stable_fingerprint','sources'):
                changed=copy.deepcopy(context);changed[field]='changed'
                with self.assertRaises(ValueError):r.validate_completion(result,changed)
            changed=copy.deepcopy(result);changed['analysis']['understanding']['lifecycle']=[]
            with self.assertRaises(ValueError):r.validate_completion(changed,context)
    def test_no_completion_with_unrepresented_old_fact_or_conflicted_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            context,bundle,relations,candidate=self.fixture(Path(tmp))
            with patch.object(r,'chapter_rows',return_value=[{'id':'old'},{'id':'missing'}]):
                with self.assertRaisesRegex(ValueError,'未全部承接'):r.completion_receipt(context,bundle,relations,candidate)
            (Path(tmp)/'current-decision/review.json').write_text(json.dumps({'model_consistency_checked':False,'conflicts':['old obligation']}))
            with self.assertRaisesRegex(ValueError,'全部约定复核'):r.completion_receipt(context,bundle,relations,candidate)
    def test_boolean_without_bound_receipt_does_not_pass(self):
        with self.assertRaises(ValueError):r.validate_completion({'source_coverage':{'relation_model_checked':True}}, {'sources':[],'stable_fingerprint':'new'})
