import test from 'node:test';
import assert from 'node:assert/strict';
import {historyEvidenceLinks,resolveHistoryTarget} from '../src/historyEvidenceLinks.js';
test('a shared filename alone cannot claim the same historical evidence',()=>{
 const value={evolution:[{title:'采购',date:'2026-07-01',evidence:[{path:'meeting',quote:'确认采购范围'}]}]};
 assert.equal(historyEvidenceLinks(value,[{path:'meeting',quote:'另谈验收'}]).length,0);
 assert.equal(historyEvidenceLinks(value,[{path:'other',quote:'确认采购范围'}]).length,0);
 assert.equal(historyEvidenceLinks(value,[{path:'meeting',quote:''}]).length,0);
});
test('direct history targets survive reorder and disappear when the evidence changes',()=>{
 const row={title:'范围变化',date:'2026-08-01',evidence:[{path:'meeting',quote:'物流本期只比价'}]};
 const target=historyEvidenceLinks({evolution:[row]},[{path:'meeting',quote:'客户表示物流本期只比价，后续再议'}])[0];
 assert.equal(target.index,0);
 const updated={evolution:[row,{title:'更早事件',date:'2026-07-01',evidence:[]}]};
 assert.deepEqual(resolveHistoryTarget(updated,target),{view:'evolution',index:1});
 assert.equal(resolveHistoryTarget({evolution:[{...row,evidence:[]}]},target),null);
});
