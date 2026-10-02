import hashlib,json,tempfile,unittest
from pathlib import Path
from project_workspace import build_projects
import project_crm

class ProjectCrmTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.k=Path(self.temp.name)/'kb';self.s=Path(self.temp.name)/'state'
        for p in (self.k/'projects',self.k/'raw',self.k/'tracking',self.s):p.mkdir(parents=True,exist_ok=True)
        self.proof=self.k/'raw/order.md';self.proof.write_text('业务日期：2026-08-26\n项目甲对应订单 XSDD20260826-022730。')
        for name in ('甲','乙'):(self.k/'projects'/f'{name}.md').write_text(f'---\nsources:\n  - raw/order.md\n---\n# 项目{name}\n\n客户：[[客户]]\n')
        self.p=next(p for p in build_projects(self.k,self.s) if p['title']=='项目甲')
        self.link={'project_id':self.p['id'],'project_source':self.p['source_path'],'order_code':'XSDD20260826-022730','customer_name':'客户分公司',
                   'evidence':{'path':'raw/order.md','quote':'项目甲对应订单 XSDD20260826-022730。','sha256':hashlib.sha256(self.proof.read_bytes()).hexdigest()}}
        self.order={'id':7,'bizCode':self.link['order_code'],'customerId':2,'customerName':'客户分公司','orderAmount':48750,'performanceAmount':48750,'receivedAmount':0,'approvalStatus':'审批通过','k100ContractSignedByBothParties':0,'contractId':8,'contractBizCode':'HT-8'}
        self.contract={'id':8,'customerId':2,'bizCode':'HT-8','contractAmount':48750,'approvalStatus':'审批通过'}
        self.snapshot={'resources':{'orders':{'data':{'list':[self.order]},'coverage':'all_available_pages'},'contracts':{'data':{'list':[self.contract]},'coverage':'all_available_pages'}}}
        self.persist()
    def tearDown(self):self.temp.cleanup()
    def persist(self):
        (self.k/'tracking/project_crm_links.json').write_text(json.dumps({'links':[self.link]}))
        (self.s/'ka_sales_snapshot.json').write_text(json.dumps(self.snapshot))
    def audit(self):return project_crm.audit(self.p['id'],self.k,self.s)
    def test_exact_order_contract_chain_keeps_approval_signature_and_receipt_separate(self):
        before={str(p):p.read_bytes() for root in (self.k,self.s) for p in root.rglob('*') if p.is_file()}
        r=self.audit();m=r['matches'][0]
        self.assertEqual(m['contract']['id'],8);self.assertEqual(m['order']['receivedAmount'],0)
        self.assertEqual(m['order']['k100ContractSignedByBothParties'],0)
        self.assertEqual(r['mode'],'read_only');self.assertIsNone(r['local_quote'])
        self.assertEqual(before,{str(p):p.read_bytes() for root in (self.k,self.s) for p in root.rglob('*') if p.is_file()})
    def test_same_customer_other_project_and_same_amount_do_not_match(self):
        other=next(p for p in build_projects(self.k,self.s) if p['id']!=self.p['id'])
        self.assertFalse(project_crm.audit(other['id'],self.k,self.s)['matches'])
        self.order['bizCode']='XSDD20260515-020308';self.persist()
        self.assertFalse(self.audit()['matches'])
    def test_changed_evidence_and_wrong_customer_fail_closed(self):
        self.proof.write_text(self.proof.read_text()+'\n订单双方对应仍存疑')
        self.assertFalse(self.audit()['matches'])
        self.link['evidence']['sha256']=hashlib.sha256(self.proof.read_bytes()).hexdigest();self.order['customerName']='其他主体';self.persist()
        self.assertFalse(self.audit()['matches'])
    def test_missing_or_wrong_contract_is_not_no_contract(self):
        self.contract['customerId']=999;self.snapshot['resources']['contracts']['coverage']='first_page_only';self.persist()
        r=self.audit();self.assertIsNone(r['matches'][0]['contract']);self.assertIn('不据此判断无合同',r['matches'][0]['contract_note'])
        self.assertEqual(r['coverage']['contracts'],'first_page_only')
    def test_unlinked_source_and_invalid_project_rejected(self):
        (self.k/'raw/unlinked.md').write_bytes(self.proof.read_bytes());self.link['evidence']['path']='raw/unlinked.md';self.persist()
        self.assertFalse(self.audit()['matches'])
        with self.assertRaises(ValueError):project_crm.audit('../bad',self.k,self.s)
    def test_epoch_placeholder_is_not_a_signing_date(self):
        self.contract['signedDate']='1969-12-31T16:00:00.000+00:00';self.persist()
        c=self.audit()['matches'][0]['contract']
        self.assertIsNone(c['signedDateDisplay']);self.assertEqual(c['signedDate'],self.contract['signedDate'])
    def test_business_change_updates_ai_but_unchanged_refresh_does_not(self):
        from project_activity import activity_fingerprint
        before=activity_fingerprint(project_crm.business_sources(self.p,self.k,self.s))
        self.snapshot['resources']['orders']['fetched_at']='2026-09-08T02:00:00+08:00';self.order['updatedAt']='2026-09-08T01:00:00+08:00';self.persist()
        self.assertEqual(before,activity_fingerprint(project_crm.business_sources(self.p,self.k,self.s)))
        self.order['receivedAmount']=48750;self.persist()
        self.assertNotEqual(before,activity_fingerprint(project_crm.business_sources(self.p,self.k,self.s)))
    def test_customer_promise_does_not_get_replaced_by_crm_plan(self):
        self.proof.write_text(self.proof.read_text()+'客户承诺2026年9月30日前付款。')
        self.link['evidence']['sha256']=hashlib.sha256(self.proof.read_bytes()).hexdigest()
        self.link['customer_payment']={'due':'2026-09-30','evidence':{**self.link['evidence'],'quote':'客户承诺2026年9月30日前付款。'}}
        self.order['planReceivableDate1']='2026-10-30T16:00:00.000+00:00';self.persist()
        p=self.audit()['matches'][0]['payment_comparison']
        self.assertEqual(p['customer_due'],'2026-09-30');self.assertEqual(p['crm_due'],'2026-10-31');self.assertTrue(p['different'])
        self.link['customer_payment']['due']='2026-10-01';self.persist()
        self.assertIsNone(self.audit()['matches'][0]['payment_comparison'])
