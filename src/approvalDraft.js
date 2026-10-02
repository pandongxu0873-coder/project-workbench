export const APPROVAL_KEY='workbench-independent-approval';
export const COST_FIELDS=[['own_labor','自有人力预算金额'],['pco','PCO预算金额'],['formal','正式预算金额'],['travel','差旅预算金额'],['procurement','代采预算金额'],['token','Token预算金额'],['presales','售前预算金额'],['other','其他预算金额']];
export const emptyApproval=()=>({open:false,customer:'',requirement:'',version:'',effort:'',rate:'',costs:Object.fromEntries(COST_FIELDS.map(([key])=>[key,'0'])),selfCostEnabled:false,customerConfirmed:false,costsConfirmed:false,calculatorFingerprint:''});
export function restoreApproval(storage){const empty=emptyApproval();try{const value=JSON.parse(storage.getItem(APPROVAL_KEY));if(!value||typeof value!=='object'||Array.isArray(value))return empty;for(const key of ['customer','requirement','version','effort','rate','calculatorFingerprint'])if(typeof value[key]==='string'&&value[key].length<=6000)empty[key]=value[key];for(const key of ['open','selfCostEnabled','customerConfirmed','costsConfirmed'])empty[key]=value[key]===true;for(const [key] of COST_FIELDS)if(typeof value.costs?.[key]==='string'&&value.costs[key].length<50)empty.costs[key]=value.costs[key];if(COST_FIELDS.some(([key])=>typeof value.costs?.[key]!=='string')||typeof value.selfCostEnabled!=='boolean'){empty.customerConfirmed=false;empty.costsConfirmed=false;}}catch{}return empty;}
export function syncApprovalFromQuote(current,values,calculation){const fingerprint=JSON.stringify(values);if(current.calculatorFingerprint===fingerprint)return current;return {...current,calculatorFingerprint:fingerprint,effort:values.quotedDays,rate:values.billingRate,costs:{...current.costs,own_labor:calculation.costKnown?String(calculation.internalTotal):''},selfCostEnabled:values.selfCostEnabled,customerConfirmed:false,costsConfirmed:false};}
export function editApproval(current,patch){return {...current,...patch,customerConfirmed:false,costsConfirmed:false};}
const amount=value=>Number(value).toLocaleString('zh-CN',{minimumFractionDigits:0,maximumFractionDigits:2});
function parsed(value,blankZero=false,places=2){if(typeof value!=='string')return null;const text=value.trim();if(!text)return blankZero?0:null;if(!/^\d+(?:\.\d+)?$/.test(text)||(text.split('.')[1]?.length||0)>places)return null;const number=Number(text);return Number.isFinite(number)&&number>=0?number:null;}
export function formatApproval(draft){
  const effort=parsed(draft.effort,false,6),rate=parsed(draft.rate);
  const costs=Object.fromEntries(COST_FIELDS.map(([key])=>[key,parsed(draft.costs?.[key],true)]));
  const invalid=[];if(effort===null||effort<=0)invalid.push('确认人日需为正数且最多6位小数');if(rate===null||rate<=0)invalid.push('对客单价需为正数且最多2位小数');for(const [key,label] of COST_FIELDS)if(costs[key]===null)invalid.push(`${label}需为有效非负数且最多2位小数`);
  if(invalid.length)return {valid:false,ready:false,text:'请先修正：'+invalid.join('；'),errors:invalid};
  const round=value=>Math.round((value+Number.EPSILON)*100)/100;
  const revenue=round(effort*rate),budget=round(Object.values(costs).reduce((sum,value)=>sum+value,0));
  const selfCost=draft.selfCostEnabled?round(revenue*.1):0,totalCost=round(budget+selfCost),profit=round(revenue-totalCost),margin=profit/revenue*100;
  if(![revenue,budget,selfCost,totalCost,profit,margin].every(Number.isFinite)||revenue<=0)return {valid:false,ready:false,text:'数值超出可计算范围，请核对输入。',errors:['数值超出范围']};
  const customer=draft.customer.trim()||'【客户待填】',requirement=draft.requirement.trim()||'【需求待填】',version=draft.version.trim()||'【版本待填】';
  const reasons=[];if(!draft.customer.trim())reasons.push('客户未填');if(!draft.requirement.trim())reasons.push('需求未填');if(!draft.version.trim())reasons.push('版本未填');if(!draft.customerConfirmed)reasons.push('客户尚未确认本次人日版本');if(!draft.costsConfirmed)reasons.push('内部成本尚未核对');const ready=!reasons.length;
  let text=`@审批负责人，${customer}新增定制需求“${requirement}”（版本：${version}），`;
  text+=ready?`客户已完成工作量复核确认，最终为${String(effort)}人日，按${amount(rate)}元/人日计算，对客报价金额为${amount(revenue)}元。`:`当前为待核实草稿，拟确认${String(effort)}人日，按${amount(rate)}元/人日试算，对客报价金额为${amount(revenue)}元。`;
  text+=`\n\n项目预算成本（以下八项合计）：${amount(budget)}元\n`;
  if(draft.selfCostEnabled)text+=`另计成交额10%自成本：${amount(selfCost)}元（未计入八项预算，不重复计提）\n含自成本的试算总成本：${amount(totalCost)}元\n`;
  text+=`毛利：${amount(profit)}元\n毛利率：${margin.toFixed(2)}%\n\n成本明细：\n`;
  text+=COST_FIELDS.map(([key,label])=>`${label}：${amount(costs[key])}元`).join('\n');
  text+=ready?'\n\n客户已确认人天，内部成本已核对，辛苦审批负责人审批报价申请、合同工单及提前启动工单～':'\n\n待核实：'+reasons.join('；')+'。\n本草稿暂不可作为已确认审批申请提交。';
  return {valid:true,ready,text,revenue,budget,selfCost,totalCost,profit,margin,errors:reasons};
}
