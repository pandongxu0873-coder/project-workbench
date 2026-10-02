import unittest
from unittest.mock import patch
import k100_metrics as metrics
import k100_sync as sync

def order(id='1', day='2026-09-30T16:00:00Z', paid='10.10', pending='20.20'):
    return dict(id=id,orderId='detail-'+id,orderNo='TEST-'+id,customerName='测试客户',approvalStatus='审批通过',fields=dict(orderDate=day,receivedAmount=paid,pendingReceivableAmount=pending))

class CollectionTests(unittest.TestCase):
    def test_timezone_boundary_decimal_and_visible_scope(self):
        rows=[order(),order('2','2026-09-30T15:59:59Z')]
        with patch.object(sync,'request',return_value={'items':rows,'totalElements':2}):
            r=metrics.collection_summary({'from':'2026-10-01','through':'2026-12-31'})
        self.assertEqual(r['order_count'],1)
        self.assertEqual(r['received'],'10.10')
        self.assertEqual(r['pending'],'20.20')
        self.assertEqual(r['scope'],'当前账号可见订单')
        self.assertTrue(r['orders'][0]['url'].endswith('/detail-1'))
    def test_partial_or_duplicate_pages_do_not_claim_total(self):
        for pages in [[{'items':[order()],'totalElements':2},{'items':[],'totalElements':2}], [{'items':[order()],'totalElements':2},{'items':[order()],'totalElements':2}], [{'items':[order()],'totalElements':2},{'items':[order('2')],'totalElements':3}]]:
            with patch.object(sync,'request',side_effect=pages),self.assertRaises(sync.SyncError):
                metrics.collection_summary({'from':'2026-01-01','through':'2026-12-31'})
    def test_missing_amount_is_not_zero(self):
        with patch.object(sync,'request',return_value={'items':[order(paid=None)],'totalElements':1}),self.assertRaises(sync.SyncError):
            metrics.collection_summary({'from':'2026-01-01','through':'2026-12-31'})
    def test_real_empty_period_is_zero(self):
        with patch.object(sync,'request',return_value={'items':[],'totalElements':0}):
            r=metrics.collection_summary({'from':'2026-01-01','through':'2026-12-31'})
        self.assertEqual(r['received'],'0');self.assertEqual(r['order_count'],0)
    def test_all_pages_are_read(self):
        with patch.object(sync,'request',side_effect=[{'items':[order()],'totalElements':2},{'items':[order('2')],'totalElements':2}]) as req:
            r=metrics.collection_summary({'from':'2026-01-01','through':'2026-12-31'})
        self.assertEqual(r['received'],'20.20');self.assertEqual(req.call_count,2)

class PersonalMetricsTests(unittest.TestCase):
    def board(self):
        return {'level':'PERSON','subjectId':'78','title':'测试用户','range':{'from':'2026-07-01','through':'2026-09-30','period':'QUARTER'},'metric':{'target':'2500000','completed':'2593876.69','rate':'103.76','gap':'-93876.69'},'sync':{'SIGNED_ORDERS':'2026-09-29 21:54:17'}}
    def context(self):
        return {'selfId':'78','people':[{'id':'78','accountId':'83'}]}
    def test_official_rate_above_100_and_gap_preserved(self):
        with patch.object(sync,'identity',return_value='83'),patch.object(sync,'request',side_effect=[self.context(),self.board()]),patch.object(metrics,'collection_summary',side_effect=sync.SyncError('回款未读取')):
            r=metrics.business_summary('QUARTER','2026-09-30')
        self.assertEqual(r['metric']['rate'],'103.76');self.assertEqual(r['metric']['gap'],'-93876.69');self.assertFalse(r['cash']['available']);self.assertNotEqual(r['as_of'],r['source_updated_at'])
    def test_missing_target_is_not_zero(self):
        board=self.board();board['metric'].update(target=None,rate=None,gap=None)
        with patch.object(sync,'identity',return_value='83'),patch.object(sync,'request',side_effect=[self.context(),board]),patch.object(metrics,'collection_summary',return_value={'available':True}):
            r=metrics.business_summary('QUARTER','2026-09-30')
        self.assertIsNone(r['metric']['rate'])
    def test_identity_mismatch_blocks_mixing_accounts(self):
        with patch.object(sync,'identity',return_value='other'),patch.object(sync,'request',return_value=self.context()),self.assertRaises(sync.SyncError):
            metrics.business_summary('QUARTER','2026-09-30')
    def test_response_period_mismatch_rejected(self):
        with patch.object(sync,'identity',return_value='83'),patch.object(sync,'request',side_effect=[self.context(),self.board()]),self.assertRaises(sync.SyncError):
            metrics.business_summary('YEAR','2026-09-30')
    def test_same_period_wrong_quarter_is_rejected(self):
        with patch.object(sync,'identity',return_value='83'),patch.object(sync,'request',side_effect=[self.context(),self.board()]),self.assertRaises(sync.SyncError):
            metrics.business_summary('QUARTER','2026-10-01')
    def test_invalid_input_no_network(self):
        with patch.object(sync,'request') as call,self.assertRaises(sync.SyncError):metrics.business_summary('WEEK','2026-10-01')
        call.assert_not_called()
