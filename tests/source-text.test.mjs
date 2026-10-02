import test from 'node:test';
import assert from 'node:assert/strict';
import { readableSource } from '../src/sourceText.js';

test('folds archive fields while preserving all business text, amounts and embedded separators', () => {
  const body = '\n# 范围核验\n\n19.5人天 / 48750元\n---\n9月30日与10月31日尚未对齐。\n[[projects/原项目]]\n';
  const original = '---\ntitle: 范围核验\nreviewed_at: 2026-09-08\n---\n' + body;
  assert.deepEqual(readableSource(original, '核验.md'), { body, folded: true });
});
test('keeps uncertain headers and non-Markdown source formats intact', () => {
  for (const content of ['---\ntitle: 未闭合\n48750元', '---\n48750元\n---\n正文', '---\ntitle: 仅归档信息\n---\n']) {
    assert.deepEqual(readableSource(content, '原文.md'), { body: content, folded: false });
  }
  const txt = '---\ntitle: 客户原信\n---\n付款15工作日';
  for (const path of ['邮件.txt', 'unknown', '数据.json']) assert.deepEqual(readableSource(txt, path), { body: txt, folded: false });
});
test('preserves Windows line endings and business markup literally', () => {
  const body = '\r\n金额：73000\r\n<script>原件文字</script>\r\n';
  assert.deepEqual(readableSource('\uFEFF---\r\ntitle: 报价\r\n---\r\n' + body, '原文.MD'), { body, folded: true });
});
