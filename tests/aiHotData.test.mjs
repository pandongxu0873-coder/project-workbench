import test from 'node:test';
import assert from 'node:assert/strict';
import { safeNewsLink, newsTime, mergeNews } from '../src/aiHotData.js';

test('news links cannot execute returned scripts or expose embedded credentials', () => {
  for (const url of ['javascript:alert(1)', 'data:text/html,hi', 'file:///etc/passwd', 'https://u:p@example.com', null]) assert.equal(safeNewsLink(url), '');
  assert.equal(safeNewsLink('https://aihot.news/items/a'), 'https://aihot.news/items/a');
});
test('dates use Beijing time and label discovery fallback accurately', () => {
  assert.match(newsTime({ publishedAt: '2026-09-16T23:10:00Z' }), /09\/17.*07:10/);
  assert.match(newsTime({ discoveredAt: '2026-09-16T23:10:00Z' }), /^收录于/);
  assert.equal(newsTime({}), '');
  assert.equal(newsTime({ publishedAt: 'bad' }), '');
});
test('pagination preserves API order without duplicating updated entries', () => {
  assert.deepEqual(mergeNews([{ id: 'a', title: 'old' }, { id: 'b' }], [{ id: 'a', title: 'new' }, { id: 'c' }]), [{ id: 'a', title: 'new' }, { id: 'b' }, { id: 'c' }]);
});
