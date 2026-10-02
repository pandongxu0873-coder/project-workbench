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
const {OperationsStrip}=await import(`data:text/javascript;base64,${Buffer.from(transformed.code).toString('base64')}`);
const render=job=>renderToStaticMarkup(React.createElement(OperationsStrip,{data:{operations:{jobs:{communications:job}}}}));

test('running external retry shows its own start instead of an old check or success',()=>{
  const html=render({status:'running',current_started_at:'2026-09-20T01:39:23+08:00',last_attempt_at:'2026-09-20T01:24:32+08:00',last_success_at:'2026-09-19T20:00:00+08:00'});
  assert.match(html,/后台处理中/);assert.match(html,/本轮开始 2026-09-20 01:39/);
  assert.doesNotMatch(html,/最近检查 2026-09-20 01:24|上次完成 2026-09-19/);
});

test('partial terminal receipt retains warning and displays the actual finish',()=>{
  const html=render({status:'partial',current_finished_at:'2026-09-20T01:45:00+08:00',last_success_at:'2026-09-19T20:00:00+08:00',error:'部分材料尚未完成'});
  assert.match(html,/部分更新/);assert.match(html,/本轮结束 2026-09-20 01:45/);assert.match(html,/部分材料尚未完成/);
  assert.doesNotMatch(html,/最近完成|上次完成 2026-09-19/);
});
