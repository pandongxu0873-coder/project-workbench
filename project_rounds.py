import project_archive
"""Independent, revisioned local working rounds. Never writes source or CRM state."""
import fcntl
import json
import project_activity
import os
import tempfile
from datetime import datetime, date
from project_workspace import build_projects

SCENARIOS = ('first', 'return', 'relationship', 'collaboration', 'procurement', 'change', 'close')
RELATIONSHIPS = ('unknown', 'budget', 'blocked', 'concern', 'no_need', 'no_contact')
STATUSES = ('准备中', '已发出等待反馈', '已收到反馈', '本轮完成', '暂停跟进')
FIELDS = ('scenario', 'relationship', 'status', 'contact', 'facts', 'judgement', 'action', 'owner', 'due', 'feedback', 'next_step', 'recontact_basis', 'topic', 'analysis_id', 'origin_action_id', 'quick_outcome', 'quick_action', 'quick_request_id', 'k100_type', 'k100_occurred_at')

class RevisionConflict(ValueError):
    pass

def project_exists(project_id, knowledge_root, state_root):
    if not isinstance(project_id, str) or not any(p['id'] == project_id for p in build_projects(knowledge_root, state_root)):
        raise ValueError('项目不存在，请重新选择')

def _read(path, project_id):
    if not path.exists():
        return {'project_id': project_id, 'revision': 0, 'record': None, 'history': []}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(value, dict) or value.get('project_id') != project_id
                or type(value.get('revision')) is not int or value['revision'] < 1
                or not isinstance(value.get('history'), list) or len(value['history']) != value['revision']):
            raise ValueError('invalid record container')
        for i, history in enumerate(value['history']):
            if (not isinstance(history, dict) or type(history.get('revision')) is not int
                    or history['revision'] != i + 1):
                raise ValueError('invalid history revision')
            record = history.get('record')
            if not isinstance(record, dict) or any(not isinstance(record.get(f), str) or len(record[f]) > 6000 for f in FIELDS if f not in ('topic', 'analysis_id', 'origin_action_id', 'quick_outcome', 'quick_action', 'quick_request_id', 'k100_type', 'k100_occurred_at')):
                raise ValueError('invalid stored field')
            if any(not isinstance(record.get(f,''),str) or len(record.get(f,''))>6000 for f in ('quick_outcome','quick_action','quick_request_id','k100_type','k100_occurred_at')):
                raise ValueError('invalid execution receipt')
            if not isinstance(record.get('origin_action_id', ''), str) or len(record.get('origin_action_id', '')) > 6000:
                raise ValueError('invalid action origin')
            if not isinstance(record.get('topic', ''), str) or len(record.get('topic', '')) > 6000:
                raise ValueError('invalid topic')
            if not isinstance(record.get('analysis_id', ''), str) or len(record.get('analysis_id', '')) > 6000:
                raise ValueError('invalid analysis identity')
            if record['scenario'] not in SCENARIOS or record['relationship'] not in RELATIONSHIPS or record['status'] not in STATUSES:
                raise ValueError('invalid stored selection')
            if record['due'] and date.fromisoformat(record['due']).isoformat() != record['due']:
                raise ValueError('invalid stored date')
            if not any(record[f] for f in ('facts', 'judgement', 'action', 'feedback')):
                raise ValueError('empty stored round')
            if record['status'] in ('已收到反馈', '本轮完成') and not record['feedback']:
                raise ValueError('missing stored feedback')
            if not isinstance(record.get('saved_at'), str):
                raise ValueError('missing saved date')
            datetime.fromisoformat(record['saved_at'])
        if value.get('record') != value['history'][-1]['record']:
            raise ValueError('latest/history mismatch')
        return value
    except (ValueError, KeyError, AssertionError, TypeError, IndexError) as exc:
        raise ValueError('本地工作记录异常，已保留原文件；请先恢复记录再保存') from exc

def read_round(project_id, knowledge_root, state_root):
    project_exists(project_id, knowledge_root, state_root)
    return {'ok': True, **_read(state_root / 'project_rounds' / f'{project_id}.json', project_id)}

def followups(knowledge_root, state_root, today=None, projects=None):
    """Project the latest round once, without copying it to external/task stores."""
    today = today or date.today()
    items, errors, claimed = [], [], {}
    projects = build_projects(knowledge_root, state_root) if projects is None else projects
    for project in projects:
        try:
            stored = _read(state_root / 'project_rounds' / f"{project['id']}.json", project['id'])
        except (ValueError, OSError):
            errors.append({'project_id': project['id'], 'title': project['title'], 'message': '本轮记录读取失败，请核实'})
            continue
        for h in stored['history']:
            origin = h['record'].get('origin_action_id')
            if origin: claimed[origin] = project['id']
        record = stored['record']
        if not record or record['status'] in ('本轮完成', '暂停跟进') or record['relationship'] == 'no_contact':
            continue
        due = record['due']
        bucket = 'unscheduled' if not due else 'overdue' if due < today.isoformat() else 'today' if due == today.isoformat() else 'future'
        items.append({'id': f"round:{project['id']}", 'project_id': project['id'], 'title': project['title'],
                      'customer': project['customer'], 'revision': stored['revision'], 'status': record['status'],
                      'action': record['action'], 'next_step': record['next_step'], 'due': due,
                      'schedule_bucket': bucket, 'feedback': record['feedback'], 'saved_at': record['saved_at']})
    items.sort(key=lambda item: (item['due'] or '9999', item['title']))
    return {'ok': True, 'items': project_archive.decorate_items(items, state_root, projects), 'errors': errors, 'claimed_actions': claimed}

@project_archive.sales_write
def save_round(payload, knowledge_root, state_root):
    if not isinstance(payload, dict):
        raise ValueError('工作记录必须为对象')
    project_id = payload.get('project_id')
    project_exists(project_id, knowledge_root, state_root)
    if type(payload.get('revision')) is not int or payload['revision'] < 0:
        raise ValueError('缺少有效版本，请先读取本项目记录')
    record = {}
    for field in FIELDS:
        value = payload.get(field, '')
        if not isinstance(value, str) or len(value) > 6000:
            raise ValueError('记录字段必须是文字且不超过 6000 字')
        record[field] = value.strip()
    if record['scenario'] not in SCENARIOS or record['relationship'] not in RELATIONSHIPS or record['status'] not in STATUSES:
        raise ValueError('请选择有效场景、关系状态和执行状态')
    if record['due']:
        try:
            if date.fromisoformat(record['due']).isoformat() != record['due']:
                raise ValueError('noncanonical date')
        except (ValueError, AssertionError):
            raise ValueError('跟进日期需为有效的 YYYY-MM-DD')
    if not any(record[f] for f in ('facts', 'judgement', 'action', 'feedback')):
        raise ValueError('至少记下一项事实、判断、动作或反馈即可保存')
    if record['status'] in ('已收到反馈', '本轮完成') and not record['feedback']:
        raise ValueError('请记录实际反馈或本轮验收结果')
    folder = state_root / 'project_rounds'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{project_id}.json'
    with (folder / f'{project_id}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        prior = _read(path, project_id)
        if payload['revision'] != prior['revision']:
            raise RevisionConflict('记录已被另一页面更新；你的输入已保留，请查看最新记录后再合并')
        origin = record['origin_action_id']
        prior_origins = {h['record'].get('origin_action_id') for h in prior['history']}
        if origin and origin not in prior_origins:
            project = next(p for p in build_projects(knowledge_root, state_root) if p['id'] == project_id)
            if origin not in {i['id'] for i in project_activity.active_actions(project, state_root)}:
                raise ValueError('原行动与当前项目不一致或已结束，请重新读取')
        if prior['record'] and prior['record']['relationship'] == 'no_contact' and record['relationship'] != 'no_contact' and not record['recontact_basis']:
            raise ValueError('客户曾明确暂勿联系；恢复联系需记录新的事实依据')
        if record['relationship'] == 'no_contact':
            record['recontact_basis'] = ''
        record['saved_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
        revision = prior['revision'] + 1
        value = {'project_id': project_id, 'revision': revision, 'record': record,
                 'history': [*prior['history'], {'revision': revision, 'record': record}]}
        # History and latest are committed together: failure cannot split the two.
        fd, temporary = tempfile.mkstemp(prefix=f'.{project_id}.', dir=folder)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                json.dump(value, out, ensure_ascii=False, indent=2)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {'ok': True, **value}
