"""Read models for public research. Reads never manufacture customer progress."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import hashlib
import math
import re

TZ = timezone(timedelta(hours=8))

def public_url(value):
    try:
        u = urlparse(str(value or '').strip())
        return u.geturl() if u.scheme in ('http', 'https') and u.hostname else ''
    except ValueError:
        return ''

def signal_key(row):
    url = public_url(row.get('source_url') or row.get('url'))
    if url:
        u = urlparse(url)
        url = urlunparse((u.scheme.lower(), u.netloc.lower(), u.path.rstrip('/'), '', urlencode(sorted((k,v) for k,v in parse_qsl(u.query) if not k.lower().startswith('utm_'))), ''))
    return hashlib.sha256((url or str(row.get('title',''))).encode()).hexdigest()[:20]

def merge_signals(previous, incoming, stamp, limit=60):
    """An empty/partial scan preserves history; retries retain first-seen identity."""
    old = {signal_key(x): x for x in previous if isinstance(x, dict)}
    merged = dict(old)
    for row in incoming:
        key = signal_key(row)
        prior = old.get(key, {})
        merged[key] = {**prior, **row, 'id': prior.get('id') or row.get('id') or key,
                       'first_seen_at': prior.get('first_seen_at') or row.get('first_seen_at') or prior.get('observed_at') or row.get('observed_at') or stamp,
                       'last_seen_at': stamp or row.get('last_seen_at') or prior.get('last_seen_at','')}
    return sorted(merged.values(), key=lambda x:(str(x.get('published_at','')),str(x.get('first_seen_at',''))), reverse=True)[:limit]

def name_key(value):
    # Customer identifiers may be explicit knowledge-vault paths. Never substring-match.
    name = str(value or '').strip().replace('[[','').replace(']]','').split('|')[0]
    if name.startswith(('entities/','customers/')):name=name.split('/')[-1]
    return re.sub(r'\s+', '', name.removesuffix('.md'))

def identity_aliases(value):
    # Reviewed customer identity labels, never search keywords or related companies.
    groups = [('示例汽车集团/星海汽车','星海汽车','星海汽车商城'), ('松果宠物','松果宠物宠物'), ('云杉百货','云杉')]
    key=name_key(value)
    return next((list(g) for g in groups if key in g), [key])

def same_customer(left, right, aliases=lambda x:[]):
    a = {name_key(left), *(name_key(x) for x in aliases(name_key(left)))} - {''}
    b = {name_key(right), *(name_key(x) for x in aliases(name_key(right)))} - {''}
    return bool(a & b)

def run_status(task, runs, now=None):
    now = now or datetime.now(TZ)
    due = now.replace(hour=6,minute=0,second=0,microsecond=0)
    if now < due: due -= timedelta(days=1)
    stamp = str(task.get('last_run_at') or '')
    try: last = datetime.fromisoformat(stamp.replace('Z','+00:00')); last=last.replace(tzinfo=TZ) if last.tzinfo is None else last
    except ValueError: last = None
    state = task.get('last_run_status', 'waiting')
    overdue = not last or last < due
    successful = next((r.get('at') for r in runs if r.get('status') in ('ok','no_change')), '')
    label = '本轮尚未收到搜索回执' if overdue else {'ok':'本轮结果已保存','no_change':'本轮已查，无新增信号','no_import':'已回传，但有效结果为零','error':'搜索未完成','failed':'搜索未完成','running':'正在搜索'}.get(state,'等待搜索结果')
    return {'last_attempt_at':stamp, 'last_success_at':successful, 'status':state, 'label':label,
            'overdue':overdue, 'scheduled_for':due.isoformat(timespec='seconds'),
            'next_run_at':(due+timedelta(days=1)).isoformat(timespec='seconds'),
            'error':task.get('last_run_error',''), 'schedule':'每天 06:00 · 本机 Codex',
            'checked_customers':task.get('checked_customers',[])}

def build_hub(state, projects=(), aliases=lambda x:[], now=None):
    now = now or datetime.now(TZ)
    rows=[]
    for customer, record in (state.get('customers') or {}).items():
        related=[]
        for project in projects:
            primary=same_customer(customer,project.get('customer'),aliases)
            reference=next((ref for ref in project.get('related_customers',[]) if isinstance(ref,dict)
                            and ref.get('path')==project.get('source_path') and ref.get('link')
                            and same_customer(customer,ref.get('customer'),aliases)),None)
            if primary or reference:
                related.append({'id':project['id'],'title':project['title'],'customer':project['customer'],
                                'relation_scope':'primary_customer' if primary else 'explicit_project_reference',
                                **({'relation_evidence':reference} if not primary else {})})
        for item in record.get('signals',[]):
            row={**item,'customer':customer,'source_url':public_url(item.get('source_url') or item.get('url')),
                 'observed_at':item.get('last_seen_at') or record.get('updated_at',''),
                 'related_projects':related,'relation_scope':'customer','should_create_todo':False}
            date=str(item.get('published_at') or '')[:10]
            try: age=(now.date()-datetime.strptime(date,'%Y-%m-%d').date()).days
            except ValueError: age=None
            row['freshness']='date_unknown' if age is None else 'future_date' if age<0 else 'historical' if age>30 else 'recent'
            row['freshness_label']={'date_unknown':'事件日期待核实','future_date':'日期异常待核实','historical':'历史背景','recent':'30天内公开资料'}[row['freshness']]
            rows.append(row)
    rows.sort(key=lambda x:(x['freshness']=='recent',str(x.get('published_at','')),x['observed_at']),reverse=True)
    unique={}
    for row in rows: unique.setdefault((name_key(row['customer']),signal_key(row)),row)
    return {'ok':True,'generated_at':now.isoformat(timespec='seconds'),'task':run_status(state.get('task',{}),state.get('runs',[]),now),
            'signals':list(unique.values()),'runs':state.get('runs',[])[:10],
            'boundary':'公开事实、AI影响判断和建议分开；客户级关联不代表该项目已有采购或推进。'}

def tender_receipt(state):
    """A scanner result is independent of the scheduler's waiting/running heartbeat."""
    task=state.get('task') or {}
    runs=[r for r in state.get('runs',[]) if r.get('source')=='zhiliao_tender_search']
    latest=runs[0] if runs else {}
    summary=state.get('summary') or {}
    return {'at':latest.get('at') or task.get('last_attempt_at') or task.get('last_run_at',''),
            'status':latest.get('status') or task.get('last_run_status','waiting'),
            'last_success_at':next((r.get('at') for r in runs if r.get('status') in ('ok','no_result')),task.get('last_run_at','')),
            'error':task.get('last_run_error',''),
            'search_total':latest.get('search_total'), 'searched_item_count':latest.get('searched_item_count'),
            'detail_count':latest.get('detail_count'), 'detail_error_count':latest.get('detail_error_count'),
            'result_count':latest.get('result_count'),
            'current_candidate_count':summary.get('candidate_count',0),
            'watch_count':summary.get('watch_count',0), 'next_run_at':task.get('next_run_at','')}

def verified_revenue(evidence, company=''):
    if not isinstance(evidence,dict):return False
    amount=evidence.get('amount_yi');entity=str(evidence.get('entity') or '').strip()
    text=str(evidence.get('source_text') or '')
    try:year=int(evidence.get('year'))
    except (TypeError,ValueError):return False
    if not (isinstance(amount,(int,float)) and not isinstance(amount,bool) and math.isfinite(amount) and amount>0
            and str(evidence.get('status','')).startswith('verified') and public_url(evidence.get('source_url'))
            and entity and (not company or same_customer(entity,company,identity_aliases))
            and evidence.get('period') == 'annual' and 2000 <= year < datetime.now(TZ).year
            and str(year) in text and entity in text):return False
    # Assess the actual revenue sentence, not a nearby GMV/target sentence.
    for sentence in re.split(r'[。；;\n]',text):
        if not re.search(r'营业收入|营收',sentence):continue
        if re.search(r'目标|预计|预测|季度|半年|前[三四一二]季|1[—–-][369]月',sentence,re.I):continue
        for match in re.finditer(r'(?:营业收入|营收)[^\d]{0,12}([\d,.]+)\s*(亿元|亿|万元|元)',sentence):
            try:value=float(match[1].replace(',',''))*{'亿元':1,'亿':1,'万元':0.0001,'元':0.00000001}[match[2]]
            except ValueError:continue
            if math.isclose(value,amount,rel_tol=.005):return True
    return False

def deadline_nodes(text):
    """Conservative node-local extraction; an unresolved earlier node blocks admission."""
    markers = re.compile(r'(?:招标文件|采购文件|文件)(?:获取|领取|发售)(?:截止)?时间|(?:报名|提问|答疑|报价|投标|响应|申请文件|投标文件递交|响应文件递交)(?:截止时间|截止日期|截止|时间)|开标时间')
    dates = re.compile(r'(20\d{2})\s*(?:年|[-/.])\s*(\d{1,2})\s*(?:月|[-/.])\s*(\d{1,2})\s*日?')
    matches=list(markers.finditer(text));nodes=[]
    for i,m in enumerate(matches):
        segment=text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)]
        # Stop at the next sentence or unrelated financial/service node.
        segment=re.split(r'[。；;\n]|保证金|服务期限|合同期限|发布时间|公告日期',segment,maxsplit=1)[0][:160]
        found=[]
        for d in dates.finditer(segment):
            try:found.append(datetime(int(d[1]),int(d[2]),int(d[3])).date().isoformat())
            except ValueError:pass
        interval=bool(re.search(r'获取|领取|发售|报名时间',m[0])) and '截止' not in m[0]
        if re.search(r'延期|更正|变更|另行通知',segment) or not found or (interval and len(found)<2):
            nodes.append({'kind':m[0],'date':'','source_text':(m[0]+segment)[:180],'unresolved':True})
        else:
            nodes.append({'kind':m[0],'date':found[-1] if interval else found[0],'source_text':(m[0]+segment)[:180],'unresolved':False})
    return nodes
