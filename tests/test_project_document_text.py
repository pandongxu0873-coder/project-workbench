import json
from pathlib import Path
import tempfile
import unittest
from project_document_text import reviewed_pdf_text

class ReviewedPdfTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.digest='a'*64
  self.value={'schema_version':1,'source_sha256':self.digest,'pages':[{'page':1,'text':'金额被遮挡，不能推定'}],'reviewed_pages':[1],'limitations':'OCR可能有误，遮挡未知'}
 def save(self):
  (self.root/(self.digest+'.json')).write_text(json.dumps(self.value))
 def test_exact_source_and_review_keep_page_and_limitations(self):
  self.save();v=reviewed_pdf_text(self.digest,self.root)
  self.assertIn('PDF第1页',v['text']);self.assertIn('金额被遮挡',v['text']);self.assertIn('遮挡未知',v['limitations'])
 def test_changed_original_cannot_reuse(self):
  self.save();self.assertIsNone(reviewed_pdf_text('b'*64,self.root))
 def test_mismatched_digest_is_rejected(self):
  self.value['source_sha256']='b'*64;self.save()
  with self.assertRaises(ValueError):reviewed_pdf_text(self.digest,self.root)
 def test_missing_page_or_review_is_rejected(self):
  for field in ['pages','reviewed_pages']:
   old=self.value[field];self.value[field]=[];self.save()
   with self.assertRaises(ValueError):reviewed_pdf_text(self.digest,self.root)
   self.value[field]=old
 def test_traversal_is_rejected(self):
  with self.assertRaises(ValueError):reviewed_pdf_text('../secret',self.root)
