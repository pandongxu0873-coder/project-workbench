"""Read-only personal K100 results. No opportunity inference or CRM writes."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, quote
from zoneinfo import ZoneInfo
from calendar import monthrange
import k100_sync


def number(value):
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
        if not parsed.is_finite():
            raise ValueError()
        return str(parsed)
    except (ValueError, InvalidOperation):
        raise k100_sync.SyncError('K100 金额格式未识别，未将缺失数据当作零') from None


def collection_summary(period_range):
    rows, seen, total = [], set(), None
    for page in range(100):
        query = urlencode({'items':'false','page':page,'size':20,'sort':'createdAt:DESC','filters':'[]'})
        data = k100_sync.request('/api/sales/signed-orders?' + query)
        if not isinstance(data, dict) or not isinstance(data.get('items'),list) or type(data.get('totalElements')) is not int:
            raise k100_sync.SyncError('订单分页未核完整，回款暂不汇总')
        if total is None:
            total = data['totalElements']
        if data['totalElements'] != total or data.get('page',page) != page:
            raise k100_sync.SyncError('订单读取期间发生变化，回款暂不汇总')
        for row in data['items']:
            key = str(row.get('id') or '')
            if not key or key in seen:
                raise k100_sync.SyncError('订单分页重复或缺编号，回款暂不汇总')
            seen.add(key); rows.append(row)
        if len(rows) == total:
            break
        if not data['items'] or len(rows) > total:
            raise k100_sync.SyncError('订单分页不完整，回款暂不汇总')
    else:
        raise k100_sync.SyncError('订单超过读取范围，回款暂不汇总')
    orders, received, pending = [], Decimal(0), Decimal(0)
    for row in rows:
        if row.get('approvalStatus') != '审批通过':
            continue
        fields = row.get('fields',{})
        try:
            raw = fields['orderDate']
            if len(raw) == 10:
                order_day = date.fromisoformat(raw).isoformat()
            else:
                stamp = datetime.fromisoformat(raw.replace('Z','+00:00'))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
                order_day = stamp.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
        except (ValueError,TypeError,KeyError):
            raise k100_sync.SyncError('订单日期缺失，暂不能按期间汇总回款') from None
        if not period_range['from'] <= order_day <= period_range['through']:
            continue
        paid, unpaid = number(fields.get('receivedAmount')), number(fields.get('pendingReceivableAmount'))
        if paid is None or unpaid is None:
            raise k100_sync.SyncError('部分订单回款字段缺失，暂不显示合计')
        received += Decimal(paid); pending += Decimal(unpaid)
        orders.append({'id':str(row['id']), 'order_no':row.get('orderNo'), 'customer':row.get('customerName'),
                       'order_date':order_day, 'received':paid, 'pending':unpaid,
                       'url':k100_sync.BASE + '/sales-workspace/signed-orders/' + quote(k100_sync.valid_id(str(row.get('orderId') or '')), safe='')})
    sync_state = None
    if rows and rows[0].get('customerId'):
        try:
            customer_id = k100_sync.valid_id(str(rows[0]['customerId']))
            summary = k100_sync.request('/api/sales/customer-business-summary/' + customer_id)
            sync_state = next((s for s in summary.get('synchronization',[]) if s.get('module') == 'SIGNED_ORDERS'),None)
        except k100_sync.SyncError:
            pass
    return {'available':True,'scope':'当前账号可见订单','order_count':len(orders),'received':str(received),
            'pending':str(pending),'orders':orders,'synchronization':sync_state}


def business_summary(period='QUARTER', selected_date=None):
    if period not in ('MONTH', 'QUARTER', 'YEAR'):
        raise k100_sync.SyncError('仅支持年度、季度和月度')
    try:
        day = date.fromisoformat(selected_date or datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat())
    except (ValueError, TypeError):
        raise k100_sync.SyncError('统计日期无效') from None
    account = k100_sync.identity()
    context = k100_sync.request('/api/sales/dashboard/context')
    person = str(context.get('selfId') or '')
    if not person or not any(str(p.get('id')) == person and str(p.get('accountId')) == account for p in context.get('people',[])):
        raise k100_sync.SyncError('K100 未返回本人业绩身份，未使用团队数据')
    query = urlencode({'level':'PERSON', 'subjectId':person, 'period':period, 'date':day.isoformat()})
    board = k100_sync.request('/api/sales/dashboard?' + query)
    start_month = 1 if period == 'YEAR' else ((day.month-1)//3*3+1 if period == 'QUARTER' else day.month)
    end_month = 12 if period == 'YEAR' else (start_month+2 if period == 'QUARTER' else start_month)
    expected_range = {'from':date(day.year,start_month,1).isoformat(),
                      'through':date(day.year,end_month,monthrange(day.year,end_month)[1]).isoformat(),'period':period}
    if board.get('level') != 'PERSON' or str(board.get('subjectId')) != person or board.get('range') != expected_range:
        raise k100_sync.SyncError('K100 返回的统计身份或期间不一致')
    metric = board.get('metric')
    if not isinstance(metric, dict) or 'completed' not in metric:
        raise k100_sync.SyncError('K100 业绩未能读取')
    result = {'ok':True, 'source':'新 K100', 'person':board.get('title'), 'range':board['range'],
            'as_of':board.get('asOf'), 'read_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
            'source_updated_at':board.get('sync',{}).get('SIGNED_ORDERS'),
            'metric':{key:number(metric.get(key)) for key in ('target','completed','rate','gap')},
            'review_count':metric.get('review'), 'notes':board.get('notes',[]),
            'cash':{'available':False, 'reason':'回款暂未读取。'}}
    try:
        result['cash'] = collection_summary(board['range'])
        state = result['cash'].pop('synchronization',None)
        result['source_paused'] = state is not None and state.get('enabled') is False
        result['source_status'] = state.get('status') if state else None
    except k100_sync.SyncError as exc:
        result['cash'] = {'available':False,'reason':str(exc)}
    return result
