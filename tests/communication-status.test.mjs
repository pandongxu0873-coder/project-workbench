import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { transformWithOxc } from 'vite';

const file=new URL('../src/CommunicationSync.jsx',import.meta.url);
const source=(await readFile(file,'utf8'))
  .replace("from 'react'",`from '${import.meta.resolve('react')}'`)
  .replace("from 'lucide-react'",`from '${import.meta.resolve('lucide-react')}'`)
  .replace("from './api.js'",`from '${new URL('../src/api.js',import.meta.url)}'`)
  .replace("from './communicationSync.js'",`from '${new URL('../src/communicationSync.js',import.meta.url)}'`)
  .replace("import './communication-sync.css';",'');
const transformed=await transformWithOxc(source,file.pathname,{jsx:{runtime:'classic'}});
const {CommunicationRunStatus,CommunicationReceiptScope}=await import(`data:text/javascript;base64,${Buffer.from(transformed.code).toString('base64')}`);
const render=data=>renderToStaticMarkup(React.createElement(CommunicationRunStatus,{data}));
const savedGroups={groups:[{id:'previous-results',items:[{id:'already-filed'}]}]};
const projectSavedReceipt=receipt=>JSON.parse(execFileSync('python3',['-c',`
import json, sys, tempfile
from pathlib import Path
from unittest.mock import patch
import communication_jobs as jobs
with tempfile.TemporaryDirectory() as folder:
    state=Path(folder)/'state'; root=state/'communication_pipeline'; root.mkdir(parents=True)
    knowledge=Path(folder)/'knowledge'; knowledge.mkdir()
    (root/'latest.json').write_text(json.dumps(json.load(sys.stdin)))
    with patch.object(jobs,'daily_digest',return_value={'groups':[]}):
        print(json.dumps(jobs.status(state,knowledge)))
`],{cwd:new URL('..',import.meta.url),input:JSON.stringify(receipt),encoding:'utf8',env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}}));

test('partial collected results cannot replace warning title and unresolved detail with completion',()=>{
  const html=render({job:{state:'partial'},receipt:{run_id:'current',status:'partial',unresolved:{ready_for_review:1,extraction_pending:2}},digest:savedGroups});
  assert.match(html,/sync-run-strip warning/);
  assert.match(html,/同步未完成，原件已保留/);
  assert.match(html,/2 份材料提取未完成/);
  assert.match(html,/1 份材料分析未完成/);
  assert.match(html,/lucide-circle-alert/);
  assert.doesNotMatch(html,/已自动归档，以下为整理结果|lucide-circle-check/);
});

test('failed job wins over saved results and the preceding completed receipt',()=>{
  const html=render({job:{state:'failed'},receipt:{run_id:'previous',status:'completed',checked_at:'2026-09-20T01:00:00+08:00'},digest:savedGroups});
  assert.match(html,/本轮未完成，已保留进度/);
  assert.match(html,/sync-run-strip warning/);
  assert.match(html,/上次采集回执 2026-09-20 01:00/);
  assert.doesNotMatch(html,/本轮整理完成|lucide-circle-check/);
});

test('running progress remains visible with completed historical groups',()=>{
  const html=render({job:{running:true,phase:'refreshing',phase_label:'更新项目判断',refresh_done:1,refresh_total:5},receipt:{run_id:'previous',status:'completed'},digest:savedGroups});
  assert.match(html,/sync-run-strip running/);
  assert.match(html,/更新项目判断 · 已更新 1 \/ 5 个项目/);
  assert.match(html,/可以离开本页，后台继续/);
  assert.doesNotMatch(html,/本轮整理完成|lucide-circle-check/);
});

test('partial receipt without detailed counters still cannot claim full completion',()=>{
  const html=render({receipt:{run_id:'partial',status:'partial'},digest:savedGroups});
  assert.match(html,/本轮仅部分完成，已有整理结果保留/);
  assert.match(html,/sync-run-strip warning/);
  assert.doesNotMatch(html,/本轮整理完成|lucide-circle-check/);
});

test('completed work shows success but initial loading never does',()=>{
  const completed=render({receipt:{run_id:'done',status:'completed'},digest:savedGroups});
  assert.match(completed,/sync-run-strip done/);
  assert.match(completed,/本轮整理完成/);
  assert.match(completed,/lucide-circle-check/);
  const loading=render(null);
  assert.match(loading,/正在读取整理结果/);
  assert.doesNotMatch(loading,/lucide-circle-check/);
});

test('saved retry receipt passes through the actual API projection and renders one of one with two extraction gaps',()=>{
  const data=projectSavedReceipt({run_id:'retry',status:'partial',checked_at:'2026-09-20T02:17:18+08:00',source_scope:['stored_material_retry'],material_ids:['saved-weekly-report'],completed_material_ids:['saved-weekly-report'],unresolved:{extraction_pending:2},observed:0,duplicates:0,from:'2026-09-18',to:'2026-09-20',gaps:[{source:'图片一',reason:'提取未完成'},{source:'图片二',reason:'提取未完成'}]});
  const html=renderToStaticMarkup(React.createElement(React.Fragment,null,
    React.createElement(CommunicationRunStatus,{data}),
    React.createElement(CommunicationReceiptScope,{receipt:data.receipt,job:data.job})));
  assert.match(html,/已保存材料补跑1份，完成1份/);
  assert.match(html,/上次补跑回执 2026-09-20 02:17/);
  assert.match(html,/sync-run-strip warning/);
  assert.match(html,/2 份材料提取未完成/);
  assert.match(html,/来源缺口仍按全队列显示/);
  assert.doesNotMatch(html,/上次采集回执|读取范围：|本轮读取|重复跳过|2026-09-18|本轮整理完成|lucide-circle-check/);
});

test('the real previous API shape with omitted retry IDs cannot claim zero materials',()=>{
  const data={job:{state:'partial',phase:'done',analysis_done:4,analysis_total:4,running:false},receipt:{run_id:'2026-09-20T02-01-55+08-00-134d7b',status:'partial',checked_at:'2026-09-20T02:17:18+08:00',source_scope:['stored_material_retry'],observed:0,new:0,unresolved:{ready_for_review:0,extraction_pending:2,needs_review:0},projects:[],refreshed:[]}};
  const html=renderToStaticMarkup(React.createElement(React.Fragment,null,
    React.createElement(CommunicationRunStatus,{data}),
    React.createElement(CommunicationReceiptScope,{receipt:data.receipt,job:data.job})));
  assert.match(html,/已保存材料补跑，回执未提供份数/);
  assert.match(html,/sync-run-strip warning/);
  assert.match(html,/2 份材料提取未完成/);
  assert.doesNotMatch(html,/补跑0份|完成0份|本轮读取/);
});

test('ordinary collection receipt preserves its date range and observed counts',()=>{
  const receipt={source_scope:['email'],from:'2026-09-18',to:'2026-09-20',observed:12,duplicates:4};
  const html=renderToStaticMarkup(React.createElement(CommunicationReceiptScope,{receipt}));
  assert.match(html,/读取范围：2026-09-18 — 2026-09-20/);
  assert.match(html,/本轮读取 12 项，重复跳过 4 项/);
  assert.doesNotMatch(html,/补跑/);
});
