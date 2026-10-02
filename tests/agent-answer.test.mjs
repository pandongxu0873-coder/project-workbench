import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import AgentAnswer from '../src/AgentAnswer.js';
const render=props=>renderToStaticMarkup(React.createElement(AgentAnswer,props));
test('Agent renders date and business-boundary tables as semantic cells',()=>{
 const html=render({content:'| 项目 | 日期 | 含义 |\n| --- | --- | --- |\n| 星海汽车 | 10月8日 | 建议日期，非客户确认 |',conversationId:'c1'});
 assert.match(html,/<table>/);assert.match(html,/<th>日期<\/th>/);assert.match(html,/<td>建议日期，非客户确认<\/td>/);assert.match(html,/tabindex="0"/);
});
test('GFM autolinks and explicit unknown links do not bypass source receipts',()=>{
 const html=render({content:'https://example.com [未知](https://example.com/other) [原文](/business/source.md)',conversationId:'c1',sources:[{path:'/business/source.md'}]});
 assert.doesNotMatch(html,/href="https:/);assert.match(html,/href="\/api\/agent\/source\?id=c1&amp;path=%2Fbusiness%2Fsource.md"/);
});
test('Agent preserves prose escaping and disabled task lists',()=>{
 const html=render({content:'<script>alert(1)</script>\n\n- [x] 已做\n- [ ] 待反馈',conversationId:'c1'});
 assert.doesNotMatch(html,/<script>/);assert.match(html,/type="checkbox" disabled="" checked=""/);assert.match(html,/待反馈/);
});
