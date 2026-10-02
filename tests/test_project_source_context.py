import tempfile
import unittest
import zipfile
import os
from unittest.mock import patch
from pathlib import Path
import project_source_context as source_context


class SourceContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'raw/assets').mkdir(parents=True)
        (self.root/'projects').mkdir()
        (self.root/'entities').mkdir()
        self.main=self.root/'projects/main.md';self.main.write_text('')
        self.project={'customer':'甲客户','sources':[{'path':'projects/main.md','exists':True,'readable':True}]}
        source_context._asset_index.cache_clear()

    def test_json_retains_exact_source_text_and_rejects_malformed_records(self):
        p=self.root/'approval.json'
        original='{"status":"待审批","amount":159480,"scope":"独立项目"}'
        p.write_text(original)
        self.assertEqual(source_context.attachment_text(p),original)
        p.write_text('{broken')
        with self.assertRaises(ValueError):source_context.attachment_text(p)

    def test_whole_file_cap_is_enforced_before_extraction(self):
        p=self.root/'oversized.json'
        with p.open('wb') as handle:handle.truncate(60_000_001)
        with self.assertRaisesRegex(ValueError,'附件超过可读大小'):
            source_context.attachment_text(p)

    def test_unique_exact_attachment_links_only_and_background_profile(self):
        (self.root/'raw/assets/报价.xlsx').touch()
        (self.root/'entities/甲客户.md').write_text('甲客户背景')
        self.main.write_text('[[raw/assets/B报价.xlsx]]')
        found=source_context.supplement_sources(self.project,self.root)
        self.assertEqual([s['relation'] for s in found],['cited_attachment','customer_background'])
        self.assertEqual(found[0]['path'],'raw/assets/B报价.xlsx');self.assertFalse(found[0]['exists'])
        self.main.write_text('[[raw/assets/报价.xlsx]]')
        found=source_context.supplement_sources(self.project,self.root)
        self.assertEqual([s['relation'] for s in found],['cited_attachment','customer_background'])
        self.assertEqual(found[0]['cited_by'],'projects/main.md')

    def test_duplicate_basename_and_other_project_references_never_attach(self):
        for sub in ('a','b'):
            (self.root/'raw/assets'/sub).mkdir()
            (self.root/'raw/assets'/sub/'报价.xlsx').touch()
        self.main.write_text('[[报价.xlsx]]')
        self.assertEqual(source_context.supplement_sources(self.project,self.root),[])
        (self.root/'raw/assets/b/报价.xlsx').unlink();source_context._asset_index.cache_clear()
        self.project['sources'][0]['relation']='background_reference'
        self.assertEqual(source_context.supplement_sources(self.project,self.root),[])

    def test_entity_path_cannot_escape_customer_directory(self):
        self.project['customer']='../projects/main'
        self.assertEqual(source_context.supplement_sources(self.project,self.root),[])

    def test_explicit_raw_text_and_pdf_are_discovered_without_background_expansion(self):
        (self.root/'raw/articles').mkdir()
        (self.root/'raw/articles/原始聊天.txt').write_text('客户说已有容量够用。')
        (self.root/'raw/assets/范围.pdf').touch()
        self.main.write_text('原始沟通 `raw/articles/原始聊天.txt`；书面附件 范围.pdf')
        found=source_context.supplement_sources(self.project,self.root)
        self.assertEqual({s['path'] for s in found},{'raw/articles/原始聊天.txt','raw/assets/范围.pdf'})
        self.assertTrue(next(s for s in found if s['path'].endswith('.txt'))['readable'])
        self.project['sources'][0]['relation']='background_reference'
        self.assertEqual(source_context.supplement_sources(self.project,self.root),[])

    def test_mutual_entity_link_is_background_not_an_inferred_legal_identity(self):
        self.project['source_path']='projects/main.md'
        self.main.write_text('[[entities/甲科技]]\n[[entities/行业对照]]')
        (self.root/'entities/甲科技.md').write_text('关联[[projects/main]]')
        (self.root/'entities/行业对照.md').write_text('独立客户')
        found=source_context.supplement_sources(self.project,self.root)
        self.assertEqual([(s['path'],s['relation']) for s in found],[('entities/甲科技.md','background_reference')])

    def test_pdf_text_layer_retains_page_boundaries_and_reports_image_gaps(self):
        path=self.root/'raw/assets/范围.pdf';path.touch()
        with patch.object(source_context,'_pdf_text',return_value={'text':'PDF第1页\n书面范围\nPDF第2页\n【本页无可读文字层，图像内容未读取】','missing_pages':[2],'pages':2}):
            content=source_context.attachment_text(path)
            self.assertIn('图像、图表及签章未核验',content)
            self.assertIn('无文字层页：2',content)
            self.assertIn('PDF第1页\n书面范围',content)

    def test_pdf_cache_identity_changes_with_same_size_and_preserved_mtime(self):
        path=self.root/'raw/assets/范围.pdf';path.write_bytes(b'FIRST');before=path.stat()
        with patch.object(source_context,'_pdf_text',return_value={'text':'text','missing_pages':[],'pages':1}) as read:
            source_context.attachment_text(path);first=read.call_args.args
            path.write_bytes(b'LATER');os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
            source_context.attachment_text(path);second=read.call_args.args
            self.assertEqual(first[0],second[0]);self.assertNotEqual(first[1],second[1])

    def test_missing_explicit_path_never_substitutes_other_customers_basename(self):
        (self.root/'raw/乙客户').mkdir()
        (self.root/'raw/乙客户/原始聊天.txt').write_text('乙的合同')
        self.main.write_text('[原始聊天.txt](raw/甲客户/原始聊天.txt)')
        found=source_context.supplement_sources(self.project,self.root)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['path'],'raw/甲客户/原始聊天.txt')
        self.assertFalse(found[0]['exists'])

    def test_explicit_existing_path_resolves_even_when_basename_is_ambiguous(self):
        for sub in ('甲客户','乙客户'):
            (self.root/'raw'/sub).mkdir()
            (self.root/'raw'/sub/'原始聊天.txt').write_text(sub)
        self.main.write_text('[[raw/甲客户/原始聊天.txt]]')
        found=source_context.supplement_sources(self.project,self.root)
        self.assertEqual([s['path'] for s in found],['raw/甲客户/原始聊天.txt'])

    def test_secondary_reference_missing_everywhere_is_reported_as_unavailable(self):
        (self.root/'raw/articles').mkdir()
        note=self.root/'raw/articles/整理.md';note.write_text('原件 [[raw/甲客户/尚未归档的确认.txt]]')
        self.project['sources'].append({'path':'raw/articles/整理.md','exists':True,'readable':True})
        found=source_context.supplement_sources(self.project,self.root)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['path'],'raw/甲客户/尚未归档的确认.txt')
        self.assertFalse(found[0]['exists'])

    def test_docx_paragraphs_and_xlsx_sheet_cell_values_are_retained(self):
        doc=self.root/'raw/assets/需求.docx'
        with zipfile.ZipFile(doc,'w') as z:
            z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>取消发票查询</w:t></w:r></w:p><w:p><w:r><w:t>保留开票类型</w:t></w:r></w:p></w:body></w:document>')
        self.assertEqual(source_context.attachment_text(doc),'取消发票查询\n保留开票类型')
        xls=self.root/'raw/assets/报价.xlsx'
        with zipfile.ZipFile(xls,'w') as z:
            z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="报价" r:id="r1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="/xl/worksheets/sheet1.xml"/></Relationships>')
            z.writestr('xl/sharedStrings.xml','<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>物流范围</t></si></sst>')
            z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="B1"><v>136</v></c><c r="C1"><f>B1*2500</f><v>340000</v></c><c r="A2" t="inlineStr"><is><t>未确认</t></is></c></row></sheetData></worksheet>')
        self.assertEqual(source_context.attachment_text(xls),'工作表：报价\nA1=物流范围 | B1=136 | C1=340000 | A2=未确认')

    def test_invalid_archive_fails_without_interpreting_binary_as_text(self):
        bad=self.root/'raw/assets/损坏.docx';bad.write_bytes(b'not an archive')
        with self.assertRaises(zipfile.BadZipFile):source_context.attachment_text(bad)

    def test_long_recent_sources_cannot_displace_short_early_sources_or_profile(self):
        docs=[{'path':f'recent-{i}','content':'甲'*40000} for i in range(10)]
        docs += [{'path':f'old-{i}','content':'早期范围核实'*100} for i in range(50)]
        docs += [{'path':'customer','content':'客户业务'*100}]
        result=source_context.covered_excerpts(docs)
        self.assertEqual(len(result),61)
        self.assertLessEqual(sum(len(s['content']) for s in result),160000)
        self.assertTrue(all(s['truncated'] for s in result[:10]))
        self.assertTrue(all(not s['truncated'] for s in result[10:]))
        self.assertEqual(result[-1]['content'],docs[-1]['content'])

    def test_only_exact_missing_extension_is_resolved(self):
        note=self.root/'projects/history.md';note.write_text('早期需求')
        self.project['sources'].append({'path':'projects/history','readable':False,'exists':False,'relation':'explicit_evidence'})
        found=source_context.supplement_sources(self.project,self.root)
        self.assertEqual(found,[{'path':'projects/history.md','readable':True,'exists':True,'relation':'explicit_evidence'}])


if __name__=='__main__':unittest.main()
