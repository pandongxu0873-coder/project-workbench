import unittest
from communication_roles import describe,evidence_label
from tools.communication_pipeline import validate_review,Failure


class CommunicationRolesTest(unittest.TestCase):
    def setUp(self):
        self.key='a'*20
        self.entry={'origin':'wechat-local://'+self.key+'/message'}

    def test_our_quote_in_customer_chat_is_not_internal_chat_or_acceptance(self):
        role=describe(self.entry,[{'summary':'我方向客户发送80万元报价。','evidence':[{'level':'internal_statement'}]}],
            {self.key:{'type':'customer','reason':'需求方直接对接','conversation':'客户业务群'}})
        self.assertEqual(role['type'],'customer')
        self.assertFalse(role['customer_direct']);self.assertFalse(role['customer_relay'])

    def test_internal_relay_cannot_become_direct_customer_confirmation(self):
        role=describe(self.entry,[{'summary':'同事转述客户同意。','evidence':[{'level':'customer_statement'}]}],
            {self.key:{'type':'internal','reason':'业务平台内部同事会话'}})
        self.assertTrue(role['customer_relay']);self.assertFalse(role['customer_direct'])
        self.assertIn('非客户直接确认',evidence_label('customer_statement',role))

    def test_partner_and_unclear_identities_are_not_forced_into_customer_bucket(self):
        for kind in ('partner','unknown'):
            role=describe(self.entry,[{'summary':'对方报价','evidence':[{'level':'customer_statement'}]}],{self.key:{'type':kind}})
            self.assertEqual(role['type'],kind);self.assertFalse(role['customer_direct'])
            self.assertNotEqual(evidence_label('customer_statement',role),'客户原话')

    def test_outgoing_claim_alone_does_not_identify_a_colleague(self):
        role=describe({},[{'summary':'我方已发送报价。','evidence':[{'level':'internal_statement'}]}])
        self.assertEqual(role['type'],'unknown')

    def test_legacy_customer_label_cannot_override_actual_outgoing_direction(self):
        role=describe({**self.entry,'channel':'wechat','message_direction':'outgoing'},[{'summary':'已发送报价','evidence':[{'level':'customer_statement'}]}],{self.key:{'type':'customer'}})
        self.assertFalse(role['customer_direct']);self.assertEqual(evidence_label('customer_statement',role),'我方发出，非客户回复')

    def test_lack_of_customer_acceptance_is_not_a_customer_relay(self):
        role=describe({'communication':{'type':'internal'}},[{'summary':'内部估价20万元，未见客户确认。','evidence':[]}])
        self.assertFalse(role['customer_relay'])

    def test_asking_customer_to_discuss_internally_does_not_identify_internal_chat(self):
        role=describe({**self.entry,'channel':'wechat','title':'微信｜刘秋霞｜16:12:20'},[{'summary':'我方建议客户先内部讨论，再反馈需求。','evidence':[{'level':'internal_statement'}]}])
        self.assertEqual(role['type'],'unknown')
        self.assertEqual(role['conversation'],'刘秋霞')

    def test_inference_rejects_customer_level_for_internal_or_partner_source(self):
        row={'source_id':'x','project_id':'','classification':'needs_review','summary':'同事转述客户同意。',
            'business_date':'','date_quote':'','next_action':'','uncertainties':[],
            'evidence':[{'quote':'客户说可以','level':'customer_statement','meaning':'客户接受'}]}
        for kind in ('internal','partner'):
            source={'source_id':'x','text':'客户说可以','business_date':'','communication':{'type':kind}}
            with self.assertRaises(Failure):validate_review({'items':[row]},[source],[])


if __name__=='__main__':unittest.main()
