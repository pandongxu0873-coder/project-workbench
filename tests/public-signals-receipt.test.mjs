import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { transformWithOxc } from 'vite';

const file=new URL('../src/PublicSignals.jsx',import.meta.url);
const source=(await readFile(file,'utf8'))
  .replace("from 'react'",`from '${import.meta.resolve('react')}'`)
  .replace("from './signalProjectContext.js'",`from '${new URL('../src/signalProjectContext.js',import.meta.url)}'`)
  .replace("from './api.js'",`from '${new URL('../src/api.js',import.meta.url)}'`)
  .replace("from './discovery-model.js'",`from '${new URL('../src/discovery-model.js',import.meta.url)}'`)
  .replace("from 'lucide-react'",`from '${import.meta.resolve('lucide-react')}'`)
  .replace(/import '[^']+\.css';/g,'');
const transformed=await transformWithOxc(source,file.pathname,{jsx:{runtime:'classic'}});
const {ResearchStatus,SignalRows,ResearchOverview}=await import(`data:text/javascript;base64,${Buffer.from(transformed.code).toString('base64')}`);
const render=(data,compact=false)=>renderToStaticMarkup(React.createElement(ResearchStatus,{data,compact}));

test('missing opportunity receipt is not represented as a completed zero-result search',()=>{
  const html=render({opportunity_task:{status:'waiting',overdue:true},opportunity_receipt:{}});
  assert.match(html,/新客户搜索/);
  assert.match(html,/尚无完成回执/);
  assert.match(html,/查询范围、新增线索和核对排除说明尚待回传/);
  assert.doesNotMatch(html,/回执查询 0|新增客户线索 0|本轮已完成|本轮已查/);
});

test('verified zero results show completed coverage independently of customers and tenders',()=>{
  const html=render({opportunity_task:{status:'no_change',last_success_at:'2026-09-20T01:00:00+08:00'},opportunity_receipt:{
    at:'2026-09-20T01:00:00+08:00',checked_at:'2026-09-20T00:58:00+08:00',status:'no_change',candidate_added_count:0,
    checked_queries:[{group:'连锁零售',query:'会员系统升级'},{group:'文旅',query:'私域系统'}],
    coverage_notes:[{group:'文旅',result:'未发现合格新增',gap:'部分公告仅有摘要'}],
    reviewed_exclusions:[{company:'已合作客户',reason:'已有合作，不作新增候选',source_url:'https://example.com/customer'}],
    source_links:[{url:'https://example.com/report',read_status:'已核读',supports:'会员系统采购范围'},{url:'javascript:alert(1)',read_status:'未核读'}]
  }});
  assert.match(html,/本轮已查，无新增线索/);
  assert.match(html,/上次实际完成 2026-09-20 00:58/);
  assert.match(html,/回执查询 2 式/);
  assert.match(html,/新增客户线索 0 个/);
  assert.match(html,/查询范围：连锁零售、文旅/);
  assert.match(html,/核对与排除说明：已合作客户 · 已有合作，不作新增候选/);
  assert.match(html,/覆盖缺口：部分公告仅有摘要/);
  assert.match(html,/href="https:\/\/example.com\/customer"[^>]*>原文 ↗/);
  assert.match(html,/href="https:\/\/example.com\/report"/);
  assert.match(html,/核读状态：已核读 · 支持依据：会员系统采购范围/);
  assert.doesNotMatch(html,/href="javascript:/);
  assert.doesNotMatch(html,/标讯核查|客户研究：/);
});

test('failed latest search retains actual previous completion and missing counts remain unknown',()=>{
  const html=render({opportunity_task:{status:'failed',last_success_at:'2026-09-19T06:20:00+08:00',error:'来源读取失败'},opportunity_receipt:{at:'2026-09-20T06:20:00+08:00',status:'failed'}});
  assert.match(html,/本轮搜索未完成/);
  assert.match(html,/上次实际完成 2026-09-19 06:20/);
  assert.match(html,/查询数未提供/);
  assert.match(html,/新增客户线索 未提供/);
  assert.match(html,/核对与排除说明未提供/);
  assert.match(html,/覆盖缺口未提供，不能据此认定已完整覆盖/);
  assert.doesNotMatch(html,/上次实际完成 2026-09-20|新增客户线索 0/);
});

test('home compact status does not expand opportunity receipts or query details',()=>{
  assert.doesNotMatch(render({opportunity_task:{status:'no_change'},opportunity_receipt:{at:'2026-09-20',checked_queries:[{group:'测试',query:'详细搜索式'}]}},true),/新客户搜索|详细搜索式/);
});

test('an older successful receipt cannot claim completion of the current overdue run',()=>{
  const html=render({opportunity_task:{status:'no_change',overdue:true,last_success_at:'2026-09-19T06:20:00+08:00'},opportunity_receipt:{at:'2026-09-19T06:20:00+08:00',status:'no_change',candidate_added_count:0,checked_queries:['旧查询']}});
  assert.match(html,/本轮尚未收到搜索回执/);
  assert.match(html,/上次实际完成 2026-09-19 06:20/);
  assert.match(html,/回执查询 1 式/);
  assert.doesNotMatch(html,/本轮已查|本轮已完成/);
});

test('public dates and project links describe evidence rather than current eligibility or shared status',()=>{
  const renderRows=related_projects=>renderToStaticMarkup(React.createElement(SignalRows,{rows:[{id:'public',customer:'示例汽车集团/星海汽车',title:'历史原文仍保留',published_at:'2026-09-10',related_projects}],navigate:()=>{}}));
  const linked=renderRows([{id:'rights',title:'星海汽车数字资产中台',customer:'示例汽车集团汽车',relation_scope:'explicit_project_reference'}]);
  assert.match(linked,/来源日期 2026-09-10/);
  assert.match(linked,/关联项目 · 影响仍待核实/);
  assert.match(linked,/资料明示关联，不代表业务关系或项目影响已确认/);
  assert.match(linked,/星海汽车数字资产中台/);
  assert.match(linked,/相对时间按原文日期理解；当前可投机会以待你准入的截止核验为准/);
  assert.doesNotMatch(linked,/同客户项目/);
  assert.match(renderRows([]),/尚无已核对的关联项目/);
});


test('research overview keeps unknown counts unknown and current tasks override old success',()=>{
 const missing=renderToStaticMarkup(React.createElement(ResearchOverview,{data:{}}));
 assert.doesNotMatch(missing,/>0</);
 const html=renderToStaticMarkup(React.createElement(ResearchOverview,{data:{
  task:{status:'ok',label:'本轮结果已保存'},
  tender_receipt:{status:'ok',at:'2026-09-19T06:00:00+08:00',detail_count:4},
  operations:{jobs:{tender:{status:'running',current_started_at:'2026-09-20T06:00:00+08:00'}}},
  opportunity_task:{status:'failed',overdue:true},
  opportunity_receipt:{status:'ok',at:'2026-09-19T06:10:00+08:00',candidate_added_count:0}
 }}));
 assert.match(html,/核查中/);
 assert.match(html,/本轮开始 2026-09-20 06:00/);
 assert.match(html,/本轮尚未收到搜索回执/);
 assert.match(html,/最近保存 2026-09-19 06:10/);
 assert.doesNotMatch(html,/本轮已完成|lucide-circle-check/);
});
