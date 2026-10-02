export function orderedHistory(value,view){return [...(value?.[view]||[])].sort((a,b)=>(a.date||'9999').localeCompare(b.date||'9999'));}
const matches=(a,b)=>a?.path&&a.path===b?.path&&a.quote?.trim()&&b.quote?.trim()&&(a.quote.includes(b.quote)||b.quote.includes(a.quote));
export function historyEvidenceLinks(value,evidence=[]){
 return ['evolution','lifecycle'].flatMap(view=>orderedHistory(value,view).flatMap((row,index)=>
  (row.evidence||[]).some(a=>evidence.some(b=>matches(a,b)))?[{view,index,title:row.title,date:row.date||'',key:JSON.stringify([view,row.title,row.date,row.evidence])}]:[]));
}
export function resolveHistoryTarget(value,target){
 if(!target||!['evolution','lifecycle'].includes(target.view))return null;
 const index=orderedHistory(value,target.view).findIndex(row=>JSON.stringify([target.view,row.title,row.date,row.evidence])===target.key);
 return index<0?null:{view:target.view,index};
}
