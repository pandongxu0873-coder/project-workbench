import unittest
from project_source_dates import explicit_dates, supported_dates

class SourceDateTests(unittest.TestCase):
    def test_rfc_mail_headers_and_pdf_radicals(self):
        self.assertEqual(explicit_dates('Date：Mon, 21 Sep 2026 22:47:43 +0800'), ['2026-09-21'])
        self.assertEqual(explicit_dates('2026年6⽉24⽇'), ['2026-06-24'])
        self.assertEqual(explicit_dates('提到 Mon, 21 Sep 2026 22:47:43 +0800'), [])
        self.assertEqual(explicit_dates('Date: malformed'), [])

    def test_chinese_recording_timestamp_is_supported(self):
        self.assertEqual(explicit_dates('2026年5月28日 下午 10:23|2小时 1分钟 47秒'), ['2026-05-28'])

    def test_invalid_future_and_partial_dates_are_not_candidates(self):
        self.assertEqual(explicit_dates('2026年2月30日 9999年1月1日 5月28日'), [])

    def test_meeting_and_retrospective_dates_are_candidates_not_assignment(self):
        self.assertEqual(explicit_dates('会议2026年5月28日。客户回顾2026年5月22日的讨论。'), ['2026-05-22', '2026-05-28'])

    def test_extracted_prose_cannot_authorize_generated_date(self):
        self.assertEqual(supported_dates({'extracted':True,'content':'2026年5月28日','original_dates':['2026-05-22']}), ['2026-05-22'])

    def test_iso_and_chinese_deduplicate(self):
        self.assertEqual(explicit_dates('2026-05-28 / 2026年05月28日'), ['2026-05-28'])

    def test_chinese_deadlines_do_not_become_occurrence_dates(self):
        self.assertEqual(explicit_dates('双方于2026年8月31日前签署，2026年9月30日前支付。'), [])
        self.assertEqual(explicit_dates('2026年5月28日会议，要求2026年5月30日前回复。'), ['2026-05-28'])
