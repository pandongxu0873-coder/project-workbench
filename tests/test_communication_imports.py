import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from tools.communication_pipeline import Pipeline,save,Failure
from tools.communication_imports import publish
import communication_jobs

class CommittedImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.kb=self.root/'kb';self.kb.mkdir();self.state=self.root/'state'
        self.pipe=Pipeline({},self.root/'isolated',self.kb,dt.date.today(),dt.date.today())
        self.ident='a'*64;self.pipe.ledger['items'][self.ident]={'id':self.ident,'sha256':'b'*64,'title':'客户电话','status':'archived','channel':'phone_recording','business_date':'2026-09-28'}
        self.review={'completed':[self.ident],'items':[{'material_id':self.ident,'classification':'project','project_id':'p','summary':'核对范围，未签约。','evidence':[]}],'projects':[{'id':'p','title':'项目甲','customer':'客户甲'}]}
    def test_isolated_committed_import_is_visible_without_mutating_active_ledger(self):
        ledger=self.state/'communication_pipeline/ledger.json';save(ledger,{'items':{}});before=ledger.read_bytes()
        publish(self.pipe,self.review,self.state,'phone')
        digest=communication_jobs.daily_digest(self.state,self.kb)
        self.assertEqual(digest['counts']['recordings'],1);self.assertEqual(digest['groups'][0]['items'][0]['business_date'],'2026-09-28')
        self.assertEqual(ledger.read_bytes(),before)
    def test_same_hash_in_formal_ledger_and_import_is_not_counted_twice(self):
        entry=self.pipe.ledger['items'][self.ident];save(self.state/'communication_pipeline/ledger.json',{'items':{self.ident:entry}})
        save(self.state/'communication_pipeline/runs'/communication_jobs.now().replace(':','-')/'review.json',self.review)
        publish(self.pipe,self.review,self.state,'phone')
        self.assertEqual(communication_jobs.daily_digest(self.state,self.kb)['counts']['recordings'],1)
    def test_pending_or_malformed_receipt_never_claims_archive(self):
        self.pipe.ledger['items'][self.ident]['status']='ready_for_review'
        with self.assertRaises(Failure):publish(self.pipe,self.review,self.state,'phone')
        save(self.state/'communication_pipeline/published_imports/bad.json',{'version':1,'ledger':{self.ident:self.pipe.ledger['items'][self.ident]},'review':self.review})
        self.assertEqual(communication_jobs.daily_digest(self.state,self.kb)['groups'],[])
    def test_publish_rejects_paths(self):
        with self.assertRaises(Failure):publish(self.pipe,self.review,self.state,'../outside')
    def test_pending_formal_entry_cannot_hide_committed_import(self):
        ledger=self.state/'communication_pipeline/ledger.json'
        save(ledger,{'items':{self.ident:{**self.pipe.ledger['items'][self.ident],'status':'ready_for_review'}}});before=ledger.read_bytes()
        publish(self.pipe,self.review,self.state,'phone')
        result=communication_jobs.daily_digest(self.state,self.kb)
        self.assertEqual(result['counts']['recordings'],1)
        self.assertEqual(ledger.read_bytes(),before)
