"""Independent, immutable quotation snapshots. No project or external write required."""
import fcntl
import json
import os
import re
import tempfile
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

COST_KEYS = ('own_labor', 'pco', 'formal', 'travel', 'procurement', 'token', 'presales', 'other')

class QuoteConflict(ValueError):
    pass

def _number(value, places=2):
    if not isinstance(value, str): raise ValueError('报价数值必须为文字数字')
    try: number = Decimal(value.strip() or '0')
    except InvalidOperation: raise ValueError('报价包含无效数值') from None
    if not number.is_finite() or number < 0 or number > Decimal('100000000000') or number != number.quantize(Decimal(1).scaleb(-places)):
        raise ValueError('报价数值超出范围或精度，请核对')
    return number

def normalize(payload):
    if not isinstance(payload, dict): raise ValueError('报价格式不正确')
    value = {}
    for key in ('customer', 'requirement', 'version'):
        text = payload.get(key, '')
        if not isinstance(text, str) or len(text) > 6000: raise ValueError('报价文字字段格式不正确')
        value[key] = text.strip()
    for key in ('selfCostEnabled', 'customerConfirmed', 'costsConfirmed'):
        if not isinstance(payload.get(key, False), bool): raise ValueError('报价确认标记格式不正确')
        value[key] = payload.get(key, False)
    effort, rate = _number(payload.get('effort', ''), 6), _number(payload.get('rate', ''))
    if not effort or not rate: raise ValueError('请先填入有效的报价人天和单价')
    costs = payload.get('costs', {})
    if not isinstance(costs, dict) or set(costs) - set(COST_KEYS): raise ValueError('成本字段不正确')
    budget = {key: _number(costs.get(key, '')) for key in COST_KEYS}
    value.update(effort=str(effort), rate=str(rate), costs={k: str(v) for k, v in budget.items()})
    money = lambda x: x.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    revenue = money(effort * rate)
    if revenue <= 0: raise ValueError('报价金额不足0.01元，请核对人天与单价')
    self_cost = money(revenue / 10) if value['selfCostEnabled'] else Decimal(0)
    base = sum(budget.values(), Decimal(0)); total = base + self_cost; profit = revenue - total
    calculation = {k: str(v) for k, v in dict(revenue=revenue, budget=base, self_cost=self_cost, total_cost=total, profit=profit, margin=money(profit / revenue * 100)).items()}
    return value, calculation

def _path(root, quote_id):
    if not isinstance(quote_id, str) or not re.fullmatch(r'[a-f0-9-]{36}', quote_id): raise ValueError('报价编号不正确')
    return root / 'quote_versions' / (quote_id + '.json')

def read(root, quote_id):
    path = _path(root, quote_id)
    if not path.exists(): return {'quote_id': quote_id, 'revision': 0, 'versions': []}
    try:
        result = json.loads(path.read_text(encoding='utf-8'))
        if result['quote_id'] != quote_id or type(result['revision']) is not int or result['revision'] < 1 or len(result['versions']) != result['revision']:
            raise ValueError()
        for i, version in enumerate(result['versions']):
            if version['revision'] != i + 1 or normalize(version['values']) != (version['values'], version['calculation']): raise ValueError()
        return result
    except (ValueError, KeyError, TypeError, OSError) as exc: raise ValueError('报价版本记录异常，原文件已保留') from exc

def current(root, quote_id, revision):
    result = read(root, quote_id)
    if type(revision) is not int or not result['versions'] or result['revision'] != revision:
        raise QuoteConflict('关联报价已有新版，请带入最新报价；当前输入已保留')
    return result['versions'][-1]

def save(root, payload):
    if not isinstance(payload, dict): raise ValueError('报价格式不正确')
    quote_id = payload.get('quote_id'); path = _path(root, quote_id)
    expected = payload.get('revision')
    if type(expected) is not int or expected < 0: raise ValueError('缺少报价版本')
    values, calculation = normalize(payload.get('values', {}))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        prior = read(root, quote_id)
        if prior['versions'] and prior['versions'][-1]['values'] == values and expected in (prior['revision'], prior['revision'] - 1):
            return {'ok': True, **prior['versions'][-1], 'quote_id': quote_id}
        if prior['revision'] != expected: raise QuoteConflict('报价已在另一页面更新，输入已保留，请先核对最新版本')
        version = {'revision': prior['revision'] + 1, 'values': values, 'calculation': calculation,
                   'created_at': datetime.now().astimezone().isoformat(timespec='seconds')}
        result = {'quote_id': quote_id, 'revision': version['revision'], 'versions': prior['versions'] + [version]}
        fd, tmp = tempfile.mkstemp(prefix='.' + quote_id, dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                json.dump(result, out, ensure_ascii=False, indent=2); out.flush(); os.fsync(out.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
    return {'ok': True, **version, 'quote_id': quote_id}


def customer_matches(quote_customer, project_customer):
    def normalize_name(value):
        return re.sub(r'[\s\[\]]', '', value.replace('entities/', '')).lower()
    left, right = normalize_name(quote_customer), normalize_name(project_customer)
    return not left or left == right or (min(len(left), len(right)) >= 2 and (left in right or right in left))
