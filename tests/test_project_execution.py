import tempfile
import unittest
from pathlib import Path
from datetime import date
import project_execution as execution

class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.addCleanup(self.temp.cleanup)
        self.pid='a'*20;self.aid='b'*32;self.day=date.today().isoformat()
        self.source={'path':'raw/transcripts/customer.md','date':self.day,'content':'客户此前要求核对范围。','relation':'explicit_evidence'}
        self.record={'quick_outcome':'done','analysis_id':self.aid,'saved_at':self.day+'T10:00:00+08:00'}
        execution.save_basis(self.root,self.pid,self.aid,[self.source])
    def state(self,sources,quote='客户此前要求核对范围。',path=None,**kw):
        return execution.execution_state(self.record,sources,{'evidence':[{'path':path or self.source['path'],'quote':quote}]},self.root,self.pid,**kw)
    def test_rewrite_round_runtime_changes_do_not_unlock(self):
        for new in [[],[{'path':'local://round','content':'本轮完成，保存日期变化'}],[{'path':'local://action/abc','content':'改了提醒日期'}]]:
            self.assertEqual(self.state([self.source,*new]),'done_waiting')
    def test_same_day_real_new_cited_reply_can_unlock(self):
        new={**self.source,'content':self.source['content']+'客户今天回复：请再次发送修改版清单。'}
        self.assertEqual(self.state([new],quote='请再次发送修改版清单。'),'actionable')
        self.assertEqual(self.state([new]),'new_evidence_review')
        self.assertEqual(self.state([new],quote='请再次发送修改版清单。',stale=True),'new_evidence_review')
    def test_internal_progress_cannot_unlock_completed_action_awaiting_customer_result(self):
        new={**self.source,'content':'内部进度：104个SKU已初始化，均下架；未收到客户复盘结果。'}
        analysis={'brief':{'attention':'等反馈'},'evidence':[{'path':new['path'],'quote':'104个SKU已初始化'}]}
        self.assertEqual(execution.execution_state(self.record,[new],analysis,self.root,self.pid),'done_waiting')
        analysis.pop('brief');analysis['execution_signal']='waiting_feedback'
        self.assertEqual(execution.execution_state(self.record,[new],analysis,self.root,self.pid),'done_waiting')
    def test_old_unknown_duplicate_and_other_project_never_unlock(self):
        for day in ['', '2020-01-01']:
            new={**self.source,'date':day,'content':'这是一份重新归档的旧客户意见。'}
            self.assertEqual(self.state([new],quote=new['content']),'new_evidence_review')
        duplicate={**self.source,'path':'raw/transcripts/rearchive.md'}
        self.assertEqual(self.state([self.source,duplicate],path=duplicate['path']),'new_evidence_review')
        background={**self.source,'content':'独立项目的新消息。','relation':'background_reference'}
        self.assertEqual(self.state([background],quote=background['content']),'done_waiting')
    def test_pause_undo_and_legacy(self):
        self.record['relationship']='no_contact';self.assertEqual(self.state([self.source]),'paused')
        self.record.pop('relationship');self.record['quick_outcome']='undo';self.assertEqual(self.state([self.source]),'actionable')
        self.record['quick_outcome']='done';self.record['analysis_id']='c'*32;self.assertEqual(self.state([self.source]),'done_waiting')
        self.record['analysis_id']='../../outside';self.assertEqual(self.state([self.source]),'done_waiting')
    def test_editorial_project_summary_cannot_unlock_but_actual_receipt_can(self):
        source={**self.source,'relation':'project_source','content':'新增编辑说明：仅调整段落措辞。'}
        self.assertEqual(self.state([source],quote='仅调整段落措辞'),'new_evidence_review')
        receipt={'path':'local://receipt/new','date':self.day,'content':'实际反馈：客户要求重新发送修改版清单。','feedback_content':'客户要求重新发送修改版清单。','relation':'execution_receipt'}
        self.assertEqual(self.state([self.source,receipt],quote=receipt['feedback_content'],path=receipt['path']),'actionable')
        self.assertEqual(self.state([self.source,receipt],quote='实际反馈：',path=receipt['path']),'new_evidence_review')
    def test_legacy_done_requires_strictly_later_original_feedback(self):
        self.record['analysis_id']='c'*32
        self.record['saved_at']='2020-01-01T10:00:00+08:00'
        source={**self.source,'content':'客户明确要求重新发送修改清单。'}
        self.assertEqual(self.state([source],quote=source['content']),'actionable')
        source['date']='2020-01-01'
        self.assertEqual(self.state([source],quote=source['content']),'done_waiting')
