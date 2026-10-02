import test from 'node:test';import assert from 'node:assert/strict';import {projectNext,blockerKind} from '../src/projectPresentation.js';
test('historical feedback is never a next action',()=>{const p={execution:{feedback:'上周已经把方案发给客户'},analysis_state:'running'};assert.equal(projectNext(p),'最新判断待更新；已有进展可在项目内查看');});
test('explicit next arrangements and boundaries survive stale analysis',()=>{assert.equal(projectNext({execution:{next_step:'核对验收清单'}}),'核对验收清单');assert.equal(projectNext({execution:{relationship:'no_contact',next_step:'发消息'}}),'遵守暂勿联系约定');});
test('source gaps are not customer blockers',()=>{assert.equal(blockerKind('原件未收录'),'资料范围');assert.equal(blockerKind('预算尚未批准'),'业务卡点');});
test('guard-generated execution receipt stays out of the next-action column',()=>{const p={analysis_state:'ready',brief:{next_action:'「提交方案」已做，结果尚待现有资料核对'},execution:{quick_outcome:'done',quick_action:'提交方案'}};assert.equal(projectNext(p),'暂无新的行动建议');p.brief.next_action='核对另一笔回款';assert.equal(projectNext(p),'核对另一笔回款');});
test('waiting receipt never replaces a separate actual arrangement',()=>{const p={execution_state:'done_waiting',execution:{quick_outcome:'done',quick_action:'提交方案'}};assert.equal(projectNext(p),'新建议待更新 · 查看项目责任');p.execution.next_step='明天核对发票';assert.equal(projectNext(p),'明天核对发票');});

test("empty execution receipt is safe", async()=>{const {isExecutionReceipt}=await import("../src/projectPresentation.js");assert.equal(isExecutionReceipt("建议",null),false);assert.equal(isExecutionReceipt("建议",undefined),false);});
