// K100 owns formal identity. Only explicit IDs or unique full legal names join.
export function k100Directory(roster=[],projects=[],summary={},signals=[]) {
 const rows=roster.filter(x=>x.isMine===true).map(x=>({...x,projects:[],signals:[]}));
 const byId=new Map(rows.map(x=>[String(x.id),x]));
 const byName=new Map();for(const row of rows){const name=row.legalName?.trim();if(name)byName.set(name,byName.has(name)?null:row);}
 for(const project of projects){const id=summary[project.id]?.link?.customer_id;const row=id?byId.get(String(id)):byName.get(project.customer?.trim());if(row)row.projects.push(project);}
 const aliases=new Map(),byProject=new Map();
 for(const row of rows)for(const p of row.projects){byProject.set(p.id,row);const name=p.customer?.trim();if(name)aliases.set(name,aliases.has(name)&&aliases.get(name)!==row?null:row);}
 for(const signal of signals){const row=signal.k100_customer_id?byId.get(String(signal.k100_customer_id)):signal.project_id?byProject.get(signal.project_id):byName.get(signal.customer?.trim())||aliases.get(signal.customer?.trim());if(row)row.signals.push(signal);}
 return rows;
}

export function isFormalCustomer(item,roster=[]) {
 const id=item.k100_customer_id;
 if(id)return roster.some(x=>String(x.id)===String(id));
 const name=(item.company||item.customer||item.name||'').trim();
 return !!name&&roster.some(x=>x.legalName?.trim()===name);
}
