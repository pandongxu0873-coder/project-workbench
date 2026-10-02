"""Read-only project-to-CRM reconciliation from explicit, source-bound IDs."""
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from project_workspace import build_projects

ORDER_FIELDS = ('id','bizCode','customerId','customerName','opportunityId','opportunityName','contractId','contractBizCode','orderAmount','performanceAmount','receivedAmount','pendingReceivableAmount','approvalStatus','paymentStatus','k100ContractSignedByBothParties','approvedTime','updatedAt','planReceivableDate1','planReceivableAmount1')
CONTRACT_FIELDS = ('id','bizCode','contractTitle','contractAmount','approvalStatus','signedDate','updatedAt')

def _read(path, default):
    return json.loads(path.read_text()) if path.exists() else default

def business_date(value):
    try:
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if dt.year <= 1970: return None
        return (dt.astimezone(timezone(timedelta(hours=8))) if dt.tzinfo else dt).date().isoformat()
    except ValueError: return None

def promised_date_valid(terms):
    due=business_date(terms.get('due'))
    if not due: return False
    year,month,day=map(int,due.split('-'))
    quote=terms.get('evidence',{}).get('quote','')
    return due in quote or f'{year}年{month}月{day}日' in quote

def evidence_valid(item, project, root):
    rel = item.get('path', '')
    allowed = {p['path'] for p in project['sources'] if p.get('exists') and p.get('readable')}
    path = (root / rel).resolve()
    if rel not in allowed or root.resolve() not in path.parents or not path.is_file(): return False
    raw = path.read_bytes()
    return bool(item.get('quote')) and item['quote'] in raw.decode('utf-8') and hashlib.sha256(raw).hexdigest() == item.get('sha256')

def audit(project_id, knowledge_root, state_root, project_snapshot=None, include_quote=True):
    knowledge_root, state_root = Path(knowledge_root), Path(state_root)
    project = project_snapshot or next((p for p in build_projects(knowledge_root,state_root) if p['id']==project_id),None)
    if not project: raise ValueError('项目不存在，请回到项目重新打开')
    links = _read(knowledge_root/'tracking/project_crm_links.json', {'links':[]}).get('links',[])
    snapshot = _read(state_root/'ka_sales_snapshot.json', {})
    resources = snapshot.get('resources',{})
    order_resource, contract_resource = resources.get('orders',{}), resources.get('contracts',{})
    orders = order_resource.get('data',{}).get('list',[])
    contracts = contract_resource.get('data',{}).get('list',[])
    matches, issues = [], []
    for link in links:
        if link.get('project_id') != project_id: continue
        code = link.get('order_code','')
        proof = link.get('evidence',{})
        if (not code or link.get('project_source') != project['source_path'] or
                not evidence_valid(proof,project,knowledge_root) or code not in proof['quote']):
            issues.append('对应依据已变化或不属于本项目，原对应关系暂不采用'); continue
        rows = [r for r in orders if r.get('bizCode')==code]
        if len(rows)!=1:
            issues.append(f'{code}：当前CRM快照未得到唯一对应订单，不代表没有订单'); continue
        order=rows[0]
        if not link.get('customer_name') or order.get('customerName') != link['customer_name']:
            issues.append(f'{code}：订单客户主体与核验依据不一致，暂不关联'); continue
        candidates = [r for r in contracts if order.get('contractId') is not None and str(r.get('id'))==str(order['contractId']) and r.get('customerId')==order.get('customerId')]
        contract = candidates[0] if len(candidates)==1 else None
        contract_view = {k:contract.get(k) for k in CONTRACT_FIELDS} if contract else None
        if contract_view:
            raw_date = contract_view.get('signedDate')
            contract_view['signedDateDisplay'] = None if not raw_date or str(raw_date).startswith(('1969-12-31','1970-01-01')) else raw_date
        materials = [e for e in link.get('materials',[]) if evidence_valid(e,project,knowledge_root)]
        if len(materials)!=len(link.get('materials',[])): issues.append('部分报价或审批材料已变化，请核对当前版本')
        terms=link.get('customer_payment',{})
        payment=None
        if terms and promised_date_valid(terms) and evidence_valid(terms.get('evidence',{}),project,knowledge_root):
            payment={'customer_due':terms.get('due'),'crm_due':business_date(order.get('planReceivableDate1')),'evidence':terms['evidence']}
            payment['different']=bool(payment['customer_due'] and payment['crm_due'] and payment['customer_due']!=payment['crm_due'])
        matches.append({'order':{k:order.get(k) for k in ORDER_FIELDS},
                        'contract':contract_view,
                        'evidence':proof,'materials':materials,'payment_comparison':payment,
                        'contract_note':'' if contract else '当前快照未匹配合同详情，订单合同编号保留；不据此判断无合同'})
    quote=None
    return {'ok':True,'project_id':project_id,'project_title':project['title'],'matches':matches,'issues':issues,'local_quote':quote,
            'orders_read_at':order_resource.get('fetched_at'),'contracts_read_at':contract_resource.get('fetched_at'),
            'coverage':{k:resources.get(k,{}).get('coverage','not_read') for k in ('orders','contracts')},
            'sync_errors':{k:v for k,v in snapshot.get('errors',{}).items() if k in ('orders','contracts')},
            'mode':'read_only','note':'按原始编号对应，不按客户名或相同金额猜测；订单业绩明细不再加到经营看板总额。'}

def business_sources(project, knowledge_root, state_root):
    if not (Path(knowledge_root)/'tracking/project_crm_links.json').exists(): return []
    value=audit(project['id'],knowledge_root,state_root,project_snapshot=project,include_quote=False)
    if not value['matches'] and not value['issues']: return []
    records=[]
    for row in value['matches']:
        record={kind:{k:v for k,v in (row[kind] or {}).items() if k!='updatedAt'} for kind in ('order','contract')}
        record['payment_comparison']=row['payment_comparison'];records.append(record)
    return [{'path':'local://crm-project-records','relation':'crm_snapshot','date':'','recorded_at':value['orders_read_at'],
             'content':'只读CRM快照，读取时间不是新客户沟通。审批通过、双方签署、验收、实际回款分别核对；订单业绩明细不能再加到公司聚合，也不能证明本地报价新版获批。\n'+json.dumps({'records':records,'issues':value['issues'],'sync_errors':value['sync_errors'],'coverage':value['coverage']},ensure_ascii=False,sort_keys=True), 'truncated':False}]
