"""Read-through business context. Original owners remain the only writers."""
import hashlib
import json
import quote_versions
from pathlib import Path


def read_store(path, empty):
    if not path.exists(): return empty
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, type(empty)): raise ValueError()
        return value
    except (ValueError, OSError, UnicodeError) as exc:
        raise ValueError('工作记录读取失败，原记录已保留，不能按空记录继续判断') from exc


def project_owner(item, projects):
    """Identity or exact explicit evidence path only; never customer-name guessing."""
    if item.get('project_id'):
        return next((p for p in projects if p['id'] == item['project_id']), None)
    refs = {str(item.get(k) or '') for k in ('project_source', 'source_path', 'transcript_path')}
    evidence = str(item.get('evidence') or '')
    prefix = '来自录音/TXT整理：'
    if evidence.startswith(prefix): refs.add(evidence[len(prefix):].strip())
    matches = [p for p in projects if p['source_path'] in refs or any(s['path'] in refs and s.get('relation') != 'background_reference' for s in p.get('sources', []))]
    return matches[0] if len(matches) == 1 else None


def active_actions(project, state_root):
    state = read_store(state_root / 'workflow_state.json', {})
    import project_rounds
    stored = project_rounds._read(state_root / 'project_rounds' / f"{project['id']}.json", project['id'])
    claimed = {h['record'].get('origin_action_id') for h in stored['history']}
    rows = []
    for item in read_store(state_root / 'risk_todos.json', []):
        if not isinstance(item, dict) or not item.get('id') or item.get('id') in claimed or item.get('status') in ('已处理', '已闭环', '已完成', '已取消'): continue
        if item.get('source_scope') == 'transcript_intake': continue
        # Project identity is explicit; shared evidence/customer aliases are insufficient here.
        if item.get('project_id') != project['id'] and not (not item.get('project_id') and item.get('project_source') == project['source_path']): continue
        status = state.get('schedule_status', {}).get(item['id'], {})
        if isinstance(status, dict) and status.get('hidden'): continue
        rows.append(item)
    return rows


def receipt_action_key(receipt):
    return str(receipt.get('action_id') or (receipt.get('todo') or {}).get('id') or
               ((receipt.get('closed_todo') or {}).get('todo') or {}).get('id') or '')


def business_sources(project, state_root):
    """Previously saved feedback and commercial preparation join AI inputs once.

    A draft remains a draft. Recording time never becomes communication time.
    """
    state = read_store(state_root / 'workflow_state.json', {})
    rows = []
    seen = set()
    receipts = list(state.get('receipts', []))
    for bucket in ('action_status', 'schedule_status', 'risk_status'):
        receipts += [v.get('receipt') for v in state.get(bucket, {}).values() if isinstance(v, dict) and v.get('receipt')]
    for receipt in receipts:
        if not isinstance(receipt, dict) or not receipt.get('id') or receipt['id'] in seen: continue
        seen.add(receipt['id'])
        if receipt.get('project_id') != project['id'] and not (
                not receipt.get('project_id') and receipt.get('project_source') == project['source_path']): continue
        rows.append({'path': 'local://receipt/' + hashlib.sha256(receipt['id'].encode()).hexdigest()[:20],
                     'date': receipt.get('occurred_at', ''), 'relation':'execution_receipt','feedback_content':str(receipt.get('resolution') or ''), 'recorded_at': receipt.get('submitted_at', ''),
                     'content': '实际执行回执（不是新建任务）：\n' + json.dumps({k: receipt.get(k) for k in ('action_id', 'status', 'resolution', 'next_step', 'todo')}, ensure_ascii=False),
                     'truncated': False, 'action_id': receipt_action_key(receipt)})
    for item in active_actions(project, state_root):
        rows.append({'path': 'local://action/' + hashlib.sha256(item['id'].encode()).hexdigest()[:20], 'date': '',
                     'recorded_at': item.get('created_at', ''), 'action_id': item['id'], 'truncated': False,
                     'content': '已存在的同项目行动。若下一步承接此事，引用本条；采纳时沿用此行动身份和原约定日期，不重复建待办。\n' + json.dumps({k: item.get(k) for k in ('id', 'title', 'status', 'action', 'next_step', 'deadline', 'resolution', 'evidence', 'internal_only')}, ensure_ascii=False)})
    draft_path = state_root / 'commercial_drafts' / (project['id'] + '.json')
    if draft_path.exists():
        draft = read_store(draft_path, {})
        if draft.get('project_id') != project['id'] or draft.get('project_source') != project['source_path']:
            raise ValueError('商务草稿项目身份不一致，不能用于项目判断')
        visible = {k: draft.get(k) for k in ('revision', 'requirement', 'effort', 'rate', 'version', 'quote_id', 'quote_revision', 'customer_confirmed', 'confirmation_source', 'confirmation_excerpt')}
        if draft.get('quote_id'):
            quote = quote_versions.read(state_root, draft['quote_id'])
            visible.update(latest_quote_revision=quote['revision'], quote_outdated=quote['revision'] != draft.get('quote_revision'))
        rows.append({'path': 'local://commercial-draft', 'date': '', 'recorded_at': draft.get('updated_at', ''),
                     'content': '本机商务准备草稿，未发送、未审批、不是合同。确认勾选仅是用户核对记录，仍需对照本版本原客户回复；草稿不能证明客户接受或审批负责人批准。\n' + json.dumps(visible, ensure_ascii=False), 'truncated': False})
    return sorted(rows, key=lambda row: row['path'])


def activity_fingerprint(sources):
    stable=[{k:v for k,v in s.items() if not (s.get('relation')=='crm_snapshot' and k=='recorded_at')} for s in sources]
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
