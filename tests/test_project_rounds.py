import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import project_rounds as rounds
from project_workspace import build_projects

class RoundTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.knowledge = self.root / 'knowledge'
        self.state = self.root / 'state'
        (self.knowledge / 'projects').mkdir(parents=True)
        for name in ('one', 'two'):
            (self.knowledge / 'projects' / f'{name}.md').write_text(f'# {name}\n客户 项目\n## 当前判断\n待核实\n')
        self.ids = [p['id'] for p in build_projects(self.knowledge,self.state)]
        self.payload = dict(project_id=self.ids[0],revision=0,scenario='return',relationship='unknown',status='准备中',facts='真实来源的隔离演练')
    def save(self, **updates):
        return rounds.save_round({**self.payload, **updates},self.knowledge,self.state)
    def read(self, project_id=None):
        return rounds.read_round(project_id or self.ids[0],self.knowledge,self.state)
    def test_roundtrip_history_conflict_isolation_and_sources_unchanged(self):
        before = {p:p.read_bytes() for p in self.knowledge.rglob('*.md')}
        first = self.save()
        second = self.save(revision=1,feedback='售前回复需补材料',status='已收到反馈')
        self.assertEqual(self.read(),second)
        self.assertEqual(second['history'][0]['record'],first['record'])
        self.assertEqual(self.read(self.ids[1])['revision'],0)
        with self.assertRaises(rounds.RevisionConflict): self.save()
        self.assertEqual(self.read(),second)
        self.assertEqual(before,{p:p.read_bytes() for p in self.knowledge.rglob('*.md')})
    def test_strict_validation(self):
        for updates in [dict(project_id='../escape'),dict(revision=True),dict(revision='0'),dict(scenario='fake'),dict(relationship='fake'),dict(status='已完成'),dict(due='2026-02-30'),dict(due='20260101'),dict(facts=[]),dict(facts=''),dict(status='本轮完成')]:
            with self.subTest(updates=updates), self.assertRaises(ValueError): self.save(**updates)
        self.assertEqual(self.read()['revision'],0)
    def test_no_contact_requires_new_fact_to_resume(self):
        self.save(relationship='no_contact')
        self.save(revision=1,relationship='no_contact',scenario='first')
        with self.assertRaises(ValueError): self.save(revision=2,relationship='unknown')
        self.assertEqual(self.save(revision=2,relationship='unknown',recontact_basis='客户明确邀请再次沟通')['revision'],3)
    def test_second_pause_requires_fresh_basis(self):
        self.save(relationship='no_contact')
        self.save(revision=1,relationship='unknown',recontact_basis='第一次客户邀请')
        paused = self.save(revision=2,relationship='no_contact',recontact_basis='第一次客户邀请')
        self.assertEqual(paused['record']['recontact_basis'], '')
        with self.assertRaises(ValueError): self.save(revision=3,relationship='unknown')

    def test_valid_json_corruption_rejected_in_every_history(self):
        prior = self.save()
        path = self.state/'project_rounds'/f'{self.ids[0]}.json'
        for field, value in [('scenario','corrupt'),('relationship',None),('due','bad'),('status','本轮完成'),('facts',{}),('saved_at','bad')]:
            corrupted = json.loads(json.dumps(prior))
            corrupted['record'][field] = value
            corrupted['history'][0]['record'][field] = value
            path.write_text(json.dumps(corrupted))
            with self.subTest(field=field), self.assertRaises(ValueError): self.read()
            with self.assertRaises(ValueError): self.save(revision=1)
        corrupted = json.loads(json.dumps(prior))
        corrupted['history'][0]['revision'] = True
        path.write_text(json.dumps(corrupted))
        with self.assertRaises(ValueError): self.read()

    def test_atomic_failure_preserves_previous_history(self):
        prior=self.save()
        with patch('project_rounds.os.replace',side_effect=OSError('simulated write failure')):
            with self.assertRaises(OSError): self.save(revision=1,feedback='新反馈')
        self.assertEqual(self.read(),prior)
    def test_corruption_fails_closed(self):
        self.save()
        path=self.state/'project_rounds'/f'{self.ids[0]}.json'
        path.write_text('{bad')
        with self.assertRaises(ValueError): self.save(revision=1)
        self.assertEqual(path.read_text(),'{bad')
    def test_minimal_feedback_and_waiting_preserved(self):
        saved=self.save(facts='',feedback='尚未收到回复',status='已发出等待反馈')
        self.assertEqual(saved['record']['relationship'],'unknown')
        self.assertEqual(saved['record']['status'],'已发出等待反馈')

    def test_followups_are_one_current_projection_and_never_write_sources(self):
        from datetime import date
        today=date(2026,9,7)
        before={p:p.read_bytes() for p in self.knowledge.rglob('*.md')}
        first=self.save(action='复核范围',next_step='收到反馈后给方案',due='2026-09-07')
        rows=lambda: rounds.followups(self.knowledge,self.state,today)['items']
        self.assertEqual(len(rows()),1);self.assertEqual(rows()[0]['schedule_bucket'],'today')
        identity=rows()[0]['id']
        self.save(revision=1,action='复核范围',due='2026-09-10')
        self.assertEqual(len(rows()),1);self.assertEqual(rows()[0]['id'],identity)
        self.assertEqual(rows()[0]['schedule_bucket'],'future')
        with self.assertRaises(rounds.RevisionConflict):self.save(revision=1)
        self.assertEqual(rows()[0]['due'],'2026-09-10')
        self.save(revision=2,status='已收到反馈',feedback='客户要求补边界',next_step='补边界',due='2026-09-08')
        self.assertEqual(rows()[0]['next_step'],'补边界')
        self.save(revision=3,status='本轮完成',feedback='范围已核对',due='2026-09-07')
        self.assertEqual(rows(),[])
        self.save(revision=4,status='暂停跟进',due='2026-09-06');self.assertEqual(rows(),[])
        self.save(revision=5,relationship='no_contact',due='2026-09-06');self.assertEqual(rows(),[])
        self.assertEqual(self.read()['history'][0]['record'],first['record'])
        self.assertEqual(before,{p:p.read_bytes() for p in self.knowledge.rglob('*.md')})
        self.assertEqual({p.name for p in self.state.iterdir()},{'project_rounds'})

    def test_followups_surface_corruption_without_hiding_healthy_projects(self):
        self.save()
        self.save(project_id=self.ids[1],action='隔离客户二的动作',due='2026-09-06')
        (self.state/'project_rounds'/f'{self.ids[0]}.json').write_text('{bad')
        result=rounds.followups(self.knowledge,self.state)
        self.assertEqual(len(result['errors']),1);self.assertEqual(result['items'][0]['project_id'],self.ids[1])

if __name__ == '__main__': unittest.main()
