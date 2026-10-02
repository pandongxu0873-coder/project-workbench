import test from 'node:test';
import assert from 'node:assert/strict';
import { analysisDraftIsCurrent } from '../src/analysisDraft.js';
const result={project_id:'project-a',analysis_id:'analysis-1',fingerprint:'source-1',analysis:{draft:'请核实接口范围'}};
const fresh=()=>({project_id:'project-a',state:'ready',stale:false,fingerprint:'source-1',result:structuredClone(result)});
test('copy accepts the same current project, source and draft',()=>assert.equal(analysisDraftIsCurrent(result,fresh()),true));
test('copy rejects changed evidence even before new analysis finishes',()=>{
  for(const changes of [{stale:true},{state:'running'},{state:'failed'},{fingerprint:'source-2'},{project_id:'project-b'},{stale:undefined}])assert.equal(analysisDraftIsCurrent(result,{...fresh(),...changes}),false);
});
test('copy rejects replacement analysis, foreign project and different draft',()=>{
  for(const changes of [{analysis_id:'analysis-2'},{project_id:'project-b'},{fingerprint:'source-2'},{analysis:{draft:'不同范围'}}])assert.equal(analysisDraftIsCurrent(result,{...fresh(),result:{...structuredClone(result),...changes}}),false);
  assert.equal(analysisDraftIsCurrent(null,fresh()),false);
});
