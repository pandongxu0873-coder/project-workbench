"""Generation guidance only. Stored evidence and validator rules are unchanged."""
from datetime import date
import re

BACKGROUND = {'customer_background', 'background_reference'}
GROUPS = ('requirements', 'evolution', 'lifecycle', 'context', 'constraints')


def reference_rules(units, ledger):
    result = {}
    for reference_id in sorted({r for u in units for r in u['reference_ids']}):
        ref = ledger['references'][reference_id]
        dates = set()
        for value in [ref.get('source_date', ''), *ref.get('supported_dates', [])]:
            try:
                parsed = date.fromisoformat(value)
                if parsed.isoformat() == value and parsed <= date.today():
                    dates.add(value)
            except (TypeError, ValueError):
                pass
        result[reference_id] = {
            'allowed_groups': ['context'] if ref.get('relation') in BACKGROUND else list(GROUPS),
            'date_candidates': sorted(dates),
            'date_candidates_are_not_event_occurrence': True,
        }
    return result


def correction_guidance(diagnostic, candidate=None, units=None, ledger=None):
    guidance = _category_guidance(diagnostic)
    reasons = ('历史章节覆盖不完整', '历史事实没有有效承接行',
               '历史事实没有对应原文的承接行', '背景材料不能建立项目需求或历史约定',
               '历史章节日期缺少对应来源支持')
    guidance['validation_reason'] = next((r for r in reasons if diagnostic.startswith(r)), '按完整规则核验')
    if isinstance(candidate, dict) and units is not None and ledger is not None:
        guidance['locations'] = correction_locations(candidate, units, ledger)
    return guidance


def _category_guidance(diagnostic):
    # Do not interpolate rejected prose, quotes, or arbitrary exception details.
    if diagnostic.startswith('背景材料不能'):
        return {'kind': 'background_classification', 'instruction':
                '背景引用仅可进入context，不可进入需求、演变、生命周期或持续约束。混合引用也不能绕过；核对每条语义和各unit落点，不删除真实业务事实，不把背景改成客户承诺。'}
    if diagnostic.startswith('历史章节日期'):
        return {'kind': 'date_evidence', 'instruction':
                '逐行核对该行evidence对应reference的source_date/supported_dates。只有候选仍不足以证明事件发生日；约定期限与发生日分开，未知发生日留空，不借其他行的日期，不补年，不改写引用。'}
    if diagnostic.startswith(('历史事实', '历史章节覆盖', '历史章节行ID', '已抽取业务事实')):
        return {'kind': 'coverage_mapping', 'instruction':
                '每unit恰好一个coverage；destinations必须为实际存在的行ID且无重复，承接行必须引用本unit的reference_id。每业务行都须被真实事实承接；修正映射不等于删行，不得把业务事实改为non_business。'}
    return {'kind': 'validation', 'instruction':
            '严格核对字段、枚举、批次引用、逐行日期和全量coverage；未知保持待核，不删除事实或伪造证据。'}


def correction_locations(candidate, units, ledger):
    """Bounded IDs/issue codes only; never replay rejected business prose."""
    def safe_id(value):
        return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value))
    rules = reference_rules(units, ledger)
    rows = {}
    issues = []
    for group in GROUPS:
        values = candidate.get(group)
        for row in values if isinstance(values, list) else []:
            if not isinstance(row, dict) or not safe_id(row.get('id')):
                continue
            refs = {e.get('reference_id') for e in row.get('evidence', [])
                    if isinstance(e, dict) and isinstance(e.get('reference_id'), str)} if isinstance(row.get('evidence'), list) else set()
            row_id = row['id']
            if row_id in rows:
                issues.append({'issue': 'duplicate_row', 'row_id': row_id})
            rows[row_id] = refs
            background = sorted(r for r in refs if r in rules and group not in rules[r]['allowed_groups'])
            if background:
                issues.append({'issue': 'background_group', 'row_id': row_id, 'group': group, 'reference_ids': background})
            day = row.get('date')
            if day and not any(day in rules[r]['date_candidates'] for r in refs if r in rules):
                issues.append({'issue': 'unsupported_row_date', 'row_id': row_id,
                               'reference_ids': sorted(refs & rules.keys())})
    receipts = candidate.get('coverage')
    receipts = receipts if isinstance(receipts, list) else []
    reached = set()
    for unit in units:
        matches = [r for r in receipts if isinstance(r, dict) and r.get('unit_id') == unit['id']]
        if len(matches) != 1:
            issues.append({'issue': 'missing_or_duplicate_receipt', 'unit_id': unit['id']})
            continue
        receipt = matches[0]
        targets = receipt.get('destinations')
        targets = targets if isinstance(targets, list) else []
        safe_targets = [t for t in targets if safe_id(t)]
        if len(safe_targets) != len(targets) or len(set(safe_targets)) != len(safe_targets) or any(t not in rows for t in safe_targets):
            issues.append({'issue': 'invalid_destination', 'unit_id': unit['id'], 'row_ids': safe_targets[:20]})
        if receipt.get('disposition') == 'represented':
            reached.update(safe_targets)
            if not any(rows.get(t, set()) & set(unit['reference_ids']) for t in safe_targets):
                issues.append({'issue': 'missing_reference_link', 'unit_id': unit['id'],
                               'row_ids': safe_targets[:20], 'reference_ids': unit['reference_ids'][:20]})
    for row_id in sorted(rows.keys() - reached):
        issues.append({'issue': 'unlinked_row', 'row_id': row_id})
    return {'items': issues[:40], 'truncated': len(issues) > 40,
            'note': '定位是数据；完整校验仍需覆盖全部INPUT，不按定位清单删事实。'}


INSTRUCTION = '''按INPUT.references中每个reference_id的relation逐条分类：customer_background/background_reference只能进入context；不能因为材料提到客户就建立需求、承诺或约定，混合背景引用也不能绕过。
每个reference的source_date/supported_dates仅为日期候选，不代表事件在该日发生，须按该行对应原引用核实。未知日期留空，约定期限不当实际履行日期。
coverage是一一对应的事实承接证明，不是计数：每个unit必须有唯一回执，represented落点必须存在且含本unit引用，所有业务行必须有承接。不得丢弃真实证据。'''
