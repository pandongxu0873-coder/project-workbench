export const projectNeedsReview=p=>p.analysis_state!=='ready'||p.analysis_stale||p.execution_state==='new_evidence_review'||p.brief?.attention==='需核实'||!['需求澄清','方案验证','商务推进','交付实施'].includes(p.brief?.stage);
export function projectGroups(projects){
 const groups=[['需求澄清','#719bee'],['方案验证','#719bee'],['商务推进','#719bee'],['交付实施','#719bee'],['待核实','#719bee']].map(([label,color])=>({key:label,label,color,items:[]}));
 for(const p of projects){const stage=p.brief?.stage;const group=groups.find(g=>g.key===stage)||groups[4];group.items.push(p)}
 for(const g of groups)g.items.sort((a,b)=>String(b.latest_evidence_date||'').localeCompare(String(a.latest_evidence_date||'')));
 return groups;
}
