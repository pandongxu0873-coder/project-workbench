import {scopeProjects,hasCurrentBrief,stageDistribution,orderOverviewProjects,ATTENTIONS} from '../projectOverview.js';
import {groupPursuits} from '../salesPursuitModel.js';
export const archiveScope=(projects,scope='active')=>projects.filter(p=>scope==='all'||(scope==='archived')===Boolean(p.archive?.archived));
export const pursuitModes={all:'全部',advance:'商机推进',delivery:'交付与经营',waiting:'结果承接',nurture:'客情培育'};
export function selectWorkbench(projects,{mode='all',query='',sort='existing'}={}){const term=query.trim().toLocaleLowerCase();const source=projects.filter(p=>!p.archive?.archived).filter(p=>!term||`${p.customer} ${p.title}`.toLocaleLowerCase().includes(term));const groups=groupPursuits(source);const eligible=new Set(['advance','delivery','waiting','nurture'].flatMap(k=>groups[k].map(p=>p.id)));let items=mode==='all'?source.filter(p=>eligible.has(p.id)):groups[mode]||[];if(sort==='name')items=[...items].sort((a,b)=>String(a.customer).localeCompare(String(b.customer),'zh-CN')||String(a.title).localeCompare(String(b.title),'zh-CN'));return {items,groups,counts:{all:eligible.size,...Object.fromEntries(Object.keys(pursuitModes).filter(k=>k!=='all').map(k=>[k,groups[k].length]))}};}

export function selectProjectOverview(projects,{query='',customer='',stage='全部',attention='全部',archive='active'}={}){
 const scope=scopeProjects(archiveScope(projects,archive),{query,customer});
 const current=scope.filter(p=>p.is_current),history=scope.filter(p=>!p.is_current);
 const stageMatch=p=>stage==='全部'||(stage==='待更新'?!hasCurrentBrief(p):hasCurrentBrief(p)&&p.brief.stage===stage);
 const attentionScope=scope.filter(stageMatch);
 return {scope,current,history,distribution:stageDistribution(scope),attentionScope,attentionCounts:Object.fromEntries(ATTENTIONS.map(a=>[a,attentionScope.filter(p=>hasCurrentBrief(p)&&p.brief.attention===a).length])),items:orderOverviewProjects(attentionScope.filter(p=>attention==='全部'||hasCurrentBrief(p)&&p.brief.attention===attention),{query,customer,stage,attention})};
}
