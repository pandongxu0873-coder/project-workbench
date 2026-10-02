import test from 'node:test';
import assert from 'node:assert/strict';
import {selectQuoteIdentity, quoteIdentity} from '../src/quoteIdentity.js';

test('same scope continues same chain; another customer or requirement owns a separate chain',()=>{
 const current=quoteIdentity({quote_id:'A',revision:1,values:{customer:'甲',requirement:'需求一'}});
 assert.equal(selectQuoteIdentity(current,{customer:'甲',requirement:'需求一'},()=> 'unused'),current);
 for(const values of [{customer:'乙',requirement:'需求一'},{customer:'甲',requirement:'需求二'}]) {
  assert.deepEqual(selectQuoteIdentity(current,values,()=> 'B'),{quote_id:'B',revision:0,...values});
 }
});
test('explicit independent quote does not continue old scope even when text stays equal',()=>{
 assert.equal(selectQuoteIdentity({quote_id:'new',revision:0},{customer:'甲',requirement:'需求'},()=> 'C').quote_id,'C');
 const recovered=quoteIdentity({quote_id:'A',revision:3,values:{customer:'甲',requirement:'需求'}});
 assert.equal(selectQuoteIdentity(recovered,{customer:'甲',requirement:'需求'},()=> 'C').revision,3);
});
