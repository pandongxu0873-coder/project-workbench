import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import workbench_agent as a

class RoutingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'knowledge';self.root.mkdir();self.state=Path(self.tmp.name)/'state';self.cid='b'*32
  self.v={'id':self.cid,'title':'核对','created_at':a.now(),'updated_at':a.now(),'status':'running','archived':False,'phase':'','messages':[{'role':'user','content':'找合同','created_at':a.now()}]};a.write(self.state,self.v);a.ACTIVE.add(self.cid)
 def tearDown(self):a.ACTIVE.clear();self.tmp.cleanup()
 def result(self,deep=False):return {'answer':'据原文尚待反馈，未确认接受。','sources':[],'needs_deep':deep,'reason':'来源冲突' if deep else ''}
 def test_simple_and_explicit_deep(self):
  self.assertEqual(a.routing(self.v),'fast');self.assertEqual(a.routing(self.v,'deep'),'deep')
 def test_strategy_and_ambiguous_followup_deep(self):
  self.v['messages'][-1]['content']='客户下一步怎么打';self.assertEqual(a.routing(self.v),'deep')
  self.v['messages']=[{'role':'assistant','content':'分析','route':'deep'},{'role':'user','content':'为什么？'}];self.assertEqual(a.routing(self.v),'deep')
 def test_invalid_mode_rejected_without_write(self):
  with self.assertRaises(ValueError):a.submit(self.state,self.root,self.cid,'找合同','request-123','invalid')
  self.assertEqual(len(a.read(self.state,self.cid)['messages']),1)
 def test_retry_different_mode_rejected(self):
  self.v.update(status='idle');self.v['messages']=[];a.write(self.state,self.v);a.ACTIVE.clear()
  with patch('workbench_agent.threading.Thread'):
   a.submit(self.state,self.root,self.cid,'找合同','request-123','auto')
   with self.assertRaises(ValueError):a.submit(self.state,self.root,self.cid,'找合同','request-123','deep')
 def test_missing_or_corrupt_index_is_hint_gap_not_failed_job(self):
  self.assertIn('索引不可用',a.handoff(self.root,self.state,'找合同')['index_gap'])
  (self.root/'tracking').mkdir();(self.root/'tracking/material_library.json').write_text('broken')
  self.assertIn('索引不可用',a.handoff(self.root,self.state,'找合同')['index_gap'])
 def test_fast_answer_and_backend_unchanged(self):
  with patch.object(a,'executable',return_value='codex'),patch.object(a,'model',return_value='configured'),patch.object(a,'invoke',return_value=self.result()) as inv:
   a.run(self.state,self.root,self.cid)
  self.assertEqual(inv.call_count,1);self.assertEqual(inv.call_args.args[4:7],(a.FAST_MODEL,'low','fast'));self.assertEqual(a.read(self.state,self.cid)['messages'][-1]['route'],'fast')
 def test_escalation_only_one_final_answer(self):
  with patch.object(a,'executable',return_value='codex'),patch.object(a,'model',return_value='configured'),patch.object(a,'invoke',side_effect=[self.result(True),self.result()]) as inv:a.run(self.state,self.root,self.cid)
  self.assertEqual(inv.call_count,2);self.assertEqual(inv.call_args.args[4:7],('configured','high','deep'));v=a.read(self.state,self.cid);self.assertEqual(len(v['messages']),2);self.assertEqual(v['messages'][-1]['route'],'deep')
 def test_quick_failure_falls_back_once(self):
  with patch.object(a,'executable',return_value='codex'),patch.object(a,'model',return_value='configured'),patch.object(a,'invoke',side_effect=[ValueError('unavailable'),self.result()]) as inv:a.run(self.state,self.root,self.cid)
  self.assertEqual(inv.call_count,2);self.assertEqual(a.read(self.state,self.cid)['status'],'completed')
 def test_cancel_between_lanes_preserves_no_answer(self):
  def first(*args):a.cancel(self.state,self.cid);return self.result(True)
  # Actual invoke must check status before opening a process, after the first pass cancels.
  original=a.invoke
  def side(*args):
   if args[6]=='fast':return first(*args)
   return original(*args)
  with patch.object(a,'executable',return_value='codex'),patch.object(a,'model',return_value='configured'),patch.object(a,'invoke',side_effect=side),patch.object(a.subprocess,'Popen') as process:a.run(self.state,self.root,self.cid)
  process.assert_not_called();self.assertEqual(a.read(self.state,self.cid)['status'],'cancelled');self.assertEqual(len(a.read(self.state,self.cid)['messages']),1)

 def test_malformed_cache_hint_does_not_block_original_retrieval(self):
  import hashlib,json
  (self.root/'projects').mkdir();source=self.root/'projects/测试客户.md';source.write_text('# 测试客户\n项目说明')
  pid=hashlib.sha256('projects/测试客户.md'.encode()).hexdigest()[:20];cache=self.state/'project_analysis';cache.mkdir()
  for value in [{'result':{'analysis':'bad'}},{'result':[]},[]]:
   (cache/f'{pid}.json').write_text(json.dumps(value));h=a.handoff(self.root,self.state,'查测试客户');self.assertEqual(h['projects'][0]['project_source'],str(source.resolve()))

 def test_summary_excluding_strategy_stays_fast(self):
  self.v['messages'][-1]['content']='汇总客户理解的金额，区分已确认和待核实，不给策略建议。';self.assertEqual(a.routing(self.v),'fast')
