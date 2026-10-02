const known=name=>Boolean(name)&&!/(待核|待确认|未知|未归属)/.test(name);
export function customerDirectory(accounts=[],projects=[],query='',customerFilter='') {
  const rows=new Map(),names=new Map();
  for(const account of accounts){
    const name=String(account.name||'客户名称待核实').trim();
    const row={id:`account:${account.id}`,name,account,projects:[]};
    rows.set(row.id,row);
    if(known(name))names.set(name,[...(names.get(name)||[]),row]);
  }
  for(const project of projects){
    const name=String(project.customer||'客户待核实').trim();
    const matches=names.get(name)||[];
    // Exact, unique identity only. Same industry, similar titles, aliases or
    // multiple same-name formal accounts are not enough to merge a customer.
    const explicit=project.account_id&&rows.get(`account:${project.account_id}`);
    let row=explicit||(matches.length===1?matches[0]:null);
    if(!row){
      const id=known(name)?`customer:${name}`:`project:${project.id}`;
      row=rows.get(id)||{id,name,account:null,projects:[]};rows.set(id,row);
    }
    row.projects.push(project);
  }
  const term=query.trim().toLocaleLowerCase();
  return [...rows.values()].filter(row=>!customerFilter||row.name===customerFilter||row.projects.some(p=>p.customer===customerFilter)).filter(row=>!term||`${row.name} ${row.projects.map(p=>p.title).join(' ')}`.toLocaleLowerCase().includes(term))
    .sort((a,b)=>Number(b.projects.some(p=>p.is_current))-Number(a.projects.some(p=>p.is_current))||a.name.localeCompare(b.name,'zh-CN'));
}
