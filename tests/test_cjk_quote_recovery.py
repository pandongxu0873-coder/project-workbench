import unittest
import project_evidence_digest as d
class CjkQuoteTests(unittest.TestCase):
 def test_cjk_boundaries_restore_verbatim_source(self):
  for source,quote in [('总部\n运营确认','总部运营确认'),('总部运营确认','总部 运 营确认'),('总部\n运营确认','总部 运营确认')]:
   self.assertEqual(d._canonical_quote(quote,source),source)
 def test_numeric_latin_mixed_and_punctuation_boundaries_not_removed(self):
  for source,quote in [('1 0万元','10万元'),('CR M接口','CRM接口'),('企微 A接口','企微A接口'),('9 月','9月'),('总部，\n确认','总部，确认')]:
   self.assertEqual(d._canonical_quote(quote,source),quote)
   self.assertNotIn(quote,source)
 def test_ambiguity_glyphs_and_cross_interval_not_repaired(self):
  for source,quote in [('总部\n运营；总部 运营','总部运营'),('爱沙健康','云朵健康'),('运营范围','总部运营范围')]:
   self.assertEqual(d._canonical_quote(quote,source),quote)
 def test_non_han_symbols_are_not_treated_as_han(self):
  for symbol in ['\u4dc0','\u4dff','☯','①','★']:
   source=symbol+' 甲';quote=symbol+'甲'
   self.assertEqual(d._canonical_quote(quote,source),quote)
   self.assertNotIn(quote,source)
 def test_long_raw_quote_stays_rejected(self):
  source=('甲 '*500)+'乙';quote=('甲'*500)+'乙'
  self.assertEqual(d._canonical_quote(quote,source),quote)
 def test_existing_whitespace_run_and_exact_quotes_unchanged(self):
  self.assertEqual(d._canonical_quote('A  B','A\nB'),'A\nB')
  self.assertEqual(d._canonical_quote('总部确认','总部确认'),'总部确认')
if __name__=='__main__':unittest.main()
