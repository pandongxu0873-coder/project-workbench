import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeQualification } from '../src/discovery-model.js';
test('communication edit never restores outdated contact permission', () => {
 const base={owner_scope:'mine',protection:'mine',ownership_evidence:'old',contact_result:'old'};
 const r=mergeQualification(base,{...base,contact_result:'new local'},{...base,protection:'other',ownership_evidence:'new protection'});
 assert.equal(r.merged.protection,'other');assert.equal(r.merged.ownership_evidence,'new protection');assert.equal(r.merged.contact_result,'new local');
});
test('conflicting fields retain remote and identify local backup',()=>{
 const r=mergeQualification({contact_result:'a'},{contact_result:'local'},{contact_result:'remote'});
 assert.equal(r.merged.contact_result,'remote');assert.deepEqual(r.conflicts,['contact_result']);
});
