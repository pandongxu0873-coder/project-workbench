export const QUICK_QUOTE_KEY='workbench-independent-quote';
export const emptyQuote=()=>({actualDays:'',internalCost:'',quotedDays:'',billingRate:'2000',targetMargin:'',selfCostEnabled:false});
export function restoreQuote(storage){
  const empty=emptyQuote();
  try{const saved=JSON.parse(storage.getItem(QUICK_QUOTE_KEY));if(!saved||typeof saved!=='object'||Array.isArray(saved))return empty;for(const key of Object.keys(empty)){if(key==='selfCostEnabled')empty[key]=saved[key]===true;else if(typeof saved[key]==='string'&&saved[key].length<50)empty[key]=saved[key];}}catch{}
  return empty;
}
export function calculateQuote(values){
  const known=key=>values[key]!==''&&Number.isFinite(Number(values[key]))&&Number(values[key])>=0;
  const number=key=>known(key)?Number(values[key]):0;
  let revenueKnown=known('quotedDays')&&known('billingRate')&&number('quotedDays')>0&&number('billingRate')>0;
  let costKnown=known('actualDays')&&known('internalCost');
  const round=value=>Math.round(value*100)/100;
  const revenue=round(number('quotedDays')*number('billingRate'));
  const selfCost=values.selfCostEnabled?round(revenue*.1):0;
  const internalTotal=round(number('actualDays')*number('internalCost'));
  const grossProfit=round(revenue-internalTotal-selfCost);
  const marginRate=revenue?grossProfit/revenue:0;
  if(![revenue,selfCost,internalTotal,grossProfit,marginRate].every(Number.isFinite)){revenueKnown=false;costKnown=false;}
  const comparisonKnown=revenueKnown&&costKnown&&known('targetMargin')&&number('targetMargin')<=100;
  return {revenueKnown,costKnown,comparisonKnown,revenue,selfCost,internalTotal,grossProfit,marginRate,passed:comparisonKnown&&marginRate>=number('targetMargin')/100};
}
