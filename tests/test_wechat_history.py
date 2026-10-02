import copy
import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
import sys
from unittest.mock import patch,MagicMock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'wechat-local'))
spec=importlib.util.spec_from_file_location('wechat_history_workflow',ROOT/'wechat-local/history_workflow.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)


class HistoryEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.messages=[{'id':str(i),'occurred_at':f'2026-08-0{i+1}T10:00:00+08:00',
            'timestamp':i,'sender_name':'本人','direction':'outgoing','type':'1',
            'text':'当时方案报价80万元。'} for i in range(3)]
        self.chunk={'messages':[h.compact_message(x) for x in self.messages],
                    'previous_context':[{'id':'previous','date':'2026-07-01','text':'客户签约了'}]}
        self.event={'project_id':'project-1','customer':'客户甲','category':'project',
            'business_date':'2026-08-01','summary':'当时我方向客户提出80万元报价，未证明客户接受。',
            'uncertainties':[],'message_ids':['0'],
            'evidence':[{'quote':'当时方案报价80万元。','level':'unverified','meaning':'我方报价'}]}
        self.result={'disposition':'business','events':[self.event]}
        self.projects=[{'id':'project-1'}]

    def test_preserves_every_message_at_chunk_boundary(self):
        chunks=list(h.message_chunks(self.messages,limit=150))
        ids=[m['id'] for c in chunks for m in c['messages']]
        self.assertEqual(ids,['0','1','2'])
        self.assertTrue(chunks[1]['previous_context'])
        self.assertEqual(chunks[1]['messages'][0]['text'],self.messages[1]['text'])

    def test_display_label_annotation_is_not_mistaken_for_customer_name(self):
        self.assertEqual(h.source_customer_label('港汇天地（会话标签）','会话：港汇天地采购'),'港汇天地')
        self.assertEqual(h.source_customer_label('港汇天地（会话标签）','匿名采购咨询'),'')
        self.assertEqual(h.source_customer_label('未知客户','匿名采购咨询'),'')
        self.assertEqual(h.source_customer_label('客户甲（成都）','客户甲（重庆）'),'')

    def test_valid_historical_quote_retains_original_day(self):
        self.assertEqual(h.validate_events(self.result,self.chunk,self.projects),self.result)

    def test_cannot_use_today_or_context_as_new_evidence(self):
        for patch in [{'business_date':'2026-09-17'}, {'message_ids':['previous']},
                      {'evidence':[{'quote':'客户签约了','level':'customer_statement','meaning':'已签'}]}]:
            result=copy.deepcopy(self.result);result['events'][0].update(patch)
            with self.assertRaises(ValueError):h.validate_events(result,self.chunk,self.projects)

    def test_cannot_guess_project_or_hide_missing_events(self):
        for patch in [{'project_id':'made-up'}, {'category':'knowledge'}, {'message_ids':[]}]:
            result=copy.deepcopy(self.result);result['events'][0].update(patch)
            with self.assertRaises(ValueError):h.validate_events(result,self.chunk,self.projects)
        with self.assertRaises(ValueError):h.validate_events({'events':[],'disposition':'business'},self.chunk,self.projects)

    def test_own_quote_cannot_be_customer_acceptance(self):
        result=copy.deepcopy(self.result)
        result['events'][0]['evidence'][0]['level']='customer_statement'
        with self.assertRaises(ValueError):h.validate_events(result,self.chunk,self.projects)

    def test_nonbusiness_chunks_stay_private(self):
        self.assertEqual(h.validate_events({'events':[],'disposition':'no_business'},self.chunk,self.projects)['events'],[])

    def test_mixed_chat_covers_every_hit_and_preserves_context(self):
        messages=[{**self.messages[0],'id':str(i),'text':'普通闲聊'} for i in range(300)]
        messages[50]['text']='小程序如何做';messages[250]['text']='客户报价范围'
        selected=h.business_windows(messages,'mixed')
        ids={int(m['id']) for m in selected}
        self.assertTrue(set(range(42,59))<=ids)
        self.assertTrue(set(range(242,259))<=ids)
        self.assertNotIn(150,ids)
        self.assertEqual(len(h.business_windows(messages,'business')),300)

    def test_preparation_never_publishes_partial_history_or_overwrites_progress(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'extractions').mkdir()
            manifest=[{'chat_id':'a','key':'a1'},{'chat_id':'b','key':'b1'},{'chat_id':'b','key':'b2'}]
            (root/'extraction-manifest.json').write_text(json.dumps(manifest))
            (root/'extractions/a1.json').write_text(json.dumps(self.result))
            # An incomplete chat must not even be parsed for consolidation.
            (root/'extractions/b1.json').write_text(json.dumps({'events':[{'invalid':'partial'}]}))
            con=MagicMock();con.execute.return_value=[{'chat_id':'a','display_name':'客户甲'},{'chat_id':'b','display_name':'客户乙'}]
            with patch.object(h,'PRIVATE',root),patch.object(h,'connection',return_value=con),patch.object(h,'save') as save,patch.object(h,'model_call') as call:
                h.consolidate({},warm=True)
            save.assert_not_called();call.assert_not_called()
            self.assertFalse((root/'publication-results.json').exists())


    def test_archive_preserves_conversation_role_across_message_directions(self):
        # Execute real staging, validation, archival transactions and role normalization.
        # Only the local index and native-analysis boundary are replaced with fixtures.
        with tempfile.TemporaryDirectory() as td:
            app=Path(td);private=app/'private';kb=app/'kb';state=app/'workbench_data'
            for folder in (private,kb/'projects',kb/'tracking',kb/'entities',app/'tools',state/'communication_pipeline'):
                folder.mkdir(parents=True,exist_ok=True)
            pid=h.p.digest('projects/项目甲.md')[:20]
            (kb/'projects/项目甲.md').write_text('# 项目甲\n\n**客户**：[[客户甲]]\n')
            (kb/'tracking/client_registry.md').write_text('正式状态保持')
            (kb/'tracking/material_library.json').write_text(json.dumps({'assets':{},'files':[],'recordings':[],'summary':{}}))
            h.p.save(state/'communication_pipeline/ledger.json',{'version':h.p.VERSION,'items':{}})
            cfg={'knowledge_root':str(kb),'wechat':{'chats':[]},'local_roots':[]}
            h.p.save(app/'tools/communication_sources.json',cfg)
            records={};results=[];roles=[]
            for index,kind in enumerate(('customer','internal','partner','unknown')):
                cid='chat-'+kind;ids=[]
                for j,direction in enumerate(('incoming','outgoing')):
                    ident=f'{index}-{j}';ids.append(ident)
                    records[ident]={'chat_id':cid,'record':json.dumps({'id':ident,'occurred_at':'2026-08-01T10:00:00+08:00',
                        'timestamp':index*2+j,'sender_name':'客户联系人' if j==0 else '本人','direction':direction,'type':'1',
                        'text':'一期范围先讨论。' if j==0 else '我来梳理报价。'})}
                event={'project_id':pid,'customer':'客户甲','category':'project','business_date':'2026-08-01',
                    'summary':kind+'会话讨论一期范围，未确认报价。','uncertainties':[],'message_ids':ids,
                    'evidence':[{'quote':'一期范围先讨论。','level':'customer_statement','meaning':'范围讨论'}]}
                results.append({'chat_id':cid,'display_name':cid,'events':[event]})
                roles.append({'chat_id':cid,'type':kind,'reason':'已核对原话身份'})
            h.p.save(private/'publication-results.json',results)
            h.p.save(private/'extraction-manifest.json',[{'key':'batch'}])
            h.p.save(private/'consolidation-receipt.json',{'source_batch_keys':['batch']})
            h.p.save(private/'chat-roles.json',roles)
            h.p.save(private/'progress.json',{'first':'2026-08-01','last':'2026-08-01'})
            con=MagicMock();con.execute.side_effect=lambda query,params:MagicMock(fetchone=lambda:records[params[0]])
            def refreshed(pipe,changed):
                h.p.save(pipe.root/'refresh_pending.json',[])
                return changed
            with patch.object(h,'APP',app),patch.object(h,'PRIVATE',private),patch.object(h,'connection',return_value=con),patch.object(h.p,'refresh',side_effect=refreshed):
                h.archive(cfg)
            ledger=h.p.load(state/'communication_pipeline/ledger.json')['items']
            self.assertEqual(len(ledger),4)
            self.assertEqual({e['communication']['type'] for e in ledger.values()},{'customer','internal','partner','unknown'})
            self.assertTrue(all(e['status']=='archived' for e in ledger.values()))
            review=next((state/'communication_pipeline/runs').glob('*/review.json'))
            for row in h.p.load(review)['items']:
                kind=ledger[row['material_id']]['communication']['type']
                self.assertEqual(row['evidence'][0]['level'],{'internal':'internal_statement','partner':'unverified','unknown':'unverified'}.get(kind,'customer_statement'))
            self.assertEqual(h.p.load(state/'communication_pipeline/wechat_history.json')['state'],'completed')
            self.assertEqual((kb/'tracking/client_registry.md').read_text(),'正式状态保持')


    def test_role_refinement_uses_full_business_evidence_and_preserves_known_roles(self):
        with tempfile.TemporaryDirectory() as td:
            app=Path(td);private=app/'private';private.mkdir()
            profile=lambda cid:{'chat_id':cid,'display_name':cid,'samples':[]}
            h.p.save(private/'profiles.json',[profile('known'),profile('unclear')])
            h.p.save(private/'chat-selection.json',[{'chat_id':c,'kind':'business'} for c in ('known','unclear')])
            known={'chat_id':'known','type':'internal','reason':'已经核实同事身份','evidence':[]}
            h.p.save(private/'chat-roles.json',[known,{'chat_id':'unclear','type':'unknown','reason':'旧样本不足','evidence':[]}])
            h.p.save(private/'extraction-results.json',[{'chat_id':'unclear','events':[{'message_ids':['new']}]}])
            record={'id':'new','timestamp':1,'occurred_at':'2026-08-01T10:00:00+08:00','sender_name':'对方','direction':'incoming','text':'我是甲方采购，这个项目由我对接。'}
            con=MagicMock();con.execute.return_value.fetchone.return_value={'chat_id':'unclear','record':json.dumps(record)}
            answer={'items':[{'chat_id':'unclear','type':'customer','reason':'对方明确负责甲方采购对接','evidence':[{'message_id':'new','quote':record['text']}]}]}
            with patch.object(h,'APP',app),patch.object(h,'PRIVATE',private),patch.object(h,'connection',return_value=con),patch.object(h,'model_call',return_value=answer) as model:
                h.classify_roles({},refine=True)
            self.assertIn(record['text'],model.call_args.args[0])
            rows=h.p.load(private/'chat-roles.json')
            self.assertEqual(len(rows),2);self.assertIn(known,rows)
            self.assertEqual(next(x for x in rows if x['chat_id']=='unclear')['type'],'customer')
            index=h.p.load(app/'workbench_data/communication_pipeline/communication_roles.json')
            self.assertEqual(len(index),2)
            self.assertEqual(h.p.load(private/'role-refinement-receipt.json')['reviewed'],1)


class HistoryRefreshResumeTest(unittest.TestCase):
    def test_resume_preserves_archive_and_requires_every_project(self):
        for completed in (True,False):
            with self.subTest(completed=completed),tempfile.TemporaryDirectory() as td:
                app=Path(td);private=app/'private';private.mkdir()
                state=app/'workbench_data/communication_pipeline';state.mkdir(parents=True)
                prior=state/'runs/original';prior.mkdir(parents=True)
                kb=app/'knowledge';kb.mkdir()
                archive={'run_id':'original','run_root':str(prior),'projects':['p1','p2'],'events':3}
                h.p.save(private/'archive-receipt.json',archive)
                h.p.save(private/'progress.json',{'first':'2026-01-04T10:00:00','last':'2026-09-17T10:00:00'})
                h.p.save(prior/'progress.json',{'observed':3,'new':2,'duplicates':1})
                h.p.save(state/'ledger.json',{'version':h.p.VERSION,'items':{}})
                h.p.save(state/'wechat_history.json',{'events':2,'customers':1,'project_count':2})
                original=(private/'archive-receipt.json').read_bytes()
                def refresh(pipe,ids):
                    self.assertEqual(ids,['p1','p2'])
                    h.p.save(state/'refresh_pending.json',[] if completed else ['p2'])
                    return ids if completed else ['p1']
                with patch.object(h,'APP',app),patch.object(h,'PRIVATE',private),patch.object(h.p,'refresh',side_effect=refresh),patch.object(h,'archive') as archive_call,patch.object(h,'model_call') as model:
                    result=h.refresh_archived_history({'knowledge_root':str(kb)})
                archive_call.assert_not_called();model.assert_not_called()
                self.assertEqual((private/'archive-receipt.json').read_bytes(),original)
                self.assertEqual(result['observed'],3)
                self.assertEqual(result['resumed_archive_run'],'original')
                self.assertEqual(result['status'],'completed' if completed else 'partial')
                public=h.p.load(state/'wechat_history.json')
                self.assertEqual(public['state'],'completed' if completed else 'processing')
                self.assertEqual(public['done'],2 if completed else 1)
                self.assertEqual(public['events'],2)
                self.assertEqual(public['customers'],1)


if __name__=='__main__':unittest.main()
