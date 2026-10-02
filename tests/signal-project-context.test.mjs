import test from 'node:test';
import assert from 'node:assert/strict';
import {signalProjectContext,contextForProject,signalVerificationNote} from '../src/signalProjectContext.js';
test('only an explicitly listed related project can carry a public signal',()=>{
 const item={id:'s',title:'公开入口变化',related_projects:[{id:'one'}]};
 assert.equal(signalProjectContext(item,{id:'two'}),null);
 const context=signalProjectContext(item,{id:'one'});
 assert.equal(contextForProject(context,'two'),null);
 assert.equal(contextForProject(context,'one').title,'公开入口变化');
});
test('carried signal preserves source, judgment and verification without promoting commitment',()=>{
 const item={id:'s',title:'媒体称入口变化',published_at:'2026-09-18',source:'媒体',source_url:'https://example.com/story',impact_judgment:'可能影响归因',recommended_action:'核对入口与来源识别',related_projects:[{id:'one'}]};
 const context=signalProjectContext(item,{id:'one'}),note=signalVerificationNote(context);
 assert.match(note,/不是客户确认/);assert.match(note,/不自动改变原范围/);
 assert.match(note,/AI影响判断：可能影响归因/);assert.match(note,/本次希望核实：核对入口与来源识别/);
 assert.match(note,/https:\/\/example.com\/story/);assert.equal(item.related_projects.length,1);
});
