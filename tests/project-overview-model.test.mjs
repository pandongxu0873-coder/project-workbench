import test from 'node:test';
import assert from 'node:assert/strict';
import {projectGroups,projectNeedsReview} from '../src/projectOverviewModel.js';
test('unknown and missing stages remain visible and no projects disappear',()=>{const ps=[{id:'1',brief:{stage:'商务推进'}},{id:'2',brief:{stage:'new stage'}},{id:'3'}];const gs=projectGroups(ps);assert.equal(gs.flatMap(g=>g.items).length,3);assert.equal(gs[4].items.length,2);});
test('stale and failed analysis never loses review indication',()=>{for(const p of [{analysis_state:'error',brief:{attention:'可推进',stage:'交付实施'}},{analysis_state:'ready',analysis_stale:true,brief:{stage:'商务推进'}},{analysis_state:'ready',execution_state:'new_evidence_review',brief:{stage:'方案验证'}}])assert.ok(projectNeedsReview(p));assert.equal(projectNeedsReview({analysis_state:'ready',analysis_stale:false,brief:{attention:'可推进',stage:'需求澄清'}}),false)});
