import json
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch
from datetime import date, timedelta, datetime
import server
import project_activity as activity
import project_analysis as analysis
import project_rounds as rounds
from project_workspace import build_projects

class ProjectCoreFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.k = self.root/'knowledge'; self.state = self.root/'state'; self.state.mkdir()
        (self.k/'projects').mkdir(parents=True); (self.k/'raw').mkdir()
        for name in ('甲','乙'):
            (self.k/'raw'/f'{name}.md').write_text(f'隔离夹具：{name}范围待核。')
            (self.k/'projects'/f'{name}.md').write_text(f'---\nsources: ["raw/{name}.md"]\n---\n# 项目{name}\n**客户**：[[同一客户]]\n')
        self.projects = build_projects(self.k, self.state)
        self.a, self.b = self.projects

    def round(self, project=None, revision=0, **changes):
        return rounds.save_round(dict(project_id=(project or self.a)['id'],revision=revision,scenario='return',relationship='unknown',status=changes.pop('status','准备中'),facts='隔离测试',action='核对范围',due=date.today().isoformat(), **changes),self.k,self.state)

    def risk(self):
        with ExitStack() as stack:
            for key,val in {'SALES_WORKBENCH_KNOWLEDGE_ROOT':self.k,'WORKBENCH_DATA_ROOT':self.state}.items(): stack.enter_context(patch.object(server,key,val))
            for key,val in {'account_store_rows':[],'load_workflow_state':{},'load_risk_todos':[],'load_feishu_reminder_delivery_state':{}}.items(): stack.enter_context(patch.object(server,key,return_value=val))
            return server.risk_todos_payload()

    def test_one_shared_action_per_project_reschedule_complete_pause(self):
        before={p:p.read_bytes() for p in self.k.rglob('*.md')}
        self.round(); self.round(self.b)
        rows=self.risk()['items']; self.assertEqual(len(rows),2)
        self.assertFalse(server.is_similar_schedule_item(rows[0],rows[1]))
        self.assertEqual(len(server.dedupe_similar_schedule_items(rows)),2)
        identity=next(i['id'] for i in rows if i['project_id']==self.a['id'])
        updated=rounds.read_round(self.a['id'],self.k,self.state)
        rounds.save_round(dict(project_id=self.a['id'],revision=1,**{**updated['record'],'due':(date.today()+timedelta(days=3)).isoformat()}),self.k,self.state)
        row=next(i for i in self.risk()['items'] if i['project_id']==self.a['id'])
        self.assertEqual(row['id'],identity); self.assertEqual(row['schedule_bucket'],'future')
        self.assertFalse(server.feishu_reminder_gate(row,datetime.now(server.LOCAL_TZ))['eligible'])
        self.assertFalse(server.is_feishu_message_todo({**row,'calendar':{'task_guid':'fixture-only'}}))
        self.round(revision=2,status='本轮完成',feedback='本轮已核对')
        self.assertEqual([r['project_id'] for r in self.risk()['items']],[self.b['id']])
        self.round(self.b,revision=1,status='暂停跟进')
        self.assertEqual(self.risk()['items'],[])
        self.assertEqual(before,{p:p.read_bytes() for p in self.k.rglob('*.md')})

    def test_round_cannot_be_written_through_legacy_form(self):
        with self.assertRaisesRegex(ValueError,'项目执行记录'):
            server.submit_risk_evidence_impl({'todo_id':'round:'+self.a['id']})

    def test_activity_identity_dates_and_targeted_fingerprint(self):
        first={p['id']:analysis.packet(p['id'],'',self.k,self.state)['fingerprint'] for p in self.projects}
        receipt=dict(id='fixture-receipt',project_id=self.a['id'],action_id='a',status='已处理',resolution='范围已核',submitted_at='2026-09-07T18:00:00+08:00')
        (self.state/'workflow_state.json').write_text(json.dumps({'receipts':[receipt], 'schedule_status':{'a':{'receipt':receipt}}}))
        self.assertEqual(len(activity.business_sources(self.a,self.state)),1)
        source=activity.business_sources(self.a,self.state)[0]; self.assertEqual(source['date'],''); self.assertTrue(source['recorded_at'])
        self.assertNotEqual(first[self.a['id']],analysis.packet(self.a['id'],'',self.k,self.state)['fingerprint'])
        self.assertEqual(first[self.b['id']],analysis.packet(self.b['id'],'',self.k,self.state)['fingerprint'])
        self.assertIsNone(activity.project_owner({'customer':'同一客户'},self.projects))
        shared=[{**p,'sources':[{'path':'raw/shared.md'}]} for p in self.projects]
        self.assertIsNone(activity.project_owner({'source_path':'raw/shared.md'},shared))
        self.assertEqual(activity.project_owner({'project_source':self.a['source_path']},self.projects)['id'],self.a['id'])
        (self.state/'workflow_state.json').write_text('{corrupt')
        with self.assertRaises(ValueError): analysis.packet(self.a['id'],'',self.k,self.state)

    def test_existing_action_inherits_identity_and_completed_round_does_not_resurrect_it(self):
        origin=dict(id='legacy-a',project_id=self.a['id'],project_source=self.a['source_path'],title='旧行动',status='推进中',deadline=(date.today()+timedelta(days=2)).isoformat(),next_step='核对范围',source_scope='workflow_receipt')
        (self.state/'risk_todos.json').write_text(json.dumps([origin]))
        packet=analysis.packet(self.a['id'],'',self.k,self.state)
        source=next(s for s in packet['sources'] if s['path'].startswith('local://action/'))
        result=dict(analysis_id='fixture',source_snapshot=packet['sources'],analysis=dict(judgement='承接现有范围',next_action='继续核对范围',role='售前',acceptance='范围明确',evidence=[dict(path=source['path'],quote='旧行动')]))
        with patch('project_analysis.status',return_value=dict(result=result,stale=False,state='ready')):
            saved=analysis.adopt(dict(project_id=self.a['id'],revision=0,analysis_id='fixture'),self.k,self.state)
        self.assertEqual(saved['record']['origin_action_id'],'legacy-a'); self.assertEqual(saved['record']['due'],origin['deadline'])
        self.assertEqual(rounds.followups(self.k,self.state)['claimed_actions'],{'legacy-a':self.a['id']})
        self.assertEqual(activity.active_actions(self.a,self.state),[])
        with self.assertRaises(ValueError): self.round(self.b,origin_action_id='legacy-a')
        with patch.object(server,'SALES_WORKBENCH_KNOWLEDGE_ROOT',self.k),patch.object(server,'WORKBENCH_DATA_ROOT',self.state):
            with self.assertRaisesRegex(ValueError,'项目执行记录'): server.submit_risk_evidence_impl(dict(todo_id='legacy-a'))
        result['analysis']['evidence'] = [dict(path='local://round',quote='核对范围')]
        with patch('project_analysis.status',return_value=dict(result=result,stale=False,state='ready')):
            continued=analysis.adopt(dict(project_id=self.a['id'],revision=1,analysis_id='fixture'),self.k,self.state)
        self.assertEqual(continued['record']['due'],origin['deadline'])
        self.round(revision=2,status='本轮完成',feedback='范围已核')
        self.assertEqual(rounds.followups(self.k,self.state)['items'],[])
        self.assertEqual(rounds.followups(self.k,self.state)['claimed_actions'],{'legacy-a':self.a['id']})
        self.assertEqual(activity.active_actions(self.a,self.state),[])

    def test_account_next_actions_do_not_clobber_other_project(self):
        conn=sqlite3.connect(':memory:'); conn.row_factory=sqlite3.Row
        conn.execute('CREATE TABLE accounts (id TEXT,payload_json TEXT,updated_at TEXT)')
        conn.execute('INSERT INTO accounts VALUES (?,?,?)',('fixture',json.dumps({'next_action':'乙项目尚未安排日期的下一步','next_action_source':'主账本'}),''))
        @contextmanager
        def connection(): yield conn
        with patch.object(server,'initialize_account_store'),patch.object(server,'account_store_connection',connection):
            for pid,aid in [('a','action-a'),('b','action-b')]:
                server.apply_receipt_to_account('fixture','同一客户','已沟通',pid+'下一步','推进中','receipt-'+aid,pid,aid)
            server.apply_receipt_to_account('fixture','同一客户','已完成','','已处理','receipt-closed','a','action-a')
        record=json.loads(conn.execute('SELECT payload_json FROM accounts').fetchone()[0]); conn.close()
        self.assertEqual(list(record['working_actions']),['action-b']); self.assertEqual(record['next_action'],'乙项目尚未安排日期的下一步；b下一步')
        self.assertEqual(record['interaction_history'][0]['project_id'],'a')
